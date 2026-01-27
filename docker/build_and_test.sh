#!/bin/bash
# Скрипт для сборки и тестирования Docker образов OCR
# Использование: ./build_and_test.sh [qwen|deepseek|all]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Docker OCR Build & Test ===${NC}"

# 1. Проверка ресурсов
echo -e "\n${YELLOW}1. Проверка ресурсов...${NC}"
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
VRAM_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | sed 's/ MiB//')
if [ "$VRAM_USED" -gt 4000 ]; then
    echo -e "${RED}⚠️ VRAM занят ($VRAM_USED MiB). Остановите GPU процессы:${NC}"
    echo "pkill -f deepseek; pkill -f qwen"
    exit 1
fi
echo -e "${GREEN}✅ VRAM свободен${NC}"

# 2. Проверка Docker
echo -e "\n${YELLOW}2. Проверка Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не найден. Установите Docker:${NC}"
    echo "sudo apt-get install -y docker.io docker-compose-v2"
    exit 1
fi
docker --version
echo -e "${GREEN}✅ Docker доступен${NC}"

# 3. Проверка GPU в Docker
echo -e "\n${YELLOW}3. Проверка GPU в Docker...${NC}"
if docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✅ GPU доступен в Docker${NC}"
else
    echo -e "${RED}❌ GPU недоступен в Docker. Установите nvidia-container-toolkit${NC}"
    exit 1
fi

# 4. Сборка образов
PROFILE=${1:-"all"}
cd "$(dirname "$0")"

if [ "$PROFILE" == "qwen" ] || [ "$PROFILE" == "all" ]; then
    echo -e "\n${YELLOW}4a. Сборка Qwen VLM...${NC}"
    docker compose build qwen-vlm-2b
    echo -e "${GREEN}✅ Qwen VLM 2B собран${NC}"
fi

if [ "$PROFILE" == "deepseek" ] || [ "$PROFILE" == "all" ]; then
    echo -e "\n${YELLOW}4b. Сборка DeepSeek-OCR...${NC}"
    docker compose --profile deepseek-safe build
    echo -e "${GREEN}✅ DeepSeek-OCR собран${NC}"
fi

# 5. Запуск и тест
echo -e "\n${YELLOW}5. Запуск тестов...${NC}"

if [ "$PROFILE" == "qwen" ] || [ "$PROFILE" == "all" ]; then
    echo "Запуск Qwen..."
    docker compose up -d qwen-vlm-2b
    sleep 30
    curl -s http://localhost:8001/health && echo -e "\n${GREEN}✅ Qwen работает${NC}" || echo -e "${RED}❌ Qwen не отвечает${NC}"
    docker compose down
fi

if [ "$PROFILE" == "deepseek" ] || [ "$PROFILE" == "all" ]; then
    echo "Запуск DeepSeek..."
    docker compose --profile deepseek-safe up -d
    sleep 60  # DeepSeek грузится дольше
    curl -s http://localhost:8000/health && echo -e "\n${GREEN}✅ DeepSeek работает${NC}" || echo -e "${RED}❌ DeepSeek не отвечает${NC}"
    docker compose --profile deepseek-safe down
fi

echo -e "\n${GREEN}=== Готово! ===${NC}"
