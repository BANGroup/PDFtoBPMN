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


# ============================================================================
# DiagramElementDetector: YOLO12 для внутренних элементов схем
# ============================================================================

# Graceful import - ultralytics опционален
try:
    from ultralytics import YOLO as UltralyticsYOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    UltralyticsYOLO = None


class DiagramCategory(Enum):
    """Категории элементов диаграмм/схем (BPMN и flowchart)"""
    # BPMN Tasks
    TASK = "task"
    SUBPROCESS = "subprocess"
    
    # BPMN Gateways
    EXCLUSIVE_GATEWAY = "exclusive_gateway"
    PARALLEL_GATEWAY = "parallel_gateway"
    EVENT_BASED_GATEWAY = "event_based_gateway"
    
    # BPMN Events
    EVENT = "event"
    TIMER_EVENT = "timer_event"
    MESSAGE_EVENT = "message_event"
    
    # BPMN Flows
    SEQUENCE_FLOW = "sequence_flow"
    MESSAGE_FLOW = "message_flow"
    DATA_ASSOCIATION = "data_association"
    
    # BPMN Data
    DATA_OBJECT = "data_object"
    DATA_STORE = "data_store"
    
    # BPMN Swimlanes
    POOL = "pool"
    LANE = "lane"
    
    # Flowchart generic
    DECISION = "decision"
    PROCESS = "process"
    START_END = "start_end"
    ARROW = "arrow"
    
    # Fallback
    UNKNOWN = "unknown"
    
    @classmethod
    def from_string(cls, s: str) -> "DiagramCategory":
        """Конвертация строки класса YOLO в DiagramCategory"""
        mapping = {
            # BPMN элементы (hdBPMN / ELCA-SA датасет)
            "task": cls.TASK,
            "subProcess": cls.SUBPROCESS,
            "subprocess": cls.SUBPROCESS,
            "exclusiveGateway": cls.EXCLUSIVE_GATEWAY,
            "exclusive_gateway": cls.EXCLUSIVE_GATEWAY,
            "parallelGateway": cls.PARALLEL_GATEWAY,
            "parallel_gateway": cls.PARALLEL_GATEWAY,
            "eventBasedGateway": cls.EVENT_BASED_GATEWAY,
            "event_based_gateway": cls.EVENT_BASED_GATEWAY,
            "event": cls.EVENT,
            "timerEvent": cls.TIMER_EVENT,
            "timer_event": cls.TIMER_EVENT,
            "messageEvent": cls.MESSAGE_EVENT,
            "message_event": cls.MESSAGE_EVENT,
            "sequenceFlow": cls.SEQUENCE_FLOW,
            "sequence_flow": cls.SEQUENCE_FLOW,
            "messageFlow": cls.MESSAGE_FLOW,
            "message_flow": cls.MESSAGE_FLOW,
            "dataAssociation": cls.DATA_ASSOCIATION,
            "data_association": cls.DATA_ASSOCIATION,
            "dataObject": cls.DATA_OBJECT,
            "data_object": cls.DATA_OBJECT,
            "dataStore": cls.DATA_STORE,
            "data_store": cls.DATA_STORE,
            "pool": cls.POOL,
            "lane": cls.LANE,
            # Flowchart элементы (Roboflow датасет)
            "decision": cls.DECISION,
            "decision_node": cls.DECISION,
            "process": cls.PROCESS,
            "action": cls.TASK,
            "activity": cls.TASK,
            "start_end": cls.START_END,
            "start_node": cls.EVENT,
            "final_node": cls.EVENT,
            "arrow": cls.ARROW,
            "control_flow": cls.SEQUENCE_FLOW,
            "arrow_line_up": cls.ARROW,
            "arrow_line_down": cls.ARROW,
            "arrow_line_left": cls.ARROW,
            "arrow_line_right": cls.ARROW,
        }
        return mapping.get(s, mapping.get(s.lower(), cls.UNKNOWN))


