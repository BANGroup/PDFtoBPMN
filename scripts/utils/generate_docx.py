#!/usr/bin/env python3
"""
Скрипт для генерации DOCX копий всех MD файлов процесса

Использование:
    python3 scripts/utils/generate_docx.py output/ДП-Б6001-07 ДП-Б6001-07
    
Создает DOCX версии для:
    - [base_name]_OCR.md → [base_name]_OCR.docx
    - [base_name]_RACI.md → [base_name]_RACI.docx
    - [base_name]_Pipeline.md → [base_name]_Pipeline.docx (с оглавлением)
    - [base_name].md → [base_name].docx (с оглавлением)
"""

import sys
from pathlib import Path

# Добавить путь к корню проекта в sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts"))

from pdf_to_context.utils.md_to_pdf import convert_process_files


def main():
    if len(sys.argv) < 3:
        print("Использование: python3 generate_docx.py <output_dir> <base_name>")
        print()
        print("Примеры:")
        print("  python3 generate_docx.py output/ДП-Б6001-07 ДП-Б6001-07")
        print("  python3 generate_docx.py output/ДП-М1.020-06 ДП-М1.020-06")
        print()
        print("Создаст DOCX версии всех MD файлов в указанной папке:")
        print("  - [base_name]_OCR.docx")
        print("  - [base_name]_RACI.docx")
        print("  - [base_name]_Pipeline.docx (с оглавлением)")
        print("  - [base_name].docx (с оглавлением)")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    base_name = sys.argv[2]
    
    print(f"📁 Папка процесса: {output_dir}")
    print(f"📄 Базовое имя: {base_name}")
    print()
    print("🔄 Генерация DOCX копий...")
    print()
    
    try:
        # Генерация DOCX (формат по умолчанию)
        stats = convert_process_files(
            output_dir=output_dir,
            base_name=base_name,
            format='docx'  # ВСЕГДА DOCX (лучше для таблиц)
        )
        
        print()
        print("=" * 60)
        print(f"✅ DOCX генерация завершена!")
        print(f"📊 Успешно: {stats['success']} из {stats['total']} файлов")
        
        if stats['failed'] > 0:
            print(f"❌ Ошибки: {stats['failed']} файлов")
        
        if stats['skipped'] > 0:
            print(f"⚠️ Пропущено: {stats['skipped']} файлов (pandoc не установлен)")
        
        print("=" * 60)
        
        if stats['success'] > 0:
            print()
            print("📂 Созданные DOCX файлы:")
            output_path = Path(output_dir)
            for docx_file in sorted(output_path.glob("*.docx")):
                size = docx_file.stat().st_size / 1024  # KB
                print(f"   ✓ {docx_file.name} ({size:.1f} KB)")
        
    except Exception as e:
        print(f"\n❌ Ошибка генерации DOCX: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

