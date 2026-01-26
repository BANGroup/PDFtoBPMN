"""
Layout Detector - детекция структурных элементов документа

Использует DocLayout-YOLO для определения:
- text, title, figure, table, caption
- list, header, footer, page-number
- и другие элементы документа

ПРИНЦИП ОБРАТНОЙ СОВМЕСТИМОСТИ:
- Если DocLayout-YOLO не установлен → graceful degradation
- Возвращает пустой список и работа продолжается
- Включается через флаг enable_layout_detection=True
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

# Graceful import - не падаем если пакет не установлен
try:
    from doclayout_yolo import YOLOv10
    DOCLAYOUT_AVAILABLE = True
except ImportError:
    DOCLAYOUT_AVAILABLE = False
    YOLOv10 = None

try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class LayoutCategory(Enum):
    """Категории элементов документа (DocLayout-YOLO)"""
    TEXT = "text"
    TITLE = "title"
    FIGURE = "figure"
    TABLE = "table"
    CAPTION = "caption"
    LIST = "list"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page-number"
    EQUATION = "equation"
    REFERENCE = "reference"
    ABSTRACT = "abstract"
    AUTHOR = "author"
    DATE = "date"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_string(cls, s: str) -> "LayoutCategory":
        """Конвертация строки в категорию"""
        mapping = {
            "text": cls.TEXT,
            "title": cls.TITLE,
            "figure": cls.FIGURE,
            "table": cls.TABLE,
            "caption": cls.CAPTION,
            "list": cls.LIST,
            "header": cls.HEADER,
            "footer": cls.FOOTER,
            "page-number": cls.PAGE_NUMBER,
            "page_number": cls.PAGE_NUMBER,
            "equation": cls.EQUATION,
            "reference": cls.REFERENCE,
            "abstract": cls.ABSTRACT,
            "author": cls.AUTHOR,
            "date": cls.DATE,
        }
        return mapping.get(s.lower(), cls.UNKNOWN)


@dataclass
class LayoutElement:
    """Обнаруженный элемент layout"""
    category: LayoutCategory
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    confidence: float
    page_num: int = 0
    metadata: dict = field(default_factory=dict)
    
    @property
    def x0(self) -> float:
        return self.bbox[0]
    
    @property
    def y0(self) -> float:
        return self.bbox[1]
    
    @property
    def x1(self) -> float:
        return self.bbox[2]
    
    @property
    def y1(self) -> float:
        return self.bbox[3]
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    def __repr__(self) -> str:
        return f"LayoutElement({self.category.value}, conf={self.confidence:.2f}, bbox={self.bbox})"


class LayoutDetector:
    """
    Детектор layout документов на базе DocLayout-YOLO
    
    Применяет SOLID принципы:
    - Single Responsibility: Только детекция layout
    - Open/Closed: Расширяемость через наследование
    - Dependency Inversion: Не зависит от конкретной модели YOLO
    
    ОБРАТНАЯ СОВМЕСТИМОСТЬ:
    - Если DocLayout-YOLO не установлен — возвращает пустой список
    - Не влияет на работу остального пайплайна
    """
    
    # Путь к модели по умолчанию (скачивается автоматически)
    DEFAULT_MODEL = "doclayout_yolo_docstructbench_imgsz1024.pt"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: float = 0.25,
        device: str = "auto"
    ):
        """
        Инициализация детектора
        
        Args:
            model_path: Путь к весам модели (None = скачать автоматически)
            confidence_threshold: Минимальный порог уверенности
            device: Устройство ('auto', 'cuda', 'cpu')
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.device = device
        self._model = None
        self._available = None
    
    def is_available(self) -> bool:
        """Проверка доступности детектора"""
        if self._available is not None:
            return self._available
        
        if not DOCLAYOUT_AVAILABLE:
            self._available = False
            return False
        
        if not PIL_AVAILABLE:
            self._available = False
            return False
        
        # Попытка загрузить модель
        try:
            self._load_model()
            self._available = True
        except Exception as e:
            print(f"⚠️ LayoutDetector недоступен: {e}")
            self._available = False
        
        return self._available
    
    def _load_model(self):
        """Ленивая загрузка модели"""
        if self._model is not None:
            return
        
        if not DOCLAYOUT_AVAILABLE:
            raise RuntimeError("DocLayout-YOLO не установлен: pip install doclayout-yolo")
        
        model_path = self.model_path or self.DEFAULT_MODEL
        self._model = YOLOv10(model_path)
        
        # Установка устройства
        if self.device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = self.device
        
        self._model.to(device)
    
    def detect(
        self,
        image: bytes,
        page_num: int = 0,
        imgsz: int = 1024
    ) -> List[LayoutElement]:
        """
        Детекция элементов layout на изображении
        
        Args:
            image: Байты изображения (PNG/JPEG)
            page_num: Номер страницы (для метаданных)
            imgsz: Размер изображения для модели
        
        Returns:
            Список обнаруженных элементов LayoutElement
            Пустой список если детектор недоступен
        """
        if not self.is_available():
            return []
        
        try:
            self._load_model()
            
            # Конвертация bytes → PIL Image
            pil_image = Image.open(io.BytesIO(image))
            
            # Inference
            results = self._model.predict(
                pil_image,
                imgsz=imgsz,
                conf=self.confidence_threshold,
                verbose=False
            )
            
            # Парсинг результатов
            elements = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].cpu().numpy()
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    
                    # Получение названия класса
                    class_name = result.names.get(cls_id, "unknown")
                    category = LayoutCategory.from_string(class_name)
                    
                    element = LayoutElement(
                        category=category,
                        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                        confidence=conf,
                        page_num=page_num,
                        metadata={"class_id": cls_id, "class_name": class_name}
                    )
                    elements.append(element)
            
            # Сортировка по позиции (сверху вниз, слева направо)
            elements.sort(key=lambda e: (e.y0, e.x0))
            
            return elements
        
        except Exception as e:
            print(f"⚠️ Ошибка детекции layout: {e}")
            return []
    
    def detect_from_page(
        self,
        page,  # fitz.Page
        dpi: int = 150
    ) -> List[LayoutElement]:
        """
        Детекция layout на странице PDF (PyMuPDF)
        
        Args:
            page: Объект страницы PyMuPDF (fitz.Page)
            dpi: DPI для рендеринга страницы
        
        Returns:
            Список обнаруженных элементов
        """
        if not self.is_available():
            return []
        
        try:
            import fitz
            
            # Рендеринг страницы в изображение
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            image_bytes = pix.tobytes("png")
            
            return self.detect(image_bytes, page_num=page.number)
        
        except Exception as e:
            print(f"⚠️ Ошибка детекции layout страницы: {e}")
            return []
    
    def get_service_info(self) -> dict:
        """Информация о сервисе"""
        return {
            "name": "DocLayout-YOLO",
            "available": self.is_available(),
            "model": self.model_path or self.DEFAULT_MODEL,
            "confidence_threshold": self.confidence_threshold,
            "device": self.device,
            "categories": [c.value for c in LayoutCategory if c != LayoutCategory.UNKNOWN]
        }
    
    def __repr__(self) -> str:
        status = "✅" if self.is_available() else "❌"
        return f"LayoutDetector({status}, model={self.model_path or 'default'})"


# Singleton instance для удобства
_default_detector: Optional[LayoutDetector] = None


def get_layout_detector(
    model_path: Optional[str] = None,
    confidence_threshold: float = 0.25
) -> LayoutDetector:
    """
    Получить экземпляр LayoutDetector (singleton)
    
    Args:
        model_path: Путь к модели
        confidence_threshold: Порог уверенности
    
    Returns:
        Экземпляр LayoutDetector
    """
    global _default_detector
    
    if _default_detector is None:
        _default_detector = LayoutDetector(
            model_path=model_path,
            confidence_threshold=confidence_threshold
        )
    
    return _default_detector


def is_layout_detection_available() -> bool:
    """Проверка доступности layout detection"""
    return DOCLAYOUT_AVAILABLE and PIL_AVAILABLE
