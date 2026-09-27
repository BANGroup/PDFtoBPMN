#!/usr/bin/env python3
"""
Тестирование гибридного парсера на выборке документов

Выводит детальный отчёт:
- Источник (DOCX или PDF)
- Что выкинуто по каждому фильтру
- Что сохранено
"""

import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.document_graph.hybrid_parser import (
    parse_document,
    format_parse_report,
)


def find_test_documents(base_dir: Path, count: int = 10) -> list:
    """
    Найти тестовые документы разных типов
    
    Приоритет:
    - КД (корпоративные документы)
    - ДП (документированные процедуры)
    - ИОТ (инструкции по охране труда)
    - РД, РГ, РИ, СТ
    """
    pdf_dir = base_dir / "pdf"
    
    if not pdf_dir.exists():
        print(f"❌ Директория не найдена: {pdf_dir}")
        return []
    
    # Группируем по типу
    by_type = {
        "КД": [],
        "ДП": [],
        "ИОТ": [],
        "РД": [],
        "РГ": [],
        "РИ": [],
        "СТ": [],
    }
    
    for folder in pdf_dir.iterdir():
        if not folder.is_dir():
            continue
        
        # Находим PDF в папке
        pdfs = list(folder.glob("*.pdf"))
        if not pdfs:
            continue
        
        pdf_path = pdfs[0]
        folder_name = folder.name
        
        # Определяем тип
        for doc_type in by_type.keys():
            if folder_name.startswith(doc_type) or f"-{doc_type}-" in folder_name:
                by_type[doc_type].append(pdf_path)
                break
    
    # Формируем выборку с приоритетом
    result = []
    
    # Приоритет для разнообразия типов
    priority_order = ["КД", "ДП", "ИОТ", "РД", "РГ", "РИ", "СТ"]
    
    for doc_type in priority_order:
        docs = by_type[doc_type]
        if docs and len(result) < count:
            # Берём максимум 2-3 документа каждого типа
            take = min(3, count - len(result), len(docs))
            result.extend(docs[:take])
    
    return result[:count]


def run_test(base_dir: Path, count: int = 10):
    """Запуск теста"""
    
    print("=" * 70)
    print("   ТЕСТ ГИБРИДНОГО ПАРСЕРА ДОКУМЕНТОВ")
    print("=" * 70)
    print()
    
    # Находим тестовые документы
    print(f"🔍 Поиск тестовых документов в {base_dir}...")
    test_docs = find_test_documents(base_dir, count)
    
    if not test_docs:
        print("❌ Тестовые документы не найдены")
        return
    
    print(f"✅ Найдено {len(test_docs)} документов для теста")
    print()
    
    # Определяем папку с DOCX
    docx_dir = base_dir / "docx"
    docx_base = str(docx_dir) if docx_dir.exists() else None
    
    if docx_base:
        print(f"📁 Папка DOCX: {docx_dir}")
    else:
        print("⚠️ Папка DOCX не найдена, будет использован только PDF")
    print()
    
    # Статистика
    stats = {
        "total": len(test_docs),
        "docx_used": 0,
        "pdf_used": 0,
        "total_filtered": 0,
        "by_repeat": 0,
        "by_blacklist": 0,
        "by_pattern": 0,
    }
    
    # Парсим каждый документ
    for i, pdf_path in enumerate(test_docs, 1):
        print(f"\n[{i}/{len(test_docs)}] Парсинг: {pdf_path.stem[:50]}...")
        
        try:
            result = parse_document(str(pdf_path), docx_base)
            
            # Выводим отчёт
            report = format_parse_report(result)
            print(report)
            
            # Обновляем статистику
            if result.source == "docx":
                stats["docx_used"] += 1
            else:
                stats["pdf_used"] += 1
                
                if result.filter_report:
                    fr = result.filter_report
                    stats["by_repeat"] += len(fr.get("by_repeat", []))
                    stats["by_blacklist"] += len(fr.get("by_blacklist", []))
                    stats["by_pattern"] += len(fr.get("by_pattern", []))
                    stats["total_filtered"] += (
                        fr.get("total_blocks", 0) - fr.get("after_filtering", 0)
                    )
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    # Итоговая статистика
    print("\n")
    print("=" * 70)
    print("   ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 70)
    print()
    print(f"📊 Всего документов: {stats['total']}")
    print(f"   📄 DOCX использован: {stats['docx_used']}")
    print(f"   📕 PDF (fallback): {stats['pdf_used']}")
    print()
    print(f"🗑️ Отфильтровано блоков всего: {stats['total_filtered']}")
    print(f"   По повторам (>50%): {stats['by_repeat']}")
    print(f"   По чёрному списку: {stats['by_blacklist']}")
    print(f"   По паттернам: {stats['by_pattern']}")


if __name__ == "__main__":
    # По умолчанию - input2/BND
    default_base = Path("/home/budnik_an/Obligations/input2/BND")
    
    if len(sys.argv) > 1:
        base_dir = Path(sys.argv[1])
    else:
        base_dir = default_base
    
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    run_test(base_dir, count)
