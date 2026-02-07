"""
Native Extractor - нативное извлечение контента из PDF

Использует:
- PyMuPDF (fitz) для текста, изображений, векторной графики
- pdfplumber для таблиц (опционально)

Извлекает контент как набор блоков (TextBlock, ImageBlock, DrawingBlock, TableBlock)
для последующей сборки в IR.

Принципы SOLID:
- Single Responsibility: Только нативное извлечение (не OCR, не IR)
- Dependency Inversion: Зависимость от абстракций (BBox, ContentType)
"""

import fitz  # PyMuPDF
import sys
import os
import contextlib
from typing import List, Optional, Dict, Any
import io
from PIL import Image


@contextlib.contextmanager
def suppress_stderr():
    """
    Подавление stderr на уровне файловых дескрипторов.
    Работает с низкоуровневыми C-библиотеками (PyMuPDF).
    """
    stderr_fd = sys.stderr.fileno()
    # Сохраняем оригинальный stderr
    with os.fdopen(os.dup(stderr_fd), 'wb') as old_stderr:
        # Перенаправляем stderr в /dev/null
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, stderr_fd)
        os.close(devnull_fd)
        try:
            yield
        finally:
            # Восстанавливаем stderr
            sys.stderr.flush()
            os.dup2(old_stderr.fileno(), stderr_fd)

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from ..models.data_models import (
    TextBlock,
    ImageBlock,
    DrawingBlock,
    TableBlock,
    BBox,
    ContentType
)


