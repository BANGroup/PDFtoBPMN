"""
Специализированные промпты для разных типов контента
"""

class OCRPrompts:
    """
    Коллекция промптов для DeepSeek-OCR
    
    SOLID: Single Responsibility - только хранение промптов
    KISS: Простые, понятные шаблоны
    DRY: Переиспользуемые промпты
    """
    
    @staticmethod
    def get_default_prompt() -> str:
        """Базовый промпт для общего OCR"""
        return "<image>\n<|grounding|>Convert the document to markdown."
    
    @staticmethod
    def get_bpmn_diagram_prompt() -> str:
        """
        Промпт для извлечения структуры BPMN диаграммы
        
        ВАЖНО: Промпты для DeepSeek-OCR должны быть ПРОСТЫМИ и КОРОТКИМИ!
        Модель лучше работает с минимальными инструкциями.
        """
        return "<image>\n<|grounding|>Convert the BPMN diagram to markdown. Include all text from shapes, gateways, and events."
    
    @staticmethod
    def get_complex_diagram_prompt() -> str:
        """
        Промпт для сложных диаграмм (IDEF0, схемы взаимодействия)
        
        ВАЖНО: Короткие промпты работают лучше!
        """
        return "<image>\n<|grounding|>Convert the diagram to markdown. Extract all text from boxes, connections, and annotations."
    
    @staticmethod
    def get_table_prompt() -> str:
        """Промпт для извлечения таблиц"""
        return "<image>\n<|grounding|>Convert the table to markdown format with all rows and columns."
    
    @staticmethod
    def get_text_with_graphics_prompt() -> str:
        """Промпт для страниц с текстом + встроенной графикой"""
        return "<image>\n<|grounding|>Convert the document to markdown including text, diagrams, and tables."
    
    @staticmethod
    def get_parse_figure_prompt() -> str:
        """
        ОФИЦИАЛЬНЫЙ промпт для парсинга графиков/диаграмм
        Источник: DeepSeek-OCR config.py, режим 4
        """
        return "<image>\nParse the figure."
    
    @staticmethod
    def get_free_ocr_prompt() -> str:
        """
        ОФИЦИАЛЬНЫЙ промпт для свободного OCR (без layout)
        Источник: DeepSeek-OCR config.py, режим 2
        """
        return "<image>\nFree OCR."
    
    @staticmethod
    def get_describe_prompt() -> str:
        """
        ОФИЦИАЛЬНЫЙ промпт для детального описания изображения
        Источник: DeepSeek-OCR config.py, режим 5
        """
        return "<image>\nDescribe this image in detail."
    
    @staticmethod
    def get_ocr_simple_prompt() -> str:
        """
        ОФИЦИАЛЬНЫЙ промпт для простого OCR
        Источник: DeepSeek-OCR официальная документация
        """
        return "<image>\n<|grounding|>OCR this image."
    
    @staticmethod
    def get_prompt_by_type(content_type: str) -> str:
        """
        Выбор промпта по типу контента
        
        Args:
            content_type: 'bpmn', 'complex_diagram', 'table', 'text_graphics', 'default',
                         'parse_figure', 'free_ocr', 'describe' (официальные)
        
        Returns:
            Appropriate prompt string
        """
        prompts = {
            # Наши кастомные промпты:
            'bpmn': OCRPrompts.get_bpmn_diagram_prompt(),
            'complex_diagram': OCRPrompts.get_complex_diagram_prompt(),
            'table': OCRPrompts.get_table_prompt(),
            'text_graphics': OCRPrompts.get_text_with_graphics_prompt(),
            'default': OCRPrompts.get_default_prompt(),
            
            # ОФИЦИАЛЬНЫЕ промпты из DeepSeek-OCR:
            'parse_figure': OCRPrompts.get_parse_figure_prompt(),    # ⭐⭐⭐ Для диаграмм
            'free_ocr': OCRPrompts.get_free_ocr_prompt(),
            'describe': OCRPrompts.get_describe_prompt(),
            'ocr_simple': OCRPrompts.get_ocr_simple_prompt(),
        }
        
        return prompts.get(content_type, OCRPrompts.get_default_prompt())


class BPMNPrompts:
    """
    Специализированные BPMN промпты для разных элементов
    
    ВАЖНО: Все промпты должны быть КОРОТКИМИ!
    """
    
    @staticmethod
    def get_gateway_focused_prompt() -> str:
        """Промпт с фокусом на шлюзы и условия"""
        return "<image>\n<|grounding|>Convert the diagram to markdown. Focus on gateway conditions and decision points."
    
    @staticmethod
    def get_events_focused_prompt() -> str:
        """Промпт с фокусом на события"""
        return "<image>\n<|grounding|>Convert the diagram to markdown. Focus on events and their labels."
    
    @staticmethod
    def get_lanes_focused_prompt() -> str:
        """Промпт с фокусом на дорожки и роли"""
        return "<image>\n<|grounding|>Convert the diagram to markdown. Focus on pools, lanes, and role assignments."

