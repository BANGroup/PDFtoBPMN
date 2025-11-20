#!/usr/bin/env python3
"""
Запуск парсера для VBK документа (Раздел II)
"""

import sys
from pathlib import Path

# Добавляем корневую папку проекта в путь
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.vbk_section2_parser import VBKSection2Parser


if __name__ == '__main__':
    pdf_path = "input/VBK16040002_1971_0019_9_1_2216_0008_20251111_большая.pdf"
    output_path = "output/finance/VBK_Раздел_II.xlsx"
    
    # Создаем выходную папку
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    print("="*80)
    print("🚀 ЗАПУСК ПАРСЕРА VBK РАЗДЕЛ II")
    print("="*80)
    print()
    
    # Парсим
    parser = VBKSection2Parser(pdf_path)
    df = parser.parse()
    
    if not df.empty:
        parser.save_to_excel(df, output_path)
        
        # Статистика
        print("\n" + "="*80)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        print("="*80)
        print(f"   Всего строк: {len(df)}")
        print(f"   Всего колонок: {len(df.columns)}")
        print(f"   Финансовые колонки (формат с 2 знаками): ")
        for col in parser.financial_columns:
            print(f"     • {col}")
        
        # Показываем первые несколько строк
        print("\n📋 Первые 5 строк:")
        print("-"*80)
        print(df.head(5).to_string(max_colwidth=30))
        
        print("\n" + "="*80)
        print("✅ ГОТОВО!")
        print("="*80)
    else:
        print("\n❌ Не удалось извлечь данные")

