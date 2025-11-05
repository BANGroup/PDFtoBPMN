"""
PDF to Context Pipeline - главный оркестратор

НОВАЯ АРХИТЕКТУРА: "Структура сначала, графика потом"

Управляет всем процессом обработки PDF:
1. Парсинг PDF (PDFParser)
2. Анализ страниц (PageAnalyzer) - опционально
3. Native extraction (NativeExtractor) - ВСЕГДА: структура + placeholder'ы
4. Встраивание OCR (StructurePreserver) - обработка графики
5. Построение IR (IRBuilder)
6. Анализ структуры (StructureAnalyzer)
7. Форматирование в Markdown (MarkdownFormatter)

Принципы SOLID:
- Single Responsibility: Только оркестрация компонентов
- Dependency Inversion: Все компоненты передаются как зависимости
- Open/Closed: Легко заменять компоненты
- KISS: Один путь обработки вместо маршрутизации
"""

from typing import Optional
from pathlib import Path

from .core.parser import PDFParser
from .core.analyzer import PageAnalyzer
from .core.structure_preserver import StructurePreserver
from .extractors.native_extractor import NativeExtractor
from .extractors.ocr_client import OCRClient
from .ir.builder import IRBuilder
from .ir.structure_analyzer import StructureAnalyzer
from .output.markdown_formatter import MarkdownFormatter
from .ir.models import IR
from .models.data_models import TextBlock, ImageBlock, DrawingBlock, TableBlock, OCRBlock


