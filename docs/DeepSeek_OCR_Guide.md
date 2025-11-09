# DeepSeek-OCR: Полное руководство

Комплексное руководство по установке, настройке и использованию DeepSeek-OCR для проекта BPMN Process Automation.

---

## 📋 Содержание

- [🚀 Quick Start](#-quick-start)
- [📦 Полная установка](#-полная-установка)
- [🔗 Интеграция с проектом](#-интеграция-с-проектом)
- [✅ Проверка работоспособности](#-проверка-работоспособности)
- [🐛 Troubleshooting](#-troubleshooting)
- [📚 Дополнительные ресурсы](#-дополнительные-ресурсы)

---

## 🚀 Quick Start

<details>
<summary><b>Для тех, кто уже установил DeepSeek-OCR</b> (разверните для быстрых команд)</summary>

### ⚡ TL;DR

```bash
# 1. Активировать окружение
cd ~/PDFtoBPMN
source DeepSeek-OCR/venv/bin/activate

# 2. Запустить OCR сервис
python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000

# 3. Протестировать (в другом терминале)
python test_russian_prompts.py
```

---

### 📋 ЧТО УЖЕ УСТАНОВЛЕНО

#### ✅ DeepSeek-OCR
- **Модель:** `deepseek-ai/DeepSeek-OCR` (3B параметров)
- **Расположение:** `~/.cache/huggingface/hub/`
- **Статус:** Загружена и работает
- **GPU:** Современная NVIDIA GPU (16GB+ VRAM)

#### ✅ Flash-attention-2
- **Версия:** 2.7.3
- **Размер:** 406 MB
- **Статус:** Скомпилирован для CUDA 12.8
- **Архитектуры:** sm_80, sm_90, sm_100, sm_120

#### ✅ FastAPI Микросервис
- **Файл:** `pdf_to_context/ocr_service/app.py`
- **Endpoint:** `http://localhost:8000/ocr/figure`
- **Health:** `http://localhost:8000/health`
- **Статус:** Работает

#### ✅ Библиотека Промптов
- **Файл:** `pdf_to_context/ocr_service/prompts.py`
- **Системных:** 6 (default, ocr_simple, free_ocr, parse_figure, describe, bpmn)
- **Русских:** 5 (russian_simple, russian_layout, russian_bpmn, russian_preserve, russian_full)

---

### 🎯 ДОСТУПНЫЕ ПРОМПТЫ

#### Системные (от DeepSeek)

| Промпт | Назначение | Результат |
|--------|------------|-----------|
| `default` | Layout OCR | Текст + координаты (заголовки) |
| `ocr_simple` | Simple OCR | Текст BPMN (с транслитерацией) |
| `describe` | ⭐ Описание | **Правильные русские названия** |
| `parse_figure` | График/диаграмма | Описание элементов |
| `free_ocr` | Свободный OCR | Текст без структуры |
| `bpmn` | BPMN-специфичный | Кастомный |

#### Русские (экспериментальные)

| Промпт | Назначение | Результат |
|--------|------------|-----------|
| `russian_simple` | KISS подход | Заголовки без транслитерации |
| `russian_layout` | ⭐ Рекомендован | **Координаты + чистая кириллица** |
| `russian_bpmn` | BPMN-специфичный | Заголовки без транслитерации |
| `russian_preserve` | Агрессивный | Заголовки без транслитерации |
| `russian_full` | Детальный | Заголовки без транслитерации |

---

### 🔧 КАК ИСПОЛЬЗОВАТЬ

#### Вариант 1: Через API (curl)

```bash
# Запустить сервис
source DeepSeek-OCR/venv/bin/activate
python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000 &

# Отправить изображение
curl -X POST http://localhost:8000/ocr/figure \
  -F "file=@output/page_54_fresh_300dpi.png" \
  -F "prompt_type=describe" \
  -F "base_size=1024" \
  -F "image_size=1024"
```

#### Вариант 2: Через Python

```python
import requests

# Загрузить изображение
with open("output/page_54_fresh_300dpi.png", "rb") as f:
    img_data = f.read()

# Отправить на OCR
files = {"file": ("test.png", img_data, "image/png")}
data = {
    "prompt_type": "describe",  # или "russian_layout"
    "base_size": 1024,
    "image_size": 1024
}

response = requests.post(
    "http://localhost:8000/ocr/figure",
    files=files,
    data=data
)

result = response.json()
print(result['markdown'])
```

#### Вариант 3: Готовые утилиты

```bash
# Тестирование русских промптов
python test_russian_prompts.py

# Тестирование одного изображения
python test_single_image.py

# Тестирование API промптов
python api_prompt_test.py
```

---

### 📊 ЧТО РАБОТАЕТ, ЧТО НЕТ

#### ✅ Работает отлично:
1. **Извлечение текста с документов** (заголовки, абзацы)
2. **Координаты текстовых блоков** (prompt: `default`, `russian_layout`)
3. **Описание диаграмм на английском** (prompt: `describe`, `parse_figure`)
   - Правильно цитирует русские названия: "labeled as 'Процесс 1'"
4. **Обработка русского текста** (при явном указании "Language: Russian")
5. **Скорость** (2-10 сек на изображение 300 DPI)

#### ❌ НЕ работает:
1. **Извлечение текста ИЗ элементов BPMN диаграммы**
   - Диаграмма → `<|ref|>image<|/ref|>` (единый блок)
   - Текст внутри shapes (прямоугольников, кругов) НЕ извлекается
   - Независимо от промпта!
2. **OCR внутри визуальных элементов** (boxes, circles, arrows)

#### ⚠️ Работает с ограничениями:
1. **`ocr_simple` извлекает BPMN текст, но искажает кириллицу**
   - "Процесс 1" → `npoecc1`
   - "Событие 1" → `C6bITHe1`
2. **`describe` дает правильные названия, но БЕЗ координат**
   - Описывает содержимое, но не говорит где именно

---

### 🎯 РЕКОМЕНДОВАННАЯ СТРАТЕГИЯ

#### Для текущей задачи (BPMN извлечение):

**Комбинированный подход (Вариант B):**

```
1. Запрос с describe → получить правильные русские названия элементов
   Result: "...labeled as 'Процесс 1,' 'Процесс 2,' 'Процесс 3.'"

2. Запрос с default → получить координаты заголовков
   Result: <|det|>[[77, 120, 516, 137]]<|/det|>

3. ElementMatcher → сопоставить по Y-координатам (позиционирование)

4. Экспорт в BPMN IR → конвертация в XML
```

**Ожидаемая точность:** 75-85%  
**Время реализации:** 3-4 часа  
**Сложность:** Средняя

---

### 📞 БЫСТРАЯ СПРАВКА

| Действие | Команда |
|----------|---------|
| Активировать окружение | `source DeepSeek-OCR/venv/bin/activate` |
| Запустить сервис | `python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000` |
| Проверить health | `curl http://localhost:8000/health` |
| Остановить сервис | `pkill -f "uvicorn.*ocr_service"` |
| Тест промптов | `python test_russian_prompts.py` |
| Проверить CUDA | `nvidia-smi` |
| Проверить flash-attn | `pip show flash-attn` |

</details>

---

## 📦 Полная установка

Пошаговая инструкция для новых пользователей.

### 🖥️ Требования к системе

#### Минимальные требования

- **OS**: Windows 10/11 с WSL2
- **GPU**: NVIDIA с поддержкой CUDA (минимум 8GB VRAM)
- **RAM**: 16GB+ системной памяти
- **Диск**: 30GB+ свободного места
- **CUDA**: 11.5+ (драйвер NVIDIA)

#### Рекомендуемые требования

- **GPU**: NVIDIA RTX серии 40XX/50XX или лучше (16GB+ VRAM)
- **RAM**: 32GB+ системной памяти
- **Диск**: 50GB+ свободного места (SSD)
- **CUDA**: 12.1+

---

### 🔍 Проверка окружения

#### Шаг 1: Проверка WSL2

```powershell
# В PowerShell проверяем установлен ли WSL2
wsl --list --verbose
```

**Ожидаемый вывод:**
```
  NAME                   STATE           VERSION
* Ubuntu-22.04           Running         2
  docker-desktop         Stopped         2
```

Если WSL2 не установлен:
```powershell
wsl --install -d Ubuntu-22.04
```

#### Шаг 2: Проверка NVIDIA GPU

```bash
# В WSL Ubuntu
nvidia-smi
```

**Ожидаемый вывод:**
```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 575.64.01              Driver Version: 576.88         CUDA Version: 12.9     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
|   0  NVIDIA GeForce RTX XXXX        On  |   00000000:01:00.0  On |                  N/A |
+-----------------------------------------------------------------------------------------+
```

Если `nvidia-smi` не работает - установите NVIDIA CUDA Toolkit для WSL2:
- Скачайте с: https://developer.nvidia.com/cuda-downloads
- Выберите: Linux → x86_64 → WSL-Ubuntu → 2.0 → deb (network)

#### Шаг 3: Проверка CUDA Toolkit

```bash
# В WSL Ubuntu
nvcc --version
```

**Ожидаемый вывод:**
```
Cuda compilation tools, release 11.5, V11.5.119
```

Если CUDA toolkit не установлен:
```bash
# Установка CUDA Toolkit 12.x
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-toolkit-12-8
```

#### Шаг 4: Проверка Python

```bash
# В WSL Ubuntu
python3 --version
```

**Требуется**: Python 3.10 или 3.11

Если Python не установлен:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

---

### 🚀 Установка на WSL2 Ubuntu

#### Шаг 1: Клонирование репозитория проекта

```bash
# Переход в рабочую директорию через WSL
cd ~/PDFtoBPMN

# Клонирование (если еще не сделано)
git clone YOUR_REPO_URL
cd PDFtoBPMN
```

#### Шаг 2: Клонирование DeepSeek-OCR

```bash
# В директории проекта
git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
cd DeepSeek-OCR
```

#### Шаг 3: Создание виртуального окружения

```bash
# Создание venv
python3 -m venv venv

# Активация
source venv/bin/activate

# Обновление pip
pip install --upgrade pip
```

#### Шаг 4: Установка PyTorch с CUDA

**КРИТИЧЕСКИ ВАЖНО для новейших GPU (Blackwell, sm_120)!**

```bash
# PyTorch 2.9.0 + CUDA 12.8 (~2.5GB, 5-10 минут)
# ОБЯЗАТЕЛЬНО для новейших GPU архитектур! Более старые версии могут не работать!
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Проверка установки PyTorch:**
```bash
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'CUDA Version: {torch.version.cuda}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

**Ожидаемый вывод:**
```
PyTorch: 2.9.0+cu128
CUDA Available: True
CUDA Version: 12.8
GPU: NVIDIA GeForce RTX XXXX
```

**Поддерживаемые архитектуры:**
- PyTorch 2.9.0 поддерживает: sm_50, sm_60, sm_70, sm_75, sm_80, sm_86, sm_90, **sm_120 (Blackwell)**
- PyTorch 2.7.x и старше: **НЕ поддерживают sm_120** → новейшие GPU могут не работать!

#### Шаг 5: Установка зависимостей DeepSeek-OCR

```bash
# Установка requirements.txt (~2GB, 2-3 минуты)
pip install -r requirements.txt
```

**requirements.txt включает:**
- transformers==4.46.3
- tokenizers==0.20.3
- PyMuPDF
- img2pdf
- einops
- easydict
- addict
- Pillow
- numpy

#### Шаг 6: Настройка окружения для flash-attention (КРИТИЧНО!)

**⚠️ ВАЖНО для новейших GPU (Blackwell, sm_120)!**

Flash-attention требует правильной настройки CUDA окружения и может занять 3-5 часов на компиляцию.

##### 6.1 Настройка переменных окружения в venv

Отредактируйте файл `venv/bin/activate` для автоматической настройки CUDA при активации:

```bash
nano DeepSeek-OCR/venv/bin/activate
```

Добавьте **перед строкой `export PATH`**:

```bash
# ===== CUDA Configuration (добавлено для flash-attn) =====
_OLD_VIRTUAL_CUDA_HOME="${CUDA_HOME:-}"
CUDA_HOME=/usr/local/cuda-12.8
export CUDA_HOME

_OLD_VIRTUAL_LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
export LD_LIBRARY_PATH

# Добавляем nvcc в PATH (ПЕРЕД $PATH!)
PATH="/usr/local/cuda-12.8/bin:$PATH"

# Ограничиваем параллельные потоки компиляции (критично для 18GB RAM)
export MAX_JOBS=1

# Указываем архитектуру GPU (sm_120 для Blackwell)
export TORCH_CUDA_ARCH_LIST="12.0"
# ===== End CUDA Configuration =====
```

В раздел `deactivate()` добавьте восстановление:

```bash
deactivate () {
    # ... existing code ...
    
    # Restore CUDA environment
    if [ -n "${_OLD_VIRTUAL_CUDA_HOME:-}" ] ; then
        CUDA_HOME="${_OLD_VIRTUAL_CUDA_HOME:-}"
        export CUDA_HOME
        unset _OLD_VIRTUAL_CUDA_HOME
    else
        unset CUDA_HOME
    fi
    
    if [ -n "${_OLD_VIRTUAL_LD_LIBRARY_PATH:-}" ] ; then
        LD_LIBRARY_PATH="${_OLD_VIRTUAL_LD_LIBRARY_PATH:-}"
        export LD_LIBRARY_PATH
        unset _OLD_VIRTUAL_LD_LIBRARY_PATH
    else
        unset LD_LIBRARY_PATH
    fi
    
    unset MAX_JOBS
    unset TORCH_CUDA_ARCH_LIST
    
    # ... rest of existing code ...
}
```

##### 6.2 Проверка настроек CUDA

```bash
# Деактивируйте и заново активируйте venv
deactivate
source venv/bin/activate

# Проверьте переменные
echo "CUDA_HOME: $CUDA_HOME"
echo "LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
echo "MAX_JOBS: $MAX_JOBS"
echo "TORCH_CUDA_ARCH_LIST: $TORCH_CUDA_ARCH_LIST"

# Проверьте nvcc
which nvcc
nvcc --version  # Должно быть 12.8
```

**Ожидаемый вывод:**
```
CUDA_HOME: /usr/local/cuda-12.8
LD_LIBRARY_PATH: /usr/local/cuda-12.8/lib64:...
MAX_JOBS: 1
TORCH_CUDA_ARCH_LIST: 12.0
/usr/local/cuda-12.8/bin/nvcc
Cuda compilation tools, release 12.8, V12.8.89
```

##### 6.3 Установка flash-attention

```bash
# Теперь устанавливаем flash-attn (3-5 часов)
pip install flash-attn==2.7.3 --no-build-isolation
```

**Ожидаемые этапы:**
1. **Building wheel** (~10-20 минут) - сборка Python пакета
2. **Compiling CUDA kernels** (~3-4 часа) - компиляция для всех архитектур:
   - sm_80 (Ampere) ~45 минут
   - sm_90 (Hopper) ~45 минут  
   - sm_100 (будущие архитектуры) ~45 минут
   - sm_120 (Blackwell) ~45 минут
3. **Installing** (~2-5 минут)

**Мониторинг процесса:**
```bash
# В другом терминале следите за процессом
watch -n 10 'ps aux | grep -E "pip|nvcc|cicc" | grep -v grep | head -5'

# Проверка использования памяти
watch -n 5 'free -h'

# Логи компиляции (если запущена в фоне с выводом в файл)
tail -f /tmp/flash_attn_install.log
```

**⚠️ Важно:**
- `MAX_JOBS=1` - критично! При 2+ потоках может произойти OOM (Out Of Memory)
- Не прерывайте процесс, даже если кажется, что он завис
- Убедитесь, что есть минимум 10GB свободной оперативной памяти
- Процесс `cicc` (CUDA internal compiler) будет использовать до 4-6GB RAM

##### 6.4 Проверка установки

```bash
python -c "import flash_attn; print('✅ Версия:', flash_attn.__version__)"
```

**Ожидаемый вывод:**
```
✅ flash-attn успешно импортирован!
📦 Версия: 2.7.3
🔍 Проверка доступных функций:
   - flash_attn_func: True
   - flash_attn_varlen_func: True
🎯 flash-attn готов к использованию!
```

**Альтернатива (если компиляция не удалась):**

Модель будет работать с `eager` attention (медленнее, но стабильно):

```bash
# В app.py автоматически используется fallback:
# - Если flash-attn установлен → flash_attention_2
# - Если нет → eager attention (с предупреждением)
```

#### Шаг 7: Проверка окружения

```bash
pip list | grep -E "torch|vllm|transformers|flash"
```

**Ожидаемый вывод:**
```
flash-attn              2.7.3
torch                   2.5.1+cu121
torchaudio              2.5.1+cu121
torchvision             0.20.1+cu121
transformers            4.46.3
```

---

## 🔗 Интеграция с проектом

### Шаг 1: Настройка микросервиса OCR

```bash
cd ~/PDFtoBPMN
```

Наш микросервис находится в:
```
pdf_to_context/ocr_service/app.py
```

### Шаг 2: Запуск OCR микросервиса

```bash
# Активируем окружение DeepSeek-OCR
cd DeepSeek-OCR
source venv/bin/activate

# Запускаем FastAPI сервис (наш собственный)
cd ~/PDFtoBPMN
python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000
```

**Проверка:**
```bash
# В другом терминале
curl http://localhost:8000/health
```

**Ожидаемый ответ:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "cuda_available": true,
  "cuda_device": "NVIDIA GeForce RTX XXXX"
}
```

### Шаг 3: Использование в pipeline

```python
from pdf_to_context import PDFToContextPipeline

# Инициализация с OCR
pipeline = PDFToContextPipeline(
    ocr_base_url="http://localhost:8000",
    prioritize_accuracy=True
)

# Обработка PDF
markdown = pipeline.process(
    pdf_path="input_data/document.pdf",
    output_path="output/result.md"
)
```

---

## ✅ Проверка работоспособности

### Тест 1: PyTorch + CUDA

```bash
python3 << EOF
import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA Available: {torch.cuda.is_available()}")
print(f"CUDA Device: {torch.cuda.get_device_name(0)}")
print(f"CUDA Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
EOF
```

### Тест 2: Transformers

```bash
python3 -c "from transformers import AutoTokenizer; tokenizer = AutoTokenizer.from_pretrained('deepseek-ai/DeepSeek-OCR', trust_remote_code=True); print('Tokenizer OK')"
```

### Тест 3: Полный pipeline

```bash
cd ~/PDFtoBPMN

# Активируем окружение проекта
source venv/bin/activate  # если создано для проекта

# Тестовый скрипт
python3 << EOF
from pdf_to_context import PDFToContextPipeline

# Health check
from pdf_to_context.extractors import OCRClient
client = OCRClient(base_url="http://localhost:8000")
print(f"OCR Service Available: {client.health_check()}")

# Pipeline test
pipeline = PDFToContextPipeline(
    ocr_base_url="http://localhost:8000",
    prioritize_accuracy=True
)
health = pipeline.health_check()
print(f"Pipeline Health: {health}")
EOF
```

---

## 🐛 Troubleshooting

### Проблема 1: `nvidia-smi` не работает в WSL

**Решение:**
```bash
# Обновите драйвер NVIDIA в Windows
# Скачайте с: https://www.nvidia.com/Download/index.aspx

# После обновления перезагрузите WSL
wsl --shutdown
wsl
```

### Проблема 2: CUDA Out of Memory

**Решение 1**: Уменьшить batch size
```python
# В вызовах API используйте меньшие изображения
base_size = 640  # вместо 1024
image_size = 640
```

**Решение 2**: Очистить CUDA кэш
```python
import torch
torch.cuda.empty_cache()
```

### Проблема 3: flash-attention сборка падает с ошибками CUDA

**Симптом 1: Неправильная версия nvcc**
```
RuntimeError: FlashAttention is only supported on CUDA 11.7 and above
Note: make sure nvcc has a supported version by running nvcc -V.
```

**Причина:**  
Системный `nvcc` (обычно 11.5) несовместим с PyTorch 2.9.0+cu128. Нужен nvcc из CUDA Toolkit 12.8.

**✅ РЕШЕНИЕ:**

Настройте CUDA окружение в виртуальном окружении (см. раздел "Шаг 6: Настройка окружения для flash-attention").

Коротко:
```bash
# Редактируйте venv/bin/activate
nano DeepSeek-OCR/venv/bin/activate

# Добавьте перед export PATH:
CUDA_HOME=/usr/local/cuda-12.8
export CUDA_HOME
LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
export LD_LIBRARY_PATH
PATH="/usr/local/cuda-12.8/bin:$PATH"

# Перезапустите venv и проверьте
deactivate && source venv/bin/activate
nvcc --version  # Должно быть 12.8
```

**Симптом 2: Killed during compilation / Out Of Memory**
```
Building wheels for collected packages: flash-attn
  ...
  Killed
```

**Причина:**  
`nvcc` запускает несколько процессов `cicc` параллельно, каждый потребляет 4-6GB RAM. На системах с 16-18GB RAM происходит OOM.

**✅ РЕШЕНИЕ:**

Ограничьте параллельные потоки компиляции:
```bash
# В venv/bin/activate добавьте:
export MAX_JOBS=1

# Перезапустите venv
deactivate && source venv/bin/activate

# Проверьте
echo $MAX_JOBS  # Должно быть 1

# Установка займет 3-5 часов, но завершится успешно
pip install flash-attn==2.7.3 --no-build-isolation
```

### Проблема 4: Новейшие GPU (Blackwell, sm_120) не работают с PyTorch

**Симптом:**
```
RuntimeError: CUDA error: no kernel image is available for execution on the device
NVIDIA GeForce RTX XXXX with CUDA capability sm_120 is not compatible with the current PyTorch installation.
The current PyTorch install supports CUDA capabilities sm_50 sm_60 sm_70 sm_75 sm_80 sm_86 sm_37 sm_90.
```

**Причина:**  
Новейшие GPU используют архитектуру **Blackwell (compute capability sm_120)**, которую НЕ поддерживает PyTorch 2.7.x и старше.

**✅ РЕШЕНИЕ:**

Установите **PyTorch 2.9.0+ с CUDA 12.8**:

```bash
cd ~/PDFtoBPMN/DeepSeek-OCR
source venv/bin/activate

# Удалить старую версию
pip uninstall -y torch torchvision torchaudio

# Установить PyTorch 2.9.0 + CUDA 12.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Проверка:**
```bash
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'GPU: {torch.cuda.get_device_name(0)}'); print(f'CUDA Available: {torch.cuda.is_available()}')"
```

**Ожидаемый вывод:**
```
PyTorch: 2.9.0+cu128
GPU: NVIDIA GeForce RTX XXXX
CUDA Available: True
```

### Проблема 5: `ModuleNotFoundError: No module named 'flash_attn'`

**Решение:**
```bash
source DeepSeek-OCR/venv/bin/activate  # Активировать окружение
pip show flash-attn                     # Проверить установку
```

Если не установлен → см. раздел "Шаг 6: Настройка окружения для flash-attention"

### Проблема 6: Модель не загружается

**Решение 1**: Проверить HuggingFace токен (для приватных моделей)
```bash
huggingface-cli login
```

**Решение 2**: Очистить кэш и перезагрузить
```bash
rm -rf ~/.cache/huggingface/hub/models--deepseek-ai--DeepSeek-OCR
# Модель загрузится заново при следующем запуске
```

### Проблема 7: `Connection refused` при обращении к API

**Решение:**
```bash
# Проверить, запущен ли сервис
curl http://localhost:8000/health

# Если нет → запустить
python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000
```

### Проблема 8: Медленная работа (>30 сек на изображение)

**Возможные причины:**
1. Flash-attention не используется → проверить логи запуска
2. Слишком большое изображение → уменьшить `base_size`, `image_size`
3. GPU перегружена → освободить VRAM

**Оптимизация:**
```bash
# Проверить, установлен ли flash-attention
pip show flash-attn

# Если нет → установить
pip install flash-attn==2.7.3 --no-build-isolation
```

---

## 🚀 Производительность

### Ожидаемая скорость обработки

**GPU: Современные GPU (16GB VRAM)**

| Режим | Страница (простая) | Страница (сложная) | Изображение |
|-------|-------------------|-------------------|-------------|
| Tiny | ~0.5 сек | ~1 сек | ~0.3 сек |
| Small | ~0.8 сек | ~1.5 сек | ~0.5 сек |
| **Base** | **~1.5 сек** | **~3 сек** | **~1 сек** |
| Large | ~3 сек | ~6 сек | ~2 сек |

**Batch processing:**
- Single page: 1-3 сек
- 10 pages: 15-30 сек
- 100 pages: 2-5 минут

---

## 📦 Сохранение состояния для синхронизации

### Что НЕ комитить в git

Добавьте в `.gitignore`:
```
# DeepSeek-OCR
DeepSeek-OCR/venv/
DeepSeek-OCR/__pycache__/
DeepSeek-OCR/**/__pycache__/
DeepSeek-OCR/**/*.pyc

# HuggingFace cache (модели)
.cache/

# venv проекта
venv/
venv_*/

# Output
output/
*.md.bak
```

### Что комитить

- ✅ `pdf_to_context/ocr_service/app.py` (наш микросервис)
- ✅ `docs/DeepSeek_OCR_Guide.md` (эта инструкция)
- ✅ `requirements.txt` (зависимости проекта)

---

## 📚 Дополнительные ресурсы

### Основная документация

- [DeepSeek-OCR GitHub](https://github.com/deepseek-ai/DeepSeek-OCR)
- [PyTorch Installation](https://pytorch.org/get-started/locally/)
- [CUDA WSL Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- [Flash-Attention GitHub](https://github.com/Dao-AILab/flash-attention)

### Исследовательские материалы (в проекте)

- **BPMN OCR Strategy** - `docs/research/BPMN_OCR_Strategy.md`
- **DeepSeek OCR Research Findings** - `docs/research/DeepSeek_OCR_Research_Findings.md`
- **Multilingual Analysis** - `docs/research/DeepSeek_OCR_Multilingual_Analysis.md`

---

## 📝 Полезные команды

### Управление WSL

```powershell
# Остановить WSL
wsl --shutdown

# Запустить конкретный дистрибутив
wsl --distribution Ubuntu-22.04

# Список дистрибутивов
wsl --list --verbose

# Установить дистрибутив по умолчанию
wsl --set-default Ubuntu-22.04
```

### Мониторинг GPU

```bash
# Постоянный мониторинг
watch -n 1 nvidia-smi

# Показать только использование памяти
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Лог использования GPU
nvidia-smi dmon -s u
```

### Управление окружениями

```bash
# Активировать окружение DeepSeek-OCR
cd DeepSeek-OCR && source venv/bin/activate

# Деактивировать
deactivate

# Удалить окружение (если нужно пересоздать)
rm -rf venv
python3 -m venv venv
```

### Очистка кэша и места

```bash
# Очистка pip кэша
pip cache purge

# Очистка HuggingFace кэша (освободит ~14GB)
rm -rf ~/.cache/huggingface/

# Очистка PyTorch кэша
rm -rf ~/.cache/torch/

# Показать использование места
du -sh ~/.cache/*
```

---

## ✉️ Поддержка

При проблемах проверьте:
1. ✅ NVIDIA драйвер обновлен в Windows
2. ✅ WSL2 (не WSL1)
3. ✅ `nvidia-smi` работает в WSL
4. ✅ PyTorch видит CUDA (`torch.cuda.is_available()`)
5. ✅ Достаточно VRAM (минимум 8GB)

Если проблемы остались - см. раздел [Troubleshooting](#-troubleshooting).

---

**Последнее обновление:** 09.11.2025  
**Статус:** Готово к использованию

