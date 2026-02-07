#!/usr/bin/env python3
"""
Полный парсинг документов с иерархической структурой.

Извлекает:
1. Полный текст документа (native + OCR)
2. Строит иерархическое дерево по нумерации пунктов
3. Присваивает контент каждому узлу дерева
4. Генерирует полный MD с текстом всех пунктов
"""

import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.pdf_to_context.pipeline import PDFToContextPipeline
from scripts.document_graph.hierarchy_builder import (
    DocumentTree,
    SectionNode,
    build_hierarchy,
    flatten_tree,
    parse_section_number,
    export_tree_json,
)
from scripts.document_graph.hybrid_parser import (
    parse_document,
    extract_doc_code,
)

# Альтернативный экстрактор (лучше порядок текста)
try:
    from scripts.document_graph.pdfplumber_extractor import extract_text_pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


@dataclass
class FullParseResult:
    """Результат полного парсинга"""
    doc_code: str
    source: str  # "pdf" или "docx"
    full_markdown: str  # Полный текст документа
    tree: DocumentTree  # Иерархия с контентом
    stats: Dict


def clean_markdown(markdown: str) -> str:
    """
    Очистка markdown от мусора.
    
    Удаляет:
    - Колонтитулы (Дата введения... Стр. X из Y)
    - Повторяющиеся названия документа в колонтитулах
    - Мусор от титульных страниц (векторная графика с битой кодировкой)
    - OCR мусор из схем и таблиц
    - Пустые строки подряд
    """
    lines = markdown.split('\n')
    cleaned = []
    skip_change_log = False
    heading_pattern = r'^(?:#{1,6}\s+|\d+(?:\.\d+)*\s+)'
    change_log_pattern = r'лист регистрации внесения изменений'
    
    # Паттерны для удаления
    garbage_patterns = [
        # Колонтитулы
        r'^Дата введения изменения.*Стр\.\s*\d+\s*из\s*\d+',
        r'^Стр\.\s*\d+\s*из\s*\d+',
        r'^Дата введения изменения',
        r'^Основание:?',
        r'^#\s+.*ДП-[А-Яа-я0-9.-]+\s*\{#',  # Название документа в колонтитуле
        r'^#\s+[А-Яа-я\s]+\s+ДП-[А-Яа-я0-9.-]+\s*\{#',
        
        # Мусор от титульных страниц (векторная графика с битой кодировкой)
        r'^#{1,6}\s*TIYBIII',  # "ПУБЛИЧНОЕ" с битой кодировкой
        r'^#{1,6}\s*AKUI4OHEP',  # "АКЦИОНЕРНОЕ" с битой кодировкой
        r'^#{1,6}\s*YTBEPx',  # "УТВЕРЖДЕНА" с битой кодировкой
        r'^#{1,6}\s*CI4CTEMA',  # "СИСТЕМА" с битой кодировкой
        r'^#{1,6}\s*AII-\d',  # "ДП-" с битой кодировкой
        r'^#{1,6}\s*<<An\s*u',  # "Авиакомпания" с битой кодировкой
        r'^#{1,6}\s*flara',  # "Дата" с битой кодировкой
        r'^#{1,6}\s*lpr4Ka3oM',  # "приказом" с битой кодировкой
        r'^#{1,6}\s*reHepanbHofo',  # "генерального" с битой кодировкой
        r'^#{1,6}\s*Ar\{peKTopa',  # "директора" с битой кодировкой
        r'^#{1,6}\s*rlaprepnbre',  # "Чартерные" с битой кодировкой
        r'^#{1,6}\s*peficrr',  # "рейсы" с битой кодировкой
        r'^#{1,6}\s*Xanrsr-M',  # "Ханты-Мансийск" с битой кодировкой
        r'^#{1,6}\s*OEIUECTB',  # "ОБЩЕСТВО" с битой кодировкой
        r'^r\.\s*X[a-z]',  # "г. Ханты..." с битой кодировкой
        r'TIYBIII',  # В любом месте строки
        r'AKUI4OHEP',
        r'OEIUECTB\s*O',
        
        # OCR мусор из схем и таблиц
        r'^#\s+(НЕ\s+ВЫПОЛ|ДА\s+НЕТ|ДЕЙСТВИЙ|ПРОДАЖА|Необходимость|ПРИМЕЧАН|РЕАЛИЗАЦИЯ|КОМПОНОВКА|ТИП\s+ВС|ДАТА/ВРЕМЯ|МАРШРУТ)',
        r'^#\s+ТЕХНИЧЕСКИЙ\s+ДИРЕКТОРАТ',
        
        # OCR артефакты (смешанная латиница/кириллица - признак битой кодировки)
        r'^[A-Z]{3,}[а-яА-Я]',  # Латиница потом кириллица
        r'^[а-яА-Я]+[A-Z]{3,}',  # Кириллица потом латиница (если не email)
        
        # Короткие бессмысленные строки
        r'^#?\s*[а-яА-Я]{1,3}$',  # 1-3 буквы
        r'^#?\s*[нных|ых|х|№]+$',  # Обрезки от таблиц
        r'^#?\s*ние$',  # "Изменение" обрезанное
        r'^#?\s*Измене$',
        
        # Email в заголовке
        r'^#\s+[а-яА-Я\w.]+@',
        
        # Телефоны как заголовки
        r'^#?\s*\(\d+\)\s*\d+',
    ]
    
    for line in lines:
        skip = False
        line_stripped = line.strip()
        
        # Пропускаем весь раздел "ЛИСТ РЕГИСТРАЦИИ ВНЕСЕНИЯ ИЗМЕНЕНИЙ"
        if skip_change_log:
            if re.match(heading_pattern, line_stripped, re.IGNORECASE):
                skip_change_log = False
            else:
                continue
        
        if re.search(change_log_pattern, line_stripped, re.IGNORECASE):
            skip_change_log = True
            continue
        
        # Проверка по паттернам
        for pattern in garbage_patterns:
            if re.match(pattern, line_stripped, re.IGNORECASE):
                skip = True
                break
        
        # Дополнительная проверка: строки с высоким % нестандартной латиницы
        if not skip and line_stripped:
            # Считаем символы
            latin_chars = len(re.findall(r'[a-zA-Z]', line_stripped))
            cyrillic_chars = len(re.findall(r'[а-яА-ЯёЁ]', line_stripped))
            total_alpha = latin_chars + cyrillic_chars
            
            # Если > 50% латиницы и при этом есть кириллические символы рядом с латиницей
            # (признак битой кодировки) - это мусор
            if total_alpha > 10 and latin_chars > total_alpha * 0.6:
                # Исключаем нормальные паттерны: коды документов, email, авиационные термины
                if not re.search(
                    r'(ДП-|РК|СТО|КД-|РД-|ИОТ-|'
                    r'ISO|IATA|ICAO|DCS|PNL|MVT|LDM|APIS|'
                    r'EASA|FAA|MEL|CDL|SB|AD|AMP|MRB|RVSM|ETOPS|'
                    r'MMEL|MPD|CMM|IPC|AMM|TSM|FIM|WDM|SRM|'
                    r'AMOS|SAP|ERP|CRM|SMS|QMS|EFB|OCC|AOC|'
                    r'NOTAM|SIGMET|METAR|TAF|RVR|ILS|VOR|NDB|DME|'
                    r'PIC|SIC|FE|LAE|TRE|TRI|SFI|SFE|'
                    r'Boeing|Airbus|ATR|Bombardier|Embraer|'
                    r'B737|B767|A320|CRJ|DHC|'
                    r'UTC|GMT|MSK|'
                    r'@|http|www\.)',
                    line_stripped
                ):
                    skip = True
        
        if not skip:
            cleaned.append(line)
    
    # Убираем множественные пустые строки
    result = []
    prev_empty = False
    for line in cleaned:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        result.append(line)
        prev_empty = is_empty
    
    return '\n'.join(result)


