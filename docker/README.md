# Docker для VLM OCR сервисов

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│  Локальная машина (16GB VRAM)                          │
│  ├── service_type="qwen_local" → Qwen2-VL-2B          │
│  └── service_type="qwen_remote" → Docker (7B/72B)     │
└─────────────────────────────────────────────────────────┘
                           ↓ HTTP :8001
┌─────────────────────────────────────────────────────────┐
│  Удалённый сервер с RTX 5090 (24GB+ VRAM)             │
│  └── docker/qwen-vlm-service (Qwen2-VL-7B)            │
└─────────────────────────────────────────────────────────┘
```

## Быстрый старт

### На машине с 16GB (RTX 5080)

```bash
# Использовать локальную 2B модель
cd /home/budnik_an/Obligations
source venv/bin/activate
python3 scripts/utils/run_document.py input/doc.pdf --ocr-service qwen_local
```

### На машине с 24GB+ (RTX 5090)

```bash
# Запустить Docker с 7B моделью
cd /home/budnik_an/Obligations/docker
docker compose --profile large up -d

# Проверить статус
curl http://localhost:8001/health
```

### Подключение к удалённому серверу

```bash
# На клиенте: указать URL удалённого сервера
export QWEN_REMOTE_URL=http://server-with-5090:8001
python3 scripts/utils/run_document.py input/doc.pdf --ocr-service qwen_remote

# Или автовыбор (remote если доступен, иначе local)
python3 scripts/utils/run_document.py input/doc.pdf --ocr-service qwen
```

## Профили Docker Compose

| Профиль | Модель | VRAM | Команда |
|---------|--------|------|---------|
| **default** | Qwen2-VL-2B | ~4GB | `docker compose up` |
| **large** | Qwen2-VL-7B | ~14GB | `docker compose --profile large up` |

## API

### Health Check
```bash
curl http://localhost:8001/health
```

### OCR запрос
```bash
curl -X POST http://localhost:8001/ocr \
  -H "Content-Type: application/json" \
  -d '{
    "image": "<base64_encoded_image>",
    "language": "russian"
  }'
```

### Информация о модели
```bash
curl http://localhost:8001/info
```

## Environment Variables

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `QWEN_MODEL` | Модель HuggingFace | `Qwen/Qwen2-VL-7B-Instruct` |
| `USE_FLASH_ATTENTION` | Flash Attention 2 | `false` |
| `MAX_NEW_TOKENS` | Макс токенов ответа | `2048` |
| `QWEN_REMOTE_URL` | URL для клиента | `http://localhost:8001` |

## Требования

### Для Docker хоста
- NVIDIA GPU с 24GB+ VRAM (для 7B)
- Docker с nvidia-container-toolkit
- CUDA 12.4+

### Для клиента
- Python 3.10+
- requests
- (опционально) torch, transformers для локального fallback

## Структура файлов

```
docker/
├── README.md                 # Эта документация
├── docker-compose.yml        # Оркестрация контейнеров
└── qwen-vlm-service/
    ├── Dockerfile           # Образ для Qwen VLM
    ├── app.py               # FastAPI приложение
    └── requirements.txt     # Python зависимости
```
