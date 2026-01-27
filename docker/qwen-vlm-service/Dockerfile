# Qwen VLM OCR Service
# Поддержка RTX 5080/5090 (Blackwell sm_120) + RTX 4080/4090 (Ada sm_89)
#
# Build:
#   docker build -t qwen-vlm-service .
#
# Run:
#   docker run --gpus all -p 8001:8000 \
#     -e QWEN_MODEL=Qwen/Qwen2-VL-7B-Instruct \
#     qwen-vlm-service

# Базовый образ с CUDA 12.8 (поддержка Blackwell)
FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04

# Метаданные
LABEL maintainer="obligations-project"
LABEL description="Qwen VLM OCR Service for document processing"
LABEL version="1.1.0"

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models
ENV DEBIAN_FRONTEND=noninteractive

# Модель по умолчанию (можно переопределить при запуске)
ENV QWEN_MODEL=Qwen/Qwen2-VL-7B-Instruct
ENV USE_FLASH_ATTENTION=false
ENV MAX_NEW_TOKENS=2048
ENV MAX_PIXELS=1003520
ENV MIN_PIXELS=200704

# Рабочая директория
WORKDIR /app

# Системные зависимости + Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    python3.11-venv \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Установка PyTorch с поддержкой CUDA 12.8 (Blackwell)
RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir \
        torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# Python зависимости (без torch, уже установлен)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Приложение
COPY app.py .

# Порт
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск
CMD ["python", "app.py"]