def extract_sections_from_markdown(markdown: str) -> Dict[str, str]:
    """
    Разбить Markdown на секции по нумерации.
    
    Ищет паттерны типа:
    ## 5.1 Заголовок
    или
    **5.1** Заголовок
    или
    5.1 Заголовок (в начале строки)
    
    Returns:
        Dict: {номер_пункта: контент}
    """
    # Сначала чистим от мусора
    markdown = clean_markdown(markdown)
    
    sections = {}
    
    # Паттерн для поиска нумерованных секций
    # Ищем: число.число (и так далее) в начале строки
    section_pattern = r'^(?:#{1,6}\s+)?(?:\*\*)?(\d+(?:\.\d+)*)\**\s+(.+?)$'
    
    lines = markdown.split('\n')
    current_num = None
    current_content = []
    
    for line in lines:
        # Проверяем, это новая секция?
        match = re.match(section_pattern, line)
        if match:
            # Сохраняем предыдущую секцию
            if current_num and current_content:
                # Включаем заголовок в контент
                sections[current_num] = '\n'.join(current_content).strip()
            
            # Начинаем новую секцию
            current_num = match.group(1)
            current_content = [line]
        else:
            # Продолжаем текущую секцию
            current_content.append(line)
    
    # Сохраняем последнюю секцию
    if current_num and current_content:
        sections[current_num] = '\n'.join(current_content).strip()
    
    return sections


