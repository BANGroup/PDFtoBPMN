"""
PDF текстовый экстрактор на основе pdfplumber.

pdfplumber лучше работает с:
- Порядком текста (сверху вниз, слева направо)
- Таблицами (извлекает структуру)
- Колонками

PyMuPDF лучше работает с:
- Изображениями
- Информацией о шрифтах
- Производительностью

Гибридный подход:
- Титульная страница: OCR (текст с битой кодировкой)
- Остальные страницы: pdfplumber (правильный порядок)
"""

import pdfplumber
import fitz  # PyMuPDF для рендеринга титульной в изображение
import requests
import re
import ast
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from scripts.pdf_to_context.extractors.ocr_client import OCRClient
from scripts.pdf_to_context.extractors.native_extractor import NativeExtractor


@dataclass
class PageContent:
    """Контент страницы"""
    page_num: int
    text: str
    tables: List[List[List[str]]]  # Список таблиц, каждая таблица - список строк


def _has_header_footer_markers(text: str) -> bool:
    """Проверить наличие маркеров колонтитула в тексте."""
    if not text:
        return False
    text_lower = text.lower()
    patterns = [
        r'стр\.\s*\d+\s*из\s*\d+',
        r'дата введения изменения',
        r'основание',
    ]
    return any(re.search(p, text_lower) for p in patterns)


def _crop_header_footer(img: "Image.Image",
                        crop_top: bool,
                        crop_bottom: bool,
                        top_ratio: float = 0.08,
                        bottom_ratio: float = 0.08) -> "Image.Image":
    """Обрезать верхнюю и/или нижнюю полосу колонтитула."""
    width, height = img.size
    top = int(height * top_ratio) if crop_top else 0
    bottom = int(height * (1 - bottom_ratio)) if crop_bottom else height
    if bottom <= top:
        return img
    return img.crop((0, top, width, bottom))


def ocr_title_page(pdf_path: str | Path, 
                   ocr_url: str = "http://localhost:8000/ocr/figure",
                   timeout: int = 60,
                   scale: float = 2.0,
                   fallback_scale: float = 1.0,
                   prompt_type: str = "default") -> Optional[str]:
    """
    Распознать титульную страницу через OCR.
    
    Титульные страницы часто имеют текст с битой кодировкой (вектор графика),
    который не читается текстовыми парсерами.
    
    Args:
        pdf_path: Путь к PDF
        ocr_url: URL OCR сервиса
        timeout: Таймаут запроса
    
    Returns:
        Markdown текст титульной страницы или None при ошибке
    """
    if not PIL_AVAILABLE:
        return None
    
    doc = None
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        raw_text = page.get_text() or ""
        
        def render_to_buffer(render_scale: float) -> BytesIO:
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            if _has_header_footer_markers(raw_text):
                img = _crop_header_footer(img, crop_top=True, crop_bottom=True)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=95)
            buffer.seek(0)
            return buffer
        
        # Отправляем на OCR
        def request_ocr(buffer: BytesIO) -> Optional[str]:
            response = requests.post(
                ocr_url,
                files={"file": ("title.jpg", buffer, "image/jpeg")},
                data={"prompt_type": prompt_type},
                timeout=timeout
            )
            if not response.ok:
                return None
            result = response.json()
            markdown = result.get("markdown", "")
            lines = []
            for line in markdown.split('\n'):
                line = line.strip()
                if line and not line.startswith('BASE:') and not line.startswith('NO PATCHES'):
                    lines.append(line)
            title_md = "# ТИТУЛЬНАЯ СТРАНИЦА\n\n"
            title_md += "**ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО «Авиакомпания «ЮТэйр»**\n\n"
            for line in lines:
                if line:
                    title_md += f"{line}\n\n"
            return title_md
        
        try:
            buffer = render_to_buffer(scale)
            title_md = request_ocr(buffer)
            if title_md:
                return title_md
        except Exception as exc:
            print(f"⚠️ Ошибка OCR титульной (scale={scale}): {exc}")
        if fallback_scale and fallback_scale != scale:
            try:
                buffer = render_to_buffer(fallback_scale)
                title_md = request_ocr(buffer)
                if title_md:
                    return title_md
            except Exception as exc:
                print(f"⚠️ Ошибка OCR титульной (scale={fallback_scale}): {exc}")
        return None
    except Exception as e:
        print(f"⚠️ Ошибка OCR титульной: {e}")
        return None
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


