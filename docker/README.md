# Docker для OCR сервисов

## Финальная архитектура (27.01.2026)

```
┌─────────────────────────────────────────────────────────────────┐
│  DOCKER (универсальный, любые GPU с 8GB+ VRAM)                 │
│  └── Qwen2-VL-2B → порт 8001                                   │
│      • Работает без flash_attn (через SDPA)                    │
│      • Профили: default (Ada), blackwell (RTX 5070/5080/5090)  │
└─────────────────────────────────────────────────────────────────┘
                             
┌─────────────────────────────────────────────────────────────────┐
│  ЛОКАЛЬНЫЕ СЕРВИСЫ (для специфических задач)                    │
│  ├── DeepSeek-OCR → порт 8000                                   │
│  │   • Требует flash_attn под конкретную GPU                   │
│  │   • Дает bbox координаты текста                             │
│  │   • Установка: DeepSeek-OCR/venv/                           │
│  └── Qwen2-VL-7B → порт 8001                                   │
│      • Требует 24GB+ VRAM (RTX 5090)                           │
│      • Лучшее качество OCR                                     │
│      • Установка: venv/ + transformers                         │
└─────────────────────────────────────────────────────────────────┘
```

### Почему такая архитектура?

| Сервис | Docker | Локально | Причина |
|--------|--------|----------|---------|
| **Qwen 2B** | ✅ | ✅ | Работает без flash_attn, 5GB VRAM |
| **Qwen 7B** | ❌ | ✅ | Требует 24GB+ VRAM, локально эффективнее |
| **DeepSeek** | ❌ | ✅ | flash_attn требует компиляции под GPU |

### Сравнение OCR сервисов

| Параметр | Qwen 2B | Qwen 7B | DeepSeek |
|----------|---------|---------|----------|
| VRAM | ~5GB | ~14GB | ~8GB (+flash_attn) |
| Flash Attention | Не нужен | Не нужен | **Обязателен** |
| Bbox координаты | ❌ | ❌ | ✅ |
| Кириллица | ✅ | ✅ | ⚠️ Транслитерация |
| Docker | ✅ | ⚠️ | ❌ |

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

### Активные профили (Qwen 2B)

| GPU | Архитектура | CUDA | PyTorch | Профиль |
|-----|-------------|------|---------|---------|
| RTX 4080/4090 | Ada (sm_89) | 12.4+ | 2.5+ | `default` |
| RTX 5070/5080/5090 | **Blackwell (sm_120)** | **12.8+** | **2.10+cu128** | `blackwell` |

| Профиль | Модель | VRAM | PyTorch | Команда |
|---------|--------|------|---------|---------|
| **default** | Qwen 2B | ~5GB | 2.5+cu124 | `docker compose up` |
| **blackwell** | Qwen 2B | ~5GB | **2.10+cu128** | `docker compose --profile blackwell up` |

### ⚠️ Важно: RTX 5080/5090 требуют профиль `blackwell`

```bash
# ❌ НЕ РАБОТАЕТ на RTX 5080/5090:
docker compose up  # CUDA error: no kernel image

# ✅ РАБОТАЕТ на RTX 5080/5090:
docker compose --profile blackwell up
```

### Локальные сервисы (не Docker)

Qwen 7B и DeepSeek рекомендуется запускать локально:

```bash
# DeepSeek-OCR (с flash_attn)
cd DeepSeek-OCR
source venv/bin/activate
python ocr_server_api.py  # порт 8000

# Qwen 7B (локально, 24GB+ VRAM)
source venv/bin/activate
# Используйте qwen_local_service.py напрямую
```

## Рекомендации по GPU

| GPU | VRAM | Docker | Локально |
|-----|------|--------|----------|
| **RTX 5070** | 8GB | Qwen 2B (`blackwell`) | — |
| **RTX 5080** | 16GB | Qwen 2B (`blackwell`) | DeepSeek (с flash_attn) |
| **RTX 5090** | 24GB | Qwen 2B (`blackwell`) | Qwen 7B, DeepSeek |
| **RTX 4080** | 16GB | Qwen 2B (`default`) | DeepSeek (с flash_attn) |
| **RTX 4090** | 24GB | Qwen 2B (`default`) | Qwen 7B, DeepSeek |

### RTX 5070/5080/5090 (Blackwell)

```bash
# Docker: Qwen 2B
docker compose --profile blackwell up -d
curl http://localhost:8001/health

# Локально: DeepSeek (только на машине с flash_attn)
cd DeepSeek-OCR && source venv/bin/activate
python ocr_server_api.py &
curl http://localhost:8000/health
```

### RTX 4080/4090 (Ada)

```bash
# Docker: Qwen 2B
docker compose up -d
curl http://localhost:8001/health
```

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

### Настройка секретов (.env)

```bash
# 1. Скопировать пример конфигурации
cp .env.example .env

# 2. Отредактировать .env - добавить HF_TOKEN
# HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx  # Получить: huggingface.co/settings/tokens

# 3. Запустить Docker (автоматически читает .env)
cd docker
docker compose up -d
```

**Структура:**
```
project/
├── .env.example    # ✅ В git (шаблон без секретов)
├── .env            # ❌ НЕ в git (реальные секреты)
└── docker/
    └── docker-compose.yml  # Читает ../.env через env_file
```

**⚠️ .env добавлен в .gitignore — токены никогда не попадут в репозиторий!**

### Для клиента
- Python 3.10+
- requests
- (опционально) torch, transformers для локального fallback

## Структура файлов

```
docker/
├── README.md                    # Эта документация
├── docker-compose.yml           # Оркестрация контейнеров
├── qwen-vlm-service/
│   ├── Dockerfile              # Образ для Qwen VLM
│   ├── app.py                  # FastAPI приложение
│   └── requirements.txt        # Python зависимости
└── deepseek-ocr-service/
    ├── Dockerfile              # Образ для DeepSeek-OCR
    ├── app.py                  # FastAPI приложение
    ├── requirements.txt        # Python зависимости
    └── README.md               # Документация DeepSeek
```

## Установка Docker (WSL2)

### Вариант 1: Docker Desktop (Windows)

1. Установить Docker Desktop с https://docker.com
2. Включить "WSL 2 based engine"
3. Включить интеграцию с WSL дистрибутивом
4. Включить "GPU support" в Settings → Resources → GPU

### Вариант 2: Docker нативно в WSL

```bash
# Установка Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2

# Добавить пользователя в группу docker
sudo usermod -aG docker $USER

# Перелогиниться или:
newgrp docker

# Установка NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Проверка GPU в Docker
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

## Сборка образов

```bash
cd /home/budnik_an/Obligations/docker

# Qwen 2B для Ada (RTX 4080/4090)
docker compose build qwen-vlm-2b

# Qwen 2B для Blackwell (RTX 5080/5090)
# Уже собран: qwen-vlm-service:2b-cu128
docker images | grep qwen-vlm-service
```

## Troubleshooting

### Docker не найден в WSL

```bash
# Проверить установку
which docker

# Если путь в /mnt/c/... - это Docker Desktop, нужно включить WSL интеграцию
# Или установить Docker нативно в WSL (см. выше)
```

### GPU недоступен в Docker

```bash
# Проверить nvidia-container-toolkit
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi

# Если ошибка - установить nvidia-container-toolkit
```

### Зависание при сборке

```bash
# Перед сборкой остановить GPU процессы
pkill -f deepseek
pkill -f qwen
nvidia-smi  # Убедиться что VRAM свободен

# Затем собирать
docker compose --profile deepseek build
```
