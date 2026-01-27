#!/usr/bin/env python3
"""
DeepSeek-OCR Service - FastAPI микросервис для OCR

Использует DeepSeek-OCR модель с методом model.infer().
Поддерживает flash_attention_2 (если установлен).

Универсальный Docker для разных GPU:
- RTX 4080/4090 (sm_89, Ada Lovelace)
- RTX 5080/5090 (sm_120, Blackwell)
- H100/A100 (sm_90/sm_80, Hopper/Ampere)
"""

import os
import io
import base64
import time
import tempfile
import logging
import sys
from io import StringIO
from typing import Optional, List
from contextlib import asynccontextmanager

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-OCR")
USE_FLASH_ATTENTION = os.getenv("USE_FLASH_ATTENTION", "auto")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "4096"))

# Глобальные переменные
model = None
tokenizer = None
device_info = {}
flash_attn_available = False


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class OCRBlock(BaseModel):
    id: str
    type: str
    content: str
    bbox: BBox
    confidence: float = 1.0
    metadata: dict = {}


class OCRResponse(BaseModel):
    blocks: List[OCRBlock]
    markdown: str
    raw_output: str
    inference_time: float
    flash_attention: bool


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    cuda_available: bool
    cuda_device: str
    flash_attention: bool
    vram_total_gb: float
    vram_free_gb: float


# Промпты для OCR
PROMPTS = {
    "default": "<image>\nParse this document.",
    "ocr_simple": "<image>\nOCR with grounding. Provide text with bounding boxes.",
    "parse_figure": "<image>\nParse the figure.",
    "bpmn": "<image>\nParse this BPMN diagram. Extract all elements, connections, and text.",
    "table": "<image>\nExtract table from image as markdown.",
    "russian": "<image>\nОбработай документ. Извлеки весь текст с позициями.",
}


def check_flash_attention() -> bool:
    """Проверка доступности flash_attn"""
    global flash_attn_available
    
    if USE_FLASH_ATTENTION == "false":
        logger.info("Flash Attention отключен через конфигурацию")
        return False
    
    try:
        import flash_attn
        logger.info(f"Flash Attention {flash_attn.__version__} доступен")
        flash_attn_available = True
        return True
    except ImportError as e:
        logger.warning(f"Flash Attention не установлен: {e}")
        logger.info("Работаем без Flash Attention (медленнее, но универсально)")
        return False


def load_model():
    """Загрузка модели DeepSeek-OCR"""
    global model, tokenizer, device_info, flash_attn_available
    
    logger.info(f"Загрузка модели: {MODEL_NAME}")
    
    # Проверка CUDA
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA недоступна!")
    
    device_info = {
        "cuda_available": True,
        "cuda_device": torch.cuda.get_device_name(0),
        "vram_total": torch.cuda.mem_get_info()[1] / 1024**3,
        "vram_free": torch.cuda.mem_get_info()[0] / 1024**3,
    }
    logger.info(f"GPU: {device_info['cuda_device']}, VRAM: {device_info['vram_free']:.1f}GB free")
    
    # Проверка flash_attn
    flash_attn_available = check_flash_attention()
    
    # Загрузка модели
    from transformers import AutoModel, AutoTokenizer
    
    # Выбор attention implementation
    if flash_attn_available and USE_FLASH_ATTENTION != "false":
        attn_impl = "flash_attention_2"
        logger.info("Используем Flash Attention 2")
    else:
        attn_impl = "eager"
        logger.info("Используем eager attention")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        MODEL_NAME,
        _attn_implementation=attn_impl,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
        trust_remote_code=True,
        use_safetensors=True,
        low_cpu_mem_usage=True
    )
    model.eval()
    
    logger.info(f"Модель загружена! VRAM: {torch.cuda.mem_get_info()[0] / 1024**3:.1f}GB free")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    load_model()
    yield
    global model, tokenizer
    del model
    del tokenizer
    torch.cuda.empty_cache()


