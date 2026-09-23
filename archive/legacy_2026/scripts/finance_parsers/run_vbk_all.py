#!/usr/bin/env python3
"""
Запуск всех парсеров для VBK документа (Разделы II и III)
"""

import sys
from pathlib import Path

# Добавляем корневую папку проекта в путь
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.vbk_section2_parser import VBKSection2Parser
from scripts.finance_parser.vbk_section3_parser import VBKSection3Parser


if __name__ == '__main__':
    pdf_path = "input/VBK16040002_1971_0019_9_1_2216_0008_20251111_большая.pdf"
    
    print("="*80)
    print("🚀 ЗАПУСК ВСЕХ ПАРСЕРОВ VBK ДОКУМЕНТА")
    print("="*80)
    print()
    
    # ========== РАЗДЕЛ II ==========
    print("📊 1. ОБРАБОТКА РАЗДЕЛА II (Сведения о платежах)")
    print("-"*80)
    
    output_path_2 = "output/finance/VBK_Раздел_II.xlsx"
    Path(output_path_2).parent.mkdir(parents=True, exist_ok=True)
    
    parser2 = VBKSection2Parser(pdf_path)
    df2 = parser2.parse()
    
    if not df2.empty:
        parser2.save_to_excel(df2, output_path_2)
        print(f"\n✅ Раздел II готов: {len(df2)} строк, {len(df2.columns)} колонок")
    else:
        print("\n❌ Раздел II: не удалось извлечь данные")
    
    print()
    print("="*80)
    print()
    
    # ========== РАЗДЕЛ III ==========
    print("📊 2. ОБРАБОТКА РАЗДЕЛА III (Сведения о подтверждающих документах)")
    print("-"*80)
    
    output_path_3 = "output/finance/VBK_Раздел_III.xlsx"
    Path(output_path_3).parent.mkdir(parents=True, exist_ok=True)
    
    parser3 = VBKSection3Parser(pdf_path)
    df3 = parser3.parse()
    
    if not df3.empty:
        parser3.save_to_excel(df3, output_path_3)
        print(f"\n✅ Раздел III готов: {len(df3)} строк, {len(df3.columns)} колонок")
    else:
        print("\n❌ Раздел III: не удалось извлечь данные")
    
    # ========== ИТОГОВАЯ СТАТИСТИКА ==========
    print()
    print("="*80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*80)
    print()
    
    print(f"📄 Исходный файл: {pdf_path}")
    print()
    
    print("📁 Созданные файлы:")
    print()
    
    if not df2.empty:
        print(f"  1️⃣ VBK_Раздел_II.xlsx")
        print(f"     • Строк: {len(df2):,}")
        print(f"     • Колонок: {len(df2.columns)}")
        print(f"     • Страницы: 3-11")
        print(f"     • Финансовые колонки: {len(parser2.financial_columns)}")
        for col in parser2.financial_columns:
            print(f"       - {col}")
        print()
    
    if not df3.empty:
        print(f"  2️⃣ VBK_Раздел_III.xlsx")
        print(f"     • Строк: {len(df3):,}")
        print(f"     • Колонок: {len(df3.columns)}")
        print(f"     • Страницы: 12-61")
        print(f"     • Финансовые колонки: {len(parser3.financial_columns)}")
        for col in parser3.financial_columns:
            print(f"       - {col}")
        print()
    
    total_rows = len(df2) + len(df3) if (not df2.empty and not df3.empty) else 0
    if total_rows > 0:
        print(f"📈 ИТОГО извлечено строк: {total_rows:,}")
    
    print()
    print("="*80)
    print("✅ ВСЕ ПАРСЕРЫ ЗАВЕРШЕНЫ!")
    print("="*80)

