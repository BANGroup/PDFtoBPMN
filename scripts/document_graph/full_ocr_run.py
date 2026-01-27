#!/usr/bin/env python3
"""
Полный прогон OCR DeepSeek для всех документов
С засечением времени и логированием
"""

import sys
import time
import json

# Отключаем буферизацию для real-time логирования
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
from pathlib import Path
from datetime import datetime, timedelta

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.pdf_to_context.pipeline import PDFToContextPipeline


def format_duration(seconds):
    """Форматирование длительности"""
    if seconds < 60:
        return f"{seconds:.1f} сек"
    elif seconds < 3600:
        return f"{seconds/60:.1f} мин"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours} ч {mins} мин"


def main():
    start_time = time.time()
    start_datetime = datetime.now()
    
    print("=" * 70)
    print("🚀 ПОЛНЫЙ ПРОГОН OCR DeepSeek")
    print("=" * 70)
    print(f"⏰ Старт: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Пути
    input_path = Path("/home/budnik_an/Obligations/input2/BND/pdf")
    output_base = Path("/home/budnik_an/Obligations/output/ocr_full_run")
    output_base.mkdir(parents=True, exist_ok=True)
    
    log_file = output_base / f"ocr_run_{start_datetime.strftime('%Y%m%d_%H%M%S')}.log"
    
    # Собираем все PDF файлы
    pdf_files = []
    for folder in input_path.iterdir():
        if folder.is_dir():
            for pdf in folder.glob("*.pdf"):
                if "для печати" in pdf.name or "для ознакомления" in pdf.name:
                    pdf_files.append(pdf)
    
    total_files = len(pdf_files)
    print(f"📁 Найдено PDF файлов: {total_files}")
    print()
    
    # Статистика
    stats = {
        "total": total_files,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "total_pages": 0,
        "total_time": 0,
        "files": []
    }
    
    # Pipeline с OCR
    pipeline = PDFToContextPipeline(
        enable_ocr=True,
        ocr_base_url="http://localhost:8000"
    )
    
    # Обработка каждого файла
    for idx, pdf_path in enumerate(pdf_files, 1):
        file_start = time.time()
        
        # Извлекаем код документа из имени папки
        doc_code = pdf_path.parent.name.split(" ^")[0] if " ^" in pdf_path.parent.name else pdf_path.stem
        
        print(f"\n[{idx}/{total_files}] 📄 {doc_code}")
        print(f"    Файл: {pdf_path.name}")
        
        try:
            # Выходной файл
            output_file = output_base / f"{doc_code}_OCR.md"
            
            # Проверяем не обработан ли уже
            if output_file.exists():
                print(f"    ⏭️ Пропущен (уже существует)")
                stats["skipped"] += 1
                stats["files"].append({
                    "code": doc_code,
                    "status": "skipped",
                    "reason": "already exists"
                })
                continue
            
            # Обработка - process() возвращает markdown строку
            markdown_result = pipeline.process(str(pdf_path), output_path=str(output_file))
            
            if markdown_result:
                file_time = time.time() - file_start
                
                # Подсчитываем страницы из PDF
                import fitz
                with fitz.open(str(pdf_path)) as doc:
                    pages = len(doc)
                
                stats["success"] += 1
                stats["total_pages"] += pages
                stats["files"].append({
                    "code": doc_code,
                    "status": "success",
                    "pages": pages,
                    "time": file_time,
                    "output": str(output_file)
                })
                
                print(f"    ✅ Успешно: {pages} стр, {format_duration(file_time)}")
            else:
                raise Exception("Пустой результат")
                
        except Exception as e:
            file_time = time.time() - file_start
            stats["failed"] += 1
            stats["files"].append({
                "code": doc_code,
                "status": "failed",
                "error": str(e),
                "time": file_time
            })
            print(f"    ❌ Ошибка: {e}")
        
        # Прогресс и ETA
        elapsed = time.time() - start_time
        if idx > 0:
            avg_time = elapsed / idx
            remaining = (total_files - idx) * avg_time
            eta = datetime.now() + timedelta(seconds=remaining)
            print(f"    📊 Прогресс: {idx}/{total_files} ({idx*100//total_files}%), ETA: {eta.strftime('%H:%M:%S')}")
        
        # Сохраняем промежуточный лог
        if idx % 10 == 0:
            stats["elapsed_time"] = elapsed
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # Финальная статистика
    total_time = time.time() - start_time
    end_datetime = datetime.now()
    
    stats["total_time"] = total_time
    stats["end_time"] = end_datetime.isoformat()
    
    # Сохраняем финальный лог
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 70)
    print("🏁 ЗАВЕРШЕНО!")
    print("=" * 70)
    print(f"⏰ Начало:     {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏰ Конец:      {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️ Общее время: {format_duration(total_time)}")
    print()
    print(f"📊 Статистика:")
    print(f"   ✅ Успешно:  {stats['success']}")
    print(f"   ❌ Ошибки:   {stats['failed']}")
    print(f"   ⏭️ Пропущено: {stats['skipped']}")
    print(f"   📄 Страниц:  {stats['total_pages']}")
    print()
    if stats['success'] > 0:
        avg_per_file = total_time / stats['success']
        print(f"   ⚡ Среднее время на файл: {format_duration(avg_per_file)}")
        if stats['total_pages'] > 0:
            avg_per_page = total_time / stats['total_pages']
            print(f"   ⚡ Среднее время на страницу: {format_duration(avg_per_page)}")
    print()
    print(f"📝 Лог: {log_file}")
    print(f"📁 Результаты: {output_base}")
    

if __name__ == "__main__":
    main()