app = FastAPI(
    title="DeepSeek-OCR Service",
    description="Universal OCR service with DeepSeek-OCR model",
    version="1.1.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Проверка состояния сервиса"""
    vram_free = 0
    vram_total = 0
    if torch.cuda.is_available():
        vram_free = torch.cuda.mem_get_info()[0] / 1024**3
        vram_total = torch.cuda.mem_get_info()[1] / 1024**3
    
    return HealthResponse(
        status="healthy" if model is not None else "loading",
        model_loaded=model is not None,
        cuda_available=torch.cuda.is_available(),
        cuda_device=device_info.get("cuda_device", "N/A"),
        flash_attention=flash_attn_available,
        vram_total_gb=round(vram_total, 2),
        vram_free_gb=round(vram_free, 2)
    )


@app.get("/prompts")
async def list_prompts():
    """Список доступных промптов"""
    return {"prompts": list(PROMPTS.keys())}


@app.post("/ocr/figure", response_model=OCRResponse)
async def ocr_figure(
    file: UploadFile = File(...),
    prompt_type: str = Form("ocr_simple"),
    custom_prompt: Optional[str] = Form(None),
    base_size: int = Form(1024),
    image_size: int = Form(1024),
    crop_mode: bool = Form(False)
):
    """
    OCR изображения через DeepSeek-OCR
    
    Args:
        file: Изображение (PNG/JPEG)
        prompt_type: Тип промпта (default, ocr_simple, parse_figure, bpmn, table, russian)
        custom_prompt: Кастомный промпт (опционально)
        base_size: Базовый размер обработки
        image_size: Размер изображения
        crop_mode: Режим обрезки
    
    Returns:
        OCRResponse с распознанным текстом и блоками
    """
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    start_time = time.time()
    
    try:
        # Читаем изображение
        image_data = await file.read()
        
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(image_data)
            temp_path = tmp_file.name
        
        try:
            # Выбор промпта
            prompt = custom_prompt if custom_prompt else PROMPTS.get(prompt_type, PROMPTS["ocr_simple"])
            logger.info(f"Prompt: {prompt[:50]}...")
            
            # Временная директория для результатов
            with tempfile.TemporaryDirectory() as tmp_output:
                # Захват stdout (model.infer печатает результат)
                old_stdout = sys.stdout
                sys.stdout = captured_output = StringIO()
                
                try:
                    res = model.infer(
                        tokenizer,
                        prompt=prompt,
                        image_file=temp_path,
                        output_path=tmp_output,
                        base_size=base_size,
                        image_size=image_size,
                        crop_mode=crop_mode,
                        save_results=False,
                        test_compress=False
                    )
                finally:
                    sys.stdout = old_stdout
                    captured_stdout = captured_output.getvalue()
                
                # Определение результата
                if captured_stdout and len(captured_stdout) > 10:
                    raw_output = captured_stdout
                elif res is not None and str(res) != "None":
                    raw_output = res if isinstance(res, str) else str(res)
                else:
                    raw_output = captured_stdout or ""
                
                inference_time = time.time() - start_time
                
                # Парсинг результата
                blocks = []
                markdown_lines = []
                block_counter = 0
                
                lines = raw_output.split('\n')
                for line in lines:
                    # Парсинг bbox формата: <|ref|>text<|/ref|><|det|>(x0,y0),(x1,y1)<|/det|>
                    if '<|ref|>' in line and '<|det|>' in line:
                        try:
                            # Извлечение текста
                            ref_start = line.find('<|ref|>') + 7
                            ref_end = line.find('<|/ref|>')
                            text = line[ref_start:ref_end].strip()
                            
                            # Извлечение координат
                            det_start = line.find('<|det|>') + 7
                            det_end = line.find('<|/det|>')
                            coords = line[det_start:det_end]
                            
                            # Парсинг координат (x0,y0),(x1,y1)
                            coords = coords.strip('()').replace('),(', ',').split(',')
                            if len(coords) >= 4:
                                bbox = BBox(
                                    x0=float(coords[0]),
                                    y0=float(coords[1]),
                                    x1=float(coords[2]),
                                    y1=float(coords[3])
                                )
                                
                                blocks.append(OCRBlock(
                                    id=f"ocr_block_{block_counter}",
                                    type="text",
                                    content=text,
                                    bbox=bbox
                                ))
                                markdown_lines.append(text)
                                block_counter += 1
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга блока: {e}")
                    elif line.strip() and not line.startswith('<|'):
                        markdown_lines.append(line.strip())
                
                return OCRResponse(
                    blocks=blocks,
                    markdown='\n'.join(markdown_lines),
                    raw_output=raw_output[:2000],  # Ограничиваем размер
                    inference_time=round(inference_time, 2),
                    flash_attention=flash_attn_available
                )
        
        finally:
            # Удаление временного файла
            os.unlink(temp_path)
    
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint для совместимости с base64 API
@app.post("/ocr")
async def ocr_base64(request: dict):
    """
    OCR через base64 (legacy API)
    
    Для совместимости с клиентами, использующими base64.
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        image_b64 = request.get("image", "")
        prompt_type = request.get("prompt_type", "ocr_simple")
        
        # Декодирование base64
        image_data = base64.b64decode(image_b64)
        
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(image_data)
            temp_path = tmp_file.name
        
        start_time = time.time()
        
        try:
            prompt = PROMPTS.get(prompt_type, PROMPTS["ocr_simple"])
            
            with tempfile.TemporaryDirectory() as tmp_output:
                old_stdout = sys.stdout
                sys.stdout = captured_output = StringIO()
                
                try:
                    res = model.infer(
                        tokenizer,
                        prompt=prompt,
                        image_file=temp_path,
                        output_path=tmp_output,
                        save_results=False
                    )
                finally:
                    sys.stdout = old_stdout
                    raw_output = captured_output.getvalue()
                
                inference_time = time.time() - start_time
                
                return {
                    "text": raw_output.strip(),
                    "model": MODEL_NAME,
                    "inference_time": round(inference_time, 2),
                    "flash_attention": flash_attn_available
                }
        finally:
            os.unlink(temp_path)
    
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
