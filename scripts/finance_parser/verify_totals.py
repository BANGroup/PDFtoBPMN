"""
Проверка: сравнение сумм по количеству бумаг и поиск дубликатов
"""

import pandas as pd
from pathlib import Path

def verify_totals():
    """Сравниваем итоговые суммы и ищем проблемы"""
    
    # Читаем оба файла
    old_path = Path("output/finance/Выпуск_4-02_на_16.06.2020.xlsx")
    new_path = Path("output/finance_marker/Выпуск_4-02_marker.xlsx")
    
    old_df = pd.read_excel(old_path)
    new_df = pd.read_excel(new_path)
    
    print("="*80)
    print("📊 ПРОВЕРКА ИТОГОВЫХ СУММ")
    print("="*80)
    print()
    
    # 1. Базовая статистика
    print("1️⃣ Количество записей:")
    print(f"   Старый (OCR):   {len(old_df)} записей")
    print(f"   Новый (Marker): {len(new_df)} записей")
    print(f"   Разница:        {len(old_df) - len(new_df)} записей")
    print()
    
    # 2. Суммы по количеству бумаг
    print("2️⃣ Сумма по количеству бумаг:")
    
    # Конвертируем в числа
    old_df['Количество в штуках'] = pd.to_numeric(old_df['Количество в штуках'], errors='coerce')
    new_df['Количество в штуках'] = pd.to_numeric(new_df['Количество в штуках'], errors='coerce')
    
    old_total = old_df['Количество в штуках'].sum()
    new_total = new_df['Количество в штуках'].sum()
    
    print(f"   Старый (OCR):   {old_total:,.0f} бумаг")
    print(f"   Новый (Marker): {new_total:,.0f} бумаг")
    print(f"   Разница:        {old_total - new_total:,.0f} бумаг ({(old_total - new_total)/old_total*100:.1f}%)")
    print()
    
    # 3. Проверка на дубликаты в старом файле
    print("3️⃣ Проверка дубликатов в старом файле:")
    
    # Дубликаты по коду владельца
    old_codes = old_df['Код владельца'].dropna()
    old_duplicates_codes = old_codes[old_codes.duplicated(keep=False)]
    
    if len(old_duplicates_codes) > 0:
        print(f"   ⚠️ Найдено {len(old_duplicates_codes)} дублирующихся кодов владельца!")
        print(f"   Уникальных дублей: {old_duplicates_codes.nunique()}")
        print()
        print("   Примеры дубликатов:")
        for code in old_duplicates_codes.unique()[:5]:
            count = (old_codes == code).sum()
            print(f"      • {code}: {count} раз")
    else:
        print("   ✅ Дубликатов по коду владельца нет")
    
    print()
    
    # Дубликаты по ФИО
    old_names = old_df['ФИО'].dropna()
    old_duplicates_names = old_names[old_names.duplicated(keep=False)]
    
    if len(old_duplicates_names) > 0:
        print(f"   ⚠️ Найдено {len(old_duplicates_names)} дублирующихся ФИО!")
        print(f"   Уникальных имен с дублями: {old_duplicates_names.nunique()}")
        print()
        print("   Примеры дубликатов:")
        for name in old_duplicates_names.unique()[:5]:
            count = (old_names == name).sum()
            records = old_df[old_df['ФИО'] == name]
            quantities = records['Количество в штуках'].tolist()
            print(f"      • {name}: {count} раз, количества: {quantities}")
    else:
        print("   ✅ Дубликатов по ФИО нет")
    
    print()
    
    # 4. Проверка новых данных
    print("4️⃣ Проверка нового файла (Marker):")
    
    new_codes = new_df['Код владельца'].dropna()
    new_duplicates = new_codes[new_codes.duplicated()]
    
    if len(new_duplicates) > 0:
        print(f"   ⚠️ Найдено дубликатов: {len(new_duplicates)}")
    else:
        print(f"   ✅ Дубликатов нет - все {len(new_codes)} кодов уникальны")
    
    print()
    
    # 5. Сравнение топ владельцев
    print("5️⃣ ТОП-10 владельцев по количеству бумаг:")
    print()
    
    print("   СТАРЫЙ (OCR):")
    old_top = old_df.nlargest(10, 'Количество в штуках')[['ФИО', 'Количество в штуках']]
    for idx, row in old_top.iterrows():
        print(f"      • {row['ФИО'][:50]:50s} {row['Количество в штуках']:>10,.0f}")
    
    print()
    print("   НОВЫЙ (Marker):")
    new_top = new_df.nlargest(10, 'Количество в штуках')[['ФИО', 'Количество в штуках']]
    for idx, row in new_top.iterrows():
        print(f"      • {row['ФИО'][:50]:50s} {row['Количество в штуках']:>10,.0f}")
    
    print()
    
    # 6. Итоговый вывод
    print("="*80)
    print("💡 ВЫВОД")
    print("="*80)
    print()
    
    if abs(old_total - new_total) / old_total < 0.01:  # Разница < 1%
        print("✅ СУММЫ СОВПАДАЮТ!")
        print(f"   Разница всего {abs(old_total - new_total):,.0f} бумаг ({abs(old_total - new_total)/old_total*100:.2f}%)")
        print()
        print("   📌 Marker парсер работает КОРРЕКТНО")
        print(f"   📌 Правильное количество записей: {len(new_df)}")
        print(f"   📌 В старом файле возможны дубликаты или ошибки")
    else:
        print("⚠️ СУММЫ НЕ СОВПАДАЮТ!")
        print(f"   Marker недосчитал {old_total - new_total:,.0f} бумаг")
        print()
        print("   Требуется дальнейшая доработка парсера")


if __name__ == "__main__":
    verify_totals()

