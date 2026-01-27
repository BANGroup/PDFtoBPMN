# DeepSeek-OCR Docker Service

Универсальный Docker-образ для DeepSeek-OCR, работающий на любых NVIDIA GPU.

## Поддерживаемые GPU

| GPU | Архитектура | flash_attn | Статус |
|-----|-------------|------------|--------|
| RTX 4080/4090 | sm_89 (Ada) | ⚠️ Опционально | Поддерживается |
| RTX 5080/5090 | sm_120 (Blackwell) | ✅ Работает | Проверено |
| H100/A100 | sm_90/sm_80 | ✅ Pre-built | Поддерживается |

## Быстрый старт

### Вариант 1: С flash_attn (быстрее)

```bash
cd docker
docker compose --profile deepseek up -d

# Проверка
curl http://localhost:8000/health
```

### Вариант 2: Без flash_attn (гарантированно работает)

```bash
cd docker
docker compose --profile deepseek-safe up -d
```

## API

### Health Check

```bash
curl http://localhost:8000/health
```

**Ответ:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "cuda_available": true,
  "cuda_device": "NVIDIA GeForce RTX 5080",
  "flash_attention": true,
  "vram_total_gb": 16.0,
  "vram_free_gb": 8.5
}
```

### OCR

```bash
# Base64-encoded изображение
curl -X POST http://localhost:8000/ocr \
  -H "Content-Type: application/json" \
  -d '{
    "image": "<base64_encoded_image>",
    "prompt": "Извлеки текст с изображения",
    "system_prompt": "Ты эксперт OCR. Извлеки весь текст."
  }'
```

**Ответ:**
```json
{
  "text": "Распознанный текст...",
  "model": "deepseek-ai/DeepSeek-OCR",
  "inference_time": 2.34,
  "flash_attention": true
}
```

### Системные промпты

```bash
curl http://localhost:8000/prompts
```

| Промпт | Назначение |
|--------|------------|
| `default` | Универсальный OCR |
| `russian` | OCR русского текста |
| `bpmn` | Извлечение BPMN диаграмм |
| `table` | Извлечение таблиц |
| `layout` | OCR с координатами |

## Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DEEPSEEK_MODEL` | Модель HuggingFace | `deepseek-ai/DeepSeek-OCR` |
| `USE_FLASH_ATTENTION` | auto/true/false | `auto` |
| `MAX_NEW_TOKENS` | Макс. токенов | `4096` |

## Локальный запуск (без Docker)

```bash
# Активировать окружение DeepSeek
cd /home/budnik_an/Obligations
source DeepSeek-OCR/venv/bin/activate

# Запустить сервис
python -m uvicorn scripts.pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000

# Проверить
curl http://localhost:8000/health
```

## Интеграция с проектом

```python
from scripts.pdf_to_context.ocr_service import OCRServiceFactory

# Автовыбор (remote если доступен, иначе локально)
ocr = OCRServiceFactory.create(service_type="deepseek")

# Или явно через Docker
import os
os.environ["DEEPSEEK_URL"] = "http://server:8000"
ocr = OCRServiceFactory.create(service_type="deepseek")
```

## Требования

- NVIDIA GPU с 8GB+ VRAM
- Docker с поддержкой GPU (--gpus all)
- CUDA 12.x

## Troubleshooting

### flash_attn не компилируется

```bash
# Использовать профиль без flash_attn
docker compose --profile deepseek-safe up -d
```

### OOM (Out of Memory)

```bash
# Проверить использование VRAM
nvidia-smi

# Остановить другие GPU процессы
pkill -f qwen
pkill -f deepseek
```

### Модель не загружается

```bash
# Проверить логи
docker logs deepseek-ocr

# Очистить кэш моделей
docker volume rm deepseek-ocr-models
```
