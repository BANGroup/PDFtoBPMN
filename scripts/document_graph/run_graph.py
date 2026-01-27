#!/usr/bin/env python3
"""
Скрипт построения графа документов СМК

Использование (из корня проекта):
    python scripts/document_graph/run_graph.py
    python scripts/document_graph/run_graph.py --input input2/BND/pdf
    python scripts/document_graph/run_graph.py --output output/my_graph
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.document_graph.graph_builder import DocumentGraphBuilder


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Построение графа документов СМК")
    parser.add_argument('--input', '-i', 
                       default='input2/BND/pdf',
                       help='Папка с документами (default: input2/BND/pdf)')
    parser.add_argument('--output', '-o',
                       default='output/document_graph', 
                       help='Папка для результатов (default: output/document_graph)')
    
    args = parser.parse_args()
    
    input_path = PROJECT_ROOT / args.input
    output_path = PROJECT_ROOT / args.output
    
    print("=" * 60)
    print("📊 ПОСТРОЕНИЕ ГРАФА ДОКУМЕНТОВ СМК")
    print("=" * 60)
    print(f"\n📁 Источник: {input_path}")
    print(f"📂 Результат: {output_path}")
    print()
    
    if not input_path.exists():
        print(f"❌ Папка не найдена: {input_path}")
        return 1
    
    # Строим граф
    builder = DocumentGraphBuilder()
    
    print("🔍 Сканирование документов...")
    count = builder.scan_folder(input_path)
    print(f"   Найдено: {count} документов")
    
    if count == 0:
        print("⚠️ Документы не найдены")
        return 1
    
    # Ищем xlsx каталог и docx папку
    xlsx_catalog = None
    docx_base = None
    
    # Автопоиск xlsx каталога
    xlsx_files = list(input_path.parent.glob("*.xlsx"))
    if xlsx_files:
        xlsx_catalog = xlsx_files[0]
    
    # Автопоиск docx папки
    docx_folder = input_path.parent / "docx"
    if docx_folder.exists():
        docx_base = docx_folder
    
    # Извлекаем метаданные из всех источников
    print("\n📖 Извлечение метаданных...")
    extracted = builder.extract_metadata(
        docx_base_path=docx_base,
        xlsx_catalog_path=xlsx_catalog
    )
    print(f"   Обработано: {extracted} документов")
    
    print("\n🔨 Построение графа...")
    graph = builder.build_graph()
    print(f"   Узлов: {len(graph.nodes)}")
    print(f"   Связей: {len(graph.edges)}")
    
    # Экспорт
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("\n💾 Экспорт...")
    
    json_path = builder.export_json(output_path / "graph_data.json")
    print(f"   ✅ JSON: {json_path}")
    
    html_path = builder.export_html(output_path / "graph_viewer.html")
    print(f"   ✅ HTML: {html_path}")
    
    # Статистика
    stats = graph.metadata.get('statistics', {})
    
    print("\n" + "=" * 60)
    print("📈 СТАТИСТИКА")
    print("=" * 60)
    
    if stats.get('by_group'):
        print("\n🏷️ По группам процессов:")
        for group, cnt in sorted(stats['by_group'].items(), key=lambda x: -x[1]):
            bar = "█" * (cnt // 5) + "░" * (20 - cnt // 5)
            print(f"   {group[:30]:<30} {bar} {cnt}")
    
    if stats.get('by_type'):
        print("\n📋 По типам документов:")
        for doc_type, cnt in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
            bar = "█" * (cnt // 3) + "░" * (20 - cnt // 3)
            print(f"   {doc_type[:30]:<30} {bar} {cnt}")
    
    if stats.get('by_process'):
        print("\n🔝 Топ-10 процессов:")
        top_processes = sorted(stats['by_process'].items(), key=lambda x: -x[1])[:10]
        for i, (process, cnt) in enumerate(top_processes, 1):
            bar = "█" * (cnt // 2) + "░" * (20 - cnt // 2)
            print(f"   {i:2}. {process:<10} {bar} {cnt}")
    
    # Статистика по ссылкам
    refs_edges = [e for e in graph.edges if e.edge_type == "references"]
    if refs_edges:
        print(f"\n🔗 Ссылки между документами: {len(refs_edges)}")
    
    print("\n" + "=" * 60)
    print("🎉 ГОТОВО!")
    print("=" * 60)
    print(f"\n🌐 Откройте в браузере:")
    print(f"   file://{html_path.absolute()}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