@dataclass
class DiagramElement:
    """Обнаруженный элемент диаграммы"""
    category: DiagramCategory
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    confidence: float
    text: str = ""  # Текст внутри элемента (из OCR)
    element_id: str = ""  # Уникальный ID элемента
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
    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    @property
    def is_node(self) -> bool:
        """Является ли элемент узлом (task, gateway, event)"""
        return self.category in (
            DiagramCategory.TASK, DiagramCategory.SUBPROCESS,
            DiagramCategory.EXCLUSIVE_GATEWAY, DiagramCategory.PARALLEL_GATEWAY,
            DiagramCategory.EVENT_BASED_GATEWAY,
            DiagramCategory.EVENT, DiagramCategory.TIMER_EVENT,
            DiagramCategory.MESSAGE_EVENT,
            DiagramCategory.DECISION, DiagramCategory.PROCESS,
            DiagramCategory.START_END,
            DiagramCategory.DATA_OBJECT, DiagramCategory.DATA_STORE,
        )
    
    @property
    def is_flow(self) -> bool:
        """Является ли элемент связью (flow, arrow)"""
        return self.category in (
            DiagramCategory.SEQUENCE_FLOW, DiagramCategory.MESSAGE_FLOW,
            DiagramCategory.DATA_ASSOCIATION, DiagramCategory.ARROW,
        )
    
    def __repr__(self) -> str:
        text_preview = f', text="{self.text[:30]}"' if self.text else ""
        return f"DiagramElement({self.category.value}, conf={self.confidence:.2f}{text_preview})"