class NativeExtractor:
    """
    Нативный экстрактор контента из PDF
    
    Ответственность:
    - Извлечение текстовых блоков (с font info)
    - Извлечение растровых изображений
    - Извлечение векторной графики
    - Извлечение таблиц (если pdfplumber доступен)
    
    Не отвечает за:
    - OCR (это делает OCRClient)
    - Построение IR (это делает IRBuilder)
    - Анализ структуры (это делает StructureAnalyzer)
    """
    
    def __init__(self, extract_images: bool = True, 
                 extract_drawings: bool = True,
                 extract_tables: bool = True,
                 min_text_length: int = 1,
                 render_vectors_to_image: bool = False,
                 vector_render_dpi: int = 300):
        """
        Инициализация экстрактора
        
        Args:
            extract_images: Извлекать растровые изображения
            extract_drawings: Извлекать векторную графику
            extract_tables: Извлекать таблицы (требует pdfplumber)
            min_text_length: Минимальная длина текста в блоке
            render_vectors_to_image: Рендерить векторную графику в PNG для OCR
            vector_render_dpi: DPI для рендеринга векторной графики (по умолчанию 300)
        """
        self.extract_images = extract_images
        self.extract_drawings = extract_drawings
        self.extract_tables = extract_tables and PDFPLUMBER_AVAILABLE
        self.min_text_length = min_text_length
        self.render_vectors_to_image = render_vectors_to_image
        self.vector_render_dpi = vector_render_dpi
        
        if extract_tables and not PDFPLUMBER_AVAILABLE:
            print("⚠️  pdfplumber не установлен, таблицы не будут извлекаться")
    
    def _is_header_footer_bbox(self, bbox: BBox, page_height: float) -> bool:
        """
        Проверить, находится ли bbox в зоне колонтитулов.
        
        Используется для исключения OCR по колонтитулам (header/footer).
        """
        header_ratio = 0.08
        footer_ratio = 0.05  # Снижено с 0.08 до 0.05 для уменьшения ложных пропусков текста
        max_band_height_ratio = 0.12
        
        bbox_height = bbox.y1 - bbox.y0
        if bbox_height > page_height * max_band_height_ratio:
            return False
        
        header_limit = page_height * header_ratio
        footer_limit = page_height * (1 - footer_ratio)
        
        if bbox.y1 <= header_limit:
            return True
        if bbox.y0 >= footer_limit:
            return True
        return False
    
    def extract_page(self, page: fitz.Page, 
                     pdf_path: Optional[str] = None) -> Dict[str, List]:
        """
        Извлечь весь контент со страницы
        
        Args:
            page: Объект страницы PyMuPDF
            pdf_path: Путь к PDF (для pdfplumber)
        
        Returns:
            Dict с ключами: text_blocks, image_blocks, drawing_blocks, table_blocks
        """
        page_num = page.number
        
        result = {
            "text_blocks": [],
            "image_blocks": [],
            "drawing_blocks": [],
            "table_blocks": []
        }
        
        # 1. Извлечение текстовых блоков (подавляем предупреждения PyMuPDF)
        with suppress_stderr():
            result["text_blocks"] = self.extract_text_blocks(page)
        
        # 2. Извлечение изображений (подавляем предупреждения PyMuPDF)
        if self.extract_images:
            with suppress_stderr():
                result["image_blocks"] = self.extract_image_blocks(page)
        
        # 3. Извлечение векторной графики (подавляем предупреждения PyMuPDF)
        if self.extract_drawings:
            with suppress_stderr():
                result["drawing_blocks"] = self.extract_drawing_blocks(
                page,
                render_to_image=self.render_vectors_to_image,
                render_dpi=self.vector_render_dpi
            )
        
        # 4. Извлечение таблиц
        if self.extract_tables and pdf_path:
            result["table_blocks"] = self.extract_table_blocks(page, pdf_path)
        
        return result
    
    def extract_text_blocks(self, page: fitz.Page) -> List[TextBlock]:
        """
        Извлечь текстовые блоки со страницы
        
        Использует page.get_text("dict") для получения структурированного текста
        с информацией о шрифтах и координатах.
        
        Args:
            page: Объект страницы
        
        Returns:
            Список TextBlock
        """
        text_blocks = []
        page_num = page.number
        
        # Получаем структурированный текст
        text_dict = page.get_text("dict")
        blocks = text_dict.get("blocks", [])
        
        for block_idx, block in enumerate(blocks):
            # Только текстовые блоки (type=0)
            if block.get("type") != 0:
                continue
            
            # Извлекаем bbox
            bbox_tuple = block.get("bbox")
            if not bbox_tuple:
                continue
            
            bbox = BBox(*bbox_tuple)
            
            # Извлекаем текст из всех линий блока
            lines = block.get("lines", [])
            text_parts = []
            font_sizes = []
            font_names = []
            is_bold = False
            is_italic = False
            
            for line in lines:
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    text_parts.append(span_text)
                    
                    # Информация о шрифте
                    font_size = span.get("size", 0)
                    font_name = span.get("font", "")
                    flags = span.get("flags", 0)
                    
                    font_sizes.append(font_size)
                    font_names.append(font_name)
                    
                    # Флаги: 16=bold, 2=italic (битовая маска)
                    if flags & 16:
                        is_bold = True
                    if flags & 2:
                        is_italic = True
            
            # Собираем текст
            full_text = " ".join(text_parts).strip()
            
            # Фильтруем слишком короткие блоки
            if len(full_text) < self.min_text_length:
                continue
            
            # Определяем преобладающий шрифт и размер
            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else None
            most_common_font = max(set(font_names), key=font_names.count) if font_names else None
            
            text_block = TextBlock(
                bbox=bbox,
                text=full_text,
                page_num=page_num,
                font_name=most_common_font,
                font_size=avg_font_size,
                is_bold=is_bold,
                is_italic=is_italic,
                metadata={"block_idx": block_idx}
            )
            
            text_blocks.append(text_block)
        
        return text_blocks
    
    def extract_image_blocks(self, page: fitz.Page) -> List[ImageBlock]:
        """
        Извлечь растровые изображения со страницы
        
        Args:
            page: Объект страницы
        
        Returns:
            Список ImageBlock
        """
        image_blocks = []
        page_num = page.number
        
        # Получаем список изображений
        images = page.get_images(full=True)
        
        # Debug ВЫКЛЮЧЕН для уменьшения вывода
        # if page_num < 30 and len(images) > 0:
        #     print(f"  [DEBUG] Страница {page_num+1}: найдено {len(images)} изображений через get_images()")
        
        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            
            try:
                # Получаем bbox изображения (используем get_image_rects вместо get_image_bbox)
                rects = page.get_image_rects(xref)
                if not rects or len(rects) == 0:
                    # if page_num < 30:
                    #     print(f"  [DEBUG] Страница {page_num+1}: изображение #{img_idx} xref={xref} - НЕТ bbox!")
                    continue
                
                # Берем первый rect (изображение может встречаться несколько раз на странице)
                bbox_rect = rects[0]
                
                bbox = BBox(bbox_rect.x0, bbox_rect.y0, bbox_rect.x1, bbox_rect.y1)
                
                # Пропускаем колонтитулы (header/footer), чтобы не отправлять в OCR
                if self._is_header_footer_bbox(bbox, page.rect.height):
                    continue
                area = (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)
                
                # Фильтруем маленькие изображения (логотипы, иконки)
                # Минимальный размер: 100x100 пикселей (10000 px²)
                if area < 10000:
                    continue
                
                # Извлекаем данные изображения
                base_image = page.parent.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]  # png, jpeg, etc.
                
                # Определяем размеры и проверяем валидность
                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    # Двойная проверка размера по реальным размерам изображения
                    if width < 100 or height < 100:
                        continue
                        
                except Exception as e:
                    # Изображение повреждено или в неподдерживаемом формате
                    continue
                    
                width, height = pil_image.size
                
                image_block = ImageBlock(
                    bbox=bbox,
                    image_data=image_bytes,
                    format=image_ext,
                    page_num=page_num,
                    width=width,
                    height=height,
                    xref=xref,
                    needs_ocr=True,  # Флаг для StructurePreserver
                    metadata={"img_idx": img_idx}
                )
                
                image_blocks.append(image_block)
                
                # Debug ВЫКЛЮЧЕН
                # if page_num < 30:
                #     print(f"  [DEBUG] ✅ ImageBlock создан: стр={page_num+1}, xref={xref}, area={area:.0f}px², размер={width}x{height}, формат={image_ext}")
                
            except Exception as e:
                # Некоторые изображения могут не извлекаться (встроенные шрифты и т.д.)
                # if page_num < 30:
                #     print(f"  [DEBUG] ❌ Ошибка при создании ImageBlock: стр={page_num+1}, xref={xref}, error={e}")
                continue
        
        return image_blocks
    
    def extract_drawing_blocks(self, page: fitz.Page,
                              render_to_image: bool = False,
                              render_dpi: int = 300) -> List[DrawingBlock]:
        """
        Извлечь векторную графику со страницы
        
        Векторная графика включает: линии, прямоугольники, круги, пути.
        Полезно для диаграмм, формул, схем.
        
        Args:
            page: Объект страницы
            render_to_image: Рендерить векторные блоки в PNG для OCR
            render_dpi: DPI для рендеринга (по умолчанию 300 для качества)
        
        Returns:
            Список DrawingBlock
        """
        drawing_blocks = []
        page_num = page.number
        
        # Получаем все векторные объекты
        drawings = page.get_drawings()
        
        for draw_idx, drawing in enumerate(drawings):
            rect_tuple = drawing.get("rect")
            if not rect_tuple:
                continue
            
            bbox = BBox(*rect_tuple)
            
            # Пропускаем колонтитулы (header/footer) для OCR рендера
            if render_to_image and self._is_header_footer_bbox(bbox, page.rect.height):
                continue
            
            # Сохраняем векторные данные
            drawing_data = {
                "type": drawing.get("type"),  # "l" (line), "re" (rect), "c" (curve)
                "items": drawing.get("items", []),
                "color": drawing.get("color"),
                "width": drawing.get("width"),
                "fill": drawing.get("fill")
            }
            
            # Рендерим в изображение если требуется
            image_data = None
            needs_ocr = False
            
            if render_to_image:
                image_data = self._render_region_to_image(page, bbox, dpi=render_dpi)
                needs_ocr = True if image_data else False
                
                # Отладочный вывод отключен
                # if page_num == 53:  # Индекс 53 = страница 54
                #     print(f"  [DEBUG] Векторный блок #{draw_idx}: area={bbox.area():.0f}px², rendered={image_data is not None}, needs_ocr={needs_ocr}")
            
            drawing_block = DrawingBlock(
                bbox=bbox,
                drawing_data=drawing_data,
                page_num=page_num,
                image_data=image_data,
                needs_ocr=needs_ocr,
                metadata={"draw_idx": draw_idx}
            )
            
            drawing_blocks.append(drawing_block)
        
        return drawing_blocks
    
    def _render_region_to_image(self, page: fitz.Page, bbox: BBox, dpi: int = 300) -> Optional[bytes]:
        """
        Рендерить область страницы в PNG изображение
        
        Args:
            page: Объект страницы
            bbox: Область для рендеринга
            dpi: DPI для рендеринга (влияет на качество)
        
        Returns:
            PNG изображение в байтах или None при ошибке
        """
        try:
            # Создаем Rect из bbox
            clip_rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
            
            # Проверяем, что область валидна
            # Снижен порог с 10 до 1px для поддержки отдельных векторных элементов (линии, стрелки в BPMN)
            if clip_rect.is_empty or clip_rect.width < 1 or clip_rect.height < 1:
                return None
            
            # Рассчитываем zoom для требуемого DPI
            # Стандартное разрешение PDF = 72 DPI
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            # Рендерим область в pixmap
            pix = page.get_pixmap(matrix=mat, clip=clip_rect)
            
            # Конвертируем в PNG bytes
            png_bytes = pix.tobytes("png")
            
            return png_bytes
        
        except Exception as e:
            # Логируем ошибку, но не падаем
            print(f"⚠️  Ошибка рендеринга векторной графики: {e}")
            return None
    
    def extract_table_blocks(self, page: fitz.Page, pdf_path: str) -> List[TableBlock]:
        """
        Извлечь таблицы со страницы (используя pdfplumber)
        
        Args:
            page: Объект страницы PyMuPDF
            pdf_path: Путь к PDF файлу
        
        Returns:
            Список TableBlock
        """
        if not PDFPLUMBER_AVAILABLE:
            return []
        
        table_blocks = []
        page_num = page.number
        
        try:
            # Открываем PDF через pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                plumber_page = pdf.pages[page_num]
                
                # Извлекаем таблицы
                tables = plumber_page.find_tables()
                
                for table_idx, table in enumerate(tables):
                    # Bbox таблицы
                    bbox_tuple = table.bbox
                    bbox = BBox(*bbox_tuple)
                    
                    # Данные таблицы
                    table_data = table.extract()
                    if not table_data:
                        continue
                    
                    rows = len(table_data)
                    cols = len(table_data[0]) if table_data else 0
                    
                    # Конвертируем в HTML (простой формат)
                    html = self._table_to_html(table_data)
                    
                    table_block = TableBlock(
                        bbox=bbox,
                        html=html,
                        rows=rows,
                        cols=cols,
                        page_num=page_num,
                        data=table_data,
                        source="native",
                        metadata={"table_idx": table_idx}
                    )
                    
                    table_blocks.append(table_block)
        
        except Exception as e:
            # pdfplumber может падать на некоторых PDF
            pass
        
        return table_blocks
    
    def _table_to_html(self, table_data: List[List[str]]) -> str:
        """
        Преобразовать табличные данные в HTML
        
        Args:
            table_data: Двумерный массив строк
        
        Returns:
            HTML строка
        """
        if not table_data:
            return ""
        
        html_parts = ["<table>"]
        
        # Первая строка как заголовок
        html_parts.append("<thead><tr>")
        for cell in table_data[0]:
            cell_text = str(cell) if cell else ""
            html_parts.append(f"<th>{cell_text}</th>")
        html_parts.append("</tr></thead>")
        
        # Остальные строки
        html_parts.append("<tbody>")
        for row in table_data[1:]:
            html_parts.append("<tr>")
            for cell in row:
                cell_text = str(cell) if cell else ""
                html_parts.append(f"<td>{cell_text}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody>")
        
        html_parts.append("</table>")
        
        return "".join(html_parts)
    
    def __repr__(self) -> str:
        """Строковое представление"""
        features = []
        if self.extract_images:
            features.append("images")
        if self.extract_drawings:
            features.append("drawings")
        if self.extract_tables:
            features.append("tables")
        
        return f"NativeExtractor(features={', '.join(features)})"


