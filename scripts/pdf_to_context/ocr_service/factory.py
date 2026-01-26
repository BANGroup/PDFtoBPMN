"""
OCR Service Factory - автоматический выбор OCR реализации

Применение SOLID:
- Factory Pattern: Централизованное создание объектов
- Strategy Pattern: Выбор стратегии в runtime
- Dependency Inversion: Возвращаем абстракцию (OCRService)

ОБРАТНАЯ СОВМЕСТИМОСТЬ:
- По умолчанию используется DeepSeek-OCR (как раньше)
- Qwen VL включается явно: create(service_type="qwen")
- Graceful degradation если сервис недоступен

АРХИТЕКТУРА VLM:
- qwen_local: Qwen2-VL-2B локально (16GB VRAM)
- qwen_remote: Qwen через Docker на удалённом сервере (24GB+ VRAM)
- qwen: автовыбор (remote если доступен, иначе local)
"""

import os
from typing import Optional, Literal

# Graceful import torch
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

from .base import OCRService
from .deepseek_service import DeepSeekOCRService
from .paddleocr_service import PaddleOCRService

# Lazy import для Qwen Local (чтобы не ломать если не установлен)
def _get_qwen_service():
    try:
        from .qwen_service import QwenVLService, is_qwen_available
        return QwenVLService, is_qwen_available
    except ImportError:
        return None, lambda: False

# Lazy import для Qwen Remote
def _get_qwen_remote_service():
    try:
        from .qwen_remote_service import QwenRemoteService
        return QwenRemoteService
    except ImportError:
        return None


# Типы OCR сервисов
OCRServiceType = Literal["auto", "deepseek", "qwen", "qwen_local", "qwen_remote", "paddle"]