class DiagramElementDetector:
    """
    Детектор элементов диаграмм на базе YOLO12 (attention-centric).
    
    YOLO12 использует Area Attention для захвата пространственных связей
    между элементами схемы (блоки, стрелки, ромбы), что критически важно
    для понимания структуры диаграмм.
    
    ОБРАТНАЯ СОВМЕСТИМОСТЬ:
    - Если ultralytics не установлен -> graceful degradation
    - Если модель не обучена -> возвращает пустой список
    - Fallback на OCR + пространственный анализ
    """
    
    DEFAULT_MODEL = "models/diagram_detector.pt"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: float = 0.3,
        device: str = "auto"
    ):
        """
        Args:
            model_path: Путь к fine-tuned весам (None = DEFAULT_MODEL)
            confidence_threshold: Минимальный порог уверенности
            device: Устройство ('auto', 'cuda', 'cpu')
        """
        self.model_path = model_path or self.DEFAULT_MODEL
        self.confidence_threshold = confidence_threshold
        self.device = device
        self._model = None
        self._available = None
    
    def is_available(self) -> bool:
        """Проверка доступности детектора (ultralytics + обученная модель)"""
        if self._available is not None:
            return self._available
        
        if not ULTRALYTICS_AVAILABLE:
            self._available = False
            return False
        
        if not PIL_AVAILABLE:
            self._available = False
            return False
        
        # Проверяем наличие файла модели
        if not os.path.exists(self.model_path):
            self._available = False
            return False
        
        try:
            self._load_model()
            self._available = True
        except Exception as e:
            print(f"DiagramElementDetector unavailable: {e}")
            self._available = False
        
        return self._available
    
    def _load_model(self):
        """Ленивая загрузка модели YOLO12"""
        if self._model is not None:
            return
        
        if not ULTRALYTICS_AVAILABLE:
            raise RuntimeError("ultralytics not installed: pip install ultralytics")
        
        self._model = UltralyticsYOLO(self.model_path)
        
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
        imgsz: int = 640
    ) -> List[DiagramElement]:
        """
        Детекция элементов диаграммы на изображении.
        
        Args:
            image: Байты изображения (PNG/JPEG)
            page_num: Номер страницы
            imgsz: Размер для модели
        
        Returns:
            Список DiagramElement (пустой если детектор недоступен)
        """
        if not self.is_available():
            return []
        
        try:
            self._load_model()
            pil_image = Image.open(io.BytesIO(image))
            
            results = self._model.predict(
                pil_image,
                imgsz=imgsz,
                conf=self.confidence_threshold,
                verbose=False
            )
            
            elements = []
            elem_counter = 0
            
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].cpu().numpy()
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    class_name = result.names.get(cls_id, "unknown")
                    category = DiagramCategory.from_string(class_name)
                    
                    element = DiagramElement(
                        category=category,
                        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                        confidence=conf,
                        element_id=f"elem_{elem_counter}",
                        page_num=page_num,
                        metadata={"class_id": cls_id, "class_name": class_name}
                    )
                    elements.append(element)
                    elem_counter += 1
            
            elements.sort(key=lambda e: (e.y0, e.x0))
            return elements
        
        except Exception as e:
            print(f"Diagram detection error: {e}")
            return []
    
    def detect_and_merge_ocr(
        self,
        image: bytes,
        ocr_boxes: List[dict],
        page_num: int = 0,
        imgsz: int = 640
    ) -> List[DiagramElement]:
        """
        Детекция элементов + объединение с OCR текстом по перекрытию bbox.
        
        Args:
            image: Байты изображения
            ocr_boxes: Список OCR-боксов [{"text": str, "x0": float, "y0": float, "x1": float, "y1": float}]
            page_num: Номер страницы
            imgsz: Размер для модели
        
        Returns:
            Список DiagramElement с заполненным полем text
        """
        elements = self.detect(image, page_num, imgsz)
        
        if not elements or not ocr_boxes:
            return elements
        
        # Для каждого node-элемента найти OCR текст внутри его bbox
        for elem in elements:
            if not elem.is_node:
                continue
            
            texts_inside = []
            for ocr_box in ocr_boxes:
                overlap = _compute_overlap(
                    (elem.x0, elem.y0, elem.x1, elem.y1),
                    (ocr_box["x0"], ocr_box["y0"], ocr_box["x1"], ocr_box["y1"])
                )
                if overlap > 0.3:
                    texts_inside.append(ocr_box["text"])
            
            if texts_inside:
                elem.text = " ".join(texts_inside)
        
        return elements
    
    @staticmethod
    def build_connections(elements: List[DiagramElement]) -> List[dict]:
        """
        Определить связи между элементами по пространственной близости.
        
        Для каждого flow-элемента (стрелки) найти ближайший node-источник
        и node-назначение.
        
        Returns:
            Список {"from": elem_id, "to": elem_id, "type": category_value}
        """
        nodes = [e for e in elements if e.is_node]
        flows = [e for e in elements if e.is_flow]
        
        if not nodes or not flows:
            return []
        
        connections = []
        for flow in flows:
            fcx, fcy = flow.center
            fw = flow.width
            fh = flow.height
            
            # Определить направление стрелки (горизонтальная / вертикальная)
            is_horizontal = fw > fh
            
            closest_source = None
            closest_target = None
            min_dist_source = float("inf")
            min_dist_target = float("inf")
            
            for node in nodes:
                ncx, ncy = node.center
                dist = ((fcx - ncx) ** 2 + (fcy - ncy) ** 2) ** 0.5
                
                if is_horizontal:
                    # Горизонтальная стрелка: source слева, target справа
                    if ncx < fcx and dist < min_dist_source:
                        min_dist_source = dist
                        closest_source = node
                    elif ncx >= fcx and dist < min_dist_target:
                        min_dist_target = dist
                        closest_target = node
                else:
                    # Вертикальная стрелка: source сверху, target снизу
                    if ncy < fcy and dist < min_dist_source:
                        min_dist_source = dist
                        closest_source = node
                    elif ncy >= fcy and dist < min_dist_target:
                        min_dist_target = dist
                        closest_target = node
            
            if closest_source and closest_target:
                connections.append({
                    "from": closest_source.element_id,
                    "to": closest_target.element_id,
                    "type": flow.category.value,
                    "confidence": flow.confidence,
                })
        
        return connections
    
    @staticmethod
    def to_structured_json(
        elements: List[DiagramElement],
        connections: List[dict],
        page_num: int = 0
    ) -> dict:
        """
        Структурированный JSON для GraphRAG.
        
        Returns:
            dict с полями type, page, elements, connections
        """
        elem_list = []
        for elem in elements:
            entry = {
                "id": elem.element_id,
                "type": elem.category.value,
                "bbox": list(elem.bbox),
                "confidence": round(elem.confidence, 3),
            }
            if elem.text:
                entry["text"] = elem.text
            if elem.is_flow:
                # Для flow-элементов bbox менее важен
                pass
            elem_list.append(entry)
        
        return {
            "type": "diagram",
            "page": page_num,
            "elements": elem_list,
            "connections": connections,
        }
    
    @staticmethod
    def to_markdown(elements: List[DiagramElement], connections: List[dict]) -> str:
        """
        Markdown-описание диаграммы для вставки в документ.
        
        Returns:
            Строка Markdown с описанием элементов и связей
        """
        if not elements:
            return ""
        
        lines = ["\n**Структура диаграммы (YOLO12):**\n"]
        
        # Узлы
        nodes = [e for e in elements if e.is_node]
        if nodes:
            lines.append("Элементы:")
            for node in nodes:
                text_part = f': "{node.text}"' if node.text else ""
                lines.append(f"- [{node.category.value}] {node.element_id}{text_part}")
        
        # Связи
        if connections:
            lines.append("")
            lines.append("Связи:")
            
            # Создаём маппинг id -> text для читаемости
            id_to_text = {}
            for e in elements:
                label = e.text if e.text else e.element_id
                id_to_text[e.element_id] = label
            
            for conn in connections:
                src = id_to_text.get(conn["from"], conn["from"])
                tgt = id_to_text.get(conn["to"], conn["to"])
                lines.append(f"- {src} -> {tgt}")
        
        lines.append("")
        return "\n".join(lines)
    
    def get_service_info(self) -> dict:
        """Информация о сервисе"""
        return {
            "name": "DiagramElementDetector (YOLO12)",
            "available": self.is_available(),
            "model": self.model_path,
            "confidence_threshold": self.confidence_threshold,
            "device": self.device,
            "ultralytics_installed": ULTRALYTICS_AVAILABLE,
            "categories": [c.value for c in DiagramCategory if c != DiagramCategory.UNKNOWN],
        }
    
    def __repr__(self) -> str:
        status = "available" if self.is_available() else "unavailable"
        return f"DiagramElementDetector({status}, model={self.model_path})"


