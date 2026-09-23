"""
Полная расшифровка PDF через Marker
Обрабатывает весь документ целиком
"""

from pathlib import Path
import time
from marker_processor import MarkerProcessor


def process_full_pdf():
    """Обрабатываем весь PDF документ"""
    
    print("="*80)
    print("📄 ПОЛНАЯ РАСШИФРОВКА PDF ЧЕРЕЗ MARKER")
    print("="*80)
    print()
    
    # Пути
    pdf_path = Path("/home/budnik_an/Obligations/input/Finance/Выпуск 4-02 на 16.06.2020.pdf")
    output_dir = Path("/home/budnik_an/Obligations/output/finance")
    
    if not pdf_path.exists():
        print(f"❌ Файл не найден: {pdf_path}")
        return
    
    print(f"📁 Входной PDF: {pdf_path.name}")
    print(f"📂 Выходная папка: {output_dir}")
    print()
    
    # Инициализация
    print("🔄 Инициализация Marker...")
    processor = MarkerProcessor()
    print()
    
    # Обработка
    print("🚀 ЗАПУСК ОБРАБОТКИ (весь документ)")
    print("-"*80)
    print("⏳ Это может занять несколько минут...")
    print()
    
    start_time = time.time()
    
    try:
        result = processor.process_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            page_range=None,      # Все страницы
            disable_ocr=False,    # OCR включен
            verbose=False         # Без подробного вывода (чтобы не засорять консоль)
        )
        
        elapsed = time.time() - start_time
        
        print()
        print("="*80)
        print("✅ ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО!")
        print("="*80)
        print()
        
        # Статистика
        print("📊 СТАТИСТИКА:")
        print("-"*80)
        print(f"   ⏱️  Время обработки: {elapsed:.1f} секунд ({elapsed/60:.1f} минут)")
        
        md_file = result['md_file']
        meta_file = result['meta_file']
        
        print(f"   📄 Markdown файл: {md_file.name}")
        print(f"   💾 Размер: {md_file.stat().st_size:,} байт ({md_file.stat().st_size / 1024:.1f} KB)")
        
        if meta_file and meta_file.exists():
            print(f"   📋 Метаданные: {meta_file.name}")
        
        print()
        print(f"   📂 Полный путь: {md_file}")
        print()
        
        # Метаданные
        if result['metadata']:
            metadata = result['metadata']
            
            print("📋 МЕТАДАННЫЕ:")
            print("-"*80)
            
            if 'table_of_contents' in metadata:
                toc = metadata['table_of_contents']
                print(f"   📑 Разделов в оглавлении: {len(toc)}")
                
                if toc and len(toc) > 0:
                    print(f"\n   Первые разделы:")
                    for i, section in enumerate(toc[:5]):
                        title = section.get('title', 'Без названия')
                        print(f"      {i+1}. {title}")
                    
                    if len(toc) > 5:
                        print(f"      ... и еще {len(toc) - 5} разделов")
            
            print()
        
        # Предварительный просмотр
        print("👀 ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР (первые 2000 символов):")
        print("-"*80)
        
        with open(md_file, 'r', encoding='utf-8') as f:
            preview = f.read(2000)
            print(preview)
            print("\n...")
        
        print()
        print("="*80)
        print("🎉 ГОТОВО!")
        print("="*80)
        print()
        print(f"💡 Результат сохранен в: {md_file}")
        print(f"💡 Откройте файл для просмотра полного содержимого")
        
        return result
        
    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print("="*80)
        print(f"❌ ОШИБКА после {elapsed:.1f} секунд")
        print("="*80)
        print()
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    process_full_pdf()




