#!/usr/bin/env python3
"""
Пример использования пайплайна обработки PDF

Демонстрирует автоматическое определение режима работы (Native + OCR или Native only)
"""

import sys
from pathlib import Path

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent))

from pdf_to_context.pipeline import PDFToContextPipeline


def process_document(pdf_path: str, output_base_name: str):
    """
    Обработать PDF документ
    
    Args:
        pdf_path: Путь к входному PDF файлу
        output_base_name: Базовое имя для выходных файлов (без расширения)
    """
    
    # Создаем пайплайн (автоматически определит режим OCR)
    # При инициализации выведет:
    # "🔍 Автоопределение режима: Native + OCR" или
    # "🔍 Автоопределение режима: Native only"
    pipeline = PDFToContextPipeline()
    
    # Определяем путь вывода
    output_dir = Path("output") / output_base_name
    output_file = output_dir / f"{output_base_name}_OCR.md"
    
    # Обработка
    print(f"\n📄 Обработка: {pdf_path}")
    print(f"💾 Результат: {output_file}\n")
    
    markdown = pipeline.process(
        pdf_path=pdf_path,
        output_path=str(output_file)
    )
    
    print(f"\n✅ Готово! Создан файл: {output_file}")
    print(f"📝 Длина результата: {len(markdown)} символов")
    
    return markdown


if __name__ == "__main__":
    # Пример использования
    if len(sys.argv) < 2:
        print("Использование: python example_usage.py <путь_к_pdf>")
        print("\nПример:")
        print("  python example_usage.py input/ДП-М1.020-06.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Извлекаем базовое имя из пути
    base_name = Path(pdf_path).stem
    # Очистка имени (убрать скобки, пробелы → подчеркивания)
    if '(' in base_name:
        base_name = base_name[:base_name.index('(')].strip()
    base_name = base_name.replace(' ', '_')
    while '__' in base_name:
        base_name = base_name.replace('__', '_')
    base_name = base_name.strip('_')
    
    # Обработка
    process_document(pdf_path, base_name)

