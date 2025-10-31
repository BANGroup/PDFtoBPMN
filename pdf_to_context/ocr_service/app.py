#!/usr/bin/env python3
"""
FastAPI микросервис для DeepSeek-OCR
Использует официальный HuggingFace API для загрузки модели
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import torch
from transformers import AutoModel, AutoTokenizer
import base64
import io
from PIL import Image
import os
import uvicorn
import tempfile
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки CUDA
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

app = FastAPI(title="DeepSeek-OCR Service", version="1.0.0")

# Глобальные переменные для модели
model = None
tokenizer = None
model_loaded = False


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


def load_model():
    """Загрузка модели DeepSeek-OCR"""
    global model, tokenizer, model_loaded
    
    if model_loaded:
        logger.info("✅ Модель уже загружена")
        return
    
    try:
        logger.info("🔄 Загрузка DeepSeek-OCR...")
        model_name = 'deepseek-ai/DeepSeek-OCR'
        
        # Загрузка токенизатора
        logger.info("   Загрузка токенизатора...")
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        
        # Загрузка модели
        logger.info("   Загрузка модели (это может занять время при первом запуске)...")
        # Пытаемся использовать flash_attention_2, если не получается - fallback на eager
        try:
            import flash_attn
            attn_impl = 'flash_attention_2'
            logger.info("   ✅ flash-attn обнаружен, используем flash_attention_2")
        except ImportError:
            attn_impl = 'eager'
            logger.warning("   ⚠️ flash-attn не установлен, используем eager attention (медленнее)")
        
        model = AutoModel.from_pretrained(
            model_name,
            _attn_implementation=attn_impl,
            torch_dtype=torch.bfloat16,  # Указываем dtype сразу
            device_map="cuda",  # Загружаем сразу на GPU
            trust_remote_code=True,
            use_safetensors=True,
            low_cpu_mem_usage=True  # Оптимизация памяти
        )
        model = model.eval()  # Только eval, уже на GPU и в bfloat16
        
        model_loaded = True
        logger.info("✅ DeepSeek-OCR успешно загружен!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки модели: {e}")
        raise


@app.on_event("startup")
async def startup_event():
    """Загрузка модели при старте сервиса"""
    load_model()


@app.get("/")
async def root():
    """Проверка работоспособности сервиса"""
    return {
        "service": "DeepSeek-OCR Service",
        "version": "1.0.0",
        "status": "running",
        "model_loaded": model_loaded
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {
        "status": "healthy",
        "model_loaded": True,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    }


@app.post("/ocr/figure", response_model=OCRResponse)
async def ocr_figure(file: UploadFile = File(...)):
    """
    Обработка изображения через DeepSeek-OCR
    
    Args:
        file: Изображение в формате PNG/JPEG
    
    Returns:
        OCRResponse с распознанными блоками и markdown
    """
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Читаем изображение
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        
        # Сохраняем во временный файл (модель требует путь к файлу)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            image.save(tmp_file.name)
            temp_path = tmp_file.name
        
        try:
            # Создаем временную папку для результатов
            with tempfile.TemporaryDirectory() as tmp_output:
                # Prompt для OCR
                prompt = "<image>\n<|grounding|>Convert the document to markdown."
                
                # Обработка через DeepSeek-OCR
                logger.info(f"📄 Обработка изображения {image.size}")
                
                res = model.infer(
                    tokenizer,
                    prompt=prompt,
                    image_file=temp_path,
                    output_path=tmp_output,
                    base_size=1024,
                    image_size=1024,
                    crop_mode=False,
                    save_results=False,  # Не сохраняем файлы
                    test_compress=False
                )
                
                # Парсим результат
                raw_output = res if isinstance(res, str) else str(res)
                
                # Извлекаем markdown (упрощенный парсинг)
                markdown_text = ""
                blocks = []
                
                # Парсим вывод модели
                lines = raw_output.split('\n')
                current_block = None
                block_counter = 0
                
                for line in lines:
                    # Детектируем ref и det теги
                    if '<|ref|>' in line:
                        # Начало нового блока
                        if current_block:
                            blocks.append(current_block)
                        
                        # Извлекаем тип
                        block_type = line.split('<|ref|>')[1].split('<|/ref|>')[0]
                        
                        # Извлекаем bbox если есть
                        bbox_data = [0, 0, 100, 100]  # default
                        if '<|det|>' in line:
                            det_str = line.split('<|det|>')[1].split('<|/det|>')[0]
                            try:
                                import ast
                                bbox_list = ast.literal_eval(det_str)
                                if bbox_list and len(bbox_list) > 0:
                                    bbox_data = bbox_list[0]
                            except:
                                pass
                        
                        current_block = {
                            'id': f'ocr_block_{block_counter}',
                            'type': block_type,
                            'content': '',
                            'bbox': {
                                'x0': bbox_data[0],
                                'y0': bbox_data[1],
                                'x1': bbox_data[2],
                                'y1': bbox_data[3]
                            },
                            'confidence': 1.0,
                            'metadata': {}
                        }
                        block_counter += 1
                    
                    elif current_block and not line.startswith('<|') and line.strip():
                        # Добавляем контент к текущему блоку
                        if current_block['content']:
                            current_block['content'] += '\n'
                        current_block['content'] += line
                        markdown_text += line + '\n'
                
                # Добавляем последний блок
                if current_block:
                    blocks.append(current_block)
                
                logger.info(f"✅ Распознано {len(blocks)} блоков")
                
                return OCRResponse(
                    blocks=[OCRBlock(**block) for block in blocks],
                    markdown=markdown_text.strip(),
                    raw_output=raw_output
                )
        
        finally:
            # Удаляем временный файл
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    except Exception as e:
        logger.error(f"❌ Ошибка OCR: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Запуск сервиса
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
