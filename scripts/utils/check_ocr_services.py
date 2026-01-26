#!/usr/bin/env python3
"""
Утилита для проверки доступных OCR сервисов

Показывает:
- Какие OCR сервисы доступны
- Какие зависимости установлены
- Рекомендации по установке

Использование:
    python3 scripts/utils/check_ocr_services.py
"""

import sys
from pathlib import Path

# Добавляем путь к проекту
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    print("=" * 60)
    print("🔍 ДИАГНОСТИКА OCR СЕРВИСОВ")
    print("=" * 60)
    print()
    
    # 1. Проверка базовых зависимостей
    print("📦 БАЗОВЫЕ ЗАВИСИМОСТИ:")
    print("-" * 40)
    
    try:
        import torch
        cuda = torch.cuda.is_available()
        cuda_version = torch.version.cuda if cuda else "N/A"
        gpu_name = torch.cuda.get_device_name(0) if cuda else "N/A"
        print(f"  ✅ torch: {torch.__version__}")
        print(f"     CUDA: {cuda} ({cuda_version})")
        if cuda:
            print(f"     GPU: {gpu_name}")
    except ImportError:
        print("  ❌ torch: не установлен")
        print("     pip install torch")
    
    try:
        import transformers
        print(f"  ✅ transformers: {transformers.__version__}")
    except ImportError:
        print("  ❌ transformers: не установлен")
        print("     pip install transformers")
    
    try:
        from PIL import Image
        import PIL
        print(f"  ✅ Pillow: {PIL.__version__}")
    except ImportError:
        print("  ❌ Pillow: не установлен")
        print("     pip install Pillow")
    
    print()
    
    # 2. Проверка OCR сервисов
    print("🔍 OCR СЕРВИСЫ:")
    print("-" * 40)
    
    try:
        from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory
        
        services = OCRServiceFactory.list_available_services()
        
        for name, info in services.items():
            available = info.get("available", False)
            status = "✅" if available else "❌"
            desc = info.get("description", info.get("error", ""))
            stype = info.get("type", "")
            
            print(f"  {status} {name.upper()}")
            print(f"     Тип: {stype}")
            print(f"     Статус: {desc}")
            print()
    except Exception as e:
        print(f"  ❌ Ошибка загрузки фабрики: {e}")
    
    # 3. Проверка Layout Detection
    print("📐 LAYOUT DETECTION:")
    print("-" * 40)
    
    try:
        from scripts.pdf_to_context.extractors.layout_detector import (
            is_layout_detection_available,
            DOCLAYOUT_AVAILABLE
        )
        
        if is_layout_detection_available():
            print("  ✅ DocLayout-YOLO: доступен")
        else:
            print("  ❌ DocLayout-YOLO: не установлен")
            print("     pip install doclayout-yolo")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
    
    print()
    
    # 4. Рекомендации
    print("💡 РЕКОМЕНДАЦИИ:")
    print("-" * 40)
    
    try:
        from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory
        services = OCRServiceFactory.list_available_services()
        
        available_count = sum(1 for s in services.values() if s.get("available", False))
        
        if available_count == 0:
            print("  ⚠️ Ни один OCR сервис недоступен!")
            print()
            print("  Варианты установки:")
            print("  1. PaddleOCR (CPU, простая установка):")
            print("     pip install paddlepaddle paddleocr")
            print()
            print("  2. DeepSeek-OCR (GPU, высокая точность):")
            print("     Запустить сервис на порту 8000")
            print()
            print("  3. Qwen VL (GPU, state-of-the-art):")
            print("     pip install transformers torch accelerate")
        else:
            print(f"  ✅ Доступно {available_count} OCR сервис(ов)")
            print()
            print("  Использование:")
            print("  from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory")
            print("  service = OCRServiceFactory.create()  # авто-выбор")
            print("  # или")
            print('  service = OCRServiceFactory.create(service_type="qwen")  # явный выбор')
    except Exception as e:
        print(f"  Ошибка: {e}")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