def is_title_page_corrupted(pdf_path: str | Path) -> bool:
    """
    Проверить имеет ли титульная страница битую кодировку текста.
    
    Признаки:
    - Текст содержит латинские буквы вместо кириллицы
    - Шрифт Helvetica с WinAnsiEncoding
    """
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        text = page.get_text()[:500]
        doc.close()
        
        # Если текст короткий или содержит много латиницы - скорее всего битая кодировка
        if len(text) < 50:
            return True
        
        # Проверяем соотношение латиницы к кириллице
        import re
        latin = len(re.findall(r'[a-zA-Z]', text))
        cyrillic = len(re.findall(r'[а-яА-ЯёЁ]', text))
        
        # Если латиницы больше 50% - битая кодировка
        if latin > (latin + cyrillic) * 0.5:
            return True
        
        return False
        
    except Exception:
        return False


def extract_text_pdfplumber(pdf_path: str | Path, 
                            skip_first_n_pages: int = 0,
                            ocr_title: bool = True,
                            ocr_url: str = "http://localhost:8000/ocr/figure",
                            ocr_graphics: bool = False,
                            ocr_base_url: str = "http://localhost:8000") -> str:
    """
    Извлечь текст из PDF используя pdfplumber.
    
    Гибридный подход:
    - Титульная страница: OCR (если текст с битой кодировкой)
    - Остальные страницы: pdfplumber (правильный порядок)
    
    Args:
        pdf_path: Путь к PDF файлу
        skip_first_n_pages: Пропустить первые N страниц (титульная и т.д.)
        ocr_title: Использовать OCR для титульной страницы
        ocr_url: URL OCR сервиса
    
    Returns:
        Текст документа в Markdown формате
    """
    markdown_parts = []
    pdf_path = Path(pdf_path)
    
    # Проверяем нужен ли OCR для титульной
    use_ocr_for_title = ocr_title and is_title_page_corrupted(pdf_path)
    ocr_client = OCRClient(base_url=ocr_base_url, max_retries=1, timeout=15) if ocr_graphics else None
    native_extractor = NativeExtractor(
        extract_images=True,
        extract_drawings=True,
        extract_tables=False,
        render_vectors_to_image=bool(ocr_graphics),
        vector_render_dpi=300
    ) if ocr_graphics else None
    fitz_doc = fitz.open(str(pdf_path)) if ocr_graphics else None
    ocr_graphics_active = bool(ocr_graphics and ocr_client and native_extractor and fitz_doc)
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            
            # Титульная страница с OCR
            if i == 0 and use_ocr_for_title:
                markdown_parts.append(f"\n<!-- Страница {page_num} (OCR) -->\n")
                ocr_result = ocr_title_page(pdf_path, ocr_url)
                if ocr_result:
                    markdown_parts.append(ocr_result)
                else:
                    markdown_parts.append("<!-- OCR не удался -->\n")
                continue
            
            if i < skip_first_n_pages:
                markdown_parts.append(f"\n<!-- Страница {page_num} (пропущена) -->\n")
                continue
            
            markdown_parts.append(f"\n<!-- Страница {page_num} -->\n")
            
            # Извлекаем таблицы (если есть) и исключаем их из текста
            found_tables = page.find_tables()
            table_data_list = []
            table_cells = set()
            table_rows = set()
            if found_tables:
                for tbl in found_tables:
                    data = tbl.extract()
                    if data:
                        table_data_list.append(data)
                        for row in data:
                            cells = []
                            for cell in row:
                                cell_norm = _normalize_text(_escape_cell(cell))
                                if cell_norm:
                                    table_cells.add(cell_norm)
                                    cells.append(cell_norm)
                            if cells:
                                table_rows.add(_normalize_text(" ".join(cells)))
            if found_tables:
                filtered_page = _filter_table_chars(page, found_tables)
                text = filtered_page.extract_text()
            else:
                text = page.extract_text()
            if text:
                # Очистка от колонтитулов
                lines = text.split('\n')
                cleaned_lines = []
                
                for line in lines:
                    # Пропускаем колонтитулы
                    if _is_header_footer(line):
                        continue
                    # Убираем дубли из таблиц (строки, совпадающие с ячейками)
                    if found_tables:
                        line_norm = _normalize_text(line)
                        if line_norm in table_cells or line_norm in table_rows:
                            continue
                        if len(line_norm) <= 120:
                            # Если строка состоит из нескольких ячеек, разделенных пробелами
                            for row_text in table_rows:
                                if line_norm == row_text:
                                    break
                            else:
                                # Дополнительная эвристика: строка содержит 2+ значения ячеек
                                hits = 0
                                for cell in table_cells:
                                    if len(cell) < 4:
                                        continue
                                    if cell in line_norm:
                                        hits += 1
                                        if hits >= 2:
                                            break
                                if hits >= 2:
                                    continue
                                cleaned_lines.append(line)
                            continue
                    cleaned_lines.append(line)
                
                # Определяем заголовки
                for line in cleaned_lines:
                    formatted = _format_heading(line)
                    markdown_parts.append(formatted)
            
            # Извлекаем таблицы (если есть)
            if table_data_list:
                for data in table_data_list:
                    if data:
                        markdown_parts.append(_table_to_markdown(data))

            # OCR графики (изображения + векторные схемы)
            if ocr_graphics_active:
                fitz_page = fitz_doc[page_num - 1]
                ocr_chunks = []
                page_area = fitz_page.rect.width * fitz_page.rect.height
                # Растровые изображения
                for image_block in native_extractor.extract_image_blocks(fitz_page):
                    if image_block.bbox.area() / page_area < 0.08:
                        continue
                    try:
                        ocr_response = ocr_client.ocr_image(
                            image_data=image_block.image_data,
                            page_num=page_num,
                            bbox=image_block.bbox,
                            prompt_type="ocr_simple",
                            base_size=1280,
                            image_size=1280
                        )
                    except RuntimeError as exc:
                        print(f"⚠️ OCR image error (page {page_num}): {exc}")
                        ocr_response = None
                        ocr_graphics_active = False
                    if ocr_response:
                        structured = _format_ocr_structure(ocr_response.markdown)
                        if structured:
                            ocr_chunks.append(structured)
                # Векторные схемы (берем только крупные области)
                page_area = fitz_page.rect.width * fitz_page.rect.height
                drawing_blocks = native_extractor.extract_drawing_blocks(
                    fitz_page,
                    render_to_image=False,
                    render_dpi=300
                )
                for drawing_block in drawing_blocks:
                    if drawing_block.bbox.area() / page_area < 0.08:
                        continue
                    if not ocr_graphics_active:
                        break
                    image_bytes = native_extractor._render_region_to_image(
                        fitz_page,
                        drawing_block.bbox,
                        dpi=300
                    )
                    if not image_bytes:
                        continue
                    try:
                        ocr_response = ocr_client.ocr_image(
                            image_data=image_bytes,
                            page_num=page_num,
                            bbox=drawing_block.bbox,
                            prompt_type="ocr_simple",
                            base_size=1280,
                            image_size=1280
                        )
                    except RuntimeError as exc:
                        print(f"⚠️ OCR drawing error (page {page_num}): {exc}")
                        ocr_response = None
                        ocr_graphics_active = False
                    if ocr_response:
                        structured = _format_ocr_structure(ocr_response.markdown)
                        if structured:
                            ocr_chunks.append(structured)
                if ocr_chunks:
                    markdown_parts.append("\n".join(ocr_chunks))
    
    if fitz_doc:
        fitz_doc.close()
    
    return '\n'.join(markdown_parts)


