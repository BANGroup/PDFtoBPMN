#!/usr/bin/env python3
"""
Запуск chunk_parser для Выпуск 4-02 на 16.06.2020
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.finance_parser.chunk_parser_4_02 import ChunkParser

def main():
    pdf_path = "input/Finance/Выпуск 4-02 на 16.06.2020.pdf"
    output_path = "output/finance/Выпуск_4-02_на_16.06.2020.xlsx"
    
    print("🔄 Запуск ChunkParser для Выпуск 4-02...")
    print(f"📄 PDF: {pdf_path}")
    print(f"📊 Output: {output_path}")
    print()
    
    parser = ChunkParser()
    records = parser.parse(pdf_path)
    
    print(f"✅ Извлечено записей: {len(records)}")
    print()
    
    # Статистика заполненности
    filled_qty = sum(1 for r in records if r.quantity)
    filled_fio = sum(1 for r in records if r.full_name)
    filled_addr = sum(1 for r in records if r.address)
    filled_doc = sum(1 for r in records if r.document_number)
    filled_acc = sum(1 for r in records if r.account_number)
    
    total = len(records)
    
    print("📊 СТАТИСТИКА ЗАПОЛНЕННОСТИ:")
    print(f"  Количество:  {filled_qty}/{total} ({filled_qty/total*100:.1f}%)")
    print(f"  ФИО:         {filled_fio}/{total} ({filled_fio/total*100:.1f}%)")
    print(f"  Адрес:       {filled_addr}/{total} ({filled_addr/total*100:.1f}%)")
    print(f"  Документ:    {filled_doc}/{total} ({filled_doc/total*100:.1f}%)")
    print(f"  Номер счета: {filled_acc}/{total} ({filled_acc/total*100:.1f}%)")
    print()
    
    # Сохраняем
    parser.save_to_excel(records, output_path)
    print(f"💾 Сохранено в {output_path}")
    
    # Итоговая сумма
    total_bonds = sum(r.quantity for r in records if r.quantity)
    print()
    print(f"📈 ИТОГО облигаций: {total_bonds:,}")
    print(f"   Эталон (СОВОКУПНЫЕ ДАННЫЕ): 9,179,259")
    print(f"   Разница: {9179259 - total_bonds:,} ({(9179259-total_bonds)/9179259*100:+.2f}%)")

if __name__ == "__main__":
    main()