def assign_content_to_tree(tree: DocumentTree, sections: Dict[str, str]) -> None:
    """
    Присвоить контент узлам дерева.
    
    Args:
        tree: Дерево структуры
        sections: Словарь {номер: контент}
    """
    nodes = flatten_tree(tree.root)
    assigned = 0
    
    for node in nodes:
        if node.num in sections:
            node.content = sections[node.num]
            assigned += 1
            
            # Определяем is_actionable
            node.is_actionable = _check_actionable(node.content)
            if node.is_actionable:
                tree.actionable_sections += 1
    
    print(f"   📝 Присвоен контент: {assigned}/{len(nodes)} узлов")


def _check_actionable(content: str) -> bool:
    """Проверка, содержит ли пункт действие"""
    action_keywords = [
        r'несет\s+ответственность',
        r'обязан[ыа]?\b',
        r'должен\b',
        r'должны\b',
        r'выполняет',
        r'осуществляет',
        r'проводит',
        r'обеспечивает',
        r'контролирует',
        r'согласовывает',
        r'утверждает',
        r'направляет',
        r'представляет',
        r'информирует',
        r'несёт\s+ответственность',
    ]
    
    content_lower = content.lower()
    for keyword in action_keywords:
        if re.search(keyword, content_lower):
            return True
    return False


def parse_document_full(
    pdf_path: str,
    enable_ocr: bool = True,
    ocr_base_url: str = "http://localhost:8000",
    use_pdfplumber: bool = False
) -> FullParseResult:
    """
    Полный парсинг документа.
    
    1. Извлекает полный текст через PDFToContextPipeline или pdfplumber
    2. Строит иерархию заголовков
    3. Присваивает контент каждому узлу
    
    Args:
        pdf_path: Путь к PDF
        enable_ocr: Использовать OCR для картинок
        ocr_base_url: URL OCR сервиса
        use_pdfplumber: Использовать pdfplumber (лучший порядок текста)
    
    Returns:
        FullParseResult
    """
    pdf_path = Path(pdf_path)
    doc_code = extract_doc_code(str(pdf_path))
    
    print(f"\n{'='*60}")
    print(f"📄 Полный парсинг: {pdf_path.name}")
    print(f"{'='*60}")
    
    # 1. Извлечение полного текста
    print("\n🔍 Этап 1: Извлечение полного текста...")
    
    if use_pdfplumber and PDFPLUMBER_AVAILABLE:
        # pdfplumber - лучше порядок текста, OCR только для титульной
        print("   📘 Используем pdfplumber (лучший порядок текста)")
        if enable_ocr:
            print("   🧾 OCR для титульной страницы: включен")
        else:
            print("   🧾 OCR для титульной страницы: отключен")
        full_markdown = extract_text_pdfplumber(
            str(pdf_path),
            ocr_title=enable_ocr,
            ocr_url=f"{ocr_base_url}/ocr/figure",
            ocr_graphics=enable_ocr,
            ocr_base_url=ocr_base_url
        )
    else:
        # PDFToContextPipeline - поддерживает OCR
        if use_pdfplumber and not PDFPLUMBER_AVAILABLE:
            print("   ⚠️ pdfplumber не установлен, используем PyMuPDF")
        
        pipeline = PDFToContextPipeline(
            ocr_base_url=ocr_base_url,
            enable_ocr=enable_ocr,
            extract_images=True,
            extract_drawings=True,
            extract_tables=True,
            include_frontmatter=False,  # Без frontmatter для чистого текста
            include_toc=False,  # Без оглавления
        )
        
        full_markdown = pipeline.process(str(pdf_path))
    
    print(f"   ✅ Извлечено {len(full_markdown)} символов")
    
    # 2. Получаем заголовки через hybrid_parser (для структуры)
    print("\n🏗️ Этап 2: Построение иерархии...")
    
    parse_result = parse_document(str(pdf_path))
    
    # Сортируем заголовки по номеру пункта ПЕРЕД построением дерева
    headings_list = [{"text": h.text, "level": h.level} for h in parse_result.headings]
    
    def heading_sort_key(h):
        text = h.get("text", "")
        num, level, title, stype = parse_section_number(text)
        if not num:
            return ((0,), text)  # Служебные в начало - tuple для консистентности
        return (_sort_key_for_section(num), text)
    
    sorted_headings = sorted(headings_list, key=heading_sort_key)
    
    # Строим дерево из отсортированных заголовков
    tree = build_hierarchy(
        headings=sorted_headings,
        doc_code=doc_code,
        source=parse_result.source
    )
    
    print(f"   ✅ Построено дерево: {tree.total_sections} узлов, глубина {tree.max_depth}")
    
    # 3. Разбиваем markdown на секции
    print("\n📋 Этап 3: Разбиение на секции...")
    
    sections = extract_sections_from_markdown(full_markdown)
    print(f"   ✅ Найдено {len(sections)} секций по нумерации")
    
    # 4. Присваиваем контент узлам
    print("\n🔗 Этап 4: Присвоение контента...")
    
    assign_content_to_tree(tree, sections)
    
    # Статистика
    stats = {
        "total_chars": len(full_markdown),
        "total_sections": tree.total_sections,
        "sections_with_content": sum(1 for n in flatten_tree(tree.root) if n.content),
        "actionable_sections": tree.actionable_sections,
        "max_depth": tree.max_depth,
    }
    
    print(f"\n📊 Статистика:")
    print(f"   Символов: {stats['total_chars']:,}")
    print(f"   Узлов в дереве: {stats['total_sections']}")
    print(f"   С контентом: {stats['sections_with_content']}")
    print(f"   Actionable: {stats['actionable_sections']}")
    
    return FullParseResult(
        doc_code=doc_code,
        source=parse_result.source,
        full_markdown=full_markdown,
        tree=tree,
        stats=stats
    )


