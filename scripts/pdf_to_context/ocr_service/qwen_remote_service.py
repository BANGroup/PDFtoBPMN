"""
Qwen Remote OCR Service - клиент для удалённого Qwen VLM сервиса

Подключается к Docker контейнеру с Qwen VLM (7B/72B модели).
Используется когда локальной VRAM недостаточно.

Использование:
    service = QwenRemoteService(base_url="http://server:8001")
    if service.is_available():
        text = service.recognize(image_bytes)
"""

import io
import base64
from typing import Optional

import requests
from PIL import Image

from .base import OCRService


class QwenRemoteService(OCRService):
    """
    Клиент для удалённого Qwen VLM OCR сервиса
    
    Подключается к Docker контейнеру qwen-vlm-service.
    Поддерживает любые модели Qwen2-VL (2B, 7B, 72B).
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        timeout: int = 120,
        language: str = "russian"
    ):
        """
        Инициализация клиента
        
        Args:
            base_url: URL сервиса (http://host:port)
            timeout: Таймаут запроса в секундах
            language: Язык для OCR (russian, english, auto)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.language = language
        self._available = None
        self._model_info = None
    
    def is_available(self) -> bool:
        """Проверка доступности сервиса"""
        if self._available is not None:
            return self._available
        
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                self._available = data.get("status") == "healthy"
                self._model_info = data
            else:
                self._available = False
        except Exception:
            self._available = False
        
        return self._available
    
    def get_info(self) -> dict:
        """Получить информацию о сервисе"""
        if self._model_info:
            return self._model_info
        
        try:
            response = requests.get(
                f"{self.base_url}/info",
                timeout=5
            )
            if response.status_code == 200:
                self._model_info = response.json()
                return self._model_info
        except Exception:
            pass
        
        return {}
    
    def recognize(
        self, 
        image_data: bytes, 
        prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Распознать текст на изображении
        
        Args:
            image_data: Байты изображения (PNG/JPEG)
            prompt: Кастомный промпт (опционально)
            max_tokens: Максимум токенов в ответе
            
        Returns:
            Распознанный текст
        """
        if not self.is_available():
            raise RuntimeError("Qwen Remote Service недоступен")
        
        # Конвертация в base64
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        
        # Запрос
        payload = {
            "image": image_b64,
            "language": self.language,
        }
        if prompt:
            payload["prompt"] = prompt
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        try:
            response = requests.post(
                f"{self.base_url}/ocr",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("text", "")
            
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Timeout ({self.timeout}s) при OCR")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ошибка запроса к Qwen Remote: {e}")
    
    def recognize_file(self, file_path: str) -> str:
        """Распознать текст из файла"""
        with open(file_path, "rb") as f:
            return self.recognize(f.read())
    
    def get_name(self) -> str:
        """Название сервиса"""
        info = self.get_info()
        model = info.get("model", "unknown")
        return f"Qwen Remote ({model})"
    
    def get_description(self) -> str:
        """Описание сервиса"""
        info = self.get_info()
        return f"Remote Qwen VLM at {self.base_url} (model: {info.get('model', 'N/A')})"
    
    # ===== Реализация абстрактных методов OCRService =====
    
    def get_service_name(self) -> str:
        """Название сервиса для логирования"""
        return self.get_name()
    
    def get_service_type(self) -> str:
        """Тип сервиса: GPU (через Docker)"""
        return "gpu"
    
    def process_image(self, image_data: bytes, prompt: str = "") -> str:
        """
        Обработка изображения через OCR
        
        Args:
            image_data: Байты изображения (PNG/JPEG)
            prompt: Подсказка для OCR
        
        Returns:
            str: Распознанный текст
        """
        return self.recognize(image_data, prompt=prompt if prompt else None)
