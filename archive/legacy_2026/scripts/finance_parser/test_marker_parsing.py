"""
Тест парсинга Markdown от Marker и сравнение с существующим Excel
"""

from pathlib import Path
import sys
import pandas as pd

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from scripts.finance_parser.md_parser import MDParser

def show_existing_excel():
    """Показать структуру существующего Excel"""
    excel_path = Path("/home/budnik_an/Obligations/output/finance/Выпуск_4-02_на_16.06.2020.xlsx")
    
    print("="*80)
    print("📊 СУЩЕСТВУЮЩИЙ EXCEL ФАЙЛ")
    print("="*80)
    print()
    
    if excel_path.exists():
        df = pd.read_excel(excel_path)
        print(f"Строк: {len(df)}")
        print(f"Колонок: {len(df.columns)}")
        print()
        print("Колонки:")
        for i, col in enumerate(df.columns, 1):
            print(f"  {i}. {col}")
        print()
        print("Первые 3 записи:")
        print(df.head(3).to_string())
    else:
        print("❌ Файл не найден")
    
    print()

def parse_marker_md():
    """Парсим Markdown от Marker"""
    md_path = Path("/home/budnik_an/Obligations/output/finance_marker/Выпуск 4-02 на 16.06.2020/Выпуск 4-02 на 16.06.2020.md")
    
    print("="*80)
    print("🔍 ПАРСИНГ MARKDOWN ОТ MARKER")
    print("="*80)
    print()
    
    if not md_path.exists():
        print(f"❌ Файл не найден: {md_path}")
        return None
    
    parser = MDParser()
    
    print("📄 Читаем Markdown...")
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"Размер: {len(content):,} символов")
    print()
    
    print("🔄 Парсинг записей...")
    records = parser.parse_md_content(content)
    
    print(f"✅ Извлечено записей: {len(records)}")
    print()
    
    if records:
        print("Первые 3 записи:")
        for i, record in enumerate(records[:3], 1):
            print(f"\n{i}. {record.owner_name}")
            print(f"   Адрес: {record.address}")
            print(f"   Документ: {record.document_number}")
            print(f"   Количество: {record.quantity}")
    
    return records

def export_to_excel(records, output_path):
    """Экспортируем записи в Excel"""
    print()
    print("="*80)
    print("💾 ЭКСПОРТ В EXCEL")
    print("="*80)
    print()
    
    if not records:
        print("❌ Нет записей для экспорта")
        return
    
    # Конвертируем в DataFrame
    data = []
    for record in records:
        data.append({
            'Владелец': record.owner_name,
            'Адрес': record.address,
            'Номер документа': record.document_number,
            'Тип документа': record.document_type,
            'Количество': record.quantity,
            'ISIN': record.isin if hasattr(record, 'isin') else '',
            'Дата рождения': record.birth_date if hasattr(record, 'birth_date') else ''
        })
    
    df = pd.DataFrame(data)
    
    print(f"Записей для экспорта: {len(df)}")
    print()
    
    # Сохраняем
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)
    
    print(f"✅ Сохранено: {output_path}")
    print(f"   Размер: {output_path.stat().st_size:,} байт")
    print()

if __name__ == "__main__":
    print()
    
    # 1. Показываем существующий Excel
    show_existing_excel()
    
    # 2. Парсим Markdown от Marker
    records = parse_marker_md()
    
    # 3. Экспортируем в новый Excel
    if records:
        output_path = Path("/home/budnik_an/Obligations/output/finance_marker/Выпуск_4-02_marker.xlsx")
        export_to_excel(records, output_path)
        
        print("="*80)
        print("✅ ГОТОВО!")
        print("="*80)
        print()
        print(f"Сравните файлы:")
        print(f"  • Старый: output/finance/Выпуск_4-02_на_16.06.2020.xlsx")
        print(f"  • Новый:  output/finance_marker/Выпуск_4-02_marker.xlsx")
    else:
        print()
        print("="*80)
        print("⚠️ НЕТ ИЗВЛЕЧЕННЫХ ДАННЫХ")
        print("="*80)
        print()
        print("Возможные причины:")
        print("  • MDParser не распознает формат Markdown от Marker")
        print("  • Нужно адаптировать регулярные выражения")
        print("  • Структура данных в Markdown отличается от ожидаемой")

