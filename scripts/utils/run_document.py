#!/usr/bin/env python3
"""
Универсальный скрипт для обработки документов любого формата

Поддерживаемые форматы:
- PDF (с native text extraction, OCR опционально)
- DOCX/DOC (Microsoft Word)
- XLSX/XLS (Microsoft Excel)

Автоматически:
- Определяет формат по расширению
- Создает output папку
- Извлекает базовое имя процесса из имени файла

Использование:
    python3 run_document.py input/document.pdf
    python3 run_document.py input/document.docx --output output/process/process_OCR.md
    python3 run_document.py input/scan.pdf --enable-ocr
    python3 run_document.py input/data.xlsx --no-images
    
    # Локальные документы (автомаршрутизация: input2/ → output2/)
    python3 run_document.py input2/document.pdf
    python3 run_document.py input2/doc.docx --output-dir output2

Автор: PDFtoBPMN Project
Дата: 11.11.2025
Обновлено: 26.01.2026 - добавлена маршрутизация input2/ → output2/
"""

import sys
import argparse
import re
from pathlib import Path
from typing import Optional
import subprocess

# Добавить путь к корню проекта в sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts"))

from pdf_to_context.document_pipeline import DocumentToContextPipeline


def clean_document_name(filename: str) -> str:
    """
    Очистка имени документа для использования в путях
    
    Правила (из .cursorrules БЛОК 2):
    1. Взять имя файла без расширения
    2. Убрать содержимое в скобках: "(Эталон №14)" → ""
    3. Убрать спецсимволы кроме дефиса и подчеркивания
    4. Заменить пробелы на подчеркивания
    5. Удалить повторяющиеся подчеркивания
    6. Удалить подчеркивания в начале/конце
    
    Args:
        filename: Имя файла с расширением
        
    Returns:
        Очищенное базовое имя
        
    Examples:
        "ДП-М1.020-06 (Эталон №14).pdf" → "ДП-М1020-06"
        "СТО И.38-2025 V3.docx" → "СТО_И38-2025_V3"
    """
    # 1. Убрать расширение
    base = Path(filename).stem
    
    # 2. Убрать содержимое в скобках
    base = re.sub(r'\([^)]*\)', '', base)
    
    # 3. Убрать спецсимволы кроме дефиса и подчеркивания (и точки оставить)
    base = re.sub(r'[^\w\s\-.]', '', base)
    
    # 4. Заменить пробелы на подчеркивания
    base = base.replace(' ', '_')
    
    # 5. Удалить повторяющиеся подчеркивания
    base = re.sub(r'_+', '_', base)
    
    # 6. Удалить подчеркивания в начале/конце
    base = base.strip('_')
    
    return base


def detect_format(file_path: Path) -> str:
    """
    Определение формата документа по расширению
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Формат: 'pdf', 'docx', 'xlsx'
        
    Raises:
        ValueError: Если формат не поддерживается
    """
    suffix = file_path.suffix.lower()
    
    format_map = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.doc': 'docx',  # Попытаться открыть как DOCX
        '.xlsx': 'xlsx',
        '.xls': 'xlsx'   # Попытаться открыть как XLSX
    }
    
    if suffix not in format_map:
        raise ValueError(
            f"Неподдерживаемый формат: {suffix}\n"
            f"Поддерживаются: {', '.join(format_map.keys())}"
        )
    
    return format_map[suffix]


def print_progress(message: str, prefix: str = "🔄"):
    """Вывод прогресса с префиксом"""
    print(f"{prefix} {message}")


def print_stats(stats: dict):
    """Вывод статистики обработки"""
    print("\n📊 Статистика обработки:")
    print(f"   ✓ Формат: {stats.get('format', 'N/A')}")
    print(f"   ✓ Страниц/листов: {stats.get('pages_processed', 0)}")
    print(f"   ✓ Текстовых блоков: {stats.get('text_blocks', 0)}")
    print(f"   ✓ Заголовков: {stats.get('headings', 0)}")
    print(f"   ✓ Таблиц: {stats.get('tables', 0)}")
    print(f"   ✓ Изображений: {stats.get('images', 0)}")
    print(f"   ✓ Символов: {stats.get('total_chars', 0):,}")


