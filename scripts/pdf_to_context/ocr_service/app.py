#!/usr/bin/env python3
"""
FastAPI микросервис для DeepSeek-OCR
Использует официальный HuggingFace API для загрузки модели
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
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
async def ocr_figure(
    file: UploadFile = File(...),
    prompt_type: str = Form("default"),
    custom_prompt: str = Form(None),
    base_size: int = Form(1024),
    image_size: int = Form(1024),
    crop_mode: bool = Form(False)
):
    """
    Обработка изображения через DeepSeek-OCR
    
    Args:
        file: Изображение в формате PNG/JPEG
        prompt_type: Тип промпта ('default', 'bpmn', 'parse_figure', etc.)
        custom_prompt: Кастомный промпт (опционально)
        base_size: Базовый размер для обработки (default: 1024)
        image_size: Размер изображения (default: 1024)
        crop_mode: Режим обрезки (default: False)
    
    Returns:
        OCRResponse с распознанными блоками и markdown
    """
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Читаем изображение
        image_data = await file.read()
        
        # Сохраняем во временный файл (модель требует путь к файлу)
        # DeepSeek-OCR имеет собственный internal parser, не нужна проверка PIL
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(image_data)
            temp_path = tmp_file.name
        
        try:
            # Создаем временную папку для результатов
            with tempfile.TemporaryDirectory() as tmp_output:
                # Получаем промпт
                if custom_prompt:
                    prompt = custom_prompt
                    logger.info(f"   Используется custom_prompt")
                else:
                    # Абсолютный импорт для работы при прямом запуске
                    try:
                        from .prompts import OCRPrompts
                    except ImportError:
                        import sys
                        from pathlib import Path
                        sys.path.insert(0, str(Path(__file__).parent))
                        from prompts import OCRPrompts
                    prompt = OCRPrompts.get_prompt_by_type(prompt_type)
                    logger.info(f"   Используется prompt_type: {prompt_type}")
                
                # Обработка через DeepSeek-OCR
                logger.info(f"📄 Обработка изображения ({len(image_data)} байт)")
                logger.info(f"🔍 Prompt: {prompt[:100]}...")
                
                # КРИТИЧНО: Захватываем stdout, т.к. model.infer() печатает результат туда
                import sys
                from io import StringIO
                
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
                        save_results=False,  # Не сохраняем файлы
                        test_compress=False
                    )
                finally:
                    sys.stdout = old_stdout
                    captured_stdout = captured_output.getvalue()
                
                logger.info(f"🔍 Тип результата: {type(res)}")
                logger.info(f"🔍 Результат (первые 500 символов): {str(res)[:500]}")
                
                # ВАЖНО: model.infer() печатает результат в stdout, а не возвращает!
                raw_output = ""
                if captured_stdout and len(captured_stdout) > 100:
                    logger.info("✅ Используем captured stdout как результат")
                    raw_output = captured_stdout
                elif res is not None and str(res) != "None":
                    logger.info("✅ Используем return value как результат")
                    raw_output = res if isinstance(res, str) else str(res)
                elif captured_stdout:
                    logger.info("⚠️ Return пустой, используем stdout (даже если короткий)")
                    raw_output = captured_stdout
                else:
                    logger.warning("⚠️ И return и stdout пусты!")
                    raw_output = ""
                
                logger.info(f"🔍 raw_output (первые 500 символов):\n{'='*21}\n{raw_output[:500]}\n{'='*21}")
                
                # Извлекаем markdown (упрощенный парсинг)
                markdown_text = ""
                blocks = []
                
                # Парсим вывод модели
                lines = raw_output.split('\n')
                current_block = None
                block_counter = 0
                i = 0
                
                while i < len(lines):
                    line = lines[i]
                    
                    # Детектируем ref и det теги (для ocr_simple)
                    if '<|ref|>' in line:
                        # Сохраняем предыдущий блок
                        if current_block and current_block['content'].strip():
                            blocks.append(current_block)
                        
                        # Извлекаем текст элемента из <|ref|>...<|/ref|>
                        ref_text = line.split('<|ref|>')[1].split('<|/ref|>')[0]
                        
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
                            'type': 'text',  # Для ocr_simple всегда text
                            'content': ref_text,  # ИСПРАВЛЕНО: Текст элемента из <|ref|>
                            'bbox': {
                                'x0': float(bbox_data[0]),
                                'y0': float(bbox_data[1]),
                                'x1': float(bbox_data[2]),
                                'y1': float(bbox_data[3])
                            },
                            'confidence': 1.0,
                            'metadata': {}
                        }
                        block_counter += 1
                        markdown_text += ref_text + '\n'
                        
                        # Добавляем блок сразу (каждый элемент - отдельный блок)
                        blocks.append(current_block)
                        current_block = None
                    
                    elif current_block and not line.startswith('<|') and not line.startswith('===') and line.strip():
                        # Добавляем контент к текущему блоку (текст на следующих строках)
                        if current_block['content']:
                            current_block['content'] += '\n'
                        current_block['content'] += line.strip()
                        markdown_text += line.strip() + '\n'
                    
                    i += 1
                
                # Добавляем последний блок
                if current_block and current_block['content'].strip():
                    blocks.append(current_block)
                
                # Если нет структурированных блоков, но есть raw_output,
                # создаем один блок с описанием (для parse_figure, describe)
                if not blocks and raw_output.strip():
                    # Фильтруем служебные сообщения (BASE:, NO PATCHES, ===)
                    clean_lines = []
                    for line in raw_output.split('\n'):
                        line_stripped = line.strip()
                        if (line_stripped and 
                            not line_stripped.startswith('===') and 
                            not line_stripped.startswith('BASE:') and 
                            not line_stripped.startswith('NO PATCHES')):
                            clean_lines.append(line_stripped)
                    
                    description = '\n'.join(clean_lines).strip()
                    
                    if description:
                        blocks.append({
                            'id': 'ocr_block_description',
                            'type': 'text',
                            'content': description,
                            'bbox': {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 100},
                            'confidence': 0.8
                        })
                        markdown_text = description
                
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
