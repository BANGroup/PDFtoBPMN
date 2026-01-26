#!/usr/bin/env python3
"""
DeepSeek-OCR Service - FastAPI микросервис для OCR

Универсальный Docker-образ для разных GPU:
- RTX 4080/4090 (sm_89, Ada Lovelace)
- RTX 5080/5090 (sm_120, Blackwell)
- H100/A100 (sm_90/sm_80, Hopper/Ampere)

flash_attn опционален — работает и без него (медленнее).
"""

import os
import io
import base64
import time
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-OCR")
USE_FLASH_ATTENTION = os.getenv("USE_FLASH_ATTENTION", "auto")  # auto, true, false
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "4096"))

# Глобальные переменные
model = None
tokenizer = None
device_info = {}
flash_attn_available = False


class OCRRequest(BaseModel):
    """Запрос на OCR"""
    image: str  # Base64 encoded
    prompt: Optional[str] = None
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = None


class OCRResponse(BaseModel):
    """Ответ OCR"""
    text: str
    model: str
    inference_time: float
    flash_attention: bool


class HealthResponse(BaseModel):
    """Статус сервиса"""
    status: str
    model_loaded: bool
    cuda_available: bool
    cuda_device: str
    flash_attention: bool
    vram_total_gb: float
    vram_free_gb: float


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
    except Exception as e:
        logger.warning(f"Ошибка Flash Attention: {e}")
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
    
    load_kwargs = {
        "trust_remote_code": True,
        "torch_dtype": torch.bfloat16,
        "device_map": "auto",
    }
    
    if flash_attn_available and USE_FLASH_ATTENTION != "false":
        load_kwargs["attn_implementation"] = "flash_attention_2"
        logger.info("Используем Flash Attention 2")
    else:
        logger.info("Используем стандартный attention (sdpa)")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModel.from_pretrained(MODEL_NAME, **load_kwargs)
    model.eval()
    
    logger.info(f"Модель загружена! VRAM: {torch.cuda.mem_get_info()[0] / 1024**3:.1f}GB free")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    load_model()
    yield
    # Cleanup
    global model, tokenizer
    del model
    del tokenizer
    torch.cuda.empty_cache()


app = FastAPI(
    title="DeepSeek-OCR Service",
    description="Universal OCR service with DeepSeek-OCR model",
    version="1.0.0",
    lifespan=lifespan
)


# Системные промпты
SYSTEM_PROMPTS = {
    "default": "You are an expert OCR assistant. Extract all text from the image preserving structure.",
    "russian": "Ты эксперт OCR. Извлеки весь текст с изображения, сохраняя структуру. Формат: Markdown.",
    "bpmn": "Extract all text from this BPMN diagram. List process steps, participants, and connections.",
    "table": "Extract the table from the image. Format as Markdown table.",
    "layout": "Extract text with layout information. Use coordinates for positioning.",
}


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
    """Список доступных системных промптов"""
    return {"prompts": list(SYSTEM_PROMPTS.keys())}


@app.post("/ocr", response_model=OCRResponse)
async def ocr(request: OCRRequest):
    """
    OCR изображения
    
    Args:
        request: OCRRequest с base64-encoded изображением
        
    Returns:
        OCRResponse с распознанным текстом
    """
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Декодирование изображения
        image_data = base64.b64decode(request.image)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        
        # Выбор промпта
        system_prompt = request.system_prompt or SYSTEM_PROMPTS.get("russian")
        user_prompt = request.prompt or "Извлеки текст с изображения."
        
        # Формирование сообщения
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": user_prompt}
            ]}
        ]
        
        # Токенизация
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
            return_dict=True
        ).to(model.device)
        
        # Генерация
        start_time = time.time()
        
        max_tokens = request.max_tokens or MAX_NEW_TOKENS
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id
            )
        
        inference_time = time.time() - start_time
        
        # Декодирование
        result = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
        
        return OCRResponse(
            text=result,
            model=MODEL_NAME,
            inference_time=round(inference_time, 2),
            flash_attention=flash_attn_available
        )
        
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint для совместимости
@app.post("/ocr/figure")
async def ocr_figure(request: OCRRequest):
    """Legacy endpoint - перенаправляет на /ocr"""
    return await ocr(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
