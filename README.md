# 🚀 PDFtoBPMN - BPMN Process Automation

[![Cross-Platform Tests](https://github.com/UTGroup/PDFtoBPMN/workflows/Cross-Platform%20Tests/badge.svg)](https://github.com/UTGroup/PDFtoBPMN/actions/workflows/test.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> Автоматизированная обработка текстов, таблиц и схем для построения схем бизнес-процессов в формате BPMN 2.0, совместимом с Camunda Modeler.

---

## ⚠️ ВАЖНО: Требования к окружению

**Этот проект предназначен для работы ТОЛЬКО в IDE с интегрированным ИИ:**

- ✅ **Cursor AI** (рекомендуется) - автоматически читает `.cursorrules`
- ✅ **VS Code с GitHub Copilot** - через `.github/copilot-instructions.md` или ручное указание контекста
- ✅ Другие IDE с AI-ассистентами - требуется настройка custom instructions

**ИИ-ассистент должен:**
- Читать и следовать правилам методологии (из `.cursorrules` или аналогов)
- Автоматически структурировать процессы
- Создавать BPMN XML, RACI матрицы, документацию
- Выполнять валидацию по 25+ проверкам

> ❌ **Без AI-ассистента** проект требует ручного кодирования и глубоких знаний BPMN 2.0
>
> 📌 **Для Cursor AI:** Методология загружается автоматически из `.cursorrules`  
> 📌 **Для VS Code/Copilot:** Нужно вручную указать контекст из `.cursorrules` через `@workspace` или создать `.github/copilot-instructions.md`

---

## 🎯 Что делает проект

Автоматическое преобразование документации бизнес-процессов из **PDF, DOCX, XLSX** в:

1. **BPMN 2.0 диаграммы** (.bpmn) - открываются в Camunda Modeler
2. **RACI матрицы** (.md + .docx) - распределение ролей и ответственности
3. **Текстовые пайплайны** (.md + .docx) - детальное описание каждого шага
4. **Документацию процессов** (.md + .docx) - таблицы с описанием элементов

**Поддерживаемые форматы входных документов:**
- 📄 **PDF** - с OCR для графики (DeepSeek-OCR/PaddleOCR)
- 📝 **DOCX** - Word документы (структура, таблицы, изображения)
- 📊 **XLSX** - Excel таблицы (данные, формулы, листы)

**Для каждого документа:** 9 связанных файлов (OCR, RACI, Pipeline, BPMN, MD, DOCX)

---

## ⚙️ Быстрый старт

### Шаг 1: Клонирование и настройка папок

```bash
# Клонировать репозиторий
git clone https://github.com/UTGroup/PDFtoBPMN
cd PDFtoBPMN

# Создать папки для входных и выходных файлов
mkdir -p input output
```

**Альтернатива (с Nextcloud):**
```bash
# Для автоматической синхронизации с облаком
ln -s ~/Nextcloud/PDFtoBPMN/input input
ln -s ~/Nextcloud/PDFtoBPMN/output output

# Для WSL (если Nextcloud на Windows):
ln -s /mnt/c/Users/YourName/Nextcloud/PDFtoBPMN/input input
ln -s /mnt/c/Users/YourName/Nextcloud/PDFtoBPMN/output output
```

---

### Шаг 2: Установка зависимостей

**Минимальная установка (без OCR):**
```bash
pip install PyMuPDF Pillow requests
```

**Полная установка (с OCR для графики):**
   ```bash
pip install -r requirements.txt
   ```

**Проверка:**
   ```bash
python3 -c "import fitz; print('PyMuPDF OK')"
   ```

**Проверка окружения:**
   ```bash
python3 scripts/utils/check_environment.py
   ```

---

## 🖥️ Поддерживаемые платформы

### ✅ Linux (основная платформа)
- ✅ Разработка и тестирование проводятся на Linux (Ubuntu 20.04+, Debian, Arch, etc.)
- ✅ Полная поддержка всех функций
- ✅ Все скрипты и команды тестировались на Linux

### ⚠️ Windows (частичная поддержка)
- ⚠️ Работает, но требует настройки UTF-8 кодировки
- ⚠️ Известные проблемы:
  - Кодировки терминала (по умолчанию CP1251/CP866 вместо UTF-8)
  - Виртуальное окружение (другие команды активации)
  - Переносы строк (CRLF vs LF)
- ✅ **Рекомендация:** используйте WSL2 (Windows Subsystem for Linux) для полной совместимости

#### 🪟 Настройка для Windows

**Вариант 1: WSL2 (рекомендуется)**

WSL2 дает полную Linux-совместимость в Windows:

```powershell
# 1. Установить WSL2
wsl --install -d Ubuntu

# 2. Перезагрузить Windows

# 3. Открыть Ubuntu терминал
wsl

# 4. Следовать инструкциям для Linux (выше)
```

**Вариант 2: Native Windows (требует настройки)**

Если не хотите использовать WSL2, настройте UTF-8:

```powershell
# PowerShell: установить UTF-8 для текущей сессии
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
chcp 65001

# Или установить глобально через переменные окружения:
# Параметры системы → Дополнительные → Переменные среды → Создать:
# PYTHONIOENCODING = utf-8
```

**Активация виртуального окружения в Windows:**

```powershell
# PowerShell
venv\Scripts\Activate.ps1

# CMD
venv\Scripts\activate.bat
```

**Установка зависимостей:**

```powershell
# Убедитесь что Python ≥3.9
python --version

# Установить зависимости
pip install -r requirements.txt

# Проверка окружения
python scripts\utils\check_environment.py
```

**Известные ограничения на Windows:**
- ❌ GPU/CUDA для OCR может не работать (зависит от драйверов)
- ⚠️ Генерация DOCX требует установки [Pandoc](https://pandoc.org/installing.html)
- ⚠️ Некоторые пути в документации используют `/` (Linux), в Windows используйте `\`

### ℹ️ macOS (не тестировалось)
- ℹ️ Теоретически работает (Unix-подобная система, как Linux)
- ℹ️ Платформа не тестировалась разработчиками
- ℹ️ Если используете macOS - сообщите о проблемах через Issues

**Если что-то не работает на macOS:**
1. Проверьте окружение: `python3 scripts/utils/check_environment.py`
2. Убедитесь что Python ≥3.9: `python3 --version`
3. Проверьте UTF-8: `locale` (должно быть UTF-8)
4. Создайте Issue с описанием проблемы

---

## 🔄 CI/CD и автоматическое тестирование

### GitHub Actions

Проект использует **GitHub Actions** для автоматического тестирования на **Linux и Windows** при каждом коммите и Pull Request.

**Что тестируется автоматически:**

```
┌──────────────────────────────────────────────────┐
│  Триггер: Push / Pull Request / Manual          │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ JOB 1: Environment Check (matrix: OS × Python)   │
│  ✓ Linux (Ubuntu) + Windows                      │
│  ✓ Python 3.10, 3.12                             │
│  ✓ Проверка ОС, версии, кодировок, зависимостей │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ JOB 2: Code Quality (Linux only)                 │
│  ✓ Black (форматирование)                        │
│  ✓ isort (сортировка imports)                    │
│  ✓ flake8 (линтер)                               │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ JOB 3: Unit Tests (Linux + Windows)              │
│  ✓ pytest с coverage                             │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ JOB 4: Integration Tests (Linux + Windows)       │
│  ✓ Тестирование run_document.py                  │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ JOB 5: UTF-8 Encoding Check                      │
│  ✓ Проверка encoding='utf-8' во всех файлах      │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│ JOB 6: Final Status                              │
│  ✅ Все критические проверки пройдены            │
└──────────────────────────────────────────────────┘
```

### Как работает workflow

**Триггеры:**
- **Push** в любую ветку → автоматический запуск всех тестов
- **Pull Request** → тесты блокируют Merge если не пройдены
- **Ручной запуск** через GitHub UI (Actions → Run workflow)

**Matrix Testing:**
```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
    python-version: ['3.10', '3.12']
```
Это означает: **4 параллельных теста** (2 ОС × 2 версии Python)

**Результаты в GitHub:**
- ✅ Зеленая галочка → все тесты прошли, можно делать Merge
- ❌ Красный крестик → есть ошибки, нужно исправить
- 🟡 Желтый значок → тесты в процессе

**Где смотреть результаты:**
```
GitHub → Репозиторий → Actions → Выбрать workflow run
```

### Локальное тестирование перед коммитом

**Рекомендуется запускать проверки локально:**

```bash
# 1. Проверка окружения (как в CI/CD)
python3 scripts/utils/check_environment.py --strict

# 2. Линтер (если установлен flake8)
flake8 scripts/ --exclude=venv --max-line-length=120 --ignore=E501,W503

# 3. Форматирование (если установлен black)
black --check scripts/ --exclude "venv|DeepSeek-OCR"

# 4. Юнит-тесты (если установлен pytest)
pytest tests/ -v

# 5. Интеграционные тесты
python3 scripts/utils/run_document.py --check-env input/test_document.docx
```

**Установка инструментов для локального тестирования:**
```bash
pip install flake8 black isort pytest pytest-cov
```

### Continuous Integration преимущества

✅ **Автоматическая проверка совместимости:**
- Код тестируется на Windows автоматически (даже если разработчик на Linux)
- Нет сюрпризов "работало у меня, но не работает у пользователей Windows"

✅ **Защита от регрессий:**
- Каждый коммит проверяется → сломанный код не попадет в main
- Pull Request блокируется если тесты не прошли

✅ **Кодировки под контролем:**
- Автоматическая проверка `encoding='utf-8'` во всех файлах
- Обнаружение не-UTF-8 файлов

✅ **Качество кода:**
- Линтер ловит ошибки стиля и потенциальные баги
- Форматирование единообразно

### Workflow файл

Полная конфигурация: `.github/workflows/test.yml`

**Основные job'ы:**
- `environment-check`: Проверка окружения (strict mode)
- `lint`: Качество кода (flake8, black, isort)
- `unit-tests`: Юнит-тесты с pytest
- `integration-tests`: Интеграционные тесты
- `encoding-check`: UTF-8 валидация
- `all-tests-passed`: Финальный статус

**Требования для Merge:**
- ✅ `environment-check` ОБЯЗАН пройти
- ✅ `encoding-check` ОБЯЗАН пройти
- ⚠️ `lint`, `unit-tests`, `integration-tests` - warnings не блокируют

---

### Шаг 3: Настройка Cursor AI

1. Открыть проект в Cursor AI:
   ```bash
   cursor .
   ```

2. Убедиться что `.cursorrules` подключен (Cursor читает автоматически)

3. Положить документ в `input/` (PDF, DOCX или XLSX):
   ```bash
   cp ~/Documents/process.pdf input/
   # или
   cp ~/Documents/process.docx input/
   # или
   cp ~/Documents/data.xlsx input/
   ```

4. Запросить у AI:
   ```
   обработай документ process.pdf
   # или
   обработай документ process.docx
   # или
   обработай документ data.xlsx
   ```

5. AI автоматически выполнит все 7 этапов обработки

---

### Что происходит автоматически

```
┌────────────────────────────────────────────────┐
│ AI читает .cursorrules → следует методологии   │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 1: OCR обработка (Native + DeepSeek-OCR)  │
│ → Создает: _OCR.md                             │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 2: RACI матрица (роли и ответственность)  │
│ → Создает: _RACI.md                            │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 3: Текстовый пайплайн (7 пунктов/задача)  │
│ → Создает: _Pipeline.md                        │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 4: BPMN XML + Документация                │
│ → Создает: .bpmn + .md                         │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 5: Валидация (25+ проверок, отчет)        │
│ → Проверяет: RACI, Pipeline, SubProcess, XML   │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 6: DOCX копии (pandoc конвертация)        │
│ → Создает: _OCR.docx, _RACI.docx и т.д.       │
└────────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────────┐
│ ШАГ 7: Отчет пользователю (9 файлов + stats)  │
└────────────────────────────────────────────────┘
```

**Результат:** Папка `output/process/` с 9 файлами

---

## 🏗️ Архитектура решения

### Компоненты системы

```
┌─────────────────────────────────────────────────────────┐
│                    AI-АССИСТЕНТ                         │
│              (Cursor AI / GitHub Copilot)               │
│                                                         │
│  Читает: .cursorrules (методология, правила BPMN)      │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│         МОДУЛЬ DOCUMENT TO CONTEXT                      │
│          (scripts/pdf_to_context/)                       │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Parsers    │  │  Extractors  │  │  OCR Service │ │
│  │ PDF/DOCX/    │  │ PDF: текст,  │  │ DeepSeek-OCR │ │
│  │ XLSX         │  │ таблицы, OCR │  │ (GPU)        │ │
│  │              │  │ DOCX: struct │  │ PaddleOCR    │ │
│  │              │  │ XLSX: формулы│  │ (CPU)        │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         └─────────────────┼─────────────────┘         │
│                           ↓                             │
│              ┌────────────────────────┐                │
│              │ Промежуточное          │                │
│              │ представление (IR)     │                │
│              └────────────┬───────────┘                │
│                           ↓                             │
│              ┌────────────────────────┐                │
│              │  Markdown Formatter    │                │
│              └────────────────────────┘                │
└─────────────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│                  AI PROCESSING                           │
│                                                         │
│  1. Анализ структуры процесса                           │
│  2. Построение RACI матрицы                             │
│  3. Создание текстового пайплайна                       │
│  4. Генерация BPMN XML (с lanes, SubProcess)            │
│  5. Валидация (соответствие RACI, Pipeline, БЛОК 5.1)   │
│  6. Создание MD документации                            │
└─────────────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│                    OUTPUT                                │
│                                                         │
│  output/ДП-М1.020-06/                                   │
│  ├── ДП-М1.020-06_OCR.md + .docx                        │
│  ├── ДП-М1.020-06_RACI.md + .docx                       │
│  ├── ДП-М1.020-06_Pipeline.md + .docx                   │
│  ├── ДП-М1.020-06.bpmn  (XML для Camunda)              │
│  └── ДП-М1.020-06.md + .docx  (документация)            │
└─────────────────────────────────────────────────────────┘
```

---

### Структура проекта

```
PDFtoBPMN/
├── input/                    # 📥 Входные PDF документы
├── output/                   # 📤 Результаты (9 файлов/процесс)
│
├── scripts/
│   ├── pdf_to_context/      # Модуль обработки PDF
│   │   ├── pipeline.py      # Главный пайплайн
│   │   ├── core/            # Parser, Analyzer
│   │   ├── extractors/      # Текст, таблицы, графика
│   │   ├── ir/              # Промежуточное представление
│   │   └── ocr_service/     # DeepSeek-OCR интеграция
│   └── utils/               # 🛠️ CLI утилиты и тесты
│       ├── run_ocr.py               # Обработка PDF с OCR
│       ├── check_ocr_health.py      # Проверка OCR сервиса
│       ├── test_deepseek_ocr.py     # Тест DeepSeek-OCR
│       └── test_paddle_isolated.py  # Тест PaddleOCR (CPU)
│
├── docs/
│   ├── Architecture.md             # Техническая архитектура
│   ├── BPMN_Elements_Reference.md  # Справочник BPMN 2.0
│   └── DeepSeek_OCR_Guide.md       # Установка OCR
│
├── .cursorrules              # 🤖 Правила для AI (методология)
├── README.md                 # Этот файл
├── Changelog.md              # История изменений
└── requirements.txt          # Python зависимости
```

---

## 🎨 BPMN 2.0 - Стандарты и элементы

Проект использует **полный набор элементов BPMN 2.0** согласно спецификации OMG.

### Поддерживаемые элементы

#### 🎯 Активности (Activities)
- **Tasks:** Abstract, User, Manual, Service, Script, Business Rule
- **SubProcesses:** Subprocess, Event Subprocess, Transaction, Call Activity
- **Loops:** Standard Loop, Multi-Instance (Parallel/Sequential)

#### ⚡ События (Events)
- **Start:** None, Message, Timer, Conditional, Signal
- **Intermediate:** Message Catch/Throw, Timer Catch, Escalation, Compensation
- **End:** None, Message, Error, Escalation, Terminate

#### 🔀 Шлюзы (Gateways)
- **Exclusive (XOR)** - исключающее ИЛИ (только одна ветвь)
- **Parallel (AND)** - параллельный (все ветви одновременно)
- **Inclusive (OR)** - неэксклюзивный (выполненные условия)
- **Event-Based** - на основе событий

#### 🏊 Организация
- **Pool** - организация/участник процесса
- **Lane** - роль/подразделение (1-5 оптимально, макс. 7)

#### 📦 Артефакты
- **Data Objects** - документы, данные
- **Data Stores** - базы данных, хранилища
- **Text Annotations** - комментарии
- **Groups** - визуальная группировка

### Стандарты и лучшие практики

**Источники:**
- OMG BPMN 2.0.2 Specification
- Camunda BPMN 2.0 Implementation Reference
- Best Practices процессного моделирования

**Рекомендации по количеству элементов:**
- **Lanes:** 1-5 (оптимально 3-5, максимум 7)
- **Tasks:** 3-15 (оптимально), максимум 20
- **Формат:** A4 альбомная ориентация
- **Направление:** Слева направо по времени

**Полное описание всех элементов:**  
→ [docs/BPMN_Elements_Reference.md](docs/BPMN_Elements_Reference.md)

---

## 🛠️ Утилиты для пользователей

### 1️⃣ `run_ocr` - CLI-обёртка для OCR

**Формат команды:**
```bash
python3 scripts/utils/run_ocr.py <путь_к_PDF> [<путь_к_выходному_MD>]
```

**Использование:**
```bash
# Запуск обработки PDF (с указанием выходного файла):
python3 scripts/utils/run_ocr.py input/document.pdf output/document_OCR.md

# Вывод в stdout (без сохранения):
python3 scripts/utils/run_ocr.py input/document.pdf
```

**Что делает:**
- Автоматически определяет режим (Native + OCR или Native only)
- Извлекает текст, таблицы, векторную графику
- Распознает изображения через DeepSeek-OCR (если доступно)
- Создает структурированный Markdown

---

### 2️⃣ `generate_docx` - Генерация DOCX копий процесса

**Формат команды:**
```bash
python3 scripts/utils/generate_docx.py <output_dir> <base_name>
```

**Использование:**
```bash
# Генерация DOCX версий всех MD файлов процесса:
python3 scripts/utils/generate_docx.py output/ДП-Б6001-07 ДП-Б6001-07

# Другой пример:
python3 scripts/utils/generate_docx.py output/ДП-М1.020-06 ДП-М1.020-06
```

**Что делает:**
- Конвертирует все MD файлы процесса в DOCX (Word формат)
- Автоматически применяет препроцессинг (Unicode → ASCII, удаление emoji)
- Добавляет оглавление для Pipeline и документации
- Выводит статистику генерации

**Создаваемые файлы:**
- `[base_name]_OCR.docx` - расшифровка документа
- `[base_name]_RACI.docx` - матрица ответственности  
- `[base_name]_Pipeline.docx` - текстовый пайплайн (с TOC)
- `[base_name].docx` - документация процесса (с TOC)

**Зависимости:** Требуется `pandoc`

---

### 3️⃣ `bpmn_viewer` - Универсальный web-просмотрщик BPMN

**Расположение:** `scripts/bpmn_viewer.html`

**Возможности:**
- 📂 **Открытие** .bpmn/.xml файлов (кнопка или Drag & Drop)
- 💾 **Сохранение** изменений в исходный файл
- 📥 **Сохранить как** в новый файл
- 🔍 **Drill-down** в SubProcess (двойной клик)
- 🏠 **Breadcrumb** навигация для возврата
- 🔎 **Zoom** управление (+, -, 1:1, вписать)
- 📱 **Адаптация** под iOS/iPad

**Использование на ПК:**
```bash
# Просто открыть в браузере:
file:///path/to/scripts/bpmn_viewer.html
# Перетащить .bpmn файл на страницу или нажать "Открыть"
```

**Использование на iOS/iPad:**
```bash
# Запустить локальный сервер на компьютере:
cd scripts && python3 -m http.server 8080
# На iPad открыть: http://<IP-компьютера>:8080/bpmn_viewer.html
```

**Планируется:** Публикация на GitHub Pages для доступа без сервера

**Технологии:** bpmn-js Modeler (Camunda), File System Access API

---

### 3️⃣ `test_deepseek_ocr` - Тест модели DeepSeek-OCR (GPU)

**Формат команды:**
```bash
python3 scripts/utils/test_deepseek_ocr.py
```

**Использование:**
```bash
# Проверка установки DeepSeek-OCR:
python3 scripts/utils/test_deepseek_ocr.py
```

**Что проверяет:**
- PyTorch + CUDA доступность
- Загрузка модели DeepSeek-OCR
- Тестовый inference
- Детальный отчет

---

### 4️⃣ `check_ocr_health` - Проверка OCR сервиса

**Формат команды:**
```bash
python3 scripts/utils/check_ocr_health.py
```

**Использование:**
```bash
# Проверка что OCR сервис запущен и готов:
python3 scripts/utils/check_ocr_health.py
```

**Что проверяет:**
- OCR сервис доступен (localhost:8000)
- Модель загружена
- CUDA работает
- Показывает GPU

**Использование:**
```bash
# Перед обработкой документа
python3 scripts/utils/check_ocr_health.py && python3 scripts/utils/run_ocr.py input/doc.pdf output/result.md
```

---

### 5️⃣ `test_paddle_isolated` - Тест PaddleOCR (CPU fallback)

**Формат команды:**
```bash
python3 scripts/utils/test_paddle_isolated.py
```

**Использование:**
```bash
# Проверка PaddleOCR без GPU:
python3 scripts/utils/test_paddle_isolated.py
```

**Что проверяет:**
- Импорт PaddleOCR и PaddlePaddle
- Инициализация в CPU режиме (lang='ru')
- Создание тестового изображения с русским текстом
- OCR распознавание на CPU
- Время обработки (~20-30 сек/изображение)

**Когда использовать:**
- Нет NVIDIA GPU или CUDA
- Тестирование CPU fallback механизма
- Проверка работы PaddleOCR перед обработкой больших документов

---

### 5️⃣ `smoke_test` - Быстрая проверка компонентов

```bash
# Проверка что ничего не сломано (перед коммитом)
bash scripts/tests/smoke_test.sh
```

**Что проверяет:**
- Импорты работают (app.py, prompts.py, pipeline.py)
- Нет абсолютных импортов в ocr_service
- Структура проекта корректна

**Когда запускать:**
- Перед git commit
- После рефакторинга
- При переносе проекта на новую машину

---

## 📚 Навигация по документации

| Документ | Описание |
|----------|----------|
| **[README.md](README.md)** | ⭐ Этот файл - быстрый старт и обзор |
| **[.cursorrules](.cursorrules)** | Методология работы AI (5 этапов + валидация) |
| **[docs/Architecture.md](docs/Architecture.md)** | Техническая архитектура PDF to Context |
| **[docs/BPMN_Elements_Reference.md](docs/BPMN_Elements_Reference.md)** | Полный справочник BPMN 2.0 |
| **[docs/DeepSeek_OCR_Guide.md](docs/DeepSeek_OCR_Guide.md)** | Установка и настройка OCR |
| **[docs/CURSOR_AI_TOOLS_GUIDE.md](docs/CURSOR_AI_TOOLS_GUIDE.md)** | 🛠️ Полное руководство по инструментам Cursor AI |
| **[Changelog.md](Changelog.md)** | История всех изменений |
| **[output/Integrated_Pipeline/](output/Integrated_Pipeline/)** | 🔗 Интегрированный пайплайн обязательств |

### Архивные материалы

| Документ | Описание |
|----------|----------|
| **[archive/finance_parsers/](archive/finance_parsers/)** | 📦 Финансовые парсеры (архив) |

---

## 🔧 Опциональные настройки

### DeepSeek-OCR (для распознавания графики)

**Требования:**
- NVIDIA GPU с CUDA
- 16+ GB VRAM
- PyTorch 2.0+

**Виртуальное окружение:**
```bash
# Рекомендуется использовать окружение с DeepSeek-OCR
# Обычно это DeepSeek-OCR/venv/ или подобная структура

# Как найти правильное окружение:
# 1. Ищите папку содержащую flash-attn, torch, transformers
find . -type d -name "venv" -o -name "env" 2>/dev/null

# 2. Активируйте и проверьте содержимое
source <путь_к_venv>/bin/activate
pip list | grep -E "flash|torch|transformers"

# Проверка что окружение активировано:
which python3  # Должен показать путь в venv
pip list | grep flash_attn  # Должен найти flash-attn
```

**Быстрый запуск:**
```bash
# 1. Запустить OCR сервис (в отдельном терминале)
cd <корень_проекта>
source <путь_к_venv>/bin/activate  # Например: DeepSeek-OCR/venv/bin/activate
python -m uvicorn scripts.pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000

# 2. В другом терминале - обработать документ
source <путь_к_venv>/bin/activate
python3 scripts/utils/run_ocr.py input/document.pdf output/document_OCR.md
```

**Без OCR:**
- ✅ Текст и таблицы обрабатываются
- ❌ Графика (диаграммы, схемы) пропускается

**Детальная установка:**  
→ См. [docs/DeepSeek_OCR_Guide.md](docs/DeepSeek_OCR_Guide.md)

---

### Nextcloud (для синхронизации)

<details>
<summary><b>🔽 Настройка облачной синхронизации</b></summary>

**Зачем:**
- ☁️ Автоматическая синхронизация между устройствами
- 💾 Резервное копирование
- 👥 Совместная работа

**Установка:**
1. Установить [Nextcloud Desktop](https://nextcloud.com/install/#install-clients)
2. Создать структуру папок:
   ```
   Nextcloud/PDFtoBPMN/
   ├── input/
   └── output/
   ```
3. Связать с проектом:
   ```bash
   ln -s ~/Nextcloud/PDFtoBPMN/input input
   ln -s ~/Nextcloud/PDFtoBPMN/output output
   ```

</details>

---

## 📝 История изменений

Все изменения документируются в [Changelog.md](Changelog.md)

**Формат:**
```markdown
## [DD-MM-YYYY] - Описание

### Добавлено
- Новые функции

### Изменено
- Модификации

### Исправлено
- Баги и ошибки
```

---

## 🔗 Интегрированный пайплайн обязательств

### Описание

Проект включает **единый сквозной пайплайн контроля обязательств**, объединяющий несколько регулятивных документов в целостную картину бизнес-процесса.

**Расположение:** `output/Integrated_Pipeline/`

### Состав пайплайна

| Файл | Описание |
|------|----------|
| `Obligations_Pipeline.bpmn` | BPMN-схема с drill-down (24 SubProcess, 98 Tasks) |
| `Obligations_Pipeline.md` | Текстовое описание и методология |
| `Obligations_Pipeline.docx` | DOCX-версия для печати |
| `Критические_замечания_и_TO-BE.md` | Аудит AS-IS и рекомендации TO-BE |
| `Критические_замечания_и_TO-BE.docx` | DOCX-версия для согласования |

### Интегрированные документы

| Документ | Процессы | Покрытие |
|----------|----------|----------|
| **РД-Б7.004-05** | Жизненный цикл договора (11 SubProcess) | ✅ 100% |
| **КД-РГ-039-05** | Претензионно-исковая работа (9 SubProcess) | ✅ 100% |
| **РГ-179-02** | Платежи и валютный контроль (4 SubProcess) | ⚠️ 67% |

### Порядок обновления

При изменении исходных документов:

1. **Обновить исходную схему** (`output/[Документ]/[Документ].bpmn`)
2. **Проверить стыки** с другими документами (см. `Критические_замечания_и_TO-BE.md`)
3. **Обновить пайплайн** (`output/Integrated_Pipeline/Obligations_Pipeline.bpmn`)
4. **Обновить документацию** (`Obligations_Pipeline.md`)
5. **Регенерировать DOCX** (`pandoc ... -o ....docx`)

### Валидация

```bash
# Проверка BPMN
camunda-modeler output/Integrated_Pipeline/Obligations_Pipeline.bpmn

# Проверка соответствия
grep -c '<bpmn:subProcess' output/Integrated_Pipeline/Obligations_Pipeline.bpmn  # Должно быть 24
```

---

## 🚧 Развитие проекта

### В разработке

- [ ] Экспорт в другие форматы для распечатки на А4
- [ ] Внедрение Tool calls

### Планируется

- [ ] **Поддержка дополнительных входных форматов:**
  - [ ] TXT (текстовые файлы) - определение структуры по отступам
- [ ] Веб-интерфейс для загрузки документов
- [ ] Batch-обработка множества документов
- [ ] Сравнение версий процессов

---

## 📞 Контакты и поддержка

**Проект:** PDFtoBPMN - BPMN Process Automation  
**GitHub:** [https://github.com/UTGroup/PDFtoBPMN](https://github.com/UTGroup/PDFtoBPMN)

---

*Последнее обновление: 11.11.2025*
