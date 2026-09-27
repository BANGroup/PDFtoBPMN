"""
Тест работоспособности Marker для конвертации PDF в Markdown
"""

from pathlib import Path
import time
from marker.convert import convert_single_pdf
from marker.models import load_all_models


def test_marker():
    """Тестируем Marker на одном PDF файле"""
    
    print("="*80)
    print("🧪 ТЕСТ MARKER PDF → MARKDOWN")
    print("="*80)
    print()
    
    # Путь к тестовому PDF (берем меньший файл для быстроты)
    test_pdf = Path("/home/budnik_an/Obligations/input/Finance/Выпуск 4-02 на 16.06.2020.pdf")
    
    if not test_pdf.exists():
        print(f"❌ Файл не найден: {test_pdf}")
        return
    
    print(f"📄 Тестовый PDF: {test_pdf.name}")
    print()
    
    # Шаг 1: Загрузка моделей
    print("🔄 ШАГ 1: Загрузка моделей Marker...")
    print("-"*80)
    
    start_load = time.time()
    try:
        models = load_all_models()
        load_time = time.time() - start_load
        print(f"✅ Модели загружены за {load_time:.1f} секунд")
    except Exception as e:
        print(f"❌ Ошибка загрузки моделей: {e}")
        return
    
    print()
    
    # Шаг 2: Конвертация PDF (только первые 3 страницы для теста)
    print("🔄 ШАГ 2: Конвертация PDF → Markdown (первые 3 страницы)")
    print("-"*80)
    
    start_convert = time.time()
    try:
        full_text, images, out_meta = convert_single_pdf(
            str(test_pdf),
            models,
            max_pages=3,  # Только первые 3 страницы для теста
            langs=["Russian", "English"],
            batch_multiplier=2
        )
        convert_time = time.time() - start_convert
        
        print(f"✅ Конвертация завершена за {convert_time:.1f} секунд")
        print()
        
        # Статистика
        print("📊 СТАТИСТИКА:")
        print("-"*80)
        print(f"   Размер текста: {len(full_text):,} символов".replace(',', ' '))
        print(f"   Строк: {full_text.count(chr(10)):,}".replace(',', ' '))
        print(f"   Изображений извлечено: {len(images)}")
        print()
        
        # Метаданные
        if out_meta:
            print("📋 МЕТАДАННЫЕ:")
            print("-"*80)
            for key, value in out_meta.items():
                print(f"   {key}: {value}")
            print()
        
        # Сохраняем результат
        output_md = Path("/home/budnik_an/Obligations/output/finance/marker_test.md")
        output_md.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(full_text)
        
        print(f"💾 Результат сохранен: {output_md}")
        print()
        
        # Показываем начало результата
        print("📄 НАЧАЛО РЕЗУЛЬТАТА (первые 1000 символов):")
        print("-"*80)
        print(full_text[:1000])
        print("...")
        print()
        
        print("="*80)
        print("✅ ТЕСТ ПРОЙДЕН УСПЕШНО!")
        print("="*80)
        print()
        print(f"⏱️  Общее время: {load_time + convert_time:.1f} секунд")
        print(f"   - Загрузка моделей: {load_time:.1f} сек")
        print(f"   - Конвертация: {convert_time:.1f} сек")
        
    except Exception as e:
        print(f"❌ Ошибка конвертации: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_marker()




