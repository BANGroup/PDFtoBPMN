# Docker для OCR сервисов

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│  Локальная машина                                       │
│  ├── qwen_local → Qwen2-VL-2B (16GB VRAM)             │
│  ├── qwen_remote → Docker Qwen (7B+)                   │
│  └── deepseek → Docker DeepSeek-OCR                    │
└─────────────────────────────────────────────────────────┘
              ↓ HTTP :8001 (Qwen)    ↓ HTTP :8000 (DeepSeek)
┌─────────────────────────────────────────────────────────┐
│  Docker сервисы (любая GPU: 4080/5080/5090/H100)       │
│  ├── qwen-vlm-service (порт 8001)                      │
│  └── deepseek-ocr-service (порт 8000)                  │
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

| Профиль | Сервис | Модель | VRAM | Порт | Команда |
|---------|--------|--------|------|------|---------|
| **default** | Qwen | 2B | ~4GB | 8001 | `docker compose up` |
| **large** | Qwen | 7B | ~14GB | 8001 | `docker compose --profile large up` |
| **deepseek** | DeepSeek | 3B | ~8GB | 8000 | `docker compose --profile deepseek up` |
| **deepseek-safe** | DeepSeek | 3B (no flash) | ~10GB | 8000 | `docker compose --profile deepseek-safe up` |

### DeepSeek-OCR

```bash
# С автоопределением flash_attn (быстрее если работает)
docker compose --profile deepseek up -d

# Без flash_attn (гарантированно работает на любой GPU)
docker compose --profile deepseek-safe up -d

# Проверка
curl http://localhost:8000/health
```

**Поддерживаемые GPU:**
- RTX 4080/4090 (Ada Lovelace, sm_89)
- RTX 5080/5090 (Blackwell, sm_120)
- H100/A100 (Hopper/Ampere, sm_90/sm_80)

**flash_attn:**
- `USE_FLASH_ATTENTION=auto` — попытка использовать, fallback если не работает
- `USE_FLASH_ATTENTION=true` — обязательно (ошибка если не работает)
- `USE_FLASH_ATTENTION=false` — отключить (медленнее, но универсально)

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