def _sort_key_for_section(num: str) -> Tuple:
    """
    Ключ сортировки для номера секции.
    
    "5.1.2" -> (5, 1, 2)
    "Приложение 1" -> (9999, 1)  # Приложения в конец
    "" -> (0,)  # Служебные в начало
    """
    if not num:
        return (0,)
    
    # Приложения - в конец
    if num.lower().startswith('приложение'):
        match = re.search(r'(\d+)', num)
        if match:
            return (9999, int(match.group(1)))
        return (9999, 0)
    
    # Обычная нумерация
    parts = []
    for part in num.split('.'):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def generate_full_structure_md(result: FullParseResult) -> str:
    """
    Генерация полного MD с иерархической структурой и контентом.
    Секции сортируются по номеру пункта.
    """
    lines = [
        f"# {result.doc_code}",
        "",
        f"**Источник:** {result.source.upper()}",
        f"**Разделов:** {result.tree.total_sections}",
        f"**С контентом:** {result.stats['sections_with_content']}",
        f"**Actionable:** {result.stats['actionable_sections']}",
        f"**Макс. глубина:** {result.tree.max_depth}",
        "",
        "---",
        "",
    ]
    
    def render_node(node: SectionNode, level: int = 1):
        if node.id == "root":
            # Сортируем детей по номеру
            sorted_children = sorted(node.children, key=lambda n: _sort_key_for_section(n.num))
            for child in sorted_children:
                render_node(child, 1)
            return
        
        # Заголовок с нумерацией
        header_level = min(level + 1, 6)  # Максимум h6
        num_part = f"{node.num} " if node.num else ""
        marker = "📌 " if node.is_actionable else ""
        
        lines.append(f"{'#' * header_level} {marker}{num_part}{node.title}")
        lines.append("")
        
        # Контент (если есть)
        if node.content:
            # Убираем повторение заголовка из контента
            content = node.content
            # Убираем первую строку если она совпадает с заголовком
            first_line_match = re.match(r'^(?:#{1,6}\s+)?(?:\*\*)?[\d.]+\**\s+.+$', content.split('\n')[0])
            if first_line_match:
                content = '\n'.join(content.split('\n')[1:]).strip()
            
            if content:
                lines.append(content)
                lines.append("")
        
        # Рекурсивно для детей (сортированных)
        sorted_children = sorted(node.children, key=lambda n: _sort_key_for_section(n.num))
        for child in sorted_children:
            render_node(child, level + 1)
    
    render_node(result.tree.root)
    
    return '\n'.join(lines)


