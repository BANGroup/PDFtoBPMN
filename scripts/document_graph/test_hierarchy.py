#!/usr/bin/env python3
"""
Тестирование hierarchy_builder на документах из output3/hybrid_parser_test/
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.document_graph.hierarchy_builder import (
    build_hierarchy,
    print_tree_stats,
    export_tree_json,
    export_tree_markdown,
    flatten_tree,
    get_nodes_by_level,
)


def test_hierarchy_on_documents(input_dir: Path, output_dir: Path):
    """
    Прогон hierarchy_builder на тестовых документах
    """
    results_dir = input_dir / "results"
    if not results_dir.exists():
        print(f"❌ Директория не найдена: {results_dir}")
        return
    
    # Создаём выходную директорию
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("   ТЕСТИРОВАНИЕ HIERARCHY BUILDER")
    print("=" * 60)
    print()
    
    # Находим все документы
    doc_dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])
    
    total_stats = {
        "documents": 0,
        "total_sections": 0,
        "max_depth_overall": 0,
        "actionable_total": 0,
        "by_level": {},
    }
    
    for doc_dir in doc_dirs:
        parse_result = doc_dir / "parse_result.json"
        if not parse_result.exists():
            continue
        
        print(f"\n📄 {doc_dir.name}")
        print("-" * 40)
        
        # Загружаем parse_result.json
        with open(parse_result, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        headings = data.get("headings", [])
        doc_code = data.get("doc_code", doc_dir.name)
        source = data.get("source", "pdf")
        
        print(f"   Заголовков в исходнике: {len(headings)}")
        
        # Строим иерархию
        tree = build_hierarchy(headings, doc_code=doc_code, source=source)
        
        # Статистика
        print_tree_stats(tree)
        
        # Обновляем общую статистику
        total_stats["documents"] += 1
        total_stats["total_sections"] += tree.total_sections
        total_stats["max_depth_overall"] = max(total_stats["max_depth_overall"], tree.max_depth)
        total_stats["actionable_total"] += tree.actionable_sections
        
        for level in range(tree.max_depth + 1):
            nodes = get_nodes_by_level(tree.root, level)
            total_stats["by_level"][level] = total_stats["by_level"].get(level, 0) + len(nodes)
        
        # Сохраняем результаты
        doc_output_dir = output_dir / doc_dir.name
        doc_output_dir.mkdir(exist_ok=True)
        
        export_tree_json(tree, doc_output_dir / "structure_tree.json")
        export_tree_markdown(tree, doc_output_dir / "structure_tree.md")
        
        # Показываем первые несколько узлов дерева
        nodes = flatten_tree(tree.root)[:10]
        if nodes:
            print("\n   Первые 10 узлов:")
            for node in nodes:
                indent = "  " * node.level
                marker = "📌" if node.is_actionable else "📄"
                print(f"   {indent}{marker} [{node.level}] {node.num} {node.title[:30]}...")
    
    # Итоговая статистика
    print("\n")
    print("=" * 60)
    print("   ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 60)
    print(f"\n📊 Обработано документов: {total_stats['documents']}")
    print(f"   Всего разделов: {total_stats['total_sections']}")
    print(f"   Макс. глубина: {total_stats['max_depth_overall']}")
    print(f"   Actionable разделов: {total_stats['actionable_total']}")
    print("\n   По уровням:")
    for level in sorted(total_stats["by_level"].keys()):
        print(f"     Level {level}: {total_stats['by_level'][level]} узлов")
    
    # Сохраняем общую статистику
    stats_file = output_dir / "statistics.json"
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(total_stats, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Результаты сохранены в: {output_dir}")
    print(f"   📁 {len(doc_dirs)} папок с structure_tree.json")
    print(f"   📊 statistics.json")


if __name__ == "__main__":
    input_dir = Path("/home/budnik_an/Obligations/output3/hybrid_parser_test")
    output_dir = Path("/home/budnik_an/Obligations/output3/hierarchy_test")
    
    test_hierarchy_on_documents(input_dir, output_dir)
