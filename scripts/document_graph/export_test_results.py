#!/usr/bin/env python3
"""
Экспорт результатов тестирования гибридного парсера в структурированный формат
"""

import sys
import shutil
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.document_graph.hybrid_parser import (
    parse_document,
    format_parse_report,
)
from scripts.document_graph.hierarchy_builder import export_tree_json
from scripts.document_graph.test_hybrid_parser import find_test_documents


def export_test_results(base_dir: Path, output_dir: Path, count: int = 8):
    """
    Экспортировать результаты тестов в структурированном виде
    
    Структура output_dir:
    ├── sources/           # Исходные PDF файлы (ссылки или копии)
    │   ├── 01_КД-ДП-М1.046-02.pdf
    │   └── ...
    ├── results/           # Детальные результаты по каждому документу
    │   ├── 01_КД-ДП-М1.046-02/
    │   │   ├── parse_result.json
    │   │   └── report.txt
    │   └── ...
    ├── reports/           # Сводные отчёты
    │   ├── summary.txt
    │   └── statistics.json
    └── README.md          # Описание структуры
    """
    
    # Создаём директории
    sources_dir = output_dir / "sources"
    results_dir = output_dir / "results"
    reports_dir = output_dir / "reports"
    
    for d in [sources_dir, results_dir, reports_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Экспорт результатов в {output_dir}")
    print()
    
    # Находим тестовые документы
    test_docs = find_test_documents(base_dir, count)
    
    if not test_docs:
        print("❌ Тестовые документы не найдены")
        return
    
    print(f"✅ Найдено {len(test_docs)} документов")
    
    # DOCX директория
    docx_dir = base_dir / "docx"
    docx_base = str(docx_dir) if docx_dir.exists() else None
    
    # Статистика
    stats = {
        "timestamp": datetime.now().isoformat(),
        "total_documents": len(test_docs),
        "docx_used": 0,
        "pdf_used": 0,
        "filter_stats": {
            "total_blocks": 0,
            "after_filtering": 0,
            "by_repeat": 0,
            "by_blacklist": 0,
            "by_pattern": 0,
        },
        "documents": []
    }
    
    all_reports = []
    
    # Обрабатываем каждый документ
    for i, pdf_path in enumerate(test_docs, 1):
        doc_code = pdf_path.stem.split()[0].replace("(", "").replace(")", "")
        prefix = f"{i:02d}_{doc_code}"
        
        print(f"\n[{i}/{len(test_docs)}] {doc_code}...")
        
        # 1. Создаём симлинк на источник
        source_link = sources_dir / f"{prefix}.pdf"
        if source_link.exists():
            source_link.unlink()
        source_link.symlink_to(pdf_path.resolve())
        
        # 2. Парсим документ
        try:
            result = parse_document(str(pdf_path), docx_base)
            
            # 3. Создаём папку для результатов
            result_dir = results_dir / prefix
            result_dir.mkdir(exist_ok=True)
            
            # 3.1 Копируем исходный PDF в папку результата
            local_pdf = result_dir / f"source.pdf"
            if not local_pdf.exists():
                shutil.copy2(pdf_path, local_pdf)
            
            # 3.2 Копируем DOCX если есть
            if result.docx_path:
                docx_src = Path(result.docx_path)
                if docx_src.exists():
                    local_docx = result_dir / f"source.docx"
                    if not local_docx.exists():
                        shutil.copy2(docx_src, local_docx)
            
            # 4. Сохраняем JSON с результатом
            result_json = {
                "doc_code": result.doc_code,
                "source": result.source,
                "headings_count": len(result.headings),
                "headings": [{"text": h.text, "level": h.level} for h in result.headings],
                "pdf_path": str(pdf_path),
                "docx_path": result.docx_path or None,
                "validation": {
                    "is_valid": result.validation.is_valid if result.validation else None,
                    "details": result.validation.details if result.validation else None,
                } if result.validation else None,
                "filter_report": result.filter_report,
            }
            
            with open(result_dir / "parse_result.json", "w", encoding="utf-8") as f:
                json.dump(result_json, f, ensure_ascii=False, indent=2)
            
            # 4.1 Сохраняем иерархическую структуру
            if result.structure_tree:
                export_tree_json(result.structure_tree, result_dir / "structure_tree.json")
            
            # 5. Сохраняем текстовый отчёт
            report = format_parse_report(result)
            with open(result_dir / "report.txt", "w", encoding="utf-8") as f:
                f.write(report)
            
            all_reports.append(report)
            
            # 6. Сохраняем MD с результатом парсинга (контент документа)
            md_lines = [
                f"# {result.doc_code or doc_code}",
                "",
                f"**Источник:** {result.source.upper()}",
                f"**Заголовков:** {len(result.headings)}",
                "",
            ]
            
            if result.validation:
                md_lines.extend([
                    "## Валидация DOCX",
                    "",
                    f"- Результат: {'✅ Актуален' if result.validation.is_valid else '❌ Не актуален'}",
                    f"- Детали: {result.validation.details}",
                    "",
                ])
            
            if result.filter_report:
                fr = result.filter_report
                md_lines.extend([
                    "## Фильтрация",
                    "",
                    f"| Метрика | Значение |",
                    f"|---------|----------|",
                    f"| Блоков до | {fr.get('total_blocks', 0)} |",
                    f"| Блоков после | {fr.get('after_filtering', 0)} |",
                    f"| По повторам | {len(fr.get('by_repeat', []))} |",
                    f"| По blacklist | {len(fr.get('by_blacklist', []))} |",
                    f"| По паттернам | {len(fr.get('by_pattern', []))} |",
                    "",
                ])
            
            # Иерархическая структура
            if result.structure_tree:
                tree = result.structure_tree
                md_lines.extend([
                    "## Иерархическая структура",
                    "",
                    f"| Метрика | Значение |",
                    f"|---------|----------|",
                    f"| Разделов | {tree.total_sections} |",
                    f"| Макс. глубина | {tree.max_depth} |",
                    f"| Actionable | {tree.actionable_sections} |",
                    f"| RACI статус | {tree.raci_status} |",
                    "",
                    "### Дерево документа",
                    "",
                ])
                
                # Рекурсивный вывод дерева
                def render_tree(node, indent=0):
                    lines = []
                    if node.id != "root":
                        prefix = "  " * indent
                        marker = "📌" if node.is_actionable else "📄"
                        num_part = f"**{node.num}** " if node.num else ""
                        title_short = node.title[:60] + "..." if len(node.title) > 60 else node.title
                        lines.append(f"{prefix}- {marker} {num_part}{title_short}")
                    for child in node.children[:50]:  # Лимит на children
                        lines.extend(render_tree(child, indent + 1))
                    return lines
                
                tree_lines = render_tree(tree.root)
                md_lines.extend(tree_lines[:200])  # Лимит на общее количество
                
                if len(tree_lines) > 200:
                    md_lines.append(f"\n*... и ещё {len(tree_lines) - 200} узлов*")
            else:
                # Fallback: плоский список если нет дерева
                md_lines.extend([
                    "## Структура документа",
                    "",
                ])
                
                if result.filter_report and result.filter_report.get("kept_important"):
                    md_lines.append("### Важные разделы")
                    md_lines.append("")
                    for h in result.filter_report["kept_important"][:20]:
                        md_lines.append(f"- {h}")
                    md_lines.append("")
                
                md_lines.append("### Заголовки")
                md_lines.append("")
                for h in result.headings[:50]:
                    prefix = "#" * min(h.level, 4)
                    md_lines.append(f"{prefix} {h.text}")
                    md_lines.append("")
                
                if len(result.headings) > 50:
                    md_lines.append(f"*... и ещё {len(result.headings) - 50} заголовков*")
            
            with open(result_dir / "structure.md", "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))
            
            # 7. Обновляем статистику
            doc_stats = {
                "code": result.doc_code or doc_code,
                "source": result.source,
                "headings": len(result.headings),
            }
            
            if result.source == "docx":
                stats["docx_used"] += 1
            else:
                stats["pdf_used"] += 1
                
                if result.filter_report:
                    fr = result.filter_report
                    stats["filter_stats"]["total_blocks"] += fr.get("total_blocks", 0)
                    stats["filter_stats"]["after_filtering"] += fr.get("after_filtering", 0)
                    stats["filter_stats"]["by_repeat"] += len(fr.get("by_repeat", []))
                    stats["filter_stats"]["by_blacklist"] += len(fr.get("by_blacklist", []))
                    stats["filter_stats"]["by_pattern"] += len(fr.get("by_pattern", []))
                    
                    doc_stats["filtered"] = {
                        "total": fr.get("total_blocks", 0),
                        "kept": fr.get("after_filtering", 0),
                        "by_repeat": len(fr.get("by_repeat", [])),
                        "by_blacklist": len(fr.get("by_blacklist", [])),
                        "by_pattern": len(fr.get("by_pattern", [])),
                    }
            
            stats["documents"].append(doc_stats)
            
            print(f"   ✅ {result.source.upper()}: {len(result.headings)} заголовков")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            stats["documents"].append({
                "code": doc_code,
                "error": str(e),
            })
    
    # Сохраняем сводные отчёты
    print("\n📊 Сохранение сводных отчётов...")
    
    # 1. statistics.json
    with open(reports_dir / "statistics.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # 2. summary.txt
    summary_lines = [
        "=" * 70,
        "   СВОДНЫЙ ОТЧЁТ ПО ТЕСТИРОВАНИЮ ГИБРИДНОГО ПАРСЕРА",
        "=" * 70,
        "",
        f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Источник: {base_dir}",
        "",
        "=" * 70,
        "   СТАТИСТИКА",
        "=" * 70,
        "",
        f"📊 Всего документов: {stats['total_documents']}",
        f"   📄 DOCX использован: {stats['docx_used']}",
        f"   📕 PDF (fallback): {stats['pdf_used']}",
        "",
        f"🗑️ Отфильтровано:",
        f"   Всего блоков до фильтрации: {stats['filter_stats']['total_blocks']}",
        f"   После фильтрации: {stats['filter_stats']['after_filtering']}",
        f"   Удалено: {stats['filter_stats']['total_blocks'] - stats['filter_stats']['after_filtering']}",
        "",
        f"   По фильтру повторов (>50%): {stats['filter_stats']['by_repeat']} уникальных паттернов",
        f"   По чёрному списку: {stats['filter_stats']['by_blacklist']} совпадений",
        f"   По regex-паттернам: {stats['filter_stats']['by_pattern']} совпадений",
        "",
        "=" * 70,
        "   ДОКУМЕНТЫ",
        "=" * 70,
        "",
    ]
    
    for doc in stats["documents"]:
        if "error" in doc:
            summary_lines.append(f"❌ {doc['code']}: ОШИБКА - {doc['error']}")
        else:
            source_icon = "📄" if doc["source"] == "docx" else "📕"
            summary_lines.append(f"{source_icon} {doc['code']}: {doc['headings']} заголовков ({doc['source'].upper()})")
            if "filtered" in doc:
                f = doc["filtered"]
                summary_lines.append(f"   Блоков: {f['total']} → {f['kept']} (фильтр: повторы={f['by_repeat']}, blacklist={f['by_blacklist']}, pattern={f['by_pattern']})")
    
    summary_lines.extend([
        "",
        "=" * 70,
        "   ДЕТАЛЬНЫЕ ОТЧЁТЫ",
        "=" * 70,
        "",
    ])
    
    for report in all_reports:
        summary_lines.append(report)
        summary_lines.append("\n")
    
    with open(reports_dir / "summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))
    
    # 3. README.md
    readme = f"""# Результаты тестирования гибридного парсера

**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Структура

```
output3/hybrid_parser_test/
├── sources/           # Символические ссылки на исходные PDF файлы
├── results/           # Детальные результаты по каждому документу
│   └── NN_DOC-CODE/
│       ├── source.pdf          # Копия исходного PDF (для сравнения)
│       ├── source.docx         # Копия DOCX если есть (для сравнения)
│       ├── parse_result.json   # Структурированный результат парсинга
│       ├── report.txt          # Текстовый отчёт о фильтрации
│       └── structure.md        # Структура документа в Markdown
└── reports/           # Сводные отчёты
    ├── summary.txt             # Полный сводный отчёт
    └── statistics.json         # Статистика в JSON
```

## Статистика

| Метрика | Значение |
|---------|----------|
| Всего документов | {stats['total_documents']} |
| DOCX использован | {stats['docx_used']} |
| PDF (fallback) | {stats['pdf_used']} |
| Блоков до фильтрации | {stats['filter_stats']['total_blocks']} |
| Блоков после фильтрации | {stats['filter_stats']['after_filtering']} |

## Фильтрация

| Фильтр | Срабатываний |
|--------|--------------|
| Повторы (>50% страниц) | {stats['filter_stats']['by_repeat']} |
| Чёрный список | {stats['filter_stats']['by_blacklist']} |
| Regex-паттерны | {stats['filter_stats']['by_pattern']} |

## Документы

| # | Код | Источник | Заголовков |
|---|-----|----------|------------|
"""
    
    for i, doc in enumerate(stats["documents"], 1):
        if "error" in doc:
            readme += f"| {i} | {doc['code']} | ❌ ОШИБКА | - |\n"
        else:
            readme += f"| {i} | {doc['code']} | {doc['source'].upper()} | {doc['headings']} |\n"
    
    with open(output_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(readme)
    
    print(f"\n✅ Экспорт завершён: {output_dir}")
    print(f"   📁 sources/: {len(test_docs)} файлов")
    print(f"   📁 results/: {len(test_docs)} папок")
    print(f"   📁 reports/: summary.txt, statistics.json")
    print(f"   📄 README.md")


if __name__ == "__main__":
    base_dir = Path("/home/budnik_an/Obligations/input2/BND")
    output_dir = Path("/home/budnik_an/Obligations/output3/hybrid_parser_test")
    
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    
    export_test_results(base_dir, output_dir, count)
