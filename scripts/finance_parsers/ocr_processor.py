"""
Компонент 2: DeepSeek OCR Processor
Обработка изображений страниц через DeepSeek OCR API
"""

import requests
from typing import Dict, List
import io


class DeepSeekOCRProcessor:
    """Обработчик для DeepSeek OCR API"""
    
    def __init__(self, api_url: str = "http://localhost:8000"):
        """
        Args:
            api_url: URL DeepSeek OCR API (default: http://localhost:8000)
        """
        self.api_url = api_url
        self.endpoint = f"{api_url}/ocr/figure"
    
    def check_health(self) -> bool:
        """Проверяет доступность API"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def process_page(self, image_bytes: bytes, timeout: int = 120) -> Dict:
        """
        Обрабатывает одну страницу через DeepSeek OCR
        
        Args:
            image_bytes: Изображение страницы в PNG
            timeout: Таймаут запроса в секундах
        
        Returns:
            {
                'raw_output': str,  # Полный вывод с HTML таблицами
                'blocks': List[Dict],  # Блоки с координатами
                'markdown': str  # Markdown представление
            }
        
        Raises:
            RuntimeError: Если API недоступен или вернул ошибку
        """
        files = {'file': ('page.png', io.BytesIO(image_bytes), 'image/png')}
        data = {
            'prompt_type': 'default',
            'base_size': 1024,
            'image_size': 1024,
            'crop_mode': False
        }
        
        try:
            response = requests.post(
                self.endpoint,
                files=files,
                data=data,
                timeout=timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise RuntimeError(f"OCR API error: {response.status_code} - {response.text}")
        
        except requests.exceptions.Timeout:
            raise RuntimeError(f"OCR API timeout after {timeout} seconds")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot connect to OCR API at {self.api_url}")
