# DeepSeek-OCR API - Полная документация

**Дата:** 31 октября 2025  
**Источник:** `DeepSeek-OCR-hf/run_dpsk_ocr.py` + `config.py`  
**Версия модели:** deepseek-ai/DeepSeek-OCR

---

## 📋 Содержание

1. [Инициализация модели](#инициализация-модели)
2. [Метод model.infer()](#метод-modelinfer)
3. [Режимы работы](#режимы-работы)
4. [Промпты](#промпты)
5. [Параметры производительности](#параметры-производительности)
6. [Примеры использования](#примеры-использования)

---

## 🚀 Инициализация модели

### Загрузка модели с HuggingFace

```python
from transformers import AutoModel, AutoTokenizer
import torch
import os

# Опционально: выбор GPU
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

model_name = 'deepseek-ai/DeepSeek-OCR'

# Загрузка tokenizer
tokenizer = AutoTokenizer.from_pretrained(
    model_name, 
    trust_remote_code=True
)

# Загрузка модели
model = AutoModel.from_pretrained(
    model_name,
    _attn_implementation='flash_attention_2',  # или 'eager' если flash-attn не установлен
    trust_remote_code=True,
    use_safetensors=True,
    torch_dtype=torch.bfloat16,  # Рекомендуется для производительности
    device_map="cuda"  # Автоматически загружает на GPU
)
model = model.eval()
```

### Параметры загрузки модели

| Параметр | Значение | Описание |
|----------|----------|----------|
| `_attn_implementation` | `'flash_attention_2'` | ⚡ Быстрый attention (требует flash-attn) |
| | `'eager'` | Fallback (медленнее, но без зависимостей) |
| `torch_dtype` | `torch.bfloat16` | Оптимальный для RTX 5080 (точность + скорость) |
| | `torch.float16` | Альтернатива (может быть менее стабильным) |
| `device_map` | `"cuda"` | Автоматическая загрузка на GPU |
| | `"cuda:0"` | Конкретный GPU |
| | `"auto"` | Автоматический выбор устройства |
| `use_safetensors` | `True` | Безопасный формат весов (рекомендуется) |
| `trust_remote_code` | `True` | **ОБЯЗАТЕЛЬНО** для DeepSeek-OCR |

---

## 🔧 Метод model.infer()

### Сигнатура метода

```python
res = model.infer(
    tokenizer,           # ОБЯЗАТЕЛЬНО
    prompt='',           # ОБЯЗАТЕЛЬНО
    image_file='',       # ОБЯЗАТЕЛЬНО
    output_path='',      # ОБЯЗАТЕЛЬНО
    base_size=1024,      # По умолчанию: 1024
    image_size=1024,     # По умолчанию: 1024
    crop_mode=False,     # По умолчанию: False
    save_results=False,  # По умолчанию: False
    test_compress=False  # По умолчанию: False
)
```

### Параметры

#### tokenizer (обязательный)
- **Тип:** `AutoTokenizer`
- **Описание:** Токенизатор модели, загруженный через `AutoTokenizer.from_pretrained()`
- **Пример:** 
  ```python
  tokenizer = AutoTokenizer.from_pretrained('deepseek-ai/DeepSeek-OCR', trust_remote_code=True)
  ```

#### prompt (обязательный)
- **Тип:** `str`
- **Описание:** Инструкция для модели, определяющая тип обработки
- **Варианты:** см. раздел [Промпты](#промпты)
- **Пример:** 
  ```python
  prompt = "<image>\n<|grounding|>Convert the document to markdown."
  ```

#### image_file (обязательный)
- **Тип:** `str`
- **Описание:** Путь к изображению для обработки
- **Поддерживаемые форматы:** `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`
- **Пример:** 
  ```python
  image_file = '/path/to/image.png'
  ```

#### output_path (обязательный)
- **Тип:** `str`
- **Описание:** Путь к директории для сохранения результатов (если `save_results=True`)
- **Пример:** 
  ```python
  output_path = '/path/to/output/dir'
  ```

#### base_size (опциональный, default: 1024)
- **Тип:** `int`
- **Описание:** Базовый размер для масштабирования изображения. Влияет на количество vision tokens.
- **Варианты:** `512`, `640`, `1024`, `1280`, `1536`
- **Рекомендации:**
  - `512` (Tiny) - простые страницы, 64 vision tokens
  - `640` (Small) - средние страницы, 100 vision tokens
  - `1024` (Base) - стандарт, 256 vision tokens ⭐
  - `1280` (Large) - плотные страницы, 400 vision tokens
  - `1536` (Extra Large) - очень детальные, 576 vision tokens
- **Пример:** 
  ```python
  base_size = 1024  # Base mode
  ```

#### image_size (опциональный, default: 1024)
- **Тип:** `int`
- **Описание:** Целевой размер изображения для обработки. В режиме `crop_mode=False` должен быть равен `base_size`.
- **Варианты:** Обычно совпадает с `base_size`, кроме Gundam mode
- **Рекомендации:**
  - **Base mode:** `image_size = base_size` (например, 1024 = 1024)
  - **Gundam mode:** `image_size < base_size` (например, 1024 base, 640 image)
- **Пример:** 
  ```python
  image_size = 1024  # Для Base mode
  ```

#### crop_mode (опциональный, default: False)
- **Тип:** `bool`
- **Описание:** Режим разбиения изображения на части (tiling)
- **Варианты:**
  - `False` - Base/Large mode (единое изображение)
  - `True` - Gundam mode (разбиение на 2-9 частей)
- **Использование:**
  - `False` - для обычных документов (A4, книги)
  - `True` - для газет, постеров, плотных страниц
- **Важно:** При `crop_mode=True` также установите `image_size` меньше `base_size`
- **Пример:** 
  ```python
  crop_mode = False  # Base mode
  ```

#### save_results (опциональный, default: False)
- **Тип:** `bool`
- **Описание:** Сохранять ли результаты в файлы
- **Варианты:**
  - `False` - результат только в return value (рекомендуется для API)
  - `True` - сохраняет markdown в `output_path`
- **Пример:** 
  ```python
  save_results = False  # Не сохранять файлы
  ```

#### test_compress (опциональный, default: False)
- **Тип:** `bool`
- **Описание:** Тестировать сжатие токенов (для отладки)
- **Варианты:**
  - `False` - обычная работа
  - `True` - выводит статистику сжатия в stdout
- **Использование:** Только для разработки и отладки
- **Пример:** 
  ```python
  test_compress = False  # Отключено для production
  ```

### Возвращаемое значение

⚠️ **ВАЖНО:** `model.infer()` **печатает результат в stdout** и возвращает `None`!

```python
res = model.infer(...)  # res = None

# Результат печатается в stdout:
# =====================
# BASE:  torch.Size([1, 256, 1280])
# NO PATCHES
# =====================
# <|ref|>text<|/ref|><|det|>[[x0, y0, x1, y1]]<|/det|>
# Распознанный текст
```

**Для захвата результата:**

```python
import sys
from io import StringIO

old_stdout = sys.stdout
sys.stdout = captured_output = StringIO()

try:
    res = model.infer(tokenizer, prompt=prompt, ...)
finally:
    sys.stdout = old_stdout
    result = captured_output.getvalue()

print(result)  # Теперь у вас есть текст результата
```

---

## 🎨 Режимы работы

### Таблица режимов

| Режим | base_size | image_size | crop_mode | Vision Tokens | Применение | VRAM |
|-------|-----------|------------|-----------|---------------|------------|------|
| **Tiny** | 512 | 512 | False | 64 | Простые страницы | ~4GB |
| **Small** | 640 | 640 | False | 100 | Средние страницы | ~6GB |
| **Base** | 1024 | 1024 | False | 256 | ⭐ Стандарт (рекомендуется) | ~8GB |
| **Large** | 1280 | 1280 | False | 400 | Плотные страницы | ~12GB |
| **Extra Large** | 1536 | 1536 | False | 576 | Очень детальные | ~16GB |
| **Gundam** | 1024 | 640 | True | Dynamic (2-9 crops) | Газеты, постеры | ~12GB |

### Рекомендации по выбору режима

**Для документов (A4, книги, отчеты):**
```python
# Base mode - оптимальный баланс
base_size = 1024
image_size = 1024
crop_mode = False
```

**Для мелкого текста / таблиц:**
```python
# Large mode - больше деталей
base_size = 1280
image_size = 1280
crop_mode = False
```

**Для газет / постеров:**
```python
# Gundam mode - dynamic tiling
base_size = 1024
image_size = 640
crop_mode = True
```

**Для быстрой обработки:**
```python
# Small mode - быстрее, но менее точный
base_size = 640
image_size = 640
crop_mode = False
```

---

## 💬 Промпты

### Официальные промпты

| # | Промпт | Описание | Использование |
|---|--------|----------|---------------|
| 1 | `<image>\n<|grounding|>Convert the document to markdown.` | ⭐ Документ → Markdown с bbox | Документы, отчеты |
| 2 | `<image>\nFree OCR.` | Свободный OCR без структуры | Быстрое извлечение текста |
| 3 | `<image>\n<|grounding|>OCR this image.` | OCR с bbox координатами | Произвольные изображения |
| 4 | `<image>\nParse the figure.` | Парсинг графика/диаграммы | ❌ НЕ OCR! Описывает диаграмму |
| 5 | `<image>\nDescribe this image in detail.` | Детальное описание | ❌ НЕ OCR! Генерирует описание |
| 6 | `<image>\nLocate <\|ref\|>текст<\|/ref\|> in the image.` | Поиск конкретного текста | Локализация элементов |

### Режим `<|grounding|>` - что это?

**`<|grounding|>` = добавляет BBox координаты к распознанному тексту**

**Без `<|grounding|>`:**
```
Это текст документа.
```

**С `<|grounding|>`:**
```
<|ref|>text<|/ref|><|det|>[[106, 170, 763, 190]]<|/det|>
Это текст документа.
```

Где:
- `<|ref|>text<|/ref|>` - тип элемента (text, image, table)
- `<|det|>[[x0, y0, x1, y1]]<|/det|>` - координаты bounding box

### Кастомные промпты для BPMN (протестированные)

⚠️ **Ни один не заставил модель извлечь текст из BPMN диаграмм!**

```python
# Попытка 1
prompt = "<image>\n<|grounding|>Extract ALL text from this image, including text inside diagram shapes and boxes."

# Попытка 2
prompt = "<image>\n<|grounding|>OCR this diagram. Extract text from all shapes, labels, and annotations."

# Попытка 3
prompt = "<image>\n<|grounding|>Convert the BPMN diagram to markdown. Include all text from shapes, gateways, and events."
```

**Результат:** Модель видит диаграмму как `<|ref|>image<|/ref|>` и не извлекает текст изнутри.

---

## ⚙️ Параметры производительности

### В config.py

```python
# Concurrent запросы
MAX_CONCURRENCY = 50  # Для 16GB VRAM
# Уменьшите до 20-30 если CUDA OOM
# Увеличьте до 100 если есть запас VRAM

# Воркеры предобработки изображений
NUM_WORKERS = 32  # Оптимально = количество CPU cores

# Отладка
PRINT_NUM_VIS_TOKENS = False  # True для отладки
SKIP_REPEAT = True  # Пропускать повторы
```

### Производительность на RTX 5080 (16GB)

| Режим | Время (сек) | Vision Tokens | Качество |
|-------|-------------|---------------|----------|
| Tiny | ~0.5 | 64 | Низкое |
| Small | ~0.8 | 100 | Среднее |
| Base | ~1.5-2.0 | 256 | Высокое ⭐ |
| Large | ~2.5-3.0 | 400 | Очень высокое |
| Gundam | ~5-10 | 128-576 | Высокое (для газет) |

**С flash-attention vs без:**
- С flash-attn: ~1.5-2x быстрее
- Без (eager): стабильно, но медленнее

---

## 📝 Примеры использования

### Пример 1: Базовое использование (Base mode)

```python
from transformers import AutoModel, AutoTokenizer
import torch

# Загрузка
model_name = 'deepseek-ai/DeepSeek-OCR'
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(
    model_name,
    _attn_implementation='flash_attention_2',
    trust_remote_code=True,
    use_safetensors=True,
    torch_dtype=torch.bfloat16,
    device_map="cuda"
)
model = model.eval()

# Обработка
prompt = "<image>\n<|grounding|>Convert the document to markdown."
image_file = 'document.png'
output_path = './output'

# Захват stdout
import sys
from io import StringIO

old_stdout = sys.stdout
sys.stdout = captured_output = StringIO()

try:
    res = model.infer(
        tokenizer,
        prompt=prompt,
        image_file=image_file,
        output_path=output_path,
        base_size=1024,
        image_size=1024,
        crop_mode=False,
        save_results=False,
        test_compress=False
    )
finally:
    sys.stdout = old_stdout
    result = captured_output.getvalue()

print(result)
```

### Пример 2: Large mode для детального распознавания

```python
# Large mode - больше vision tokens
res = model.infer(
    tokenizer,
    prompt="<image>\n<|grounding|>Convert the document to markdown.",
    image_file='detailed_document.png',
    output_path='./output',
    base_size=1280,  # Large
    image_size=1280,
    crop_mode=False,
    save_results=False,
    test_compress=False
)
```

### Пример 3: Gundam mode для газет

```python
# Gundam mode - dynamic tiling
res = model.infer(
    tokenizer,
    prompt="<image>\n<|grounding|>Convert the document to markdown.",
    image_file='newspaper.png',
    output_path='./output',
    base_size=1024,
    image_size=640,  # Меньше base_size!
    crop_mode=True,  # Включен tiling
    save_results=False,
    test_compress=False
)
```

### Пример 4: Быстрое извлечение текста (без bbox)

```python
# Free OCR - быстрый, без координат
res = model.infer(
    tokenizer,
    prompt="<image>\nFree OCR.",
    image_file='simple_text.png',
    output_path='./output',
    base_size=640,  # Small mode для скорости
    image_size=640,
    crop_mode=False,
    save_results=False,
    test_compress=False
)
```

---

## 🔍 Парсинг результатов

### Формат вывода с `<|grounding|>`

```
=====================
BASE:  torch.Size([1, 256, 1280])
NO PATCHES
=====================

<|ref|>text<|/ref|><|det|>[[80, 119, 510, 135]]<|/det|>
Заголовок документа

<|ref|>text<|/ref|><|det|>[[106, 170, 763, 190]]<|/det|>
Параграф текста

<|ref|>table<|/ref|><|det|>[[100, 300, 700, 500]]<|/det|>
| Колонка 1 | Колонка 2 |
|-----------|-----------|
| Данные    | Данные    |

<|ref|>image<|/ref|><|det|>[[327, 309, 667, 536]]<|/det|>
```

### Парсинг в Python

```python
import re

def parse_deepseek_output(output):
    blocks = []
    lines = output.split('\n')
    
    for i, line in enumerate(lines):
        if '<|ref|>' in line:
            # Извлекаем тип
            block_type = line.split('<|ref|>')[1].split('<|/ref|>')[0]
            
            # Извлекаем bbox
            bbox = None
            if '<|det|>' in line:
                det_str = line.split('<|det|>')[1].split('<|/det|>')[0]
                import ast
                bbox_list = ast.literal_eval(det_str)
                if bbox_list:
                    bbox = bbox_list[0]
            
            # Извлекаем текст (на следующих строках)
            content = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith('<|'):
                if lines[j].strip():
                    content.append(lines[j].strip())
                j += 1
            
            blocks.append({
                'type': block_type,
                'bbox': bbox,
                'content': '\n'.join(content)
            })
    
    return blocks
```

---

## ⚠️ Известные ограничения

### 1. BPMN диаграммы НЕ распознаются

**Проблема:** Модель видит диаграмму как единый `<|ref|>image<|/ref|>` блок и не извлекает текст изнутри фигур.

**Решение:** Fine-tuning на BPMN датасете или использование альтернативных инструментов.

### 2. Промпты `parse_figure` и `describe` - это НЕ OCR

**Проблема:** Они генерируют описание изображения, а не распознают текст.

**Решение:** Используйте промпт `<|grounding|>Convert the document to markdown.`

### 3. model.infer() возвращает None

**Проблема:** Результат печатается в stdout, а не возвращается.

**Решение:** Захватывайте stdout через `StringIO` (см. примеры выше).

### 4. Координаты в пикселях оригинального изображения

**Проблема:** BBox координаты соответствуют масштабированному изображению, а не оригиналу.

**Решение:** Пересчитывайте координаты с учетом масштабирования.

---

## 📚 Дополнительные ресурсы

- **Официальный репозиторий:** https://github.com/deepseek-ai/DeepSeek-OCR
- **HuggingFace Hub:** https://huggingface.co/deepseek-ai/DeepSeek-OCR
- **Облачный API:** https://www.deepseek-ocr.ai/docs
- **Paper:** (ссылка на arXiv, когда опубликуют)

---

**Автор документации:** BPMN Automation Team  
**Версия:** 1.0  
**Дата:** 31 октября 2025