def extract_pages_pdfplumber(pdf_path: str | Path) -> List[PageContent]:
    """
    Извлечь контент постранично.
    
    Args:
        pdf_path: Путь к PDF файлу
    
    Returns:
        Список PageContent для каждой страницы
    """
    pages = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            
            pages.append(PageContent(
                page_num=i + 1,
                text=text,
                tables=tables
            ))
    
    return pages


def _is_header_footer(line: str) -> bool:
    """Проверить является ли строка колонтитулом."""
    line_lower = line.strip().lower()
    
    # Паттерны колонтитулов
    patterns = [
        'стр.',
        'дата введения изменения',
        'дата введения',
        'основание',
        '___'
    ]
    
    # Короткие строки с номером страницы
    if 'из' in line_lower and len(line.strip()) < 20:
        return True
    
    for p in patterns:
        if p in line_lower:
            return True
    
    return False


def _format_heading(line: str) -> str:
    """Форматировать строку как заголовок если нужно."""
    import re
    
    line = line.strip()
    if not line:
        return '\n'
    
    # Нумерованные заголовки: 1, 1.1, 1.1.1, etc.
    # Паттерн: начинается с цифры, может быть точки и цифры, ЗАТЕМ текст с заглавной буквы
    # Исключаем: "9001 «Системы..." - это продолжение предложения
    heading_match = re.match(r'^(\d+(?:\.\d+)*)\s+([А-ЯA-Z].+)$', line)
    if heading_match:
        num = heading_match.group(1)
        title = heading_match.group(2)
        
        # Дополнительная проверка: заголовок должен быть коротким (не целое предложение)
        # и не начинаться со строчной буквы в кавычках
        if title.startswith('«') or len(title) > 150:
            return line + '\n'
        
        level = num.count('.') + 1
        
        # Определяем уровень заголовка markdown
        if level == 1:
            return f'# {num} {title}\n'
        elif level == 2:
            return f'## {num} {title}\n'
        elif level == 3:
            return f'### {num} {title}\n'
        else:
            return f'#### {num} {title}\n'
    
    # Заголовки капсом (ПРЕДИСЛОВИЕ, СОДЕРЖАНИЕ и т.д.)
    # Но не слова типа "ISO", "IATA" и т.д. (короткие)
    if line.isupper() and len(line) > 5 and len(line) < 80:
        # Не должно быть цифр в середине (ГОСТ 9001 - не заголовок)
        if not re.search(r'\d', line):
            return f'# {line}\n'
    
    return line + '\n'


