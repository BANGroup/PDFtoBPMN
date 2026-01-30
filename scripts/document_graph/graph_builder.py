"""
Генератор графа документов СМК
Строит граф связей между документами и процессами
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .hybrid_parser import ParseResult
from datetime import datetime
from collections import defaultdict

from .models import (
    Document, DocumentGraph, GraphNode, GraphEdge,
    ProcessGroup, DocumentType
)
from .parser import (
    scan_documents_folder, get_process_info, normalize_process_code,
    normalize_document_code, PROCESS_REGISTRY
)
from .pdf_extractor import extract_references

# Импорт гибридного парсера для извлечения структуры
try:
    from .hybrid_parser import (
        parse_document,
        format_parse_report,
        parse_documents_batch,
        ParseResult,
    )
    HYBRID_PARSER_AVAILABLE = True
except ImportError:
    HYBRID_PARSER_AVAILABLE = False


def _print_progress(current: int, total: int, filename: str):
    """Вывод прогресса в консоль"""
    pct = (current / total) * 100
    bar_len = 30
    filled = int(bar_len * current / total)
    bar = '█' * filled + '░' * (bar_len - filled)
    print(f"\r   [{bar}] {pct:5.1f}% ({current}/{total}) {filename[:40]:<40}", end='', flush=True)


class DocumentGraphBuilder:
    """Строитель графа документов"""
    
    def __init__(self):
        self.graph = DocumentGraph()
        self.documents: List[Document] = []
        self.processes: Set[str] = set()
        self.process_groups: Set[ProcessGroup] = set()
        self.metadata_cache: Dict[str, dict] = {}
    
    def scan_folder(self, folder_path: Path) -> int:
        """
        Сканировать папку с документами
        
        Returns:
            Количество найденных документов
        """
        docs = scan_documents_folder(folder_path)
        self.documents.extend(docs)
        return len(docs)

    def build_full_content_index(self, full_content_root: Path) -> Dict[str, Path]:
        """Построить индекс doc_code -> full_content.md"""
        index: Dict[str, Path] = {}
        if not full_content_root.exists():
            return index
        for item in full_content_root.iterdir():
            if not item.is_dir():
                continue
            parts = item.name.split('_', 1)
            code = parts[1] if len(parts) == 2 and parts[0].isdigit() else item.name
            full_md = item / "full_content.md"
            if full_md.exists():
                index[normalize_document_code(code)] = full_md
        return index

    def load_full_content_references(self, full_content_root: Path) -> int:
        """Загрузить ссылки из full_content.md"""
        index = self.build_full_content_index(full_content_root)
        if not index:
            return 0
        total_refs = 0
        for doc in self.documents:
            doc_key = normalize_document_code(doc.code)
            full_md = index.get(doc_key)
            if not full_md:
                continue
            try:
                text = full_md.read_text(encoding="utf-8")
            except Exception:
                continue
            refs_raw = extract_references(text, doc.code)
            normalized_refs = set()
            for ref in refs_raw:
                ref_norm = normalize_document_code(ref)
                if ref_norm and ref_norm != doc_key:
                    normalized_refs.add(ref_norm)
            doc.references = sorted(normalized_refs)
            total_refs += len(doc.references)
        return total_refs
    
    def extract_metadata(self, max_pages: int = 50, 
                         docx_base_path: Path = None,
                         xlsx_catalog_path: Path = None) -> int:
        """
        Извлечь метаданные из PDF файлов с использованием всех источников
        
        Приоритет источников:
        1. DOCX файл - для названия документа
        2. XLSX каталог - для даты регистрации и процесса
        3. PDF файл - для ссылок и fallback данных
        
        Args:
            max_pages: Максимум страниц для чтения при поиске ссылок
            docx_base_path: Путь к папке с DOCX файлами
            xlsx_catalog_path: Путь к xlsx файлу каталога
            
        Returns:
            Количество обработанных документов
        """
        try:
            from .pdf_extractor import extract_document_metadata
            from .docx_extractor import find_docx_for_pdf
            from .xlsx_catalog import load_catalog, find_in_catalog
        except ImportError as e:
            print(f"⚠️ Модули недоступны: {e}")
            return 0
        
        # Загружаем xlsx каталог если есть
        catalog = {}
        if xlsx_catalog_path and xlsx_catalog_path.exists():
            print(f"📊 Загрузка каталога: {xlsx_catalog_path.name}")
            catalog = load_catalog(xlsx_catalog_path)
            print(f"   Загружено: {len(catalog)} записей")
        
        # Определяем базовый путь для DOCX
        if docx_base_path is None and self.documents:
            # Автоопределение: ищем папку docx рядом с pdf
            first_pdf = Path(self.documents[0].file_path) if self.documents[0].file_path else None
            if first_pdf:
                potential_docx = first_pdf.parent.parent.parent / "docx"
                if potential_docx.exists():
                    docx_base_path = potential_docx
                    print(f"📁 Найдена папка DOCX: {docx_base_path}")
        
        processed = 0
        docx_found = 0
        catalog_found = 0
        total = len(self.documents)
        
        print(f"\n📖 Извлечение метаданных из {total} документов...")
        
        for i, doc in enumerate(self.documents):
            if not doc.file_path:
                continue
            
            pdf_path = Path(doc.file_path)
            if not pdf_path.exists():
                continue
            
            _print_progress(i + 1, total, pdf_path.name)
            
            try:
                # Ищем соответствующий DOCX
                docx_path = None
                if docx_base_path:
                    docx_path = find_docx_for_pdf(pdf_path, docx_base_path)
                    if docx_path:
                        docx_found += 1
                
                # Ищем в каталоге
                catalog_entry = None
                if catalog:
                    catalog_entry = find_in_catalog(catalog, doc.code)
                    if catalog_entry:
                        catalog_found += 1
                
                # Извлекаем метаданные со всех источников
                metadata = extract_document_metadata(
                    pdf_path, 
                    doc.code,
                    docx_path=docx_path,
                    catalog_entry=catalog_entry
                )
                
                # Обновляем документ
                doc.title = metadata.title
                doc.approval_date = metadata.approval_date
                doc.effective_date = metadata.effective_date
                doc.pages = metadata.pages
                doc.references = metadata.references
                
                processed += 1
                
            except Exception as e:
                # Продолжаем при ошибках
                pass
        
        print()  # Новая строка после прогресс-бара
        print(f"   📄 DOCX найдено: {docx_found} из {total}")
        print(f"   📊 В каталоге: {catalog_found} из {total}")
        return processed
    
    def parse_document_structure(self, docx_base_path: Path = None, 
                                  verbose: bool = True) -> List[ParseResult]:
        """
        Парсинг структуры документов с помощью гибридного парсера
        
        Использует DOCX если доступен и актуален, иначе PDF с фильтрацией.
        
        Args:
            docx_base_path: Базовая директория для поиска DOCX файлов
            verbose: Выводить прогресс и отчёты
            
        Returns:
            Список результатов парсинга для каждого документа
        """
        if not HYBRID_PARSER_AVAILABLE:
            print("⚠️ Гибридный парсер недоступен")
            return []
        
        # Определяем базовый путь для DOCX
        if docx_base_path is None and self.documents:
            # Автоопределение: ищем папку docx рядом с pdf
            first_pdf = Path(self.documents[0].file_path) if self.documents[0].file_path else None
            if first_pdf:
                # Пробуем разные варианты расположения docx
                potential_paths = [
                    first_pdf.parent.parent.parent / "docx",  # input2/BND/docx
                    first_pdf.parent.parent / "docx",         # input2/docx
                    first_pdf.parent / "docx",                # pdf/docx
                ]
                for p in potential_paths:
                    if p.exists():
                        docx_base_path = p
                        break
        
        if docx_base_path and verbose:
            print(f"📁 Базовая папка DOCX: {docx_base_path}")
        
        # Собираем пути к PDF
        pdf_paths = [Path(doc.file_path) for doc in self.documents 
                     if doc.file_path and Path(doc.file_path).exists()]
        
        if verbose:
            print(f"\n📊 Парсинг структуры {len(pdf_paths)} документов...")
        
        # Запускаем гибридный парсер
        results = parse_documents_batch(
            [str(p) for p in pdf_paths],
            docx_base_dir=str(docx_base_path) if docx_base_path else None,
            verbose=verbose
        )
        
        # Статистика
        docx_count = sum(1 for r in results if r.source == "docx")
        pdf_count = sum(1 for r in results if r.source == "pdf")
        
        if verbose:
            print(f"\n   📄 DOCX (актуален): {docx_count}")
            print(f"   📕 PDF (fallback): {pdf_count}")
        
        # Сохраняем результаты для дальнейшего использования
        self._parse_results = results
        
        return results
    
    def generate_parse_reports(self, results: List[ParseResult] = None, 
                               output_path: Path = None) -> str:
        """
        Сгенерировать текстовые отчёты о парсинге
        
        Args:
            results: Результаты парсинга (или берутся из кэша)
            output_path: Путь для сохранения отчёта
            
        Returns:
            Текст отчёта
        """
        if results is None:
            results = getattr(self, '_parse_results', [])
        
        if not results:
            return "Нет результатов парсинга"
        
        reports = []
        for result in results:
            reports.append(format_parse_report(result))
            reports.append("\n")
        
        full_report = '\n'.join(reports)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_report)
        
        return full_report
    
    def build_graph(self, include_root: bool = True) -> DocumentGraph:
        """
        Построить граф из загруженных документов
        
        Args:
            include_root: Добавить корневой узел СМК
        """
        self.graph = DocumentGraph()
        
        # 1. Добавляем корневой узел
        if include_root:
            self.graph.add_node(GraphNode(
                id="root_smk",
                label="СМК",
                node_type="root",
                data={
                    "description": "Система менеджмента качества",
                    "standard": "ISO 9001:2015"
                }
            ))
        
        # 2. Собираем уникальные процессы и группы
        for doc in self.documents:
            if doc.process_id:
                self.processes.add(doc.process_id)
                self.process_groups.add(doc.process_group)
        
        # 3. Добавляем узлы групп процессов
        group_colors = {
            ProcessGroup.M: "#3498db",  # Синий
            ProcessGroup.B: "#2ecc71",  # Зеленый
            ProcessGroup.V: "#9b59b6",  # Фиолетовый
            ProcessGroup.UNKNOWN: "#95a5a6"  # Серый
        }
        
        for group in self.process_groups:
            label = group.value
            if group == ProcessGroup.UNKNOWN:
                label = "Прочие"
            self.graph.add_node(GraphNode(
                id=f"group_{group.name}",
                label=label,
                node_type="process_group",
                data={
                    "color": group_colors.get(group, "#95a5a6"),
                    "group_code": group.name
                }
            ))
            
            # Связь группы с корнем
            if include_root:
                self.graph.add_edge(GraphEdge(
                    source="root_smk",
                    target=f"group_{group.name}",
                    edge_type="hierarchy"
                ))
        
        # 4. Добавляем узлы процессов
        process_colors = {
            ProcessGroup.M: "#5dade2",
            ProcessGroup.B: "#58d68d",
            ProcessGroup.V: "#bb8fce",
        }
        
        for process_id in sorted(self.processes):
            normalized = normalize_process_code(process_id)
            process_info = get_process_info(normalized)
            
            if process_info:
                group = process_info['group']
                label = f"{normalized}: {process_info['name']}"
            else:
                # Определяем группу по первой букве
                first_char = normalized[0] if normalized else ''
                if first_char == 'М':
                    group = ProcessGroup.M
                elif first_char == 'Б':
                    group = ProcessGroup.B
                elif first_char == 'В':
                    group = ProcessGroup.V
                else:
                    group = ProcessGroup.UNKNOWN
                label = normalized
            
            self.graph.add_node(GraphNode(
                id=f"process_{normalized}",
                label=label,
                node_type="process",
                data={
                    "process_code": normalized,
                    "color": process_colors.get(group, "#95a5a6"),
                    "group": group.name
                }
            ))
            
            # Связь процесса с группой
            if group != ProcessGroup.UNKNOWN:
                self.graph.add_edge(GraphEdge(
                    source=f"group_{group.name}",
                    target=f"process_{normalized}",
                    edge_type="hierarchy"
                ))
        
        # 5. Добавляем промежуточный уровень - типы документов для каждого процесса
        doc_type_colors = {
            DocumentType.DP: "#f39c12",   # Оранжевый
            DocumentType.RD: "#e74c3c",   # Красный
            DocumentType.ST: "#1abc9c",   # Бирюзовый
            DocumentType.KD: "#34495e",   # Темно-серый
            DocumentType.RG: "#f1c40f",   # Желтый
            DocumentType.RK: "#e91e63",   # Розовый
            DocumentType.IOT: "#00bcd4",  # Голубой
            DocumentType.TPM: "#607d8b",  # Серо-синий
        }
        
        doc_type_labels = {
            DocumentType.DP: "ДП",
            DocumentType.RD: "РД",
            DocumentType.ST: "СТ",
            DocumentType.KD: "КД",
            DocumentType.RG: "РГ",
            DocumentType.RK: "РК",
            DocumentType.IOT: "ИОТ",
            DocumentType.TPM: "TPM",
        }
        
        # Собираем пары (процесс, тип) для создания промежуточных узлов
        process_doctypes = set()
        unknown_doctypes = set()
        for doc in self.documents:
            if doc.process_id:
                normalized = normalize_process_code(doc.process_id)
                process_doctypes.add((normalized, doc.doc_type))
            else:
                unknown_doctypes.add(doc.doc_type)
        
        # Создаём узлы типов документов для каждого процесса
        for process_code, doc_type in process_doctypes:
            type_node_id = f"type_{process_code}_{doc_type.name}"
            type_label = doc_type_labels.get(doc_type, doc_type.name)
            group_code = process_code[0] if process_code else "UNKNOWN"
            
            self.graph.add_node(GraphNode(
                id=type_node_id,
                label=type_label,
                node_type="doc_type",
                data={
                    "process_code": process_code,
                    "doc_type": doc_type.value,
                    "doc_type_code": doc_type.name,
                    "color": doc_type_colors.get(doc_type, "#bdc3c7"),
                    "group": normalize_process_code(group_code),
                }
            ))
            
            # Связь типа с процессом
            self.graph.add_edge(GraphEdge(
                source=f"process_{process_code}",
                target=type_node_id,
                edge_type="hierarchy"
            ))

        for doc_type in unknown_doctypes:
            type_node_id = f"type_UNKNOWN_{doc_type.name}"
            type_label = doc_type_labels.get(doc_type, doc_type.name)
            self.graph.add_node(GraphNode(
                id=type_node_id,
                label=type_label,
                node_type="doc_type",
                data={
                    "process_code": "",
                    "doc_type": doc_type.value,
                    "doc_type_code": doc_type.name,
                    "color": doc_type_colors.get(doc_type, "#bdc3c7"),
                    "group": ProcessGroup.UNKNOWN.name,
                }
            ))
            self.graph.add_edge(GraphEdge(
                source=f"group_{ProcessGroup.UNKNOWN.name}",
                target=type_node_id,
                edge_type="hierarchy"
            ))
        
        # 6. Добавляем узлы документов
        # Создаём маппинг код -> doc_id для связей
        code_to_id = {}
        
        for doc in self.documents:
            doc_id = f"doc_{doc.code.replace('.', '_').replace('-', '_')}"
            code_to_id[normalize_document_code(doc.code)] = doc_id
            
            self.graph.add_node(GraphNode(
                id=doc_id,
                label=doc.code,
                node_type="document",
                data={
                    "doc_type": doc.doc_type.value,
                    "doc_type_code": doc.doc_type.name,
                    "process_code": doc.process_code,
                    "group": doc.process_group.name,
                    "version": doc.version,
                    "file_path": doc.file_path,
                    "color": doc_type_colors.get(doc.doc_type, "#bdc3c7"),
                    # Расширенные метаданные
                    "title": doc.title or "",
                    "approval_date": doc.approval_date or "",
                    "effective_date": doc.effective_date or "",
                    "pages": doc.pages,
                    "references_count": len(doc.references) if doc.references else 0,
                }
            ))
            
            # Связь документа с типом документа (промежуточный уровень)
            if doc.process_id:
                normalized = normalize_process_code(doc.process_id)
                type_node_id = f"type_{normalized}_{doc.doc_type.name}"
                self.graph.add_edge(GraphEdge(
                    source=type_node_id,
                    target=doc_id,
                    edge_type="contains"
                ))
            else:
                type_node_id = f"type_UNKNOWN_{doc.doc_type.name}"
                self.graph.add_edge(GraphEdge(
                    source=type_node_id,
                    target=doc_id,
                    edge_type="contains"
                ))
        
        # 6. Добавляем связи между документами (ссылки)
        references_count = 0
        for doc in self.documents:
            if not doc.references:
                continue
            
            source_id = code_to_id.get(normalize_document_code(doc.code))
            if not source_id:
                continue
            
            for ref_code in doc.references:
                target_id = code_to_id.get(normalize_document_code(ref_code))
                if target_id and target_id != source_id:
                    self.graph.add_edge(GraphEdge(
                        source=source_id,
                        target=target_id,
                        edge_type="references"
                    ))
                    references_count += 1
        
        if references_count > 0:
            print(f"   🔗 Найдено связей-ссылок: {references_count}")

        self._prune_orphan_edges()
        self._prune_orphan_documents()
        
        # 6. Метаданные
        self.graph.metadata = {
            "generated_at": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "total_processes": len(self.processes),
            "total_groups": len([g for g in self.process_groups if g != ProcessGroup.UNKNOWN]),
            "statistics": self._calculate_statistics()
        }
        
        return self.graph

    def _prune_orphan_edges(self) -> None:
        """Удалить связи с отсутствующими узлами"""
        node_ids = {node.id for node in self.graph.nodes}
        before = len(self.graph.edges)
        self.graph.edges = [
            edge for edge in self.graph.edges
            if edge.source in node_ids and edge.target in node_ids
        ]
        removed = before - len(self.graph.edges)
        if removed:
            print(f"   🧹 Удалены пустые связи: {removed}")

    def _prune_orphan_documents(self) -> None:
        """Удалить устаревшие документы без связей"""
        def base_code(code: str) -> str:
            match = re.match(r"^(.*?)-(\d+)$", code)
            if match:
                return match.group(1)
            return code

        # Считаем степень узлов
        degree = defaultdict(int)
        for edge in self.graph.edges:
            degree[edge.source] += 1
            degree[edge.target] += 1

        # Определяем последние версии
        latest_by_base: Dict[str, tuple] = {}
        for doc in self.documents:
            if not doc.version:
                continue
            try:
                version_num = int(doc.version)
            except ValueError:
                continue
            base = base_code(doc.code)
            current = latest_by_base.get(base)
            if not current or version_num > current[0]:
                latest_by_base[base] = (version_num, doc.code)

        removed = []
        kept = []
        for doc in self.documents:
            doc_id = f"doc_{doc.code.replace('.', '_').replace('-', '_')}"
            if degree.get(doc_id, 0) > 0:
                continue
            base = base_code(doc.code)
            latest = latest_by_base.get(base)
            if latest and latest[1] != doc.code:
                removed.append(doc.code)
            else:
                kept.append(doc.code)

        if not removed and not kept:
            return

        if removed:
            before_nodes = len(self.graph.nodes)
            self.graph.nodes = [n for n in self.graph.nodes if n.id not in {
                f"doc_{code.replace('.', '_').replace('-', '_')}" for code in removed
            }]
            self.graph.edges = [e for e in self.graph.edges if e.source not in {
                f"doc_{code.replace('.', '_').replace('-', '_')}" for code in removed
            } and e.target not in {
                f"doc_{code.replace('.', '_').replace('-', '_')}" for code in removed
            }]
            print(f"   🗑️ Удалены устаревшие без связей: {len(removed)} (узлов: {before_nodes} -> {len(self.graph.nodes)})")
        if kept:
            print(f"   ⚠️ Без связей (актуальные/без версии): {len(kept)}")
    
    def _calculate_statistics(self) -> Dict:
        """Рассчитать статистику по документам"""
        stats = {
            "by_type": defaultdict(int),
            "by_group": defaultdict(int),
            "by_process": defaultdict(int)
        }
        
        for doc in self.documents:
            stats["by_type"][doc.doc_type.value] += 1
            stats["by_group"][doc.process_group.value] += 1
            if doc.process_id:
                stats["by_process"][normalize_process_code(doc.process_id)] += 1
        
        return {
            "by_type": dict(stats["by_type"]),
            "by_group": dict(stats["by_group"]),
            "by_process": dict(stats["by_process"])
        }
    
    def export_json(self, output_path: Path):
        """Экспортировать граф в JSON файл"""
        data = self.graph.to_cytoscape_json()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return output_path
    
    def export_html(self, output_path: Path, template_path: Path = None):
        """
        Экспортировать граф в HTML файл с встроенным визуализатором
        
        Args:
            output_path: Путь к выходному HTML файлу
            template_path: Путь к шаблону HTML (опционально)
        """
        data = self.graph.to_cytoscape_json()
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        
        html_content = generate_html_viewer(json_data, self.graph.metadata)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path


def generate_html_viewer(graph_json: str, metadata: Dict) -> str:
    """Генерация HTML визуализатора с Cytoscape.js"""
    
    stats_html = ""
    if metadata.get("statistics"):
        stats = metadata["statistics"]
        
        # Статистика по типам
        if stats.get("by_type"):
            stats_html += "<h4>По типам документов:</h4><ul>"
            for doc_type, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
                stats_html += f"<li>{doc_type}: {count}</li>"
            stats_html += "</ul>"
        
        # Статистика по группам
        if stats.get("by_group"):
            stats_html += "<h4>По группам процессов:</h4><ul>"
            for group, count in sorted(stats["by_group"].items(), key=lambda x: -x[1]):
                stats_html += f"<li>{group}: {count}</li>"
            stats_html += "</ul>"
    
    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Граф документов СМК</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            height: 100vh;
            overflow: hidden;
        }}
        
        .container {{
            display: flex;
            height: 100vh;
        }}
        
        #cy {{
            flex: 1;
            background: #16213e;
        }}
        
        .sidebar {{
            width: 350px;
            background: #0f3460;
            padding: 20px;
            overflow-y: auto;
            border-left: 2px solid #e94560;
        }}
        
        .sidebar h1 {{
            font-size: 1.5em;
            margin-bottom: 15px;
            color: #e94560;
        }}
        
        .sidebar h2 {{
            font-size: 1.2em;
            margin: 15px 0 10px;
            color: #0f9b8e;
            border-bottom: 1px solid #0f9b8e;
            padding-bottom: 5px;
        }}
        
        .sidebar h3 {{
            font-size: 1em;
            margin: 10px 0 5px;
            color: #ccc;
        }}
        
        .sidebar h4 {{
            font-size: 0.9em;
            margin: 10px 0 5px;
            color: #aaa;
        }}
        
        .sidebar ul {{
            list-style: none;
            padding-left: 10px;
        }}
        
        .sidebar li {{
            padding: 3px 0;
            font-size: 0.85em;
            color: #ddd;
        }}
        
        .info-panel {{
            background: #1a1a2e;
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
        }}
        
        .info-panel p {{
            margin: 5px 0;
            font-size: 0.9em;
        }}
        
        .info-panel .label {{
            color: #888;
        }}
        
        .info-panel .value {{
            color: #fff;
            font-weight: 500;
        }}
        
        .controls {{
            margin-bottom: 20px;
        }}
        
        .controls input {{
            width: 100%;
            padding: 10px;
            border: none;
            border-radius: 5px;
            background: #1a1a2e;
            color: #fff;
            font-size: 14px;
        }}
        
        .controls input::placeholder {{
            color: #666;
        }}
        
        .filter-buttons {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-top: 10px;
        }}
        
        .filter-btn {{
            padding: 5px 10px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }}
        
        .filter-btn:hover {{
            opacity: 0.8;
        }}
        
        .filter-btn.active {{
            box-shadow: 0 0 5px #fff;
        }}
        
        .filter-btn.M {{ background: #3498db; color: white; }}
        .filter-btn.B {{ background: #2ecc71; color: white; }}
        .filter-btn.V {{ background: #9b59b6; color: white; }}
        .filter-btn.all {{ background: #e94560; color: white; }}
        
        .layout-buttons {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
            margin-top: 8px;
        }}
        .layout-btn {{
            padding: 6px 12px;
            border: 1px solid #333;
            border-radius: 4px;
            cursor: pointer;
            background: #1a1a2e;
            color: #888;
            font-size: 12px;
            transition: all 0.2s;
        }}
        .layout-btn:hover {{
            background: #2a2a4e;
            color: #fff;
        }}
        .layout-btn.active {{
            background: #0f9b8e;
            color: white;
            border-color: #0f9b8e;
        }}
        
        .legend {{
            margin-top: 15px;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
            font-size: 0.85em;
        }}
        
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
            margin-right: 8px;
        }}
        
        .stats {{
            font-size: 0.9em;
            margin-top: 20px;
        }}
        
        .meta {{
            font-size: 0.75em;
            color: #666;
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid #333;
        }}
        
        /* Расширенная карточка документа */
        .doc-card {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 8px;
            padding: 5px;
        }}
        
        .doc-code {{
            font-size: 1.2em;
            font-weight: bold;
            color: #e94560;
            margin-bottom: 5px;
        }}
        
        .doc-title {{
            font-size: 0.95em;
            color: #0f9b8e;
            font-style: italic;
            margin: 5px 0;
            line-height: 1.3;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div id="cy"></div>
        <div class="sidebar">
            <h1>📊 Граф документов СМК</h1>
            
            <div class="controls">
                <input type="text" id="search" placeholder="🔍 Поиск документа...">
                
                <div class="filter-buttons">
                    <button class="filter-btn all active" onclick="filterByGroup('all')">Все</button>
                    <button class="filter-btn M" onclick="filterByGroup('M')">М (Менеджмент)</button>
                    <button class="filter-btn B" onclick="filterByGroup('B')">Б (Жизн. цикл)</button>
                    <button class="filter-btn V" onclick="filterByGroup('V')">В (Обеспечение)</button>
                </div>
                
                <h3 style="margin-top:15px; color:#0f9b8e;">📐 Вид графа:</h3>
                <div class="layout-buttons">
                    <button class="layout-btn active" data-layout="tree" onclick="changeLayout('tree')">🌳 Дерево</button>
                    <button class="layout-btn" data-layout="galaxy" onclick="changeLayout('galaxy')">🌌 Галактика</button>
                    <button class="layout-btn" data-layout="circle" onclick="changeLayout('circle')">⭕ Круг</button>
                </div>
            </div>
            
            <h2>ℹ️ Информация об элементе</h2>
            <div class="info-panel" id="info-panel">
                <p><span class="label">Кликните на элемент для просмотра информации</span></p>
            </div>
            
            <h2>📋 Легенда</h2>
            <div class="legend">
                <h4>Узлы:</h4>
                <div class="legend-item"><span class="legend-color" style="background:#e91e63"></span> Руководство по качеству</div>
                <div class="legend-item"><span class="legend-color" style="background:#3498db"></span> Группа М (Менеджмент)</div>
                <div class="legend-item"><span class="legend-color" style="background:#2ecc71"></span> Группа Б (Жизн. цикл)</div>
                <div class="legend-item"><span class="legend-color" style="background:#9b59b6"></span> Группа В (Обеспечение)</div>
                <div class="legend-item"><span class="legend-color" style="background:#f39c12"></span> ДП - Документация процесса</div>
                <div class="legend-item"><span class="legend-color" style="background:#e74c3c"></span> РД - Руководство по деятельности</div>
                <div class="legend-item"><span class="legend-color" style="background:#00bcd4"></span> ИОТ - Инструкция по ОТ</div>
            </div>
            
            <h2>📈 Статистика</h2>
            <div class="stats">
                <p><span class="label">Документов:</span> <span class="value">{metadata.get('total_documents', 0)}</span></p>
                <p><span class="label">Процессов:</span> <span class="value">{metadata.get('total_processes', 0)}</span></p>
                <p><span class="label">Групп:</span> <span class="value">{metadata.get('total_groups', 0)}</span></p>
                {stats_html}
            </div>
            
            <div class="meta">
                <p>Сгенерировано: {metadata.get('generated_at', 'N/A')}</p>
            </div>
        </div>
    </div>
    
    <script>
        // Данные графа
        const graphData = {graph_json};
        
        // ========================================
        // РАСЧЁТ ПОЗИЦИЙ УЗЛОВ ПО СЕТКЕ
        // ========================================
        function calculateGridPositions(elements, maxPerRow = 12) {{
            const nodeSpacingX = 120;  // Расстояние по горизонтали
            const nodeSpacingY = 120;  // Расстояние по вертикали
            const levelGap = 80;       // Дополнительный отступ между логическими уровнями
            
            // Уровни иерархии (порядок сверху вниз)
            const levelOrder = ['root', 'process_group', 'process', 'doc_type', 'document'];
            
            // Группируем узлы по типам
            const nodesByType = {{}};
            const nodes = elements.filter(el => !el.data.source);  // Только узлы
            const edges = elements.filter(el => el.data.source);   // Только рёбра
            
            nodes.forEach(node => {{
                const type = node.data.type || 'unknown';
                if (!nodesByType[type]) nodesByType[type] = [];
                nodesByType[type].push(node);
            }});
            
            // Строим дерево родителей для сортировки
            const parentMap = {{}};
            edges.forEach(edge => {{
                parentMap[edge.data.target] = edge.data.source;
            }});
            
            // Функция для получения родительского узла
            function getParent(nodeId) {{
                return parentMap[nodeId];
            }}
            
            // Сортируем узлы внутри типа по родителю (группировка)
            function sortByParent(nodesArray) {{
                return nodesArray.sort((a, b) => {{
                    const parentA = getParent(a.data.id) || '';
                    const parentB = getParent(b.data.id) || '';
                    if (parentA !== parentB) return parentA.localeCompare(parentB);
                    return (a.data.label || '').localeCompare(b.data.label || '');
                }});
            }}
            
            let currentY = 50;
            
            // Обрабатываем каждый уровень
            levelOrder.forEach((levelType, levelIndex) => {{
                const levelNodes = nodesByType[levelType] || [];
                if (levelNodes.length === 0) return;
                
                // Сортируем по родителю
                const sortedNodes = sortByParent(levelNodes);
                
                // Разбиваем на ряды по лимиту
                const rows = [];
                for (let i = 0; i < sortedNodes.length; i += maxPerRow) {{
                    rows.push(sortedNodes.slice(i, i + maxPerRow));
                }}
                
                // Позиционируем каждый ряд
                rows.forEach((row, rowIndex) => {{
                    const rowWidth = row.length * nodeSpacingX;
                    const startX = -rowWidth / 2 + nodeSpacingX / 2;
                    
                    row.forEach((node, colIndex) => {{
                        node.position = {{
                            x: startX + colIndex * nodeSpacingX,
                            y: currentY
                        }};
                    }});
                    
                    currentY += nodeSpacingY;
                }});
                
                // Добавляем отступ между логическими уровнями
                currentY += levelGap;
            }});
            
            return elements;
        }}
        
        // Функция пересчёта позиций для существующего cy объекта
        function recalculateGridPositions(cy, maxPerRow = 15) {{
            const nodeSpacingX = 120;
            const nodeSpacingY = 120;
            const levelGap = 80;
            
            const levelOrder = ['root', 'process_group', 'process', 'doc_type', 'document'];
            
            // Группируем узлы по типам
            const nodesByType = {{}};
            cy.nodes().forEach(node => {{
                const type = node.data('type') || 'unknown';
                if (!nodesByType[type]) nodesByType[type] = [];
                nodesByType[type].push(node);
            }});
            
            // Строим карту родителей
            const parentMap = {{}};
            cy.edges().forEach(edge => {{
                parentMap[edge.data('target')] = edge.data('source');
            }});
            
            function getParent(nodeId) {{
                return parentMap[nodeId];
            }}
            
            function sortByParent(nodesArray) {{
                return nodesArray.sort((a, b) => {{
                    const parentA = getParent(a.data('id')) || '';
                    const parentB = getParent(b.data('id')) || '';
                    if (parentA !== parentB) return parentA.localeCompare(parentB);
                    return (a.data('label') || '').localeCompare(b.data('label') || '');
                }});
            }}
            
            let currentY = 50;
            
            levelOrder.forEach(levelType => {{
                const levelNodes = nodesByType[levelType] || [];
                if (levelNodes.length === 0) return;
                
                const sortedNodes = sortByParent(levelNodes);
                
                const rows = [];
                for (let i = 0; i < sortedNodes.length; i += maxPerRow) {{
                    rows.push(sortedNodes.slice(i, i + maxPerRow));
                }}
                
                rows.forEach(row => {{
                    const rowWidth = row.length * nodeSpacingX;
                    const startX = -rowWidth / 2 + nodeSpacingX / 2;
                    
                    row.forEach((node, colIndex) => {{
                        node.position({{
                            x: startX + colIndex * nodeSpacingX,
                            y: currentY
                        }});
                    }});
                    
                    currentY += nodeSpacingY;
                }});
                
                currentY += levelGap;
            }});
        }}
        
        // Применяем расчёт позиций
        calculateGridPositions(graphData.elements, 15);
        
        // Инициализация Cytoscape
        const cy = cytoscape({{
            container: document.getElementById('cy'),
            elements: graphData.elements,
            style: [
                // Узлы по умолчанию
                {{
                    selector: 'node',
                    style: {{
                        'label': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'background-color': 'data(color)',
                        'color': '#fff',
                        'font-size': '10px',
                        'text-wrap': 'wrap',
                        'text-max-width': '80px',
                        'width': 40,
                        'height': 40,
                        'border-width': 2,
                        'border-color': '#fff',
                    }}
                }},
                // Корневой узел
                {{
                    selector: 'node[type="root"]',
                    style: {{
                        'width': 80,
                        'height': 80,
                        'font-size': '14px',
                        'font-weight': 'bold',
                        'background-color': '#e91e63',
                    }}
                }},
                // Группы процессов
                {{
                    selector: 'node[type="process_group"]',
                    style: {{
                        'width': 60,
                        'height': 60,
                        'font-size': '11px',
                        'font-weight': 'bold',
                        'text-max-width': '100px',
                    }}
                }},
                // Процессы
                {{
                    selector: 'node[type="process"]',
                    style: {{
                        'width': 50,
                        'height': 50,
                        'font-size': '9px',
                        'text-max-width': '120px',
                    }}
                }},
                // Типы документов (промежуточный уровень)
                {{
                    selector: 'node[type="doc_type"]',
                    style: {{
                        'width': 30,
                        'height': 30,
                        'font-size': '8px',
                        'font-weight': 'bold',
                        'shape': 'diamond',
                        'text-max-width': '50px',
                    }}
                }},
                // Документы
                {{
                    selector: 'node[type="document"]',
                    style: {{
                        'width': 35,
                        'height': 35,
                        'font-size': '8px',
                        'text-max-width': '80px',
                        'shape': 'rectangle',
                    }}
                }},
                // Выделенный узел
                {{
                    selector: 'node:selected',
                    style: {{
                        'border-width': 4,
                        'border-color': '#e94560',
                    }}
                }},
                // Подсвеченный узел
                {{
                    selector: 'node.highlighted',
                    style: {{
                        'border-width': 4,
                        'border-color': '#f1c40f',
                        'z-index': 9999,
                    }}
                }},
                // Затемненный узел
                {{
                    selector: 'node.dimmed',
                    style: {{
                        'opacity': 0.2,
                    }}
                }},
                // Связи
                {{
                    selector: 'edge',
                    style: {{
                        'width': 1.5,
                        'line-color': '#555',
                        'target-arrow-color': '#555',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'arrow-scale': 0.8,
                    }}
                }},
                // Связи hierarchy
                {{
                    selector: 'edge[type="hierarchy"]',
                    style: {{
                        'line-color': '#0f9b8e',
                        'target-arrow-color': '#0f9b8e',
                        'width': 2,
                    }}
                }},
                // Связи contains
                {{
                    selector: 'edge[type="contains"]',
                    style: {{
                        'line-color': '#666',
                        'target-arrow-color': '#666',
                        'line-style': 'dashed',
                    }}
                }},
                // Связи references (ссылки между документами)
                {{
                    selector: 'edge[type="references"]',
                    style: {{
                        'line-color': '#e94560',
                        'target-arrow-color': '#e94560',
                        'width': 1,
                        'line-style': 'solid',
                        'curve-style': 'bezier',
                    }}
                }},
                // Связи подсвеченные
                {{
                    selector: 'edge.highlighted',
                    style: {{
                        'line-color': '#e94560',
                        'target-arrow-color': '#e94560',
                        'width': 3,
                        'z-index': 9999,
                    }}
                }},
                // Затемненные связи
                {{
                    selector: 'edge.dimmed',
                    style: {{
                        'opacity': 0.1,
                    }}
                }},
            ],
            layout: {{
                name: 'preset',  // Используем ручные позиции
                fit: true,
                padding: 50,
            }}
        }});
        
        // Информационная панель
        function showInfo(node) {{
            const data = node.data();
            const panel = document.getElementById('info-panel');
            
            // Подсчёт входящих и исходящих связей
            const incomingEdges = node.incomers('edge').length;
            const outgoingEdges = node.outgoers('edge').length;
            
            // HTML для связей (общий для всех типов)
            const connectionsHtml = `
                <hr style="border-color:#333; margin:10px 0;">
                <p><span class="label">⬅️ Входящих:</span> <span class="value">${{incomingEdges}}</span></p>
                <p><span class="label">➡️ Исходящих:</span> <span class="value">${{outgoingEdges}}</span></p>
            `;
            
            let html = '';
            
            if (data.type === 'root') {{
                html = `
                    <p><span class="label">Тип:</span> <span class="value">Корневой элемент</span></p>
                    <p><span class="label">Описание:</span> <span class="value">${{data.description || 'Система менеджмента качества'}}</span></p>
                    <p><span class="label">Стандарт:</span> <span class="value">${{data.standard || 'ISO 9001:2015'}}</span></p>
                    ${{connectionsHtml}}
                `;
            }} else if (data.type === 'process_group') {{
                html = `
                    <p><span class="label">Тип:</span> <span class="value">Группа процессов</span></p>
                    <p><span class="label">Название:</span> <span class="value">${{data.label}}</span></p>
                    <p><span class="label">Код:</span> <span class="value">${{data.group_code}}</span></p>
                    ${{connectionsHtml}}
                `;
            }} else if (data.type === 'process') {{
                html = `
                    <p><span class="label">Тип:</span> <span class="value">Бизнес-процесс</span></p>
                    <p><span class="label">Название:</span> <span class="value">${{data.label}}</span></p>
                    <p><span class="label">Код:</span> <span class="value">${{data.process_code}}</span></p>
                    <p><span class="label">Группа:</span> <span class="value">${{data.group}}</span></p>
                    ${{connectionsHtml}}
                `;
            }} else if (data.type === 'doc_type') {{
                // Тип документа (промежуточный уровень)
                html = `
                    <p><span class="label">Тип:</span> <span class="value">Категория документов</span></p>
                    <p><span class="label">Категория:</span> <span class="value">${{data.doc_type}}</span></p>
                    <p><span class="label">Процесс:</span> <span class="value">${{data.process_code}}</span></p>
                    ${{connectionsHtml}}
                `;
            }} else if (data.type === 'document') {{
                // Расширенная карточка документа
                let titleHtml = data.title 
                    ? `<p class="doc-title">${{data.title}}</p>` 
                    : '';
                
                let datesHtml = '';
                if (data.approval_date) {{
                    datesHtml += `<p><span class="label">📅 Утверждён:</span> <span class="value">${{data.approval_date}}</span></p>`;
                }}
                if (data.effective_date) {{
                    datesHtml += `<p><span class="label">📅 Введён:</span> <span class="value">${{data.effective_date}}</span></p>`;
                }}
                
                let pagesHtml = data.pages > 0 
                    ? `<p><span class="label">📑 Страниц:</span> <span class="value">${{data.pages}}</span></p>`
                    : '';
                
                let refsHtml = data.references_count > 0
                    ? `<p><span class="label">🔗 Ссылок в тексте:</span> <span class="value">${{data.references_count}}</span></p>`
                    : '';
                
                html = `
                    <div class="doc-card">
                        <p class="doc-code">${{data.label}}</p>
                        ${{titleHtml}}
                        <hr style="border-color:#333; margin:10px 0;">
                        <p><span class="label">📂 Тип:</span> <span class="value">${{data.doc_type}}</span></p>
                        <p><span class="label">🏭 Процесс:</span> <span class="value">${{data.process_code || 'Общий'}}</span></p>
                        <p><span class="label">🔢 Версия:</span> <span class="value">${{data.version}}</span></p>
                        ${{datesHtml}}
                        ${{pagesHtml}}
                        ${{refsHtml}}
                        <hr style="border-color:#333; margin:10px 0;">
                        <p><span class="label">⬅️ Входящих:</span> <span class="value">${{incomingEdges}}</span></p>
                        <p><span class="label">➡️ Исходящих:</span> <span class="value">${{outgoingEdges}}</span></p>
                    </div>
                `;
            }}
            
            panel.innerHTML = html;
        }}
        
        // Подсветка связанных узлов
        function highlightConnected(node) {{
            cy.elements().removeClass('highlighted dimmed');
            
            const neighborhood = node.neighborhood().add(node);
            cy.elements().not(neighborhood).addClass('dimmed');
            neighborhood.addClass('highlighted');
        }}
        
        function clearHighlight() {{
            cy.elements().removeClass('highlighted dimmed');
        }}
        
        // События
        cy.on('tap', 'node', function(evt) {{
            const node = evt.target;
            showInfo(node);
            highlightConnected(node);
        }});
        
        cy.on('tap', function(evt) {{
            if (evt.target === cy) {{
                clearHighlight();
                document.getElementById('info-panel').innerHTML = 
                    '<p><span class="label">Кликните на элемент для просмотра информации</span></p>';
            }}
        }});
        
        // Поиск
        document.getElementById('search').addEventListener('input', function(e) {{
            const query = e.target.value.toLowerCase();
            
            if (!query) {{
                clearHighlight();
                return;
            }}
            
            cy.elements().removeClass('highlighted dimmed');
            
            const matches = cy.nodes().filter(function(node) {{
                const label = node.data('label') || '';
                const code = node.data('process_code') || '';
                return label.toLowerCase().includes(query) || code.toLowerCase().includes(query);
            }});
            
            if (matches.length > 0) {{
                cy.elements().not(matches).addClass('dimmed');
                matches.addClass('highlighted');
            }}
        }});
        
        // Фильтр по группе
        function filterByGroup(group) {{
            // Обновляем кнопки
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelector(`.filter-btn.${{group}}`).classList.add('active');
            
            cy.elements().removeClass('highlighted dimmed');
            
            if (group === 'all') {{
                return;
            }}
            
            // Показываем только документы и процессы из выбранной группы
            const nodes = cy.nodes().filter(function(node) {{
                const nodeGroup = node.data('group');
                const type = node.data('type');
                
                if (type === 'root') return true;
                if (type === 'process_group') return node.data('group_code') === group;
                if (type === 'process' || type === 'document') return nodeGroup === group;
                return false;
            }});
            
            const connectedEdges = nodes.connectedEdges();
            const visibleElements = nodes.add(connectedEdges);
            
            cy.elements().not(visibleElements).addClass('dimmed');
        }}
        
        // Переключение layout графа
        function changeLayout(layoutType) {{
            // Обновляем кнопки
            document.querySelectorAll('.layout-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelector(`.layout-btn[data-layout="${{layoutType}}"]`).classList.add('active');
            
            let layoutConfig;
            
            switch(layoutType) {{
                case 'tree':
                    // Пересчитываем позиции по сетке
                    recalculateGridPositions(cy, 15);
                    layoutConfig = {{
                        name: 'preset',
                        fit: true,
                        padding: 50,
                        animate: true,
                        animationDuration: 500,
                    }};
                    break;
                    
                case 'galaxy':
                    layoutConfig = {{
                        name: 'cose',
                        idealEdgeLength: 90,
                        nodeOverlap: 5,
                        refresh: 20,
                        fit: true,
                        padding: 40,
                        randomize: false,
                        componentSpacing: 80,
                        nodeRepulsion: 200000,
                        edgeElasticity: 120,
                        nestingFactor: 5,
                        gravity: 40,
                        numIter: 1200,
                        initialTemp: 180,
                        coolingFactor: 0.95,
                        minTemp: 1.0
                    }};
                    break;
                    
                case 'circle':
                    applySectorCircleLayout(cy);
                    layoutConfig = {{
                        name: 'preset',
                        fit: true,
                        padding: 10,
                        animate: true,
                        animationDuration: 500
                    }};
                    break;
            }}
            
            cy.layout(layoutConfig).run();
        }}

        function applySectorCircleLayout(cy) {{
            const center = {{
                x: cy.width() / 2,
                y: cy.height() / 2
            }};
            const sectorByGroup = {{
                'M': {{ start: -Math.PI / 2, end: Math.PI / 6 }},
                'B': {{ start: Math.PI / 6, end: Math.PI * 5 / 6 }},
                'V': {{ start: Math.PI * 5 / 6, end: Math.PI * 3 / 2 }},
                'UNKNOWN': {{ start: Math.PI * 3 / 2, end: Math.PI * 11 / 6 }}
            }};
            const ringRadius = {{
                root: 0,
                process_group: 160,
                process: 160,
                doc_type: 160,
                document: 260
            }};
            const ringStep = 35;
            const minSpacing = 30;

            const nodesByGroupType = {{
                'M': {{ process_group: [], process: [], doc_type: [], document: [] }},
                'B': {{ process_group: [], process: [], doc_type: [], document: [] }},
                'V': {{ process_group: [], process: [], doc_type: [], document: [] }},
                'UNKNOWN': {{ process_group: [], process: [], doc_type: [], document: [] }}
            }};

            cy.nodes().forEach(node => {{
                const type = node.data('type');
                if (type === 'root') {{
                    node.position(center);
                    return;
                }}
                if (type === 'process_group') {{
                    const groupCode = node.data('group_code') || 'UNKNOWN';
                    if (!nodesByGroupType[groupCode]) nodesByGroupType[groupCode] = {{ process_group: [], process: [], doc_type: [], document: [] }};
                    nodesByGroupType[groupCode].process_group.push(node);
                    return;
                }}
                let group = node.data('group') || 'UNKNOWN';
                if (typeof group === 'string') {{
                    if (group.toUpperCase() === 'M') group = 'M';
                    if (group.toUpperCase() === 'B') group = 'B';
                    if (group.toUpperCase() === 'V') group = 'V';
                    if (group.toUpperCase() === 'UNKNOWN') group = 'UNKNOWN';
                }}
                if (!nodesByGroupType[group]) nodesByGroupType[group] = {{ process_group: [], process: [], doc_type: [], document: [] }};
                if (type === 'process') nodesByGroupType[group].process.push(node);
                if (type === 'doc_type') nodesByGroupType[group].doc_type.push(node);
                if (type === 'document') nodesByGroupType[group].document.push(node);
            }});

            Object.keys(nodesByGroupType).forEach(groupCode => {{
                const sector = sectorByGroup[groupCode] || {{ start: -Math.PI, end: Math.PI }};
                const angleSpan = sector.end - sector.start;

                ['process_group', 'process', 'doc_type', 'document'].forEach(type => {{
                    const nodes = nodesByGroupType[groupCode][type];
                    if (!nodes.length) return;
                    let baseRadius = ringRadius[type] || 200;
                    const maxPerRing = Math.max(1, Math.floor((angleSpan * baseRadius) / minSpacing));
                    nodes.forEach((node, idx) => {{
                        const ringIndex = Math.floor(idx / maxPerRing);
                        const positionInRing = idx % maxPerRing;
                        const countInRing = Math.min(maxPerRing, nodes.length - ringIndex * maxPerRing);
                        const radius = baseRadius + ringIndex * ringStep;
                        const angle = sector.start + angleSpan * (positionInRing + 0.5) / countInRing;
                        node.position({{
                            x: center.x + radius * Math.cos(angle),
                            y: center.y + radius * Math.sin(angle)
                        }});
                    }});
                }});
            }});
        }}
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    # Тест
    from pathlib import Path
    
    builder = DocumentGraphBuilder()
    
    # Сканируем папку с документами
    docs_path = Path("/home/budnik_an/Obligations/input2/BND/pdf")
    count = builder.scan_folder(docs_path)
    print(f"Найдено документов: {count}")
    
    # Строим граф
    graph = builder.build_graph()
    print(f"Узлов: {len(graph.nodes)}, Связей: {len(graph.edges)}")
    
    # Экспортируем
    output_dir = Path("/home/budnik_an/Obligations/output/document_graph")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    builder.export_json(output_dir / "graph_data.json")
    builder.export_html(output_dir / "graph_viewer.html")
    
    print(f"Граф экспортирован в {output_dir}")