def process_documents(
    pdf_paths: List[str],
    output_dir: Path,
    enable_ocr: bool = True,
    ocr_base_url: str = "http://localhost:8000",
    use_pdfplumber: bool = False
) -> None:
    """
    Обработка нескольких документов.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    extractor = "pdfplumber" if use_pdfplumber else "PyMuPDF"
    
    print(f"\n{'='*60}")
    print(f"🚀 ПОЛНЫЙ ПАРСИНГ: {len(pdf_paths)} документов")
    print(f"   Экстрактор: {extractor}")
    if use_pdfplumber:
        print(f"   OCR титульной: {'✅ Включен' if enable_ocr else '❌ Отключен'}")
    else:
        print(f"   OCR: {'✅ Включен' if enable_ocr else '❌ Отключен'}")
    print(f"   Output: {output_dir}")
    print(f"{'='*60}")
    
    results = []
    
    for i, pdf_path in enumerate(pdf_paths, 1):
        print(f"\n[{i}/{len(pdf_paths)}] ", end="")
        
        try:
            result = parse_document_full(
                pdf_path,
                enable_ocr=enable_ocr,
                ocr_base_url=ocr_base_url,
                use_pdfplumber=use_pdfplumber
            )
            results.append(result)
            
            # Создаём папку для документа
            doc_dir = output_dir / f"{i:02d}_{result.doc_code}"
            doc_dir.mkdir(exist_ok=True)
            
            # Сохраняем полный markdown (очищенный)
            cleaned_markdown = clean_markdown(result.full_markdown)
            with open(doc_dir / "full_content.md", "w", encoding="utf-8") as f:
                f.write(cleaned_markdown)
            
            # Сохраняем структурированный markdown
            structure_md = generate_full_structure_md(result)
            with open(doc_dir / "structure.md", "w", encoding="utf-8") as f:
                f.write(structure_md)
            
            # Сохраняем дерево в JSON
            export_tree_json(result.tree, doc_dir / "structure_tree.json")
            
            # Сохраняем статистику
            with open(doc_dir / "stats.json", "w", encoding="utf-8") as f:
                json.dump(result.stats, f, ensure_ascii=False, indent=2)
            
            print(f"   💾 Сохранено в {doc_dir.name}/")
            
        except Exception as e:
            print(f"\n   ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    # Общая статистика
    print(f"\n{'='*60}")
    print(f"✅ ЗАВЕРШЕНО: {len(results)}/{len(pdf_paths)} документов")
    print(f"{'='*60}")


def find_test_documents(input_dir: Path, limit: int = 8, all_pdfs: bool = False) -> List[Path]:
    """Найти PDF документы для тестирования"""
    pdfs = []
    
    for pdf_dir in sorted(input_dir.glob("**/pdf/*")):
        if pdf_dir.is_dir():
            for pdf_file in pdf_dir.glob("*.pdf"):
                if not all_pdfs and "Эталон для печати" not in pdf_file.name:
                    continue
                pdfs.append(pdf_file)
                if limit > 0 and len(pdfs) >= limit:
                    return pdfs
    
    return pdfs


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Полный парсинг документов с иерархией")
    parser.add_argument("--limit", type=int, default=8, help="Количество документов (0 = без ограничения)")
    parser.add_argument("--all-pdfs", action="store_true", help="Обрабатывать все PDF, не только 'Эталон для печати'")
    parser.add_argument("--no-ocr", action="store_true", help="Отключить OCR")
    parser.add_argument("--pdfplumber", action="store_true", 
                       help="Использовать pdfplumber (лучший порядок текста, OCR только титульной)")
    parser.add_argument("--input", type=str, default="/home/budnik_an/Obligations/input2",
                       help="Директория с документами")
    parser.add_argument("--output", type=str, default="/home/budnik_an/Obligations/output3/full_parse",
                       help="Директория для результатов")
    
    args = parser.parse_args()
    
    # Находим документы
    pdfs = find_test_documents(Path(args.input), args.limit, all_pdfs=args.all_pdfs)
    
    if not pdfs:
        print("❌ PDF документы не найдены")
        sys.exit(1)
    
    print(f"📄 Найдено {len(pdfs)} документов")
    for pdf in pdfs:
        print(f"   - {pdf.name}")
    
    # Запускаем обработку
    process_documents(
        [str(p) for p in pdfs],
        Path(args.output),
        enable_ocr=not args.no_ocr,
        use_pdfplumber=args.pdfplumber
    )