def _escape_cell(cell: Optional[str]) -> str:
    """Экранировать содержимое ячейки для Markdown-таблицы."""
    if cell is None:
        return ' '
    cell_str = str(cell)
    # Экранируем разделители Markdown
    cell_str = cell_str.replace('|', '\\|')
    # Убираем переводы строк внутри ячеек
    cell_str = cell_str.replace('\n', ' ').replace('\r', ' ')
    cell_str = cell_str.strip()
    return cell_str if cell_str else ' '


def _normalize_text(text: str) -> str:
    """Нормализовать пробелы в строке для сравнения."""
    text = text.replace('\u00A0', ' ').replace('\u202F', ' ').replace('\u2009', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _has_cyrillic(text: str) -> bool:
    """Проверить наличие кириллицы в тексте."""
    return re.search(r'[а-яА-ЯёЁ]', text) is not None


def _ocr_markdown_to_text(ocr_markdown: str) -> str:
    """Преобразовать OCR markdown с тегами ref/det в читаемый текст."""
    if not ocr_markdown:
        return ""
    # Убираем служебные строки
    cleaned = []
    for line in ocr_markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("BASE:") or line.startswith("NO PATCHES"):
            continue
        cleaned.append(line)
    ocr_markdown = "\n".join(cleaned)
    matches = re.findall(r'<\|ref\|>(.*?)<\|/ref\|>', ocr_markdown)
    if matches:
        return "\n".join(m.strip() for m in matches if m.strip())
    return ocr_markdown.strip()


def _ocr_markdown_to_lines(ocr_markdown: str) -> list[str]:
    """Сгруппировать OCR элементы по строкам на основе bbox."""
    if not ocr_markdown:
        return []
    pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
    items = []
    for text, det in re.findall(pattern, ocr_markdown):
        try:
            bbox_list = ast.literal_eval(det)
            if not bbox_list:
                continue
            x0, y0, x1, y1 = bbox_list[0]
            items.append({
                "text": text.strip(),
                "x0": float(x0),
                "y0": float(y0),
                "y1": float(y1),
            })
        except Exception:
            continue
    if not items:
        return []
    # Сортируем и группируем по строкам
    items.sort(key=lambda i: (i["y0"], i["x0"]))
    lines = []
    current = []
    current_y = None
    threshold = 18.0
    for item in items:
        y_center = (item["y0"] + item["y1"]) / 2
        if current_y is None or abs(y_center - current_y) <= threshold:
            current.append(item)
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            current.sort(key=lambda i: i["x0"])
            line_text = " ".join(i["text"] for i in current if i["text"])
            if line_text:
                lines.append(line_text)
            current = [item]
            current_y = y_center
    if current:
        current.sort(key=lambda i: i["x0"])
        line_text = " ".join(i["text"] for i in current if i["text"])
        if line_text:
            lines.append(line_text)
    # Убираем дубли
    seen = set()
    unique_lines = []
    for line in lines:
        norm = _normalize_text(line)
        if norm and norm not in seen:
            seen.add(norm)
            unique_lines.append(line)
    return unique_lines


def _ocr_markdown_to_boxes(ocr_markdown: str) -> list[dict]:
    """Сгруппировать OCR элементы в текстовые блоки (боксы)."""
    if not ocr_markdown:
        return []
    pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
    tokens = []
    for text, det in re.findall(pattern, ocr_markdown):
        text = text.strip()
        if len(text) < 2:
            continue
        if not _has_cyrillic(text) and not re.search(r'[A-ZА-Я]{2,}', text):
            continue
        try:
            bbox_list = ast.literal_eval(det)
            if not bbox_list:
                continue
            x0, y0, x1, y1 = bbox_list[0]
            tokens.append({
                "text": text,
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
            })
        except Exception:
            continue
    if not tokens:
        return []

    # 1) Группируем в строки
    tokens.sort(key=lambda t: (t["y0"], t["x0"]))
    lines = []
    current = []
    current_y = None
    line_threshold = 14.0
    for t in tokens:
        y_center = (t["y0"] + t["y1"]) / 2
        if current_y is None or abs(y_center - current_y) <= line_threshold:
            current.append(t)
            current_y = y_center if current_y is None else (current_y + y_center) / 2
        else:
            current.sort(key=lambda i: i["x0"])
            lines.extend(_split_line_segments(current))
            current = [t]
            current_y = y_center
    if current:
        current.sort(key=lambda i: i["x0"])
        lines.extend(_split_line_segments(current))

    # 2) Группируем строки в боксы по вертикальной близости и перекрытию по X
    boxes = []
    lines.sort(key=lambda l: (l["y0"], l["x0"]))
    box = None
    for line in lines:
        if not box:
            box = {
                "lines": [line["text"]],
                "x0": line["x0"],
                "x1": line["x1"],
                "y0": line["y0"],
                "y1": line["y1"],
            }
            continue
        vertical_gap = line["y0"] - box["y1"]
        x_overlap = max(0.0, min(box["x1"], line["x1"]) - max(box["x0"], line["x0"]))
        overlap_ratio = x_overlap / max(1.0, min(box["x1"] - box["x0"], line["x1"] - line["x0"]))
        if vertical_gap <= 12 and overlap_ratio >= 0.6 and (line["y1"] - box["y0"]) <= 120:
            box["lines"].append(line["text"])
            box["x0"] = min(box["x0"], line["x0"])
            box["x1"] = max(box["x1"], line["x1"])
            box["y0"] = min(box["y0"], line["y0"])
            box["y1"] = max(box["y1"], line["y1"])
        else:
            boxes.append(box)
            box = {
                "lines": [line["text"]],
                "x0": line["x0"],
                "x1": line["x1"],
                "y0": line["y0"],
                "y1": line["y1"],
            }
    if box:
        boxes.append(box)

    # 3) Нормализация текста боксов
    normalized = []
    seen = set()
    for b in boxes:
        text = " ".join(b["lines"]).strip()
        text = _normalize_text(text)
        if len(text) < 3:
            continue
        word_count = len([w for w in text.split(" ") if w])
        if word_count < 2 and len(text) < 10 and not text.isupper():
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append({
            "text": text,
            "x0": b["x0"],
            "x1": b["x1"],
            "y0": b["y0"],
            "y1": b["y1"],
        })
    return normalized


def _split_line_segments(line_tokens: list[dict]) -> list[dict]:
    """Разбить строку на сегменты по большим разрывам X."""
    if not line_tokens:
        return []
    segments = []
    current = [line_tokens[0]]
    gap_threshold = 28.0
    for prev, curr in zip(line_tokens, line_tokens[1:]):
        gap = curr["x0"] - prev["x1"]
        if gap > gap_threshold:
            segments.append(_line_segment(current))
            current = [curr]
        else:
            current.append(curr)
    if current:
        segments.append(_line_segment(current))
    return segments


def _line_segment(tokens: list[dict]) -> dict:
    """Сформировать строковый сегмент из списка токенов."""
    text = " ".join(t["text"] for t in tokens).strip()
    return {
        "text": text,
        "x0": min(t["x0"] for t in tokens),
        "x1": max(t["x1"] for t in tokens),
        "y0": min(t["y0"] for t in tokens),
        "y1": max(t["y1"] for t in tokens),
    }


def _format_ocr_structure(ocr_markdown: str) -> str:
    """Сформировать структурированное описание диаграммы из OCR."""
    boxes = _ocr_markdown_to_boxes(ocr_markdown)
    if not boxes:
        return ""
    
    def is_valid_box(text: str) -> bool:
        norm = _normalize_text(text)
        if len(norm) < 3:
            return False
        # Доля кириллицы
        cyr = len(re.findall(r'[а-яА-ЯёЁ]', norm))
        alpha = len(re.findall(r'[a-zA-Zа-яА-ЯёЁ]', norm))
        if alpha == 0 or (cyr / alpha) < 0.6:
            return False
        # Слишком много мусорных символов
        noise = len(re.findall(r'[^а-яА-ЯёЁa-zA-Z0-9\\s.,:;()\\-]', norm))
        if noise / max(1, len(norm)) > 0.2:
            return False
        # Одиночные короткие слова (кроме ключевых)
        words = [w for w in norm.split(" ") if w]
        if len(words) == 1 and len(norm) < 5 and norm.lower() not in {"да", "нет"}:
            return False
        return True
    
    filtered = [b for b in boxes if is_valid_box(b["text"])]
    if not filtered:
        return ""
    boxes = filtered
    max_y = max(b["y1"] for b in boxes)
    min_y = min(b["y0"] for b in boxes)
    height = max(1.0, max_y - min_y)
    split_y = min_y + height / 2
    has_two_lanes = height > 180 and len(boxes) >= 6

    def lane_label(b):
        if not has_two_lanes:
            return "lane"
        return "upper" if (b["y0"] + b["y1"]) / 2 <= split_y else "lower"

    lanes = {"upper": [], "lower": [], "lane": []}
    for b in boxes:
        lanes[lane_label(b)].append(b)

    lines = ["<!-- OCR графики (структурировано) -->", ""]
    lines.append("Элементы:")
    for b in boxes:
        lines.append(f"- {b['text']}")
    lines.append("")

    if has_two_lanes:
        for lane_id, title in [("upper", "Дорожка 1 (верх)"), ("lower", "Дорожка 2 (низ)")]:
            lane_boxes = sorted(lanes[lane_id], key=lambda b: b["x0"])
            if lane_boxes:
                flow = " -> ".join(b["text"] for b in lane_boxes)
                lines.append(f"{title}:")
                lines.append(flow)
                lines.append("")
    else:
        lane_boxes = sorted(lanes["lane"], key=lambda b: b["x0"])
        if lane_boxes:
            flow = " -> ".join(b["text"] for b in lane_boxes)
            lines.append("Последовательность (OCR):")
            lines.append(flow)
            lines.append("")
    return "\n".join(lines)




def _char_in_bbox(char_obj: dict, bbox: tuple[float, float, float, float]) -> bool:
    """Проверить, что символ находится внутри bbox таблицы."""
    x0, top, x1, bottom = bbox
    return (
        char_obj.get("x0", 0) >= x0
        and char_obj.get("x1", 0) <= x1
        and char_obj.get("top", 0) >= top
        and char_obj.get("bottom", 0) <= bottom
    )


def _filter_table_chars(page: pdfplumber.page.Page, tables: list) -> pdfplumber.page.Page:
    """Удалить символы, попадающие в bbox таблиц, чтобы текст не дублировался."""
    table_bboxes = [tbl.bbox for tbl in tables]

    def keep_obj(obj: dict) -> bool:
        if obj.get("object_type") != "char":
            return False
        for bbox in table_bboxes:
            if _char_in_bbox(obj, bbox):
                return False
        return True

    return page.filter(keep_obj)


def _table_to_markdown(table: List[List[str]]) -> str:
    """Конвертировать таблицу в Markdown."""
    if not table or not table[0]:
        return ''
    
    # Фильтруем пустые строки
    table = [row for row in table if any(cell for cell in row if cell)]
    if not table:
        return ''
    
    # Нормализуем количество колонок
    max_cols = max(len(row) for row in table)
    table = [row + [''] * (max_cols - len(row)) for row in table]
    
    md_lines = ['\n']
    
    # Заголовок таблицы
    header = table[0]
    md_lines.append('| ' + ' | '.join(_escape_cell(cell) for cell in header) + ' |')
    md_lines.append('|' + '---|' * len(header))
    
    # Данные
    for row in table[1:]:
        md_lines.append('| ' + ' | '.join(_escape_cell(cell) for cell in row) + ' |')
    
    md_lines.append('\n')
    return '\n'.join(md_lines)


if __name__ == "__main__":
    # Тест
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        text = extract_text_pdfplumber(pdf_path)
        print(text[:5000])
    else:
        print("Использование: python pdfplumber_extractor.py <path_to_pdf>")
