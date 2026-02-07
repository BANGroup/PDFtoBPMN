"""
Extractors для извлечения контента из PDF

Компоненты:
- NativeExtractor: Нативное извлечение текста, изображений, таблиц
- OCRClient: Клиент для OCR сервисов
- HybridHandler: Комбинация native + OCR
- LayoutDetector: Детекция layout через DocLayout-YOLO (опционально)
- DiagramElementDetector: Детекция элементов диаграмм через YOLO12 (опционально)
"""

from .native_extractor import NativeExtractor
from .ocr_client import OCRClient
from .hybrid_handler import HybridHandler

# Lazy import для LayoutDetector (опциональная зависимость)
def get_layout_detector():
    """Получить LayoutDetector (если доступен)"""
    try:
        from .layout_detector import LayoutDetector, is_layout_detection_available
        return LayoutDetector, is_layout_detection_available
    except ImportError:
        return None, lambda: False

# Lazy import для DiagramElementDetector (опциональная зависимость)
def get_diagram_detector():
    """Получить DiagramElementDetector (если доступен)"""
    try:
        from .layout_detector import DiagramElementDetector, is_diagram_detection_available
        return DiagramElementDetector, is_diagram_detection_available
    except ImportError:
        return None, lambda: False

__all__ = [
    "NativeExtractor",
    "OCRClient", 
    "HybridHandler",
    "get_layout_detector",
    "get_diagram_detector",
]