class PDFToContextPipeline:
    """
    Главный пайплайн для обработки PDF в контекст
    
    Использование:
    ```python
    pipeline = PDFToContextPipeline(
        ocr_base_url="http://localhost:8000",
        prioritize_accuracy=True
    )
    
    markdown = pipeline.process("document.pdf", output_path="output.md")
    ```
    """
    
    def __init__(self,
                 ocr_base_url: str = "http://localhost:8000",
                 enable_ocr: Optional[bool] = None,
                 extract_images: bool = True,
                 extract_drawings: bool = True,
                 extract_tables: bool = True,
                 min_image_area: float = 1000.0,
                 ocr_vector_graphics: bool = True,
                 vector_render_dpi: int = 300,
                 include_frontmatter: bool = True,
                 include_toc: bool = True):
        """
        Инициализация пайплайна (НОВАЯ АРХИТЕКТУРА)
        
        Args:
            ocr_base_url: URL DeepSeek-OCR микросервиса
            enable_ocr: Включить обработку графики через OCR
                       (None = автоматическое определение по наличию GPU и сервиса)
            extract_images: Извлекать изображения
            extract_drawings: Извлекать векторную графику
            extract_tables: Извлекать таблицы
            min_image_area: Минимальная площадь изображения для OCR (px²)
            ocr_vector_graphics: Рендерить векторную графику для OCR (BPMN диаграммы)
            vector_render_dpi: DPI для рендеринга векторной графики (по умолчанию 300)
            include_frontmatter: Включать YAML frontmatter
            include_toc: Включать оглавление
        """
        # Автоматическое определение режима OCR
        if enable_ocr is None:
            enable_ocr = self._auto_detect_ocr(ocr_base_url)
        # Инициализация компонентов (НОВАЯ АРХИТЕКТУРА)
        self.analyzer = PageAnalyzer()
        self.native_extractor = NativeExtractor(
            extract_images=extract_images,
            extract_drawings=extract_drawings,
            extract_tables=extract_tables,
            render_vectors_to_image=enable_ocr and ocr_vector_graphics,
            vector_render_dpi=vector_render_dpi
        )
        
        # OCR клиент (опционально)
        self.ocr_client = OCRClient(base_url=ocr_base_url) if enable_ocr else None
        
        # StructurePreserver - ключевой компонент новой архитектуры
        self.structure_preserver = StructurePreserver(
            ocr_client=self.ocr_client,
            min_area=min_image_area
        )
        
        self.ir_builder = IRBuilder()
        self.structure_analyzer = StructureAnalyzer()
        self.markdown_formatter = MarkdownFormatter(
            include_frontmatter=include_frontmatter,
            include_toc=include_toc
        )
        
        self.enable_ocr = enable_ocr
        self._stats = {
            "total_pages": 0,
            "total_images": 0,
            "ocr_processed": 0,
            "errors": []
        }
    
    @staticmethod
    def _auto_detect_ocr(ocr_base_url: str) -> bool:
        """
        Автоматическое определение доступности OCR
        
        Проверяет:
        1. Наличие CUDA/GPU (через PyTorch)
        2. Доступность OCR сервиса
        
        Args:
            ocr_base_url: URL OCR сервиса
        
        Returns:
            bool: True если OCR доступен
        """
        # Проверка CUDA/GPU
        cuda_available = False
        try:
            import torch
            cuda_available = torch.cuda.is_available()
        except ImportError:
            pass
        
        # Проверка OCR сервиса
        ocr_service_available = False
        try:
            import requests
            response = requests.get(f"{ocr_base_url}/health", timeout=5)
            ocr_service_available = response.status_code == 200
        except:
            pass
        
        # Вывод информации
        if cuda_available and ocr_service_available:
            print("🔍 Автоопределение режима: Native + OCR (GPU и сервис доступны)")
            return True
        else:
            print("🔍 Автоопределение режима: Native only (только текстовая расшифровка)")
            if not cuda_available:
                print("   ℹ️  CUDA/GPU не доступна")
            if not ocr_service_available:
                print(f"   ℹ️  OCR сервис не доступен ({ocr_base_url})")
            return False
    
    def process(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        Обработать PDF документ (НОВАЯ АРХИТЕКТУРА)
        
        Args:
            pdf_path: Путь к PDF файлу
            output_path: Путь для сохранения Markdown (опционально)
        
        Returns:
            Markdown строка
        """
        print(f"🚀 Начало обработки: {pdf_path}")
        print(f"   Режим: {'Native + OCR' if self.enable_ocr else 'Native only'}")
        
        # 1. Открытие PDF
        with PDFParser(pdf_path) as parser:
            print(f"📄 Документ: {parser.get_total_pages()} страниц\n")
            
            # Извлечение метаданных
            document_metadata = parser.extract_metadata()
            self._stats["total_pages"] = document_metadata.total_pages
            
            # 2. Обработка каждой страницы (НОВЫЙ FLOW)
            extracted_data = []
            
            for page_num in range(parser.get_total_pages()):
                print(f"   Страница {page_num + 1}/{parser.get_total_pages()}: ", end="")
                
                page = parser.get_page(page_num)
                
                try:
                    # ШАГ 1: Native extraction - ВСЕГДА
                    # Извлекаем структуру + placeholder'ы для графики
                    print("extract", end="")
                    page_data = self.native_extractor.extract_page(page, pdf_path)
                    
                    # ШАГ 2: StructurePreserver - встраивание OCR
                    # Обрабатываем изображения и векторную графику с needs_ocr=True
                    if self.enable_ocr and (page_data["image_blocks"] or page_data["drawing_blocks"]):
                        print(" → ocr", end="")
                        
                        # Объединяем все блоки для обработки
                        all_blocks = (
                            page_data["text_blocks"] +
                            page_data["image_blocks"] +
                            page_data["drawing_blocks"] +
                            page_data["table_blocks"]
                        )
                        
                        # Обрабатываем через StructurePreserver
                        processed_blocks = self.structure_preserver.process_structure(
                            all_blocks,
                            page_num
                        )
                        
                        # Разделяем обратно по типам
                        page_data = self._split_blocks_by_type(processed_blocks)
                    
                    extracted_data.append(page_data)
                    print(" ✓")
                
                except Exception as e:
                    print(f" ✗ Ошибка: {e}")
                    import traceback
                    if page_num == 1:  # Печатаем traceback только для первой ошибки
                        print("\n🔍 Traceback:")
                        traceback.print_exc()
                    self._stats["errors"].append({
                        "page": page_num + 1,
                        "error": str(e)
                    })
                    # Добавляем пустые данные
                    extracted_data.append({
                        "text_blocks": [],
                        "image_blocks": [],
                        "drawing_blocks": [],
                        "table_blocks": [],
                        "ocr_blocks": []
                    })
            
            # 3. Построение IR
            print("🔨 Построение промежуточного представления...")
            ir = self.ir_builder.build_ir(extracted_data, document_metadata)
            
            # 4. Анализ структуры
            print("🔍 Анализ структуры документа...")
            ir = self.structure_analyzer.analyze(ir)
            
            # 5. Форматирование в Markdown
            print("📝 Форматирование в Markdown...")
            markdown = self.markdown_formatter.format(ir)
            
            # 6. Сохранение (если указан путь)
            if output_path:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                
                print(f"💾 Сохранено в: {output_path}")
            
            # 7. Статистика
            self._print_stats(ir)
            
            return markdown
    
    def process_to_ir(self, pdf_path: str) -> IR:
        """
        Обработать PDF и вернуть IR (без Markdown форматирования)
        
        Args:
            pdf_path: Путь к PDF файлу
        
        Returns:
            IR: Промежуточное представление
        """
        with PDFParser(pdf_path) as parser:
            document_metadata = parser.extract_metadata()
            extracted_data = []
            
            for page_num in range(parser.get_total_pages()):
                page = parser.get_page(page_num)
                
                # НОВАЯ АРХИТЕКТУРА
                page_data = self.native_extractor.extract_page(page, pdf_path)
                
                # StructurePreserver
                if self.enable_ocr and page_data["image_blocks"]:
                    all_blocks = (
                        page_data["text_blocks"] +
                        page_data["image_blocks"] +
                        page_data["drawing_blocks"] +
                        page_data["table_blocks"]
                    )
                    processed_blocks = self.structure_preserver.process_structure(
                        all_blocks,
                        page_num
                    )
                    page_data = self._split_blocks_by_type(processed_blocks)
                
                extracted_data.append(page_data)
            
            ir = self.ir_builder.build_ir(extracted_data, document_metadata)
            ir = self.structure_analyzer.analyze(ir)
            
            return ir
    
    def health_check(self) -> dict:
        """
        Проверка работоспособности пайплайна
        
        Returns:
            Словарь с статусами компонентов
        """
        ocr_status = False
        if self.ocr_client:
            try:
                ocr_status = self.ocr_client.health_check()
            except:
                ocr_status = False
        
        return {
            "ocr_service": ocr_status,
            "components": {
                "parser": "ready",
                "analyzer": "ready",
                "native_extractor": "ready",
                "structure_preserver": "ready",
                "ocr_client": "ready" if ocr_status else "unavailable",
                "ir_builder": "ready",
                "structure_analyzer": "ready",
                "markdown_formatter": "ready"
            }
        }
    
    def _split_blocks_by_type(self, blocks: list) -> dict:
        """
        Разделить блоки обратно по типам для IRBuilder
        
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
    
    def _print_stats(self, ir: IR):
        """Вывод статистики обработки (НОВАЯ АРХИТЕКТУРА)"""
        print("\n📊 Статистика обработки:")
        print(f"   Всего страниц: {self._stats['total_pages']}")
        
        # Статистика StructurePreserver
        if self.enable_ocr:
            sp_stats = self.structure_preserver.get_statistics()
            print(f"\n   Графика:")
            print(f"   - Найдено изображений: {sp_stats['total_images']}")
            print(f"   - Обработано OCR: {sp_stats['ocr_processed']}")
            print(f"   - Пропущено (маленькие): {sp_stats['ocr_skipped']}")
            if sp_stats['ocr_errors'] > 0:
                print(f"   - Ошибок OCR: {sp_stats['ocr_errors']}")
        
        # Статистика IR
        ir_stats = ir.get_statistics()
        print(f"\n   Блоков в IR: {ir_stats['total_blocks']}")
        print(f"   - Native: {ir_stats['blocks_by_source']['native']}")
        print(f"   - OCR: {ir_stats['blocks_by_source']['ocr']}")
        
        # Блоки по типам
        print(f"\n   По типам:")
        for block_type, count in ir_stats['blocks_by_type'].items():
            print(f"   - {block_type}: {count}")
        
        if self._stats['errors']:
            print(f"\n   ⚠️  Ошибок: {len(self._stats['errors'])}")
        
        print("\n✅ Обработка завершена!")
    
    def __repr__(self) -> str:
        """Строковое представление"""
        mode = "OCR enabled" if self.enable_ocr else "Native only"
        return f"PDFToContextPipeline(mode={mode})"

