#!/usr/bin/env python3
"""
Скрипт для запуска OCR обработки PDF документов
"""

import sys
from pathlib import Path

# Добавить путь к scripts в sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scripts.pdf_to_context.pipeline import PDFToContextPipeline


def main():
    if len(sys.argv) < 2:
        print("Использование: python3 run_ocr.py <путь_к_PDF> [<путь_к_выходному_MD>]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"🚀 Запуск OCR обработки...")
    print(f"📄 Входной файл: {pdf_path}")
    if output_path:
        print(f"💾 Выходной файл: {output_path}")
    print()
    
    # Создать пайплайн
    pipeline = PDFToContextPipeline(
        ocr_base_url="http://localhost:8000",
        enable_ocr=True,
        extract_images=True,
        extract_drawings=True,
        extract_tables=True,
        ocr_vector_graphics=True,
        vector_render_dpi=300,
        include_frontmatter=True,
        include_toc=True
    )
    
    # Обработать документ
    try:
        markdown = pipeline.process(pdf_path, output_path=output_path)
        
        if not output_path:
            print(markdown)
        
        print("\n✅ Готово!")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


