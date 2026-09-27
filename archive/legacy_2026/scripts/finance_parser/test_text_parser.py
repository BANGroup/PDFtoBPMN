#!/usr/bin/env python3
"""
Тест текстового парсера для VBK документа
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.vbk_text_parser import VBKTextParser


if __name__ == '__main__':
    pdf_path = "input/VBK16040002_1971_0019_9_1_2216_0008_20251111_большая.pdf"
    
    print("="*80)
    print("🧪 ТЕСТ ТЕКСТОВОГО ПАРСЕРА - РАЗДЕЛ II")
    print("="*80)
    print()
    
    output_path = "output/finance/VBK_Раздел_II_text.xlsx"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    parser = VBKTextParser(pdf_path, section="II")
    df = parser.parse()
    
    if not df.empty:
        parser.save_to_excel(df, output_path)
        
        print("\n" + "="*80)
        print("📊 ИТОГОВАЯ СТАТИСТИКА:")
        print("="*80)
        print(f"   Всего записей: {len(df)}")
        print(f"   Всего колонок: {len(df.columns)}")
        
        print("\n📋 Первые 5 записей:")
        print("-"*80)
        print(df.head(5).to_string(max_colwidth=30))
        
        print("\n📋 Записи 17-20 (проблемная зона):")
        print("-"*80)
        if len(df) >= 20:
            print(df.iloc[16:20].to_string(max_colwidth=30))
        
        print("\n" + "="*80)
        print("✅ ГОТОВО!")
        print("="*80)
    else:
        print("\n❌ Не удалось извлечь данные")

