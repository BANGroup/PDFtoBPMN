"""
Qwen2.5-VL OCR Service - альтернативный VLM-based OCR

Использует Qwen2.5-VL для распознавания:
- Текста на изображениях
- Таблиц и формул
- Диаграмм и схем

ПРИНЦИП ОБРАТНОЙ СОВМЕСТИМОСТИ:
- Это АЛЬТЕРНАТИВА DeepSeek-OCR, не замена
- Включается явно через OCRServiceFactory.create(service_type="qwen")
- Если transformers/torch не установлены → graceful degradation

Преимущества перед DeepSeek-OCR:
- Не требует отдельного микросервиса
- Поддержка Markdown output из коробки
- Multi-language (включая русский)
- Активно развивается (Qwen team)

Недостатки:
- Требует ~16GB VRAM (7B модель)
- Медленнее на инференсе
"""

import os
import io
import base64
from typing import Optional

from .base import OCRService

# Graceful imports
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

try:
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    Qwen2VLForConditionalGeneration = None
    AutoProcessor = None

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


class QwenVLService(OCRService):
    """
    OCR сервис на базе Qwen2.5-VL
    
    Модели:
    - Qwen/Qwen2-VL-2B-Instruct (2B, ~4-5GB VRAM) - рекомендуется, стабильная
    - Qwen/Qwen2-VL-7B-Instruct (7B, ~16GB VRAM)
    - Qwen/Qwen2.5-VL-7B-Instruct (7B, ~16GB VRAM) - требует flash_attn
    
    Примечание: Qwen2-VL (не 2.5) более стабильна с transformers 5.0
    """
    
    # Модели по умолчанию
    DEFAULT_MODEL = "Qwen/Qwen2-VL-2B-Instruct"  # Стабильная, работает без flash_attn
    LARGE_MODEL = "Qwen/Qwen2-VL-7B-Instruct"
    
    # Промпты для разных типов контента
    PROMPTS = {
        "default": "Please extract all text from this image. Output in Markdown format.",
        "ocr_simple": "Extract all visible text from this image exactly as shown.",
        "parse_figure": "Describe this figure/diagram in detail. Include any text labels, arrows, and relationships.",
        "table": "Extract this table to Markdown format. Preserve the structure accurately.",
        "bpmn": "This is a BPMN diagram. Describe all elements: tasks, gateways, events, flows, and swimlanes.",
        "formula": "Extract the mathematical formula/equation from this image in LaTeX format.",
        "russian": "Извлеките весь текст с изображения. Формат вывода: Markdown.",
    }
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "auto",
        torch_dtype: str = "auto",
        max_new_tokens: int = 2048,
        use_flash_attention: bool = False  # Выключен по умолчанию (требует pip install flash-attn)
    ):
        """
        Инициализация Qwen VL сервиса
        
        Args:
            model_name: Название модели HuggingFace (None = default)
            device: Устройство ('auto', 'cuda', 'cpu')
            torch_dtype: Тип данных ('auto', 'float16', 'bfloat16')
            max_new_tokens: Максимум токенов в ответе
            use_flash_attention: Использовать Flash Attention 2 (требует pip install flash-attn)
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device
        self.torch_dtype = torch_dtype
        self.max_new_tokens = max_new_tokens
        self.use_flash_attention = use_flash_attention
        
        self._model = None
        self._processor = None
        self._available = None
        self._actual_device = None
    
    def is_available(self) -> bool:
        """Проверка доступности сервиса"""
        if self._available is not None:
            return self._available
        
        # Проверка зависимостей
        if not TORCH_AVAILABLE:
            self._available = False
            return False
        
        if not TRANSFORMERS_AVAILABLE:
            self._available = False
            return False
        
        if not PIL_AVAILABLE:
            self._available = False
            return False
        
        # Проверка CUDA
        if not torch.cuda.is_available():
            print("⚠️ QwenVL: CUDA недоступна, модель будет работать на CPU (медленно)")
        
        self._available = True
        return True
    
    def _load_model(self):
        """Ленивая загрузка модели"""
        if self._model is not None:
            return
        
        if not self.is_available():
            raise RuntimeError(
                "QwenVL недоступен!\n"
                "Установите: pip install transformers torch accelerate"
            )
        
        print(f"🔄 Загрузка модели {self.model_name}...")
        
        # Определение устройства и dtype
        if self.device == "auto":
            self._actual_device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._actual_device = self.device
        
        if self.torch_dtype == "auto":
            dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        elif self.torch_dtype == "float16":
            dtype = torch.float16
        elif self.torch_dtype == "bfloat16":
            dtype = torch.bfloat16
        else:
            dtype = torch.float32
        
        # Параметры загрузки
        load_kwargs = {
            "torch_dtype": dtype,
            "device_map": "auto" if self._actual_device == "cuda" else None,
        }
        
        # Flash Attention 2 (если доступен)
        if self.use_flash_attention and torch.cuda.is_available():
            try:
                load_kwargs["attn_implementation"] = "flash_attention_2"
            except Exception:
                pass
        
        # Загрузка модели
        self._model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.model_name,
            **load_kwargs
        )
        
        # Загрузка процессора
        self._processor = AutoProcessor.from_pretrained(self.model_name)
        
        # Перенос на устройство (если не auto device_map)
        if load_kwargs.get("device_map") is None:
            self._model.to(self._actual_device)
        
        print(f"✅ Модель загружена на {self._actual_device}")
    
    def process_image(self, image_data: bytes, prompt: str = "") -> str:
        """
        OCR через Qwen2.5-VL
        
        Args:
            image_data: Байты изображения
            prompt: Тип промпта или кастомный промпт
        
        Returns:
            Распознанный текст в Markdown
        """
        if not self.is_available():
            raise RuntimeError("QwenVL недоступен")
        
        self._load_model()
        
        try:
            # Определение промпта
            if prompt in self.PROMPTS:
                actual_prompt = self.PROMPTS[prompt]
            elif prompt:
                actual_prompt = prompt
            else:
                actual_prompt = self.PROMPTS["default"]
            
            # Конвертация изображения в base64
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            
            # Формирование сообщения для модели
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": f"data:image/png;base64,{image_base64}",
                        },
                        {
                            "type": "text",
                            "text": actual_prompt
                        }
                    ]
                }
            ]
            
            # Подготовка входных данных
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            
            # Открытие изображения
            pil_image = Image.open(io.BytesIO(image_data))
            
            inputs = self._processor(
                text=[text],
                images=[pil_image],
                padding=True,
                return_tensors="pt"
            )
            
            # Перенос на устройство
            inputs = inputs.to(self._model.device)
            
            # Генерация
            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                )
            
            # Декодирование
            generated_ids = output_ids[:, inputs.input_ids.shape[1]:]
            output_text = self._processor.batch_decode(
                generated_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]
            
            return output_text.strip()
        
        except Exception as e:
            raise RuntimeError(f"QwenVL обработка не удалась: {e}")
    
    def get_service_name(self) -> str:
        return f"Qwen2.5-VL ({self.model_name.split('/')[-1]})"
    
    def get_service_type(self) -> str:
        if self._actual_device == "cuda":
            return "gpu"
        return "cpu"
    
    def get_service_info(self) -> dict:
        """Расширенная информация о сервисе"""
        return {
            "name": self.get_service_name(),
            "model": self.model_name,
            "available": self.is_available(),
            "device": self._actual_device or self.device,
            "torch_dtype": self.torch_dtype,
            "max_new_tokens": self.max_new_tokens,
            "prompts_available": list(self.PROMPTS.keys()),
        }
    
    def unload_model(self):
        """Выгрузка модели из памяти"""
        if self._model is not None:
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("🗑️ Модель выгружена из памяти")
    
    def __repr__(self) -> str:
        status = "✅" if self.is_available() else "❌"
        return f"QwenVLService({status}, model={self.model_name})"


def is_qwen_available() -> bool:
    """Проверка доступности Qwen VL"""
    return TORCH_AVAILABLE and TRANSFORMERS_AVAILABLE and PIL_AVAILABLE
