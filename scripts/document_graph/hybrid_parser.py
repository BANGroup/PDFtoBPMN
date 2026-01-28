"""
Hybrid Parser - гибридный парсер документов (DOCX + PDF)

Логика работы:
1. Если есть DOCX и он актуален → структура из DOCX
2. Иначе → PDF с фильтрацией мусора

Фильтрация PDF:
- Фильтр повторов (>50% страниц = колонтитул)
- Фильтр по паттернам (чёрный список, regex)
- Белый список важных разделов
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import Counter

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

from .docx_parser import (
    Heading,
    extract_structure_docx,
    validate_docx_vs_pdf,
    find_docx_for_pdf,
    ValidationResult,
    extract_doc_code,
    DOCX_AVAILABLE,
)

from .document_structure import (
    analyzer,
    detect_headers_footers,
    normalize_text,
    filter_with_report,
)

from .hierarchy_builder import (
    build_hierarchy,
    DocumentTree,
    export_tree_json,
    export_tree_markdown,
)


@dataclass
class ParseResult:
    """Результат парсинга документа"""
    source: str  # "docx" или "pdf"
    headings: List[Heading]
    doc_code: str
    
    # Иерархическая структура документа
    structure_tree: Optional[DocumentTree] = None
    
    # Статистика фильтрации (только для PDF)
    filter_report: Optional[Dict] = None
    
    # Информация о валидации (если был DOCX)
    validation: Optional[ValidationResult] = None
    
    # Метаданные
    pdf_path: str = ""
    docx_path: str = ""
    total_pdf_blocks: int = 0


@dataclass
class FilterReport:
    """Отчёт о фильтрации"""
    total_blocks: int = 0
    after_filtering: int = 0
    
    by_repeat: List[Tuple[str, int]] = field(default_factory=list)  # (текст, количество)
    by_blacklist: List[Tuple[str, int]] = field(default_factory=list)
    by_pattern: List[Tuple[str, int]] = field(default_factory=list)
    
    kept_important: List[str] = field(default_factory=list)
    kept_content: List[str] = field(default_factory=list)


def extract_pdf_blocks_by_page(pdf_path: str) -> List[List[str]]:
    """
    Извлечь текстовые блоки из PDF по страницам
    
    Returns:
        Список страниц, каждая страница - список блоков текста
    """
    if not FITZ_AVAILABLE:
        return []
    
    pages = []
    
    with fitz.open(pdf_path) as doc:
        for page in doc:
            blocks = []
            # Извлекаем текстовые блоки
            text_dict = page.get_text("dict")
            
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Текстовый блок
                    for line in block.get("lines", []):
                        text_parts = []
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                text_parts.append(text)
                        if text_parts:
                            blocks.append(' '.join(text_parts))
            
            pages.append(blocks)
    
    return pages


def extract_structure_pdf(pdf_path: str) -> Tuple[List[Heading], FilterReport]:
    """
    Извлечь структуру из PDF с фильтрацией мусора
    
    Args:
        pdf_path: Путь к PDF
        
    Returns:
        (список заголовков, отчёт о фильтрации)
    """
    report = FilterReport()
    
    # 1. Извлекаем блоки по страницам
    pages = extract_pdf_blocks_by_page(pdf_path)
    
    # Собираем все блоки
    all_blocks = []
    for page_blocks in pages:
        all_blocks.extend(page_blocks)
    
    report.total_blocks = len(all_blocks)
    
    # 2. Определяем колонтитулы (>50% страниц)
    repeat_garbage = detect_headers_footers(pages, threshold_percent=50.0)
    
    # 3. Фильтруем с детальным отчётом
    filter_result = filter_with_report(all_blocks, repeat_garbage)
    
    # 4. Формируем отчёт
    # Группируем по частоте
    repeat_counts = Counter(filter_result["filtered_by_repeat"])
    blacklist_counts = Counter(filter_result["filtered_by_blacklist"])
    pattern_counts = Counter(filter_result["filtered_by_pattern"])
    
    report.by_repeat = [(text, count) for text, count in repeat_counts.most_common()]
    report.by_blacklist = [(text, count) for text, count in blacklist_counts.most_common()]
    report.by_pattern = [(text, count) for text, count in pattern_counts.most_common()]
    
    # Очищаем от markdown якорей для отображения
    def clean(text):
        return re.sub(r'\s*\{#[^}]+\}\s*$', '', text).strip()
    
    report.kept_important = [clean(h) for h in filter_result["kept_important"]]
    report.kept_content = [clean(h) for h in filter_result["kept_content"]]
    
    report.after_filtering = len(report.kept_important) + len(report.kept_content)
    
    # 5. Преобразуем в Heading (все как level=1 для PDF)
    headings = []
    for text in filter_result["kept_important"]:
        headings.append(Heading(text=clean(text), level=1))
    for text in filter_result["kept_content"]:
        headings.append(Heading(text=clean(text), level=2))  # Контент как level=2
    
    return headings, report


def parse_document(pdf_path: str, docx_base_dir: str = None) -> ParseResult:
    """
    Основная функция парсинга документа
    
    Логика:
    1. Ищем пару DOCX для PDF
    2. Если DOCX есть - валидируем
    3. Если валиден - берём структуру из DOCX
    4. Иначе - парсим PDF с фильтрацией
    
    Args:
        pdf_path: Путь к PDF
        docx_base_dir: Базовая директория для поиска DOCX
        
    Returns:
        ParseResult с результатами
    """
    pdf_path = str(pdf_path)
    
    # Извлекаем код документа из имени файла
    doc_code = extract_doc_code(Path(pdf_path).stem) or ""
    
    result = ParseResult(
        source="pdf",
        headings=[],
        doc_code=doc_code,
        pdf_path=pdf_path,
    )
    
    # 1. Ищем DOCX
    docx_path = find_docx_for_pdf(pdf_path, docx_base_dir)
    
    if docx_path and DOCX_AVAILABLE:
        result.docx_path = docx_path
        
        # 2. Валидируем DOCX vs PDF
        validation = validate_docx_vs_pdf(docx_path, pdf_path)
        result.validation = validation
        
        if validation.is_valid:
            # 3. Берём структуру из DOCX
            result.source = "docx"
            result.headings = extract_structure_docx(docx_path)
            
            # 4. Строим иерархию
            result.structure_tree = build_hierarchy(
                headings=[{"text": h.text, "level": h.level} for h in result.headings],
                doc_code=result.doc_code,
                source="docx"
            )
            return result
    
    # 5. Fallback: парсим PDF с фильтрацией
    headings, filter_report = extract_structure_pdf(pdf_path)
    result.headings = headings
    result.total_pdf_blocks = filter_report.total_blocks
    result.filter_report = {
        "total_blocks": filter_report.total_blocks,
        "after_filtering": filter_report.after_filtering,
        "by_repeat": filter_report.by_repeat,
        "by_blacklist": filter_report.by_blacklist,
        "by_pattern": filter_report.by_pattern,
        "kept_important": filter_report.kept_important,
        "kept_content": filter_report.kept_content,
    }
    
    # 6. Строим иерархию
    result.structure_tree = build_hierarchy(
        headings=[{"text": h.text, "level": h.level} for h in result.headings],
        doc_code=result.doc_code,
        source="pdf"
    )
    
    return result


def format_parse_report(result: ParseResult) -> str:
    """
    Форматировать отчёт о парсинге документа
    
    Args:
        result: Результат парсинга
        
    Returns:
        Форматированный текст отчёта
    """
    lines = []
    
    # Заголовок
    lines.append("=" * 70)
    lines.append(f"=== {result.doc_code or Path(result.pdf_path).stem} ===")
    lines.append("=" * 70)
    
    # Источник
    if result.source == "docx":
        lines.append(f"Источник: DOCX (актуален)")
        if result.validation:
            lines.append(f"Валидация: {result.validation.details}")
    else:
        lines.append(f"Источник: PDF (fallback)")
        if result.validation:
            lines.append(f"DOCX найден но не актуален: {result.validation.details}")
        elif result.docx_path:
            lines.append(f"DOCX: не найден")
    
    lines.append("")
    
    # Статистика
    lines.append("СТАТИСТИКА:")
    if result.source == "docx":
        lines.append(f"  Заголовков в DOCX: {len(result.headings)}")
    else:
        report = result.filter_report or {}
        lines.append(f"  Всего блоков в PDF: {report.get('total_blocks', result.total_pdf_blocks)}")
        lines.append(f"  После фильтрации: {report.get('after_filtering', len(result.headings))}")
    
    lines.append("")
    
    # Детали фильтрации (только для PDF)
    if result.source == "pdf" and result.filter_report:
        report = result.filter_report
        
        # По фильтру повторов
        if report.get("by_repeat"):
            lines.append("ВЫКИНУТО ПО ФИЛЬТРУ ПОВТОРОВ (>50% страниц):")
            for text, count in report["by_repeat"][:10]:
                clean_text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text).strip()
                lines.append(f"  {count:3d}x │ \"{clean_text[:45]}\"")
            if len(report["by_repeat"]) > 10:
                lines.append(f"  ... и ещё {len(report['by_repeat']) - 10}")
            lines.append("")
        
        # По чёрному списку
        if report.get("by_blacklist"):
            lines.append("ВЫКИНУТО ПО ЧЁРНОМУ СПИСКУ:")
            for text, count in report["by_blacklist"][:10]:
                clean_text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text).strip()
                lines.append(f"  {count:3d}x │ \"{clean_text[:45]}\"")
            lines.append("")
        
        # По паттернам
        if report.get("by_pattern"):
            lines.append("ВЫКИНУТО ПО ПАТТЕРНАМ:")
            for text, count in report["by_pattern"][:10]:
                clean_text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text).strip()
                lines.append(f"  {count:3d}x │ \"{clean_text[:45]}\"")
            lines.append("")
    
    # Сохранённые заголовки
    lines.append("СОХРАНЕНО (важные разделы):")
    if result.source == "docx":
        for h in result.headings[:15]:
            lines.append(f"  \"{h.text[:55]}\"")
        if len(result.headings) > 15:
            lines.append(f"  ... и ещё {len(result.headings) - 15}")
    else:
        report = result.filter_report or {}
        for text in report.get("kept_important", [])[:10]:
            lines.append(f"  \"{text[:55]}\"")
        
        if report.get("kept_content"):
            lines.append("")
            lines.append("СОХРАНЕНО (контент):")
            for text in report["kept_content"][:10]:
                lines.append(f"  \"{text[:55]}\"")
            if len(report["kept_content"]) > 10:
                lines.append(f"  ... и ещё {len(report['kept_content']) - 10}")
    
    return '\n'.join(lines)


def parse_documents_batch(pdf_paths: List[str], docx_base_dir: str = None, verbose: bool = True) -> List[ParseResult]:
    """
    Пакетный парсинг нескольких документов
    
    Args:
        pdf_paths: Список путей к PDF
        docx_base_dir: Базовая директория для поиска DOCX
        verbose: Выводить прогресс
        
    Returns:
        Список результатов
    """
    results = []
    
    for i, pdf_path in enumerate(pdf_paths, 1):
        if verbose:
            print(f"[{i}/{len(pdf_paths)}] {Path(pdf_path).stem}...")
        
        try:
            result = parse_document(pdf_path, docx_base_dir)
            results.append(result)
            
            if verbose:
                source_info = "DOCX" if result.source == "docx" else "PDF"
                print(f"  → {source_info}: {len(result.headings)} заголовков")
                
        except Exception as e:
            if verbose:
                print(f"  ✗ Ошибка: {e}")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Использование: python hybrid_parser.py <pdf_path> [docx_base_dir]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    docx_base_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = parse_document(pdf_path, docx_base_dir)
    print(format_parse_report(result))
