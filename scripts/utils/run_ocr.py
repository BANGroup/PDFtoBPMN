#!/usr/bin/env python3
"""
[DEPRECATED] Скрипт для запуска OCR обработки PDF документов

⚠️ УСТАРЕВШИЙ СКРИПТ!

Этот скрипт работает только с PDF и вскоре будет удален.
Используйте вместо него: run_document.py

Новый скрипт поддерживает:
- PDF (с native text + OCR опционально)
- DOCX/DOC (Microsoft Word)
- XLSX/XLS (Microsoft Excel)

Миграция:
  СТАРОЕ: python3 run_ocr.py input/document.pdf output/process/process_OCR.md
  НОВОЕ:  python3 run_document.py input/document.pdf --output output/process/process_OCR.md
  
  СТАРОЕ: python3 run_ocr.py input/document.pdf
  НОВОЕ:  python3 run_document.py input/document.pdf

Автор: PDFtoBPMN Project
Дата: 05.11.2025 (создан), 11.11.2025 (deprecated)
"""

import sys
import subprocess
from pathlib import Path

# Определить путь к новому скрипту
current_dir = Path(__file__).resolve().parent
run_document_script = current_dir / "run_document.py"


def main():
    # Показать предупреждение
    print("=" * 70)
    print("⚠️  ВНИМАНИЕ: run_ocr.py УСТАРЕЛ!")
    print("=" * 70)
    print("Этот скрипт работает только с PDF и будет удален в будущем.")
    print()
    print("Используйте вместо него: run_document.py")
    print("  - Поддержка PDF, DOCX, XLSX")
    print("  - Автоматическое создание output папок")
    print("  - Лучшая обработка ошибок")
    print()
    print("Миграция:")
    print(f"  СТАРОЕ: python3 run_ocr.py {' '.join(sys.argv[1:])}")
    
    # Конвертировать старые аргументы в новые
    new_args = ["python3", str(run_document_script)]
    
    if len(sys.argv) >= 2:
        # Первый аргумент - входной файл
        new_args.append(sys.argv[1])
        
        # Второй аргумент (если есть) - output файл
        if len(sys.argv) >= 3:
            new_args.extend(["--output", sys.argv[2]])
        
        # Для PDF включаем OCR по умолчанию (как было раньше)
        if sys.argv[1].lower().endswith('.pdf'):
            new_args.append("--enable-ocr")
    
    print(f"  НОВОЕ:  {' '.join(new_args[1:])}")  # Без 'python3'
    print("=" * 70)
    print()
    
    # Спросить подтверждение
    print("Запустить обработку через новый скрипт? [Y/n]: ", end="", flush=True)
    
    try:
        response = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n\n❌ Отменено пользователем")
        sys.exit(1)
    
    if response in ['', 'y', 'yes', 'да']:
        print()
        # Запустить новый скрипт
    try:
            result = subprocess.run(new_args, check=False)
            sys.exit(result.returncode)
        except FileNotFoundError:
            print(f"❌ Ошибка: Не найден новый скрипт: {run_document_script}")
            sys.exit(1)
    except Exception as e:
            print(f"❌ Ошибка при запуске нового скрипта: {e}")
            sys.exit(1)
    else:
        print("\n❌ Отменено пользователем")
        print("\n💡 Для использования старой версии переключитесь на более раннюю версию проекта")
        print("   или обновите команду на run_document.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
