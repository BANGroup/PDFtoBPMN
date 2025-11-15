#!/usr/bin/env python3
"""
CLI-обёртка для обработки финансовых PDF документов (списки владельцев НРД)

Использование:
    # Обработать один файл
    python3 scripts/utils/process_finance_pdf.py input/Finance/document.pdf --output output.xlsx
    
    # Обработать всю папку
    python3 scripts/utils/process_finance_pdf.py input/Finance/ --output-dir output/Finance/
"""

import argparse
import sys
from pathlib import Path
import glob

# Добавляем scripts в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))


def find_pdf_files(input_path: Path) -> list:
    """Находит все PDF файлы в пути (файл или папка)"""
    if input_path.is_file():
        if input_path.suffix.lower() == '.pdf':
            return [input_path]
        else:
            raise ValueError(f"Файл {input_path} не является PDF")
    
    elif input_path.is_dir():
        # Рекурсивный поиск всех PDF в папке
        pdf_files = list(input_path.glob('**/*.pdf')) + list(input_path.glob('**/*.PDF'))
        return sorted(pdf_files)
    
    else:
        raise FileNotFoundError(f"Путь не найден: {input_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Обработка PDF списков владельцев облигаций НРД',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Обработать один PDF файл:
  python3 scripts/utils/process_finance_pdf.py input/Finance/Выпуск_4-01.pdf -o output.xlsx

  # Обработать всю папку input/Finance:
  python3 scripts/utils/process_finance_pdf.py input/Finance/ --output-dir output/Finance/

  # Обработать с валидацией против эталона:
  python3 scripts/utils/process_finance_pdf.py input/Finance/doc.pdf --etalon etalon.xlsx
        """
    )
    
    parser.add_argument(
        'input_path',
        help='Путь к PDF файлу или папке с PDF файлами'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Путь к выходному XLSX файлу (для одного PDF)'
    )
    
    parser.add_argument(
        '--output-dir', '-d',
        help='Папка для выходных XLSX файлов (для обработки папки)'
    )
    
    parser.add_argument(
        '--etalon', '-e',
        help='Эталонная XLSX для валидации (опционально)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Подробный вывод'
    )
    
    parser.add_argument(
        '--limit', '-l',
        type=int,
        help='Ограничить количество обрабатываемых файлов (для тестирования)'
    )
    
    args = parser.parse_args()
    
    # Проверяем входной путь
    input_path = Path(args.input_path)
    
    print("="*80)
    print("📄 FINANCE PDF PARSER - Обработка списков владельцев НРД")
    print("="*80 + "\n")
    
    try:
        # Находим все PDF файлы
        pdf_files = find_pdf_files(input_path)
        
        # Применяем лимит если задан
        if args.limit and args.limit > 0:
            pdf_files = pdf_files[:args.limit]
            print(f"⚠️  Применен лимит: обработка первых {args.limit} файлов\n")
        
        print(f"📁 Входная папка: {input_path}")
        print(f"📊 Найдено PDF файлов: {len(pdf_files)}\n")
        
        if len(pdf_files) == 0:
            print("❌ Не найдено PDF файлов для обработки")
            return 1
        
        # Показываем список файлов
        print("📋 Список файлов для обработки:")
        for i, pdf_file in enumerate(pdf_files, 1):
            size_mb = pdf_file.stat().st_size / (1024 * 1024)
            print(f"   {i:2d}. {pdf_file.name} ({size_mb:.1f} MB)")
        
        print("\n" + "="*80)
        
        # Определяем выходную папку
        if args.output_dir:
            output_dir = Path(args.output_dir)
        elif len(pdf_files) == 1 and args.output:
            output_dir = Path(args.output).parent
        else:
            # По умолчанию: output/Finance/
            output_dir = Path('output/Finance')
        
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"📂 Выходная папка: {output_dir}")
        
        # Импортируем пайплайн
        from finance_parser.pipeline import FinanceParserPipeline
        
        # Создаем пайплайн
        pipeline = FinanceParserPipeline()
        
        # Обрабатываем файлы
        try:
            if len(pdf_files) == 1:
                # Один файл
                pdf_file = pdf_files[0]
                if args.output:
                    output_file = Path(args.output)
                else:
            output_name = pdf_file.stem + "_владельцы.xlsx"
            output_file = output_dir / output_name
                
                pipeline.process_pdf(
                    pdf_file, 
                    output_file, 
                    start_page=2,
                    verbose=args.verbose
                )
            else:
                # Несколько файлов
                pipeline.process_multiple_pdfs(
                    pdf_files,
                    output_dir,
                    start_page=2,
                    verbose=args.verbose
                )
            
            print("="*80)
            print("✅ ОБРАБОТКА ЗАВЕРШЕНА")
            print("="*80)
        
        return 0
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Прервано пользователем")
            return 1
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
