#!/usr/bin/env python3
"""
CLI для системы графа документов СМК

Использование:
    python -m scripts.document_graph.cli scan --input input2/BND/pdf --output output/document_graph
    python -m scripts.document_graph.cli scan --input input2/BND/pdf --output output/document_graph --format html
    python -m scripts.document_graph.cli scan --input input2/BND/pdf --output output/document_graph --format json
"""

import argparse
import sys
from pathlib import Path


def cmd_scan(args):
    """Команда сканирования и построения графа"""
    from .graph_builder import DocumentGraphBuilder
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"❌ Папка не найдена: {input_path}")
        return 1
    
    print(f"📁 Сканирование: {input_path}")
    
    builder = DocumentGraphBuilder()
    count = builder.scan_folder(input_path)
    
    print(f"📄 Найдено документов: {count}")
    
    if count == 0:
        print("⚠️ Документы не найдены")
        return 1
    
    # Строим граф
    print("🔨 Построение графа...")
    graph = builder.build_graph()
    
    print(f"📊 Узлов: {len(graph.nodes)}, Связей: {len(graph.edges)}")
    
    # Создаем output папку
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Экспортируем
    if args.format in ['json', 'all']:
        json_path = output_path / "graph_data.json"
        builder.export_json(json_path)
        print(f"✅ JSON: {json_path}")
    
    if args.format in ['html', 'all']:
        html_path = output_path / "graph_viewer.html"
        builder.export_html(html_path)
        print(f"✅ HTML: {html_path}")
    
    # Статистика
    stats = graph.metadata.get('statistics', {})
    
    print("\n📈 Статистика:")
    print("=" * 50)
    
    if stats.get('by_group'):
        print("\nПо группам процессов:")
        for group, cnt in sorted(stats['by_group'].items(), key=lambda x: -x[1]):
            print(f"  {group}: {cnt}")
    
    if stats.get('by_type'):
        print("\nПо типам документов:")
        for doc_type, cnt in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
            print(f"  {doc_type}: {cnt}")
    
    if stats.get('by_process'):
        print("\nТоп-10 процессов по количеству документов:")
        top_processes = sorted(stats['by_process'].items(), key=lambda x: -x[1])[:10]
        for process, cnt in top_processes:
            print(f"  {process}: {cnt}")
    
    print("\n" + "=" * 50)
    print(f"🎉 Готово! Откройте {output_path / 'graph_viewer.html'} в браузере")
    
    return 0


def cmd_test(args):
    """Команда тестирования парсера"""
    from .parser import parse_document_code, get_process_info
    
    test_names = [
        "ДП-М1.020-06 ^692386276D6DDE30452584F50038090F",
        "КД-ДП-Б1.002-04 ^7B1A2943B36B17A346257BDA003FB1BA",
        "РК01-2017-07 (Эталон № 13 для печати).pdf",
        "ИОТ-001-02 ^0E02046716E6B8434525880F004081C1",
        "СТ-166-01 ^4B692AD146B4319845258C65003C450D",
        "TPM-UTA-UTG-002-03 ^CDA7C0F2C002F20A4525896300299CDE",
        "КД-РГ-039-05 ^98922A5C1D13C8AF45258B0400287F5F",
        "РД-М1.014-16",
        "РД-Б7.004-05",
    ]
    
    print("🧪 Тест парсера документов:")
    print("=" * 80)
    
    success = 0
    failed = 0
    
    for name in test_names:
        doc = parse_document_code(name)
        if doc:
            success += 1
            print(f"\n✅ {name}")
            print(f"   Код: {doc.code}")
            print(f"   Тип: {doc.doc_type.value}")
            print(f"   Процесс: {doc.process_code}")
            print(f"   Версия: {doc.version}")
            print(f"   Группа: {doc.process_group.value}")
            
            process_info = get_process_info(doc.process_id)
            if process_info:
                print(f"   Название процесса: {process_info['name']}")
        else:
            failed += 1
            print(f"\n❌ {name}")
            print(f"   НЕ РАСПОЗНАН")
    
    print("\n" + "=" * 80)
    print(f"Результат: {success} распознано, {failed} не распознано")
    
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Система графа документов СМК",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Команды')
    
    # Команда scan
    scan_parser = subparsers.add_parser('scan', help='Сканировать документы и построить граф')
    scan_parser.add_argument('--input', '-i', required=True, help='Папка с документами')
    scan_parser.add_argument('--output', '-o', required=True, help='Папка для результатов')
    scan_parser.add_argument('--format', '-f', choices=['json', 'html', 'all'], default='all',
                            help='Формат экспорта (default: all)')
    
    # Команда test
    test_parser = subparsers.add_parser('test', help='Тестировать парсер документов')
    
    args = parser.parse_args()
    
    if args.command == 'scan':
        return cmd_scan(args)
    elif args.command == 'test':
        return cmd_test(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