def run_environment_check() -> bool:
    """
    Запуск check_environment.py для валидации окружения
    
    Returns:
        True если проверка прошла, False если были ошибки
    """
    check_script = project_root / "scripts" / "utils" / "check_environment.py"
    
    if not check_script.exists():
        print("⚠️ Предупреждение: check_environment.py не найден")
        print("   Пропускаем проверку окружения...")
        return True  # Не блокировать выполнение
    
    try:
        result = subprocess.run(
            [sys.executable, str(check_script)],
            capture_output=False,  # Показываем вывод напрямую
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True
        else:
            print("\n❌ Проверка окружения не пройдена!")
            print("   Рекомендуем устранить проблемы перед продолжением.")
            response = input("\n❓ Продолжить всё равно? (y/N): ").strip().lower()
            return response == 'y'
            
    except subprocess.TimeoutExpired:
        print("⚠️ Timeout при проверке окружения (>30s)")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка при запуске проверки: {e}")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Универсальный скрипт для обработки документов (PDF/DOCX/XLSX)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  
  # Обработать PDF (native text, без OCR)
  python3 run_document.py input/document.pdf
  
  # Обработать DOCX с указанием output файла
  python3 run_document.py input/document.docx --output output/process/process_OCR.md
  
  # Обработать PDF с OCR (для графики)
  python3 run_document.py input/scan.pdf --enable-ocr
  
  # Обработать XLSX без извлечения изображений
  python3 run_document.py input/data.xlsx --no-images
  
  # ЛОКАЛЬНЫЕ ДОКУМЕНТЫ (не попадают в git):
  # Автомаршрутизация: input2/ → output2/
  python3 run_document.py input2/document.pdf
  python3 run_document.py input2/confidential.docx
  
  # Явное указание выходной директории
  python3 run_document.py input2/doc.pdf --output-dir output2

Автоматическое создание output папки:
  Если --output не указан, создается: output/<base_name>/<base_name>_OCR.md
  Для файлов из input2/ создается: output2/<base_name>/<base_name>_OCR.md
  Базовое имя извлекается из имени файла (убираются скобки, спецсимволы)
        """
    )
    
    parser.add_argument(
        'input_file',
        type=str,
        help='Путь к входному файлу (PDF/DOCX/XLSX)'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Путь к выходному MD файлу (по умолчанию: auto)'
    )
    
    parser.add_argument(
        '--enable-ocr',
        action='store_true',
        help='Включить OCR для PDF (требует GPU + DeepSeek-OCR сервис)'
    )
    
    parser.add_argument(
        '--no-images',
        action='store_true',
        help='Не извлекать изображения'
    )
    
    parser.add_argument(
        '--no-tables',
        action='store_true',
        help='Не извлекать таблицы'
    )
    
    parser.add_argument(
        '--no-frontmatter',
        action='store_true',
        help='Не включать YAML frontmatter в Markdown'
    )
    
    parser.add_argument(
        '--no-toc',
        action='store_true',
        help='Не включать оглавление в Markdown'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Подробный вывод'
    )
    
    parser.add_argument(
        '--check-env',
        action='store_true',
        help='Проверить окружение перед обработкой (ОС, Python, кодировки, зависимости)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Базовая директория для вывода (по умолчанию: auto - output/ или output2/ в зависимости от input)'
    )
    
    args = parser.parse_args()
    
    # ===== ПРОВЕРКА ОКРУЖЕНИЯ (опционально) =====
    if args.check_env:
        print("=" * 70)
        print("🔍 ПРОВЕРКА ОКРУЖЕНИЯ")
        print("=" * 70)
        print()
        
        if not run_environment_check():
            print("\n❌ Прервано пользователем.")
            sys.exit(1)
        
        print()
        print("=" * 70)
        print("✅ ПРОВЕРКА ЗАВЕРШЕНА - НАЧИНАЕМ ОБРАБОТКУ")
        print("=" * 70)
        print()
    
    # Валидация входного файла
    input_path = Path(args.input_file)
    
    if not input_path.exists():
        print(f"❌ Ошибка: Файл не найден: {input_path}")
        sys.exit(1)
    
    if not input_path.is_file():
        print(f"❌ Ошибка: Путь не является файлом: {input_path}")
        sys.exit(1)
    
    # Определение формата
    try:
        doc_format = detect_format(input_path)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Предупреждение для старого .doc формата
    if input_path.suffix.lower() == '.doc':
        print("⚠️  ВНИМАНИЕ: Формат .doc (старый Word) может не поддерживаться.")
        print("   Рекомендация: Откройте файл в Word и сохраните как .docx")
        print("   Попытка обработать как .docx...\n")
    
    # Определение output пути
    if args.output:
        output_path = Path(args.output)
    else:
        # Автоматическое создание output пути
        base_name = clean_document_name(input_path.name)
        
        # Определение базовой директории для вывода
        if args.output_dir:
            # Явно указана директория
            base_output_dir = Path(args.output_dir)
        else:
            # Автоматическая маршрутизация: input2/ → output2/, иначе output/
            input_str = str(input_path.resolve())
            input2_path = str((project_root / "input2").resolve())
            
            if input_str.startswith(input2_path):
                base_output_dir = project_root / "output2"
                print(f"📍 Маршрутизация: input2/ → output2/")
            else:
                base_output_dir = project_root / "output"
        
        output_dir = base_output_dir / base_name
        output_path = output_dir / f"{base_name}_OCR.md"
        
        # Создать папку
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Автоматически создана папка: {output_dir.relative_to(project_root) if output_dir.is_relative_to(project_root) else output_dir}")
    
    # Вывод информации
    print(f"\n{'='*60}")
    print(f"🚀 ЗАПУСК ОБРАБОТКИ ДОКУМЕНТА")
    print(f"{'='*60}")
    print(f"📄 Входной файл:  {input_path.relative_to(project_root) if input_path.is_relative_to(project_root) else input_path}")
    print(f"📝 Формат:        .{doc_format.upper()}")
    print(f"💾 Выходной файл: {output_path.relative_to(project_root) if output_path.is_relative_to(project_root) else output_path}")
    
    if args.enable_ocr and doc_format == 'pdf':
        print(f"🔍 OCR:           Включен (GPU + DeepSeek-OCR)")
    
    print(f"{'='*60}\n")
    
    # Создание пайплайна
    print_progress("Инициализация пайплайна...", "⚙️")
    
    pipeline = DocumentToContextPipeline(
        enable_pdf_ocr=args.enable_ocr if doc_format == 'pdf' else False,
        ocr_base_url="http://localhost:8000",
        extract_images=not args.no_images,
        extract_tables=not args.no_tables,
        include_frontmatter=not args.no_frontmatter,
        include_toc=not args.no_toc
    )
    
    # Обработка документа
    try:
        print_progress(f"Обработка {doc_format.upper()} документа...", "🔄")
        
        markdown = pipeline.process(
            str(input_path),
            output_path=str(output_path)
        )
        
        # Статистика
        stats = pipeline.get_stats()
        print_stats(stats)
        
        # Успех
        print(f"\n{'='*60}")
        print(f"✅ ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО!")
        print(f"{'='*60}")
        print(f"💾 Результат сохранен: {output_path.relative_to(project_root) if output_path.is_relative_to(project_root) else output_path}")
        print(f"📊 Размер файла: {output_path.stat().st_size / 1024:.1f} KB")
        print()
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ ОШИБКА ПРИ ОБРАБОТКЕ")
        print(f"{'='*60}")
        print(f"Тип ошибки: {type(e).__name__}")
        print(f"Сообщение: {e}")
        
        if args.verbose:
            print("\nПодробная информация (traceback):")
            import traceback
            traceback.print_exc()
        
        print(f"\n💡 Возможные причины:")
        if doc_format == 'pdf' and args.enable_ocr:
            print("   - OCR сервис не запущен (требуется http://localhost:8000)")
            print("   - Нет GPU или CUDA")
        elif doc_format == 'docx' and input_path.suffix.lower() == '.doc':
            print("   - Файл .doc не может быть открыт как .docx")
            print("   - Откройте в Word и сохраните как .docx")
        elif doc_format == 'xlsx':
            print("   - Поврежденный XLSX файл")
            print("   - Файл защищен паролем")
        
        print(f"\n🔍 Для подробной диагностики добавьте флаг: --verbose")
        sys.exit(1)


if __name__ == "__main__":
    main()

