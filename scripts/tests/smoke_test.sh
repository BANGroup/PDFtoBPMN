#!/bin/bash
# Быстрая проверка что основные компоненты не сломаны
# Запускать перед коммитом

set -e

echo "🔥 Smoke test"

echo "1. Проверка импортов app.py..."
python3 -c "from scripts.pdf_to_context.ocr_service.app import app" || {
    echo "❌ Не удалось импортировать app"
    exit 1
}

echo "2. Проверка относительных импортов (НЕТ абсолютных)..."
if grep -r "from pdf_to_context.ocr_service" scripts/pdf_to_context/ocr_service/*.py; then
    echo "❌ Найдены абсолютные импорты! Используйте относительные: from .prompts"
    exit 1
fi

echo "3. Проверка prompts.py..."
python3 -c "from scripts.pdf_to_context.ocr_service.prompts import OCRPrompts; assert OCRPrompts.get_ocr_simple_prompt()" || {
    echo "❌ Не удалось импортировать OCRPrompts"
    exit 1
}

echo "4. Проверка pipeline.py..."
python3 -c "from scripts.pdf_to_context.pipeline import PDFToContextPipeline" || {
    echo "❌ Не удалось импортировать PDFToContextPipeline"
    exit 1
}

echo "5. Проверка структуры проекта..."
[ -d "scripts/pdf_to_context/ocr_service" ] || {
    echo "❌ Папка ocr_service не найдена"
    exit 1
}

echo ""
echo "✅ Smoke test пройден"
echo "   Все основные компоненты работают"

