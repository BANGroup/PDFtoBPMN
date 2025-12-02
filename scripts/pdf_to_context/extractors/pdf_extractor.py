"""
PDF Extractor - экстрактор для PDF документов

Обертка над существующим NativeExtractor + OCR для соответствия
новому унифицированному интерфейсу BaseExtractor.

Применение SOLID:
- Single Responsibility: Только обработка PDF
- Dependency Inversion: Зависимость от BaseExtractor
- Liskov Substitution: Полностью заменяем базовый класс

Автор: PDFtoBPMN Project
Дата: 10.11.2025
"""

from typing import List, Dict, Any, Optional
from pathlib import Path

from .base_extractor import BaseExtractor
from .native_extractor import NativeExtractor
from .ocr_client import OCRClient
from ..core.parser import PDFParser
from ..core.structure_preserver import StructurePreserver
from ..models.data_models import TextBlock, ImageBlock, DrawingBlock, TableBlock, OCRBlock


class PDFExtractor(BaseExtractor):
    """
    Экстрактор для PDF документов
    
    Использует:
    - NativeExtractor для текста, таблиц, графики
    - OCRClient для распознавания изображений (опционально)
    - StructurePreserver для встраивания OCR результатов
    """
    
    def __init__(self,
                 extract_images: bool = True,
                 extract_tables: bool = True,
                 extract_drawings: bool = True,
                 enable_ocr: bool = False,
                 ocr_client: Optional[OCRClient] = None,
                 min_image_area: float = 1000.0,
                 ocr_vector_graphics: bool = True,
                 vector_render_dpi: int = 300):
        """
        Инициализация PDF экстрактора
        
        Args:
            extract_images: Извлекать изображения
            extract_tables: Извлекать таблицы
            extract_drawings: Извлекать векторную графику
            enable_ocr: Включить OCR для изображений
            ocr_client: Клиент OCR сервиса (если enable_ocr=True)
            min_image_area: Минимальная площадь изображения для OCR (px²)
            ocr_vector_graphics: Рендерить векторную графику для OCR
            vector_render_dpi: DPI для рендеринга векторной графики
        """
        super().__init__(extract_images=extract_images, extract_tables=extract_tables)
        
        self.extract_drawings = extract_drawings
        self.enable_ocr = enable_ocr
        self.min_image_area = min_image_area
        
        # Инициализация нативного экстрактора
        self.native_extractor = NativeExtractor(
            extract_images=extract_images,
            extract_drawings=extract_drawings,
            extract_tables=extract_tables,
            render_vectors_to_image=enable_ocr and ocr_vector_graphics,
            vector_render_dpi=vector_render_dpi
        )
        
        # OCR клиент (если включен)
        self.ocr_client = ocr_client if enable_ocr else None
        
        # StructurePreserver для встраивания OCR
        if self.enable_ocr and self.ocr_client:
            self.structure_preserver = StructurePreserver(
                ocr_client=self.ocr_client,
                min_area=min_image_area
            )
        else:
            self.structure_preserver = None
    
    def get_supported_extensions(self) -> List[str]:
        """Поддерживаемые расширения: PDF"""
        return ['.pdf', '.PDF']
    
    def extract_document(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Извлечь весь контент из PDF документа
        
        Args:
            file_path: Путь к PDF файлу
        
        Returns:
            Список страниц с извлеченным контентом
        """
        # Валидация файла
        self.validate_file(file_path)
        self.reset_stats()
        
        pages_data = []
        
        # Открываем PDF
        with PDFParser(file_path) as parser:
            total_pages = parser.get_total_pages()
            self._stats["pages_processed"] = total_pages
            
            # Обрабатываем каждую страницу
            for page_num in range(total_pages):
                page = parser.get_page(page_num)
                
                # Шаг 1: Native extraction
                page_data = self.native_extractor.extract_page(page, file_path)
                
                # Шаг 2: OCR обработка (если включен)
                if self.enable_ocr and self.structure_preserver:
                    # Объединяем все блоки для обработки
                    all_blocks = (
                        page_data.get("text_blocks", []) +
                        page_data.get("image_blocks", []) +
                        page_data.get("drawing_blocks", []) +
                        page_data.get("table_blocks", [])
                    )
                    
                    # Обрабатываем через StructurePreserver
                    processed_blocks = self.structure_preserver.process_structure(
                        all_blocks,
                        page_num
                    )
                    
                    # Разделяем обратно по типам
                    page_data = self._split_blocks_by_type(processed_blocks)
                
                # Добавляем номер страницы
                page_data["page_num"] = page_num
                
                # Обновляем статистику
                self._stats["text_blocks"] += len(page_data.get("text_blocks", []))
                self._stats["image_blocks"] += len(page_data.get("image_blocks", []))
                self._stats["table_blocks"] += len(page_data.get("table_blocks", []))
                
                pages_data.append(page_data)
        
        return pages_data
    
    def _split_blocks_by_type(self, blocks: list) -> dict:
        """
        Разделить блоки обратно по типам
        
        Args:
            blocks: Список блоков (TextBlock, OCRBlock, DrawingBlock, TableBlock)
        
        Returns:
            Dict с ключами: text_blocks, image_blocks, drawing_blocks, table_blocks, ocr_blocks
        """
        result = {
            "text_blocks": [],
            "image_blocks": [],
            "drawing_blocks": [],
            "table_blocks": [],
            "ocr_blocks": []
        }
        
        for block in blocks:
            if isinstance(block, TextBlock):
                result["text_blocks"].append(block)
            elif isinstance(block, OCRBlock):
                result["ocr_blocks"].append(block)
            elif isinstance(block, ImageBlock):
                result["image_blocks"].append(block)
            elif isinstance(block, DrawingBlock):
                result["drawing_blocks"].append(block)
            elif isinstance(block, TableBlock):
                result["table_blocks"].append(block)
        
        return result

