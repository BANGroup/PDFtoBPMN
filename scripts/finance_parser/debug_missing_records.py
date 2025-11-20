"""
Анализ пропущенных записей - почему не все извлекаются
"""

import pandas as pd
from pathlib import Path
import re

def analyze_missing():
    """Анализируем какие записи пропущены"""
    
    # Читаем файлы
    old_df = pd.read_excel("output/finance/Выпуск_4-02_на_16.06.2020.xlsx")
    new_df = pd.read_excel("output/finance_marker/Выпуск_4-02_marker.xlsx")
    md_path = Path("output/finance_marker/Выпуск 4-02 на 16.06.2020/Выпуск 4-02 на 16.06.2020.md")
    
    print("="*80)
    print("🔍 АНАЛИЗ ПРОПУЩЕННЫХ ЗАПИСЕЙ")
    print("="*80)
    print()
    
    # Находим пропущенные имена
    old_names = set(old_df['ФИО'].dropna().values)
    new_names = set(new_df['ФИО'].dropna().values)
    missing_names = old_names - new_names
    
    print(f"📊 Статистика:")
    print(f"   Старый файл: {len(old_names)} уникальных имен")
    print(f"   Новый файл:  {len(new_names)} уникальных имен")
    print(f"   Пропущено:   {len(missing_names)} имен")
    print()
    
    # Проверяем первые 10 пропущенных
    print("="*80)
    print("❌ ПРИМЕРЫ ПРОПУЩЕННЫХ ЗАПИСЕЙ")
    print("="*80)
    print()
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for i, name in enumerate(list(missing_names)[:10], 1):
        print(f"{i}. {name}")
        
        # Ищем это имя в Markdown
        if name in content:
            # Находим контекст вокруг имени
            pos = content.find(name)
            context_start = max(0, pos - 300)
            context_end = min(len(content), pos + 300)
            context = content[context_start:context_end]
            
            print(f"   ✅ Найдено в MD (позиция {pos})")
            
            # Ищем код владельца рядом
            code_pattern = r'(01_\d+)'
            codes_nearby = re.findall(code_pattern, context)
            if codes_nearby:
                print(f"   Коды рядом: {codes_nearby}")
            else:
                print(f"   ⚠️ Код владельца НЕ найден рядом!")
            
            # Ищем количество рядом
            qty_pattern = r'Количество в штуках[^\d]*?(\d+)'
            qty_match = re.search(qty_pattern, context)
            if qty_match:
                print(f"   Количество: {qty_match.group(1)}")
            else:
                print(f"   ⚠️ Количество НЕ найдено!")
            
            # Показываем фрагмент
            print(f"\n   Фрагмент MD:")
            print(f"   {'─'*76}")
            # Показываем 3 строки вокруг имени
            lines = context.split('\n')
            name_line_idx = None
            for idx, line in enumerate(lines):
                if name in line:
                    name_line_idx = idx
                    break
            
            if name_line_idx:
                start = max(0, name_line_idx - 2)
                end = min(len(lines), name_line_idx + 3)
                for line in lines[start:end]:
                    preview = line[:74]
                    print(f"   {preview}")
            print()
        else:
            print(f"   ❌ НЕ найдено в MD!")
            print()
    
    # Подсчитываем сколько кодов владельца в MD
    print("="*80)
    print("📋 ПОДСЧЕТ КОДОВ ВЛАДЕЛЬЦА")
    print("="*80)
    print()
    
    code_pattern = r'Код, присвоенный номинальным держателем[^\|]*\|(01_\d+)'
    all_codes = re.findall(code_pattern, content)
    
    print(f"Найдено кодов 'Код, присвоенный номинальным...': {len(all_codes)}")
    
    # Альтернативный поиск - просто все коды 01_XXXXXXXXXX
    simple_codes = re.findall(r'\b(01_\d{11})\b', content)
    print(f"Найдено кодов формата 01_XXXXXXXXXXX: {len(set(simple_codes))}")
    
    # Проверяем сколько количеств в документе
    qty_all = re.findall(r'Количество в штуках', content, re.IGNORECASE)
    print(f"Найдено упоминаний 'Количество в штуках': {len(qty_all)}")
    
    print()
    print("="*80)
    print("💡 ВЫВОД")
    print("="*80)
    print()
    
    # Проверяем расхождение
    old_count = len(old_df)
    marker_count = len(new_df)
    codes_count = len(all_codes)
    
    print(f"Записей в старом Excel:  {old_count}")
    print(f"Кодов в Markdown:        {codes_count}")
    print(f"Извлечено парсером:      {marker_count}")
    print()
    
    if codes_count > marker_count:
        print(f"⚠️ Парсер пропускает {codes_count - marker_count} записей!")
        print("   Причина: возможно валидация в _parse_record() отбрасывает записи")
        print("   Решение: смягчить проверки или добавить отладку")
    
    if old_count != codes_count:
        print(f"\n⚠️ Количество кодов в MD ({codes_count}) != записей в старом Excel ({old_count})")
        print("   Возможно в старом Excel есть дубликаты или записи без кодов")


if __name__ == "__main__":
    analyze_missing()


