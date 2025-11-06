"""
IR Builder - построение промежуточного представления (IR)

Объединяет результаты из разных источников:
- Native extraction (TextBlock, ImageBlock, DrawingBlock, TableBlock)
- OCR (OCRBlock)

В единое промежуточное представление (IR) с:
- Унифицированными блоками (IRBlock)
- Связями между блоками (IRRelation)
- Метаданными документа

Принципы SOLID:
- Single Responsibility: Только построение IR
- Open/Closed: Легко добавлять новые типы блоков
"""

from typing import List, Dict, Any, Optional
import uuid

from ..models.data_models import (
    TextBlock,
    ImageBlock,
    DrawingBlock,
    TableBlock,
    OCRBlock,
    ContentType,
    BBox
)
from .models import IR, IRBlock, IRRelation, DocumentMetadata


class IRBuilder:
    """
    Построитель промежуточного представления (IR)
    
    Ответственность:
    - Конвертация блоков из разных источников в IRBlock
    - Определение связей между блоками (reading order)
    - Сборка итогового IR объекта
    
    Не отвечает за:
    - Извлечение контента (это делают extractors)
    - Анализ структуры (это делает StructureAnalyzer)
    - Форматирование вывода (это делает MarkdownFormatter)
    """
    
    def __init__(self):
        """Инициализация builder"""
        self._block_counter = 0
    
    def build_ir(self, 
                 extracted_data: List[Dict[str, Any]],
                 document_metadata: DocumentMetadata) -> IR:
        """
        Построить IR из извлеченных данных
        
        Args:
            extracted_data: Список словарей с данными по страницам
                            Каждый элемент содержит:
                            {
                                "text_blocks": [...],
                                "image_blocks": [...],
                                "drawing_blocks": [...],
                                "table_blocks": [...],
                                "ocr_blocks": [...]
                            }
            document_metadata: Метаданные документа
        
        Returns:
            IR: Промежуточное представление документа
        """
        all_blocks = []
        
        # Конвертируем все блоки из всех страниц
        for page_data in extracted_data:
            # Native блоки
            for text_block in page_data.get("text_blocks", []):
                ir_block = self._convert_text_block(text_block)
                all_blocks.append(ir_block)
            
            for image_block in page_data.get("image_blocks", []):
                ir_block = self._convert_image_block(image_block)
                all_blocks.append(ir_block)
            
            # ❌ Векторная графика не нужна в MD - это только рамки, линии, декор
            # for drawing_block in page_data.get("drawing_blocks", []):
            #     ir_block = self._convert_drawing_block(drawing_block)
            #     all_blocks.append(ir_block)
            
            for table_block in page_data.get("table_blocks", []):
                ir_block = self._convert_table_block(table_block)
                all_blocks.append(ir_block)
            
            # OCR блоки
            for ocr_block in page_data.get("ocr_blocks", []):
                ir_block = self._convert_ocr_block(ocr_block)
                all_blocks.append(ir_block)
        
        # Определяем связи (reading order)
        relations = self._build_relations(all_blocks)
        
        # Обновляем статистику в метаданных
        document_metadata.processing_stats = {
            "total_blocks": len(all_blocks),
            "native_blocks": len([b for b in all_blocks if b.source == "native"]),
            "ocr_blocks": len([b for b in all_blocks if b.source == "ocr"]),
            "blocks_by_type": self._count_by_type(all_blocks)
        }
        
        # Создаем IR
        ir = IR(
            blocks=all_blocks,
            relations=relations,
            document_metadata=document_metadata
        )
        
        return ir
    
    def _convert_text_block(self, text_block: TextBlock) -> IRBlock:
        """Конвертация TextBlock в IRBlock"""
        block_id = self._generate_id("text")
        
        return IRBlock(
            id=block_id,
            type=text_block.type,
            content=text_block.text,
            page=text_block.page_num + 1,  # Переводим в 1-based индексацию
            bbox=text_block.bbox,
            source="native",
            confidence=None,
            metadata={
                "font_name": text_block.font_name,
                "font_size": text_block.font_size,
                "is_bold": text_block.is_bold,
                "is_italic": text_block.is_italic,
                **text_block.metadata
            }
        )
    
    def _convert_image_block(self, image_block: ImageBlock) -> IRBlock:
        """Конвертация ImageBlock в IRBlock"""
        block_id = self._generate_id("image")
        
        # ❌ НЕ ВСТАВЛЯЕМ BASE64 В MD - это создает бинарный мусор!
        # ✅ Используем текстовый placeholder
        content = f"[Изображение: {image_block.format.upper()}, {image_block.width}x{image_block.height}px]"
        
        return IRBlock(
            id=block_id,
            type=ContentType.IMAGE,
            content=content,
            page=image_block.page_num + 1,
            bbox=image_block.bbox,
            source="native",
            confidence=None,
            metadata={
                "format": image_block.format,
                "width": image_block.width,
                "height": image_block.height,
                "xref": image_block.xref,
                **image_block.metadata
            }
        )
    
    def _convert_drawing_block(self, drawing_block: DrawingBlock) -> IRBlock:
        """Конвертация DrawingBlock в IRBlock"""
        block_id = self._generate_id("drawing")
        
        # Для векторной графики сохраняем описание
        drawing_data = drawing_block.drawing_data
        content = f"[Векторная графика: {drawing_data.get('type', 'unknown')}]"
        
        return IRBlock(
            id=block_id,
            type=ContentType.VECTOR,
            content=content,
            page=drawing_block.page_num + 1,
            bbox=drawing_block.bbox,
            source="native",
            confidence=None,
            metadata={
                "drawing_data": drawing_data,
                **drawing_block.metadata
            }
        )
    
    def _convert_table_block(self, table_block: TableBlock) -> IRBlock:
        """Конвертация TableBlock в IRBlock"""
        block_id = self._generate_id("table")
        
        # Для таблиц content = HTML или Markdown table
        content = table_block.html
        
        return IRBlock(
            id=block_id,
            type=ContentType.TABLE,
            content=content,
            page=table_block.page_num + 1,
            bbox=table_block.bbox,
            source=table_block.source,
            confidence=None,
            metadata={
                "rows": table_block.rows,
                "cols": table_block.cols,
                "data": table_block.data,
                **table_block.metadata
            }
        )
    
    def _convert_ocr_block(self, ocr_block: OCRBlock) -> IRBlock:
        """Конвертация OCRBlock в IRBlock"""
        # OCR блоки уже имеют ID
        block_id = ocr_block.id if ocr_block.id else self._generate_id("ocr")
        
        return IRBlock(
            id=block_id,
            type=ocr_block.type,
            content=ocr_block.content,
            page=ocr_block.page_num + 1,
            bbox=ocr_block.bbox,
            source="ocr",
            confidence=ocr_block.confidence,
            metadata=ocr_block.metadata
        )
    
    def _build_relations(self, blocks: List[IRBlock]) -> List[IRRelation]:
        """
        Построить связи между блоками
        
        Основная связь: reading_order (порядок чтения)
        Определяется сортировкой по: страница → Y (сверху вниз) → X (слева направо)
        
        Args:
            blocks: Список IRBlock
        
        Returns:
            Список IRRelation
        """
        relations = []
        
        # Сортируем блоки в порядке чтения
        sorted_blocks = sorted(blocks, key=lambda b: b.get_position_key())
        
        # Создаем связи reading_order между последовательными блоками
        for i in range(len(sorted_blocks) - 1):
            current = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]
            
            relation = IRRelation(
                type="reading_order",
                from_id=current.id,
                to_id=next_block.id,
                metadata={"sequence": i}
            )
            relations.append(relation)
        
        # TODO: В будущем можно добавить другие типы связей:
        # - caption_of: связь подписи с рисунком/таблицей
        # - nested_in: вложенность элементов
        # - reference: ссылки между элементами
        
        return relations
    
    def _generate_id(self, prefix: str) -> str:
        """
        Генерация уникального ID для блока
        
        Args:
            prefix: Префикс (text, image, table, etc.)
        
        Returns:
            Уникальный ID
        """
        self._block_counter += 1
        # Формат: prefix_counter_uuid_short
        short_uuid = str(uuid.uuid4())[:8]
        return f"{prefix}_{self._block_counter}_{short_uuid}"
    
    def _count_by_type(self, blocks: List[IRBlock]) -> Dict[str, int]:
        """
        Подсчет блоков по типам
        
        Args:
            blocks: Список блоков
        
        Returns:
            Словарь {type: count}
        """
        counts = {}
        for block in blocks:
            type_name = block.type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts
    
    def __repr__(self) -> str:
        """Строковое представление"""
        return f"IRBuilder(blocks_created={self._block_counter})"


