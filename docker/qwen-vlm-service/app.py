#!/usr/bin/env python3
"""
Qwen VLM OCR Service - FastAPI микросервис для VLM OCR

Развёртывается в Docker на машине с достаточным VRAM (24GB+ для 7B).
Предоставляет REST API для OCR изображений.

Endpoints:
    POST /ocr - распознать текст на изображении
    GET /health - проверка состояния сервиса
    GET /info - информация о модели
"""

import os
import io
import base64
import time
from typing import Optional
from contextlib import asynccontextmanager

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Конфигурация через environment variables
MODEL_NAME = os.getenv("QWEN_MODEL", "Qwen/Qwen2-VL-7B-Instruct")
USE_FLASH_ATTENTION = os.getenv("USE_FLASH_ATTENTION", "false").lower() == "true"
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "2048"))
MAX_PIXELS = int(os.getenv("MAX_PIXELS", str(1280 * 28 * 28)))
MIN_PIXELS = int(os.getenv("MIN_PIXELS", str(256 * 28 * 28)))

# Глобальные переменные для модели
model = None
processor = None
device_info = {}


class OCRRequest(BaseModel):
    """Запрос на OCR"""
    image: str  # Base64 encoded image
    prompt: Optional[str] = None
    language: str = "russian"
    max_tokens: Optional[int] = None


class OCRResponse(BaseModel):
    """Ответ OCR"""
    text: str
    model: str
    inference_time: float
    vram_used_gb: float


class HealthResponse(BaseModel):
    """Статус сервиса"""
    status: str
    model: str
    vram_total_gb: float
    vram_free_gb: float
    cuda_available: bool


class InfoResponse(BaseModel):
    """Информация о сервисе"""
    model: str
    max_tokens: int
    flash_attention: bool
    cuda_version: str
    torch_version: str


# Промпты для разных языков
PROMPTS = {
    "russian": "Прочитай и извлеки весь текст с этого документа. Сохрани структуру (заголовки, списки, таблицы). Формат: Markdown.",
    "english": "Read and extract all text from this document. Preserve structure (headers, lists, tables). Format: Markdown.",
    "auto": "Extract all text from this image. Preserve document structure. Output format: Markdown."
}


def load_model():
    """Загрузка модели при старте"""
    global model, processor, device_info
    
    print(f"🚀 Loading model: {MODEL_NAME}")
    print(f"   Flash Attention: {USE_FLASH_ATTENTION}")
    print(f"   Max tokens: {MAX_NEW_TOKENS}")
    
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    
    # Определение параметров загрузки
    load_kwargs = {
        "torch_dtype": torch.bfloat16,
        "device_map": "auto",
        "low_cpu_mem_usage": True,
    }
    
    if USE_FLASH_ATTENTION:
        load_kwargs["attn_implementation"] = "flash_attention_2"
    
    # Загрузка модели
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        **load_kwargs
    )
    
    # Загрузка процессора
    processor = AutoProcessor.from_pretrained(
        MODEL_NAME,
        min_pixels=MIN_PIXELS,
        max_pixels=MAX_PIXELS
    )
    
    # Информация об устройстве
    if torch.cuda.is_available():
        device_info = {
            "cuda_available": True,
            "vram_total": torch.cuda.mem_get_info()[1] / 1024**3,
            "vram_free": torch.cuda.mem_get_info()[0] / 1024**3,
            "cuda_version": torch.version.cuda,
        }
    else:
        device_info = {
            "cuda_available": False,
            "vram_total": 0,
            "vram_free": 0,
            "cuda_version": "N/A",
        }
    
    print(f"✅ Model loaded! VRAM: {device_info.get('vram_free', 0):.1f}GB free")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    load_model()
    yield
    # Cleanup
    global model, processor
    del model
    del processor
    torch.cuda.empty_cache()


app = FastAPI(
    title="Qwen VLM OCR Service",
    description="VLM-based OCR service using Qwen2-VL models",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Проверка состояния сервиса"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    vram_free = 0
    vram_total = 0
    if torch.cuda.is_available():
        vram_free = torch.cuda.mem_get_info()[0] / 1024**3
        vram_total = torch.cuda.mem_get_info()[1] / 1024**3
    
    return HealthResponse(
        status="healthy",
        model=MODEL_NAME,
        vram_total_gb=round(vram_total, 2),
        vram_free_gb=round(vram_free, 2),
        cuda_available=torch.cuda.is_available()
    )


@app.get("/info", response_model=InfoResponse)
async def info():
    """Информация о сервисе"""
    return InfoResponse(
        model=MODEL_NAME,
        max_tokens=MAX_NEW_TOKENS,
        flash_attention=USE_FLASH_ATTENTION,
        cuda_version=device_info.get("cuda_version", "N/A"),
        torch_version=torch.__version__
    )


@app.post("/ocr", response_model=OCRResponse)
async def ocr(request: OCRRequest):
    """
    OCR изображения
    
    Args:
        request: OCRRequest с base64-encoded изображением
        
    Returns:
        OCRResponse с распознанным текстом
    """
    if model is None or processor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Декодирование изображения
        image_data = base64.b64decode(request.image)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        
        # Выбор промпта
        prompt = request.prompt or PROMPTS.get(request.language, PROMPTS["auto"])
        
        # Подготовка сообщения
        from qwen_vl_utils import process_vision_info
        
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt}
        ]}]
        
        # Токенизация
        text = processor.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        image_inputs, _ = process_vision_info(messages)
        inputs = processor(
            text=[text], 
            images=image_inputs, 
            padding=True, 
            return_tensors="pt"
        ).to("cuda" if torch.cuda.is_available() else "cpu")
        
        # Генерация
        start_time = time.time()
        
        max_tokens = request.max_tokens or MAX_NEW_TOKENS
        outputs = model.generate(
            **inputs, 
            max_new_tokens=max_tokens,
            do_sample=False
        )
        
        inference_time = time.time() - start_time
        
        # Декодирование
        result = processor.batch_decode(
            [outputs[0][len(inputs.input_ids[0]):]],
            skip_special_tokens=True
        )[0]
        
        # VRAM использование
        vram_used = 0
        if torch.cuda.is_available():
            vram_used = (torch.cuda.mem_get_info()[1] - torch.cuda.mem_get_info()[0]) / 1024**3
        
        return OCRResponse(
            text=result,
            model=MODEL_NAME,
            inference_time=round(inference_time, 2),
            vram_used_gb=round(vram_used, 2)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
