# DeepSeek-OCR Service
# Универсальный Docker для разных GPU:
# - RTX 4080/4090 (sm_89)
# - RTX 5080/5090 (sm_120)
# - H100/A100 (sm_90/sm_80)
#
# Build:
#   docker build -t deepseek-ocr-service .
#
# Run (с flash_attn):
#   docker run --gpus all -p 8000:8000 deepseek-ocr-service
#
# Run (без flash_attn, универсально):
#   docker run --gpus all -p 8000:8000 -e USE_FLASH_ATTENTION=false deepseek-ocr-service

# Base image с CUDA 12.4 (совместим с большинством GPU)
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel AS builder

# Метаданные
LABEL maintainer="obligations-project"
LABEL description="DeepSeek-OCR Service - Universal GPU Docker"
LABEL version="1.0.0"

# Системные переменные
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# Системные зависимости для компиляции
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Python зависимости (без flash_attn - он опционален)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Попытка установить flash_attn (может не собраться для некоторых GPU)
# Если не получится - работаем без него
RUN pip install flash-attn --no-build-isolation 2>/dev/null || \
    echo "⚠️ flash_attn не установлен - работаем без него"

# ===== Runtime Stage =====
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models

# Конфигурация по умолчанию
ENV DEEPSEEK_MODEL=deepseek-ai/DeepSeek-OCR
ENV USE_FLASH_ATTENTION=auto
ENV MAX_NEW_TOKENS=4096

WORKDIR /app

# Копируем установленные пакеты из builder
COPY --from=builder /opt/conda /opt/conda

# Системные зависимости runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Приложение
COPY app.py .

# Порт
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск
CMD ["python", "app.py"]
