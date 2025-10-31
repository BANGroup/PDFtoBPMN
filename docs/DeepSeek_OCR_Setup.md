# Инструкция по развертыванию DeepSeek-OCR

Полное руководство по установке и настройке DeepSeek-OCR для проекта BPMN Process Automation на WSL2 Ubuntu.

---

## 📋 Содержание

- [Требования к системе](#требования-к-системе)
- [Проверка окружения](#проверка-окружения)
- [Установка на WSL2 Ubuntu](#установка-на-wsl2-ubuntu)
- [Настройка DeepSeek-OCR](#настройка-deepseek-ocr)
- [Интеграция с проектом](#интеграция-с-проектом)
- [Проверка работоспособности](#проверка-работоспособности)
- [Решение проблем](#решение-проблем)

---

## 🖥️ Требования к системе

### Минимальные требования

- **OS**: Windows 10/11 с WSL2
- **GPU**: NVIDIA с поддержкой CUDA (минимум 8GB VRAM)
- **RAM**: 16GB+ системной памяти
- **Диск**: 30GB+ свободного места
- **CUDA**: 11.5+ (драйвер NVIDIA)

### Рекомендуемые требования

- **GPU**: NVIDIA RTX 4090, RTX 5080 или лучше (16GB+ VRAM)
- **RAM**: 32GB+ системной памяти
- **Диск**: 50GB+ свободного места (SSD)
- **CUDA**: 12.1+

---

## 🔍 Проверка окружения

### Шаг 1: Проверка WSL2

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

### Шаг 2: Проверка NVIDIA GPU

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
|   0  NVIDIA GeForce RTX 5080        On  |   00000000:01:00.0  On |                  N/A |
+-----------------------------------------------------------------------------------------+
```

Если `nvidia-smi` не работает - установите NVIDIA CUDA Toolkit для WSL2:
- Скачайте с: https://developer.nvidia.com/cuda-downloads
- Выберите: Linux → x86_64 → WSL-Ubuntu → 2.0 → deb (network)

### Шаг 3: Проверка CUDA Toolkit

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

### Шаг 4: Проверка Python

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

## 🚀 Установка на WSL2 Ubuntu

### Шаг 1: Клонирование репозитория проекта

```bash
# Переход в Windows директорию через WSL
cd /mnt/c/Users/YOUR_USERNAME/Obligations

# Клонирование (если еще не сделано)
git clone YOUR_REPO_URL
cd Obligations
```

### Шаг 2: Клонирование DeepSeek-OCR

```bash
# В директории проекта
git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
cd DeepSeek-OCR
```

### Шаг 3: Создание виртуального окружения

```bash
# Создание venv
python3 -m venv venv

# Активация
source venv/bin/activate

# Обновление pip
pip install --upgrade pip
```

### Шаг 4: Установка PyTorch с CUDA

**КРИТИЧЕСКИ ВАЖНО для RTX 5080 (Blackwell, sm_120)!**

```bash
# PyTorch 2.9.0 + CUDA 12.8 (~2.5GB, 5-10 минут)
# ОБЯЗАТЕЛЬНО для RTX 5080! Более старые версии НЕ РАБОТАЮТ!
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
GPU: NVIDIA GeForce RTX 5080
```

**Поддерживаемые архитектуры:**
- PyTorch 2.9.0 поддерживает: sm_50, sm_60, sm_70, sm_75, sm_80, sm_86, sm_90, **sm_120 (Blackwell)**
- PyTorch 2.7.x и старше: **НЕ поддерживают sm_120** → RTX 5080 не работает!

### Шаг 5: Установка зависимостей DeepSeek-OCR

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

### Шаг 6: Установка vLLM

```bash
# vLLM для high-performance inference (~2GB, 5-7 минут)
pip install vllm
```

**Альтернатива**: Если возникают проблемы со сборкой:
```bash
# Установка pre-built wheel
pip install https://github.com/vllm-project/vllm/releases/download/v0.8.5/vllm-0.8.5+cu118-cp310-cp310-manylinux1_x86_64.whl
```

### Шаг 7: Настройка окружения для flash-attention (КРИТИЧНО!)

**⚠️ ВАЖНО для RTX 5080 (Blackwell, sm_120)!**

Flash-attention требует правильной настройки CUDA окружения и может занять 3-5 часов на компиляцию.

#### 7.1 Настройка переменных окружения в venv

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

# Указываем архитектуру GPU (sm_120 для RTX 5080 Blackwell)
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

#### 7.2 Проверка настроек CUDA

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

#### 7.3 Установка flash-attention

```bash
# Теперь устанавливаем flash-attn (3-5 часов)
pip install flash-attn==2.7.3 --no-build-isolation
```

**Ожидаемые этапы:**
1. **Building wheel** (~10-20 минут) - сборка Python пакета
2. **Compiling CUDA kernels** (~3-4 часа) - компиляция для всех архитектур:
   - sm_80 (Ampere: A100) ~45 минут
   - sm_90 (Hopper: H100) ~45 минут  
   - sm_100 (будущие GPU) ~45 минут
   - sm_120 (Blackwell: RTX 5080) ~45 минут
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
- Не прерывайте процесс, даже если кажется, что он завзавис
- Убедитесь, что есть минимум 10GB свободной оперативной памяти
- Процесс `cicc` (CUDA internal compiler) будет использовать до 4-6GB RAM

#### 7.4 Проверка установки

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

### Шаг 8: Проверка окружения

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
vllm                    0.11.0
```

---

## ⚙️ Настройка DeepSeek-OCR

### Шаг 1: Редактирование config.py

```bash
cd DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm
nano config.py
```

**Основные параметры:**

```python
# Режим работы (Base рекомендуется)
BASE_SIZE = 1024
IMAGE_SIZE = 1024
CROP_MODE = False  # False для Base, True для Gundam

# Для режима Base
MIN_CROPS = 1
MAX_CROPS = 1

# Для режима Gundam (газеты, постеры)
# CROP_MODE = True
# MIN_CROPS = 2
# MAX_CROPS = 6

# Concurrency (уменьшить если мало VRAM)
MAX_CONCURRENCY = 50  # Для 16GB VRAM
NUM_WORKERS = 32

# Модель (автоматически загрузится с HuggingFace)
MODEL_PATH = 'deepseek-ai/DeepSeek-OCR'

# Пути для тестов
INPUT_PATH = '/mnt/c/Users/YOUR_USERNAME/Obligations/input_data/test.pdf'
OUTPUT_PATH = '/mnt/c/Users/YOUR_USERNAME/Obligations/output/result.md'

# Промпт (по умолчанию для документов)
PROMPT = '<image>\n<|grounding|>Convert the document to markdown.'
```

**Режимы DeepSeek-OCR:**

| Режим | BASE_SIZE | IMAGE_SIZE | CROP_MODE | Vision Tokens | Применение |
|-------|-----------|------------|-----------|---------------|------------|
| **Tiny** | 512 | 512 | False | 64 | Простые страницы |
| **Small** | 640 | 640 | False | 100 | Средние страницы |
| **Base** | 1024 | 1024 | False | 256 | Стандарт (рекомендуется) |
| **Large** | 1280 | 1280 | False | 400 | Плотные страницы |
| **Gundam** | 1024 | 640 | True | Dynamic | Газеты, постеры |

### Шаг 2: Первый запуск (загрузка модели)

```bash
cd DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm

# Тест на одном изображении
python run_dpsk_ocr_image.py
```

**При первом запуске:**
- Модель загрузится с HuggingFace (~14GB)
- Сохранится в `~/.cache/huggingface/hub/`
- Займет 10-15 минут

**Где хранится модель:**
```bash
ls -lh ~/.cache/huggingface/hub/models--deepseek-ai--DeepSeek-OCR/
```

---

## 🔗 Интеграция с проектом

### Шаг 1: Настройка микросервиса OCR

```bash
cd /mnt/c/Users/YOUR_USERNAME/Obligations
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
cd /mnt/c/Users/YOUR_USERNAME/Obligations
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
  "vllm_available": true,
  "model_loaded": true
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

### Тест 2: vLLM

```bash
python3 -c "import vllm; print(f'vLLM: {vllm.__version__}')"
```

### Тест 3: Transformers

```bash
python3 -c "from transformers import AutoTokenizer; tokenizer = AutoTokenizer.from_pretrained('deepseek-ai/DeepSeek-OCR', trust_remote_code=True); print('Tokenizer OK')"
```

### Тест 4: DeepSeek-OCR на тестовом изображении

```bash
cd DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm

# Создаем тестовое изображение с текстом
convert -size 800x600 xc:white \
  -pointsize 48 -fill black \
  -annotate +100+300 "Test OCR Document\nLine 1\nLine 2" \
  /tmp/test_ocr.png

# Обновляем config.py
python3 << EOF
import sys
sys.path.insert(0, '.')
from config import *
INPUT_PATH = '/tmp/test_ocr.png'
OUTPUT_PATH = '/tmp/test_result.md'
EOF

# Запускаем OCR
python run_dpsk_ocr_image.py
```

### Тест 5: Полный pipeline

```bash
cd /mnt/c/Users/YOUR_USERNAME/Obligations

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

### Тест 6: Автоматическая проверка всех модулей (РЕКОМЕНДУЕТСЯ)

```bash
cd DeepSeek-OCR
source venv/bin/activate

# Комплексная проверка (8 модулей)
python check_setup.py

# Детальная проверка с тестами производительности
python check_modules_detailed.py

# Базовая проверка живости
python test_vllm_basic.py
```

**Ожидаемый результат:**
- ✅ Python Environment - PASS
- ✅ PyTorch + CUDA - PASS (с тестом производительности)
- ✅ PDF Libraries - PASS
- ✅ Transformers - PASS (модель в кэше)
- ✅ vLLM - PASS
- ✅ Web Frameworks - PASS
- ✅ DeepSeek-OCR - PASS
- ✅ Project Integration - PASS

---

## 🐛 Решение проблем

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

**Решение 1**: Уменьшить concurrency в config.py
```python
MAX_CONCURRENCY = 10  # вместо 100
MAX_CROPS = 2  # вместо 6 для Gundam
```

**Решение 2**: Использовать меньший режим
```python
# Вместо Base используйте Small
BASE_SIZE = 640
IMAGE_SIZE = 640
```

**Решение 3**: Очистить CUDA кэш
```python
import torch
torch.cuda.empty_cache()
```

### Проблема 3: vLLM не устанавливается

**Решение**: Установить pre-built wheel
```bash
# Для Python 3.10 + CUDA 12.1
pip install https://github.com/vllm-project/vllm/releases/download/v0.8.5/vllm-0.8.5+cu121-cp310-cp310-manylinux1_x86_64.whl
```

### Проблема 4: flash-attention сборка падает с ошибками CUDA

**Симптом 1: Неправильная версия nvcc**
```
RuntimeError: FlashAttention is only supported on CUDA 11.7 and above
Note: make sure nvcc has a supported version by running nvcc -V.
```

**Причина:**  
Системный `nvcc` (обычно 11.5) несовместим с PyTorch 2.9.0+cu128. Нужен nvcc из CUDA Toolkit 12.8.

**✅ РЕШЕНИЕ:**

Настройте CUDA окружение в виртуальном окружении (см. раздел "Шаг 7: Настройка окружения для flash-attention").

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

**Симптом 3: Компиляция длится слишком долго (>10 часов)**

**Причина:**  
`TORCH_CUDA_ARCH_LIST` игнорируется, flash-attn компилируется для всех архитектур (sm_80, sm_90, sm_100, sm_120).

**⚠️ ИЗВЕСТНАЯ ПРОБЛЕМА:**  
В текущей версии flash-attn список архитектур hardcoded в `setup.py`. Установка `TORCH_CUDA_ARCH_LIST` может не сработать.

**Решение:**  
Дождитесь завершения компиляции (~3-5 часов с `MAX_JOBS=1`), либо пропустите установку flash-attn.

**Альтернатива: Работа без flash-attn**

DeepSeek-OCR будет работать с `eager` attention (медленнее на 20-30%, но стабильно):

```bash
# Не устанавливайте flash-attn
# app.py автоматически использует fallback:
# - Если flash-attn установлен → flash_attention_2 (быстро)
# - Если нет → eager attention (медленнее, но работает)
```

### Проблема 5: Модель не загружается

**Решение 1**: Проверить HuggingFace токен (для приватных моделей)
```bash
huggingface-cli login
```

**Решение 2**: Очистить кэш и переза грузить
```bash
rm -rf ~/.cache/huggingface/hub/models--deepseek-ai--DeepSeek-OCR
python run_dpsk_ocr_image.py  # Загрузится заново
```

### Проблема 6: Медленная обработка

**Оптимизация 1**: Установить flash-attention
```bash
pip install flash-attn --no-build-isolation
```

**Оптимизация 2**: Увеличить batch size
```python
MAX_CONCURRENCY = 100  # если хватает VRAM
```

**Оптимизация 3**: Использовать tensor parallelism (несколько GPU)
```python
# В конфигурации vLLM
tensor_parallel_size = 2  # для 2 GPU
```

### Проблема 7: RTX 5080 (Blackwell, sm_120) не работает с PyTorch (КРИТИЧНО!)

**Симптом:**
```
RuntimeError: CUDA error: no kernel image is available for execution on the device
NVIDIA GeForce RTX 5080 with CUDA capability sm_120 is not compatible with the current PyTorch installation.
The current PyTorch install supports CUDA capabilities sm_50 sm_60 sm_70 sm_75 sm_80 sm_86 sm_37 sm_90.
```

**Причина:**  
RTX 5080 использует новейшую архитектуру **Blackwell (compute capability sm_120)**, которую НЕ поддерживает PyTorch 2.7.x и старше. PyTorch 2.7.1 собран под CUDA 11.8 и поддерживает только до sm_90 (Ada Lovelace).

**✅ РЕШЕНИЕ:**

Установите **PyTorch 2.9.0+ с CUDA 12.8**:

```bash
cd ~/Obligations/DeepSeek-OCR
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
GPU: NVIDIA GeForce RTX 5080
CUDA Available: True
```

**Совместимость:**
- ✅ PyTorch 2.9.0+: поддерживает sm_120 (Blackwell)
- ✅ PyTorch 2.8.0+: частичная поддержка Blackwell
- ❌ PyTorch 2.7.x и старше: НЕ поддерживают sm_120

### Проблема 8: Несовместимость vLLM (устарело - больше не используем)

**ВАЖНО:** Мы **отказались от vLLM** и используем **HuggingFace Transformers API** напрямую.

**Причина отказа:**
- Сложные зависимости и частые breaking changes в vLLM
- Проблемы совместимости с новейшими GPU (RTX 5080)
- Избыточная сложность для нашего use-case

**✅ ТЕКУЩЕЕ РЕШЕНИЕ:**

Используйте **наш FastAPI микросервис с HuggingFace API**:

```bash
# Запуск OCR микросервиса (без vLLM!)
cd ~/Obligations
source DeepSeek-OCR/venv/bin/activate
python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000
```

**Проверка:**
```bash
curl http://localhost:8000/health
```

**Ожидаемый ответ:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "cuda_available": true,
  "cuda_device": "NVIDIA GeForce RTX 5080"
}
```

**Преимущества нашего подхода:**
- ✅ Простая установка (только transformers + PyTorch)
- ✅ Работает с RTX 5080 и PyTorch 2.9.0
- ✅ HTTP API для интеграции
- ✅ Автоматическая обработка ошибок
- ✅ Без зависимости от vLLM

---

## 📦 Сохранение состояния для синхронизации

### Что НЕ комитить в git

Добавьте в `.gitignore`:
```
# DeepSeek-OCR
DeepSeek-OCR/venv/
DeepSeek-OCR/venv_deepseek/
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

- ✅ `DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm/config.py` (настройки)
- ✅ `pdf_to_context/ocr_service/app.py` (наш микросервис)
- ✅ `docs/DeepSeek_OCR_Setup.md` (эта инструкция)
- ✅ `requirements.txt` (зависимости проекта)

### Быстрая установка на втором компьютере

```bash
# 1. Клонировать репозиторий
git clone YOUR_REPO_URL Obligations
cd Obligations

# 2. Клонировать DeepSeek-OCR
git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
cd DeepSeek-OCR

# 3. Создать окружение и установить все (запускается 15-20 минут)
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
pip install vllm
pip install flash-attn --no-build-isolation

# 4. Проверка
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# 5. Первый запуск (загрузка модели 10-15 минут)
cd DeepSeek-OCR-master/DeepSeek-OCR-vllm
python run_dpsk_ocr_image.py
```

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

## 🚀 Производительность

### Ожидаемая скорость обработки

**GPU: RTX 5080 (16GB VRAM)**

| Режим | Страница (простая) | Страница (сложная) | Изображение |
|-------|-------------------|-------------------|-------------|
| Tiny | ~0.5 сек | ~1 сек | ~0.3 сек |
| Small | ~0.8 сек | ~1.5 сек | ~0.5 сек |
| **Base** | **~1.5 сек** | **~3 сек** | **~1 сек** |
| Large | ~3 сек | ~6 сек | ~2 сек |
| Gundam | ~5-10 сек | ~10-20 сек | - |

**Batch processing:**
- Single page: 1-3 сек
- 10 pages: 15-30 сек
- 100 pages: 2-5 минут

---

## 📚 Дополнительные ресурсы

- [DeepSeek-OCR GitHub](https://github.com/deepseek-ai/DeepSeek-OCR)
- [vLLM Documentation](https://docs.vllm.ai/)
- [CUDA WSL Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- [PyTorch Installation](https://pytorch.org/get-started/locally/)

---

## ✉️ Поддержка

При проблемах проверьте:
1. ✅ NVIDIA драйвер обновлен в Windows
2. ✅ WSL2 (не WSL1)
3. ✅ `nvidia-smi` работает в WSL
4. ✅ PyTorch видит CUDA (`torch.cuda.is_available()`)
5. ✅ Достаточно VRAM (минимум 8GB)

Если проблемы остались - см. раздел [Решение проблем](#решение-проблем).

