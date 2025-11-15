"""
Finance Parser Pipeline - главный пайплайн обработки PDF списков владельцев
"""

import fitz
import requests
from pathlib import Path
from typing import List
import time

from .html_parser import HTMLTableParser
from .models import ParsedPage, OwnerRecord, ValidationReport
from .record_merger import RecordMerger
from .xlsx_exporter import XLSXExporter


class FinanceParserPipeline:
    """Главный пайплайн обработки PDF документов"""
    
    def __init__(self, ocr_url: str = "http://localhost:8000/ocr/figure"):
        self.ocr_url = ocr_url
        self.html_parser = HTMLTableParser()
        self.record_merger = RecordMerger()
        self.xlsx_exporter = XLSXExporter()
    
    def process_pdf(self, pdf_path: Path, output_xlsx: Path, 
                    start_page: int = 2, end_page: int = None,
                    verbose: bool = False) -> ValidationReport:
        """
        Обработка одного PDF файла
        
        Args:
            pdf_path: Путь к PDF файлу
            output_xlsx: Путь к выходному XLSX файлу
            start_page: Номер страницы для начала (1-based, обычно 2 - первая с данными)
            end_page: Номер страницы для окончания (None = до конца)
            verbose: Подробный вывод
            
        Returns:
            ValidationReport с результатами
        """
        print("="*80)
        print(f"📄 Обработка: {pdf_path.name}")
        print("="*80)
        print()
        
        # Открываем PDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # Определяем диапазон страниц
        start_idx = start_page - 1  # Конвертируем в 0-based
        end_idx = end_page if end_page else total_pages
        pages_to_process = list(range(start_idx, min(end_idx, total_pages)))
        
        print(f"📊 Всего страниц в PDF: {total_pages}")
        print(f"📌 Обработка страниц: {start_page} - {end_idx}")
        print(f"⏱️  Обрабатывается: {len(pages_to_process)} страниц")
        print()
        
        # Шаг 1: OCR + Парсинг всех страниц
        print("🔄 ШАГ 1: OCR и парсинг HTML таблиц")
        print("-"*80)
        
        parsed_pages = []
        
        for idx in pages_to_process:
            page_num = idx + 1
            
            if verbose or (page_num % 10 == 0):
                print(f"   Страница {page_num}/{total_pages}...", end=' ')
            
            try:
                # Конвертируем страницу в PNG
                page = doc[idx]
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                
                # OCR
                files = {'file': ('page.png', img_bytes, 'image/png')}
                response = requests.post(self.ocr_url, files=files, timeout=120)
                
                if response.status_code == 200:
                    result = response.json()
                    raw_output = result.get('raw_output', '')
                    
                    # Парсим HTML таблицы
                    blocks = self.html_parser.parse_raw_output(raw_output)
                    
                    parsed_pages.append(ParsedPage(
                        page_number=page_num,
                        blocks=blocks
                    ))
                    
                    if verbose or (page_num % 10 == 0):
                        print(f"✅ ({len(blocks)} блоков)")
                else:
                    print(f"❌ OCR ошибка: {response.status_code}")
            
            except Exception as e:
                print(f"❌ Ошибка на странице {page_num}: {e}")
            
            # Небольшая пауза между запросами
            time.sleep(0.1)
        
        doc.close()
        
        print()
        print(f"✅ Обработано страниц: {len(parsed_pages)}")
        print()
        
        # Шаг 2: Склейка записей
        print("🔄 ШАГ 2: Склейка записей владельцев")
        print("-"*80)
        
        records = self.record_merger.process_pages(parsed_pages)
        
        print(f"✅ Извлечено записей: {len(records)}")
        print()
        
        # Шаг 3: Экспорт в XLSX + валидация
        print("🔄 ШАГ 3: Экспорт в XLSX и валидация")
        print("-"*80)
        
        report = self.xlsx_exporter.export(records, output_xlsx)
        
        print(f"✅ Сохранено: {output_xlsx}")
        print()
        
        # Показываем отчет
        report.print_report()
        
        return report
    
    def process_multiple_pdfs(self, pdf_files: List[Path], output_dir: Path,
                             start_page: int = 2, verbose: bool = False):
        """
        Обработка нескольких PDF файлов
        
        Args:
            pdf_files: Список путей к PDF файлам
            output_dir: Папка для выходных XLSX
            start_page: Номер страницы для начала
            verbose: Подробный вывод
        """
        print("="*80)
        print(f"📦 BATCH ОБРАБОТКА: {len(pdf_files)} файлов")
        print("="*80)
        print()
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        
        for i, pdf_path in enumerate(pdf_files, 1):
            print(f"\n{'#'*80}")
            print(f"# ФАЙЛ {i}/{len(pdf_files)}")
            print(f"{'#'*80}\n")
            
            # Формируем имя выходного файла
            output_name = pdf_path.stem + "_владельцы.xlsx"
            output_xlsx = output_dir / output_name
            
            # Обрабатываем
            try:
                report = self.process_pdf(pdf_path, output_xlsx, start_page, verbose=verbose)
                results.append({
                    'file': pdf_path.name,
                    'output': output_xlsx.name,
                    'report': report,
                    'success': True
                })
            except Exception as e:
                print(f"\n❌ ОШИБКА при обработке {pdf_path.name}: {e}")
                results.append({
                    'file': pdf_path.name,
                    'success': False,
                    'error': str(e)
                })
        
        # Итоговый отчет
        print("\n" + "="*80)
        print("📊 ИТОГОВЫЙ ОТЧЕТ ПО ВСЕМ ФАЙЛАМ")
        print("="*80)
        print()
        
        total_records = 0
        total_quantity = 0
        successful_files = 0
        
        for result in results:
            if result['success']:
                successful_files += 1
                report = result['report']
                total_records += report.total_records
                total_quantity += report.total_quantity
                
                print(f"✅ {result['file']}")
                print(f"   → {result['output']}")
                print(f"   Записей: {report.valid_records}/{report.total_records}, "
                      f"Бумаг: {report.total_quantity:,}".replace(',', ' '))
            else:
                print(f"❌ {result['file']}: {result.get('error', 'Unknown error')}")
        
        print()
        print(f"📝 Успешно обработано: {successful_files}/{len(pdf_files)} файлов")
        print(f"📊 Всего записей: {total_records}")
        print(f"💰 Всего бумаг: {total_quantity:,} шт.".replace(',', ' '))
        print()