class OCRServiceFactory:
    """
    Factory для автоматического выбора оптимального OCR сервиса
    
    Логика выбора (mode="auto"):
    1. Если CUDA доступна + DeepSeek сервис работает → DeepSeek (GPU, высокая точность)
    2. Если PaddleOCR установлен → PaddleOCR (CPU, хорошая точность)
    3. Если Qwen VL доступен → Qwen (GPU, VLM)
    4. Иначе → RuntimeError (нет доступных сервисов)
    
    Явный выбор:
    - service_type="deepseek" → DeepSeek-OCR микросервис
    - service_type="qwen" → Qwen VL (автовыбор remote/local)
    - service_type="qwen_local" → Qwen2-VL-2B локально (16GB VRAM)
    - service_type="qwen_remote" → Qwen через Docker (7B/72B, 24GB+ VRAM)
    - service_type="paddle" → PaddleOCR (CPU)
    """
    
    # URL удалённого Qwen сервиса по умолчанию
    DEFAULT_QWEN_REMOTE_URL = os.getenv("QWEN_REMOTE_URL", "http://localhost:8001")
    
    @staticmethod
    def create(
        service_type: OCRServiceType = "auto",
        prefer_deepseek: bool = True,
        deepseek_url: str = "http://localhost:8000",
        qwen_remote_url: Optional[str] = None,
        paddleocr_lang: str = "ru",
        qwen_model: Optional[str] = None
    ) -> OCRService:
        """
        Автоматический или явный выбор OCR сервиса
        
        Args:
            service_type: Тип сервиса ("auto", "deepseek", "qwen", "qwen_local", "qwen_remote", "paddle")
            prefer_deepseek: Предпочитать DeepSeek если доступен (для auto)
            deepseek_url: URL DeepSeek-OCR сервиса
            qwen_remote_url: URL удалённого Qwen сервиса (Docker)
            paddleocr_lang: Язык для PaddleOCR ('ru', 'en', 'ch' и др.)
            qwen_model: Модель Qwen VL для локального режима (None = default 2B)
        
        Returns:
            Экземпляр OCRService
        
        Raises:
            RuntimeError: Если запрошенный сервис недоступен
        """
        services_tried = []
        qwen_url = qwen_remote_url or OCRServiceFactory.DEFAULT_QWEN_REMOTE_URL
        
        # Явный выбор Qwen Remote (Docker)
        if service_type == "qwen_remote":
            QwenRemoteService = _get_qwen_remote_service()
            if QwenRemoteService is None:
                raise RuntimeError("QwenRemoteService не импортирован")
            
            remote = QwenRemoteService(base_url=qwen_url)
            if remote.is_available():
                info = remote.get_info()
                print(f"🔍 OCR: Qwen Remote ({info.get('model', 'unknown')})")
                print(f"   URL: {qwen_url}")
                print(f"   Режим: VLM (Docker)")
                return remote
            raise RuntimeError(f"Qwen Remote недоступен: {qwen_url}")
        
        # Явный выбор Qwen Local
        if service_type == "qwen_local":
            QwenVLService, is_qwen_available = _get_qwen_service()
            if QwenVLService is None or not is_qwen_available():
                raise RuntimeError(
                    "Qwen VL Local недоступен!\n"
                    "Установите: pip install transformers torch accelerate qwen-vl-utils"
                )
            qwen = QwenVLService(model_name=qwen_model)
            if qwen.is_available():
                print(f"🔍 OCR: {qwen.get_service_name()}")
                print(f"   Режим: VLM Local (GPU)")
                return qwen
            raise RuntimeError("Qwen VL Local не удалось инициализировать")
        
        # Qwen AUTO (remote если доступен, иначе local)
        if service_type == "qwen":
            # 1. Сначала пробуем remote (более мощная модель)
            QwenRemoteService = _get_qwen_remote_service()
            if QwenRemoteService:
                remote = QwenRemoteService(base_url=qwen_url)
                if remote.is_available():
                    info = remote.get_info()
                    print(f"🔍 OCR: Qwen Remote ({info.get('model', 'unknown')})")
                    print(f"   URL: {qwen_url}")
                    print(f"   Режим: VLM (Docker, 7B+)")
                    return remote
            
            # 2. Fallback на local
            QwenVLService, is_qwen_available = _get_qwen_service()
            if QwenVLService is None or not is_qwen_available():
                raise RuntimeError(
                    "Qwen VL недоступен!\n"
                    "Варианты:\n"
                    f"  1. Запустите Docker: docker compose up (порт 8001)\n"
                    "  2. Установите локально: pip install transformers torch accelerate qwen-vl-utils"
                )
            qwen = QwenVLService(model_name=qwen_model)
            if qwen.is_available():
                print(f"🔍 OCR: {qwen.get_service_name()}")
                print(f"   Режим: VLM Local (2B)")
                return qwen
            raise RuntimeError("Qwen VL не удалось инициализировать")
        
        # Явный выбор DeepSeek
        if service_type == "deepseek":
            return OCRServiceFactory.create_deepseek_only(deepseek_url)
        
        # Явный выбор PaddleOCR
        if service_type == "paddle":
            return OCRServiceFactory.create_paddleocr_only(paddleocr_lang)
        
        # AUTO mode - оригинальная логика (ОБРАТНАЯ СОВМЕСТИМОСТЬ)
        
        # 1. Попытка DeepSeek (если CUDA + prefer)
        cuda_available = TORCH_AVAILABLE and torch.cuda.is_available()
        
        if prefer_deepseek and cuda_available:
            deepseek = DeepSeekOCRService(base_url=deepseek_url)
            if deepseek.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                print(f"🔍 OCR: {deepseek.get_service_name()}")
                print(f"   GPU: {gpu_name}")
                print(f"   Точность: 95-99% (AI-based)")
                return deepseek
            services_tried.append(f"DeepSeek ({deepseek_url}) - недоступен")
        elif prefer_deepseek and not cuda_available:
            services_tried.append("DeepSeek - нет CUDA")
        
        # 2. Fallback: PaddleOCR
        paddle = PaddleOCRService(lang=paddleocr_lang)
        if paddle.is_available():
            print(f"🔍 OCR: {paddle.get_service_name()}")
            print(f"   Режим: CPU")
            print(f"   Точность: 88-93% (rule-based + DL)")
            return paddle
        services_tried.append("PaddleOCR - не установлен")
        
        # 3. Попытка Qwen VL как последний fallback
        QwenVLService, is_qwen_available = _get_qwen_service()
        if QwenVLService and is_qwen_available():
            qwen = QwenVLService(model_name=qwen_model)
            if qwen.is_available():
                print(f"🔍 OCR: {qwen.get_service_name()} (fallback)")
                return qwen
            services_tried.append("Qwen VL - не удалось загрузить")
        else:
            services_tried.append("Qwen VL - не установлен")
        
        # 4. Ничего не доступно
        error_msg = (
            "❌ Ни один OCR сервис недоступен!\n\n"
            "Попытки:\n"
        )
        for attempt in services_tried:
            error_msg += f"  - {attempt}\n"
        
        error_msg += (
            "\n"
            "Решения:\n"
            "  1. Установите PaddleOCR (рекомендуется для CPU):\n"
            "     pip install paddlepaddle paddleocr\n\n"
            "  2. Или запустите DeepSeek-OCR сервис (для GPU):\n"
            f"     python -m uvicorn scripts.pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000\n\n"
            "  3. Или установите Qwen VL (GPU, ~16GB VRAM):\n"
            "     pip install transformers torch accelerate\n"
        )
        
        raise RuntimeError(error_msg)
    
    @staticmethod
    def create_deepseek_only(deepseek_url: str = "http://localhost:8000") -> OCRService:
        """
        Принудительное использование DeepSeek
        
        Args:
            deepseek_url: URL DeepSeek-OCR сервиса
        
        Returns:
            DeepSeekOCRService
        
        Raises:
            RuntimeError: Если DeepSeek недоступен
        """
        deepseek = DeepSeekOCRService(base_url=deepseek_url)
        if not deepseek.is_available():
            raise RuntimeError(
                f"DeepSeek-OCR сервис недоступен: {deepseek_url}\n"
                "Убедитесь что сервис запущен"
            )
        return deepseek
    
    @staticmethod
    def create_paddleocr_only(lang: str = "ru") -> OCRService:
        """
        Принудительное использование PaddleOCR
        
        Args:
            lang: Язык для распознавания
        
        Returns:
            PaddleOCRService
        
        Raises:
            RuntimeError: Если PaddleOCR не установлен
        """
        paddle = PaddleOCRService(lang=lang)
        if not paddle.is_available():
            raise RuntimeError(
                "PaddleOCR не установлен!\n"
                "Установите: pip install paddlepaddle paddleocr"
            )
        return paddle
    
    @staticmethod
    def create_qwen_only(model_name: Optional[str] = None) -> OCRService:
        """
        Принудительное использование Qwen VL
        
        Args:
            model_name: Название модели (None = default 7B)
        
        Returns:
            QwenVLService
        
        Raises:
            RuntimeError: Если Qwen VL недоступен
        """
        QwenVLService, is_qwen_available = _get_qwen_service()
        
        if QwenVLService is None or not is_qwen_available():
            raise RuntimeError(
                "Qwen VL не установлен!\n"
                "Установите: pip install transformers torch accelerate"
            )
        
        qwen = QwenVLService(model_name=model_name)
        if not qwen.is_available():
            raise RuntimeError("Qwen VL не удалось инициализировать")
        
        return qwen
    
    @staticmethod
    def list_available_services() -> dict:
        """
        Список доступных OCR сервисов
        
        Returns:
            Dict с информацией о доступности каждого сервиса
        """
        services = {}
        
        # DeepSeek
        try:
            deepseek = DeepSeekOCRService()
            services["deepseek"] = {
                "available": deepseek.is_available(),
                "type": "gpu",
                "description": "DeepSeek-OCR микросервис (требует запущенный сервер)"
            }
        except Exception as e:
            services["deepseek"] = {"available": False, "error": str(e)}
        
        # PaddleOCR
        try:
            paddle = PaddleOCRService()
            services["paddle"] = {
                "available": paddle.is_available(),
                "type": "cpu",
                "description": "PaddleOCR (локальный, CPU)"
            }
        except Exception as e:
            services["paddle"] = {"available": False, "error": str(e)}
        
        # Qwen VL Local
        QwenVLService, is_qwen_available = _get_qwen_service()
        if QwenVLService:
            try:
                services["qwen_local"] = {
                    "available": is_qwen_available(),
                    "type": "gpu",
                    "description": "Qwen2-VL-2B (локальный, GPU ~4-5GB VRAM)"
                }
            except Exception as e:
                services["qwen_local"] = {"available": False, "error": str(e)}
        else:
            services["qwen_local"] = {
                "available": False,
                "error": "transformers не установлен"
            }
        
        # Qwen VL Remote (Docker)
        QwenRemoteService = _get_qwen_remote_service()
        remote_available = False
        if QwenRemoteService:
            try:
                remote = QwenRemoteService(base_url=OCRServiceFactory.DEFAULT_QWEN_REMOTE_URL)
                remote_available = remote.is_available()
                services["qwen_remote"] = {
                    "available": remote_available,
                    "type": "gpu",
                    "description": f"Qwen VL Docker ({OCRServiceFactory.DEFAULT_QWEN_REMOTE_URL})"
                }
            except Exception as e:
                services["qwen_remote"] = {"available": False, "error": str(e)}
        else:
            services["qwen_remote"] = {
                "available": False,
                "error": "qwen_remote_service не импортирован"
            }
        
        # Qwen (автовыбор) - для совместимости
        local_available = services.get("qwen_local", {}).get("available", False)
        services["qwen"] = {
            "available": local_available or remote_available,
            "type": "gpu",
            "description": "Qwen VL (автовыбор: remote если доступен, иначе local)"
        }
        
        return services


