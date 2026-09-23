"""
Анализ структуры Markdown от Marker
"""

from pathlib import Path
import re

def analyze_markdown():
    """Анализируем структуру Markdown от Marker"""
    
    md_path = Path("/home/budnik_an/Obligations/output/finance_marker/Выпуск 4-02 на 16.06.2020/Выпуск 4-02 на 16.06.2020.md")
    
    print("="*80)
    print("📊 АНАЛИЗ MARKDOWN ОТ MARKER")
    print("="*80)
    print()
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"Размер: {len(content):,} символов")
    print(f"Строк: {content.count(chr(10)):,}")
    print()
    
    # Ищем записи владельцев
    print("🔍 ПОИСК ПАТТЕРНОВ:")
    print("-"*80)
    
    # Паттерн 1: Имена (прописные с отчеством)
    names = re.findall(r'([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)', content)
    print(f"Найдено ФИО: {len(names)}")
    if names:
        print("Примеры:")
        for name in list(set(names))[:5]:
            print(f"  • {name}")
    print()
    
    # Паттерн 2: Адреса с почтовыми индексами
    addresses = re.findall(r'\d{6}[^\n]{20,100}', content)
    print(f"Найдено адресов с индексами: {len(addresses)}")
    if addresses:
        print("Примеры:")
        for addr in addresses[:3]:
            print(f"  • {addr[:80]}...")
    print()
    
    # Паттерн 3: Количество (числа + слово "штука")
    quantities = re.findall(r'(\d+)\s*(?:штук|пятьдесят|тысяч)', content)
    print(f"Найдено количеств: {len(quantities)}")
    if quantities:
        print("Примеры:", quantities[:10])
    print()
    
    # Паттерн 4: ISIN коды
    isins = re.findall(r'(RU[A-Z0-9]{10})', content)
    print(f"Найдено ISIN кодов: {len(isins)}")
    if isins:
        print("Примеры:", list(set(isins))[:5])
    print()
    
    # Паттерн 5: Документы (паспорта, ОГРН)
    passports = re.findall(r'\b(\d{4}\s*\d{6})\b', content)
    print(f"Найдено паспортов: {len(passports)}")
    if passports:
        print("Примеры:", passports[:5])
    print()
    
    ogrns = re.findall(r'\b(10\d{11,12}|1\d{12})\b', content)
    print(f"Найдено ОГРН: {len(ogrns)}")
    if ogrns:
        print("Примеры:", list(set(ogrns))[:5])
    print()
    
    # Показываем фрагмент с записью
    print("="*80)
    print("📄 ФРАГМЕНТ ДОКУМЕНТА (запись владельца)")
    print("="*80)
    print()
    
    # Ищем первую запись с именем Шапран
    match = re.search(r'(Шапран Александр Александрович.*?)(?=Код, присвоенный|$)', content, re.DOTALL)
    if match:
        fragment = match.group(1)[:1000]
        print(fragment)
        print("\n...")

if __name__ == "__main__":
    analyze_markdown()

