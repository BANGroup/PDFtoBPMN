#!/usr/bin/env python3
"""
Тест гибридного парсера для VBK документа
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.vbk_hybrid_parser import VBKHybridParser


if __name__ == '__main__':
    pdf_path = "input/VBK16040002_1971_0019_9_1_2216_0008_20251111_большая.pdf"
    
    print("="*80)
    print("🧪 ТЕСТ ГИБРИДНОГО ПАРСЕРА - РАЗДЕЛ II")
    print("="*80)
    print()
    
    output_path = "output/finance/VBK_Раздел_II_hybrid.xlsx"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    parser = VBKHybridParser(pdf_path, section="II")
    df = parser.parse()
    
    if not df.empty:
        parser.save_to_excel(df, output_path)
        
        print("\n" + "="*80)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        print("="*80)
        print(f"   Всего записей: {len(df)}")
        print(f"   Всего колонок: {len(df.columns)}")
        
        # Проверяем наличие строк 17-19
        print("\n📋 ПРОВЕРКА СТРОК 17-19:")
        print("-"*80)
        for num in [17, 18, 19]:
            row = df[df['№ п/п'] == str(num)]
            if not row.empty:
                r = row.iloc[0]
                print(f"\n✅ Строка #{num}:")
                print(f"  Дата операции: {r['Дата операции']}")
                print(f"  Код операции: {r['Код вида операции']}")
                print(f"  Сумма платеж: {r['Сумма операции (платеж) - сумма']}")
                print(f"  Банк-нерезидент: {r['Банк-нерезидент - наименование'][:50] if r['Банк-нерезидент - наименование'] else 'None'}...")
                print(f"  Примечание: {str(r['Примечание'])[:100] if r['Примечание'] else 'None'}...")
            else:
                print(f"\n❌ Строка #{num} НЕ найдена")
        
        # Проверяем заполненность полей
        print("\n📊 ЗАПОЛНЕННОСТЬ ПОЛЕЙ:")
        print("-"*80)
        for col in df.columns:
            non_null = df[col].notna().sum()
            pct = (non_null / len(df)) * 100
            print(f"  {col[:40]:40s}: {non_null:3d}/{len(df):3d} ({pct:5.1f}%)")
        
        # Показываем первые 5 записей
        print("\n📋 ПЕРВЫЕ 5 ЗАПИСЕЙ:")
        print("-"*80)
        for idx in range(min(5, len(df))):
            r = df.iloc[idx]
            print(f"\nЗапись #{idx + 1}:")
            print(f"  № п/п: {r['№ п/п']}")
            print(f"  Дата: {r['Дата операции']}")
            print(f"  Код операции: {r['Код вида операции']}")
            print(f"  Сумма: {r['Сумма операции (платеж) - сумма']}")
        
        print("\n" + "="*80)
        print("✅ ГОТОВО!")
        print("="*80)
    else:
        print("\n❌ Не удалось извлечь данные")

