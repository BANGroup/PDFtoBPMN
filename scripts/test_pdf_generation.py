#!/usr/bin/env python3
"""
Тестовый скрипт для проверки генерации PDF из существующих MD файлов

Использование:
    python scripts/test_pdf_generation.py output/ДП-М1.020-06 ДП-М1.020-06
"""

import sys
from pathlib import Path

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent))

from pdf_to_context.utils.md_to_pdf import convert_process_files


def main():
    """Главная функция"""
    
    if len(sys.argv) < 3:
        print("Использование: python test_pdf_generation.py <output_dir> <base_name>")
        print("\nПример:")
        print("  python scripts/test_pdf_generation.py output/ДП-М1.020-06 ДП-М1.020-06")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    base_name = sys.argv[2]
    
    print(f"🔄 Генерация PDF для процесса: {base_name}")
    print(f"📁 Директория: {output_dir}\n")
    
    # Конвертация
    stats = convert_process_files(output_dir, base_name)
    
    # Статистика
    print(f"\n📊 Статистика конвертации:")
    print(f"   Всего MD файлов: {stats['total']}")
    print(f"   Успешно: {stats['success']}")
    print(f"   Ошибок: {stats['failed']}")
    print(f"   Пропущено: {stats['skipped']}")
    
    if stats['success'] > 0:
        print(f"\n✅ PDF файлы созданы в: {output_dir}/")
    elif stats['skipped'] > 0:
        print(f"\n⚠️  pandoc не установлен - PDF не созданы")
    else:
        print(f"\n❌ Не удалось создать PDF файлы")


if __name__ == "__main__":
    main()

