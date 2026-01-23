#!/usr/bin/env python3
"""
Финальный скрипт обработки VBK документа (Разделы II и III)
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.vbk_hybrid_parser import VBKHybridParser


if __name__ == '__main__':
    pdf_path = "input/VBK16040002_1971_0019_9_1_2216_0008_20251111_большая.pdf"
    
    # Создаем output директорию
    output_dir = Path("output/finance")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*80)
    print("🚀 ОБРАБОТКА VBK ДОКУМЕНТА")
    print("="*80)
    print()
    
    # ========== РАЗДЕЛ II ==========
    print("📊 РАЗДЕЛ II: Операции по контракту")
    print("-"*80)
    print()
    
    parser_section2 = VBKHybridParser(pdf_path, section="II")
    df_section2 = parser_section2.parse()
    
    if not df_section2.empty:
        output_path_2 = output_dir / "VBK_Раздел_II_финальный.xlsx"
        parser_section2.save_to_excel(df_section2, str(output_path_2))
        
        print()
        print(f"📊 Итого Раздел II: {len(df_section2)} записей")
        print()
    else:
        print("❌ Раздел II: не удалось извлечь данные")
        print()
    
    # ========== РАЗДЕЛ III ==========
    print()
    print("="*80)
    print("📊 РАЗДЕЛ III: Подтверждающие документы")
    print("-"*80)
    print()
    
    parser_section3 = VBKHybridParser(pdf_path, section="III")
    df_section3 = parser_section3.parse()
    
    if not df_section3.empty:
        output_path_3 = output_dir / "VBK_Раздел_III_финальный.xlsx"
        parser_section3.save_to_excel(df_section3, str(output_path_3))
        
        print()
        print(f"📊 Итого Раздел III: {len(df_section3)} записей")
        print()
    else:
        print("❌ Раздел III: не удалось извлечь данные")
        print()
    
    # ========== ИТОГОВЫЙ ОТЧЕТ ==========
    print()
    print("="*80)
    print("✅ ОБРАБОТКА ЗАВЕРШЕНА")
    print("="*80)
    print()
    
    if not df_section2.empty:
        print(f"✅ Раздел II:  {len(df_section2):3d} записей → {output_dir}/VBK_Раздел_II_финальный.xlsx")
    
    if not df_section3.empty:
        print(f"✅ Раздел III: {len(df_section3):3d} записей → {output_dir}/VBK_Раздел_III_финальный.xlsx")
    
    print()
    print("="*80)
    print("💡 СЛЕДУЮЩИЕ ШАГИ:")
    print("="*80)
    print("  1. Проверьте файлы Excel на корректность данных")
    print("  2. Убедитесь, что многострочные текстовые поля полные")
    print("  3. Проверьте финансовые форматы (должны быть с двумя знаками)")
    print()

