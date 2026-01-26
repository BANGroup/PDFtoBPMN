# Qwen VLM OCR Service
# Для RTX 5090 (24GB) или других GPU с достаточным VRAM
#
# Build:
#   docker build -t qwen-vlm-service .
#
# Run:
#   docker run --gpus all -p 8001:8001 \
#     -e QWEN_MODEL=Qwen/Qwen2-VL-7B-Instruct \
#     qwen-vlm-service

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Метаданные
LABEL maintainer="obligations-project"
LABEL description="Qwen VLM OCR Service for document processing"
LABEL version="1.0.0"

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models

# Модель по умолчанию (можно переопределить при запуске)
ENV QWEN_MODEL=Qwen/Qwen2-VL-7B-Instruct
ENV USE_FLASH_ATTENTION=false
ENV MAX_NEW_TOKENS=2048
ENV MAX_PIXELS=1003520
ENV MIN_PIXELS=200704

# Рабочая директория
WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Приложение
COPY app.py .

# Порт
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Запуск
CMD ["python", "app.py"]