def _compute_overlap(bbox_a: tuple, bbox_b: tuple) -> float:
    """
    Вычислить долю перекрытия bbox_b с bbox_a.
    
    Returns:
        Доля площади bbox_b, попадающая в bbox_a (0-1)
    """
    ax0, ay0, ax1, ay1 = bbox_a
    bx0, by0, bx1, by1 = bbox_b
    
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    
    if ix0 >= ix1 or iy0 >= iy1:
        return 0.0
    
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area_b = (bx1 - bx0) * (by1 - by0)
    
    if area_b <= 0:
        return 0.0
    
    return intersection / area_b


# Singleton для DiagramElementDetector
_default_diagram_detector: Optional[DiagramElementDetector] = None


def get_diagram_detector(
    model_path: Optional[str] = None,
    confidence_threshold: float = 0.3
) -> DiagramElementDetector:
    """
    Получить экземпляр DiagramElementDetector (singleton).
    
    Args:
        model_path: Путь к fine-tuned модели
        confidence_threshold: Порог уверенности
    
    Returns:
        Экземпляр DiagramElementDetector
    """
    global _default_diagram_detector
    
    if _default_diagram_detector is None:
        _default_diagram_detector = DiagramElementDetector(
            model_path=model_path,
            confidence_threshold=confidence_threshold
        )
    
    return _default_diagram_detector


def is_diagram_detection_available() -> bool:
    """Проверка доступности diagram detection"""
    return ULTRALYTICS_AVAILABLE and PIL_AVAILABLE
