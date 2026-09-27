#!/usr/bin/env python3
"""
Тест последовательного парсера для VBK документа
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.vbk_sequential_parser import VBKSequentialParser


if __name__ == '__main__':
    pdf_path = "input/VBK16040002_1971_0019_9_1_2216_0008_20251111_большая.pdf"
    
    print("="*80)
    print("🧪 ТЕСТ ПОСЛЕДОВАТЕЛЬНОГО ПАРСЕРА - РАЗДЕЛ II")
    print("="*80)
    print()
    
    output_path = "output/finance/VBK_Раздел_II_sequential.xlsx"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    parser = VBKSequentialParser(pdf_path, section="II")
    df = parser.parse()
    
    if not df.empty:
        parser.save_to_excel(df, output_path)
        
        print("\n" + "="*80)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        print("="*80)
        print(f"   Всего записей: {len(df)}")
        print(f"   Всего колонок: {len(df.columns)}")
        
        # Проверяем наличие строк 17-19
        print("\n📋 Проверка строк 17-19:")
        print("-"*80)
        for num in [17, 18, 19]:
            row = df[df.iloc[:, 0] == str(num)]
            if not row.empty:
                r = row.iloc[0]
                print(f"\n✅ Строка #{num} найдена:")
                print(f"  Дата операции: {r.iloc[1]}")
                print(f"  Код операции: {r.iloc[4]}")
                print(f"  Сумма платеж: {r.iloc[7]}")
                print(f"  Примечание: {r.iloc[18][:100] if r.iloc[18] else 'None'}...")
            else:
                print(f"\n❌ Строка #{num} НЕ найдена")
        
        # Показываем первые 5 записей
        print("\n📋 Первые 5 записей:")
        print("-"*80)
        print(df.head(5).to_string(max_colwidth=30))
        
        print("\n" + "="*80)
        print("✅ ГОТОВО!")
        print("="*80)
    else:
        print("\n❌ Не удалось извлечь данные")

