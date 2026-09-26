# Roadmap: от текущего состояния до Graph RAG

> **Версия:** 1.2  
> **Дата обновления:** 27.01.2026  
> **Статус:** ✅ ЭТАП 0 ЗАВЕРШЁН → В разработке (Этап 1)

---

## ⚠️ ПРИНЦИП ОБРАТНОЙ СОВМЕСТИМОСТИ

**ВСЕ изменения должны сохранять работоспособность существующего кода!**

### Паттерны реализации

```python
# 1. Factory Pattern — выбор реализации через конфигурацию
class OCRServiceFactory:
    @staticmethod
    def create(service_type: str = "deepseek") -> OCRService:
        if service_type == "deepseek":
            return DeepSeekOCRService()  # ✅ Старое (по умолчанию)
        elif service_type == "qwen":
            return QwenVLService()       # 🆕 Новое (опционально)
        elif service_type == "paddle":
            return PaddleOCRService()    # Fallback

# 2. Feature Flags — включение новых функций
ENABLE_LAYOUT_DETECTION = os.getenv("ENABLE_LAYOUT_DETECTION", "false") == "true"
ENABLE_QWEN_OCR = os.getenv("ENABLE_QWEN_OCR", "false") == "true"

# 3. Graceful Degradation — работа без новых зависимостей
try:
    from doclayout_yolo import YOLOv10
    DOCLAYOUT_AVAILABLE = True
except ImportError:
    DOCLAYOUT_AVAILABLE = False
    print("⚠️ DocLayout-YOLO не установлен, используем эвристики")
```

### Правила изменений

| Правило | Описание |
|---------|----------|
| **Не ломать существующее** | Все текущие скрипты должны работать без изменений |
| **Опциональные зависимости** | Новые пакеты — опциональны, graceful degradation |
| **Feature flags** | Новые функции включаются явно (env/config) |
| **Тесты перед merge** | Каждый этап заканчивается тестами старого + нового |
| **Документация** | Обновлять README при добавлении новых возможностей |

---

## Оглавление

- [Обзор](#обзор)
- [Текущее состояние](#текущее-состояние)
- [Исследование инструментов](#исследование-инструментов)
- [План развития](#план-развития)
- [Зависимости](#зависимости)

---

## Обзор

Данный документ описывает план развития проекта Obligations от текущего состояния (парсинг документов + генерация BPMN) до полноценной системы **Graph RAG** с интеллектуальным поиском по базе знаний.

### Цели

1. **Улучшить качество парсинга** — внедрить современные VLM-модели
2. **Построить граф знаний** — автоматически из RACI/Pipeline/BPMN
3. **Создать RAG-систему** — гибридный поиск (векторный + графовый)
4. **Обеспечить масштабируемость** — обработка тысяч документов

### Timeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  ТЕКУЩЕЕ СОСТОЯНИЕ                                                  │
│  ✅ PDF/DOCX/XLSX экстракция (PyMuPDF, python-docx, openpyxl)      │
│  ✅ DeepSeek-OCR для графики                                        │
│  ✅ IR (Intermediate Representation)                                │
│  ✅ RACI/Pipeline/BPMN генерация                                    │
│  ❌ Современные VLM для OCR                                         │
│  ❌ Автоматическое извлечение сущностей                            │
│  ❌ Граф знаний                                                     │
│  ❌ RAG-система                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
┌─────────┐  2-3 дня         ┌─────────┐  1 неделя          ┌─────────┐
│ ЭТАП 0  │ ─────────────▶   │ ЭТАП 1  │ ─────────────▶     │ ЭТАП 2  │
│ Quick   │                  │ Data    │                    │ Basic   │
│ Wins    │                  │ Layer   │                    │ Graph   │
└─────────┘                  └─────────┘                    └─────────┘
                                                                 │
    ┌────────────────────────────────────────────────────────────┘
    ▼                               ▼
┌─────────┐  2 недели        ┌─────────┐  2-3 недели
│ ЭТАП 3  │ ─────────────▶   │ ЭТАП 4  │
│ Vector  │                  │ Graph   │
│ RAG     │                  │ RAG     │
└─────────┘                  └─────────┘
```

**Итого: 6-9 недель** до полноценного Graph RAG.

---

## Текущее состояние

### Архитектура парсера документов

```
DocumentToContextPipeline
         │
         ▼
  ┌──────────────────┐
  │ Format Detection │
  └────────┬─────────┘
           │
     ┌─────┴─────┬─────────────┐
     ▼           ▼             ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│   PDF   │ │  DOCX   │ │  XLSX   │
│Extractor│ │Extractor│ │Extractor│
└────┬────┘ └────┬────┘ └────┬────┘
     │           │           │
     │     PyMuPDF      python-docx    openpyxl
     │     pdfplumber
     │           │           │
     └─────┬─────┴───────────┘
           ▼
    ┌─────────────┐
    │  IRBuilder  │  ◄── Промежуточное представление
    └──────┬──────┘
           ▼
  ┌────────────────┐
  │StructureAnalyzer│
  └───────┬────────┘
          ▼
  ┌────────────────┐
  │MarkdownFormatter│
  └───────┬────────┘
          ▼
     Output: _OCR.md
```

### Текущий OCR стек

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| **Native text** | PyMuPDF | Извлечение текста из PDF |
| **Tables** | pdfplumber | Извлечение таблиц |
| **Graphics OCR** | DeepSeek-OCR v1 | Распознавание диаграмм, схем (primary, D-018) |
| **Fast OCR fallback** | GLM-OCR | Быстрый fallback (63% quality, 4x faster, D-018) |
| **Layout** | Эвристики + PageClassifier | Определение структуры (D-016) |

### OCR/VLM Benchmark (D-018, 20.03.2026)

7 моделей протестированы на 18 страницах. Результат:
- **DeepSeek-OCR v1** — primary (100% baseline, 40с/стр, 6.5GB VRAM)
- **GLM-OCR** — fast fallback (63%, 10.6с/стр, 2.1GB VRAM)
- Подробности: `poc/BENCHMARK_HANDOFF.md`, `poc/benchmark_results/summary.json`

### Ограничения текущего решения

1. **DeepSeek-OCR v1** — требует GPU + flash-attn, зацикливание на ~9% страниц (known issue)
2. **Нет layout detection** — эвристики вместо ML-модели (PageClassifier — rule-based, D-016)
3. **Нет table detection** — только pdfplumber (rule-based)
4. **Нет автоизвлечения сущностей** — роли/задачи извлекаются вручную
5. **Метрика OCR** — Levenshtein (грубая), нужна семантическая

---

## Исследование инструментов

### A. VLM для OCR документов (State of the Art 2025-2026)

#### Топ-модели по OmniDocBench (CVPR 2025)

| Модель | Параметры | Точность | Особенности | Лицензия |
|--------|-----------|----------|-------------|----------|
| **Qwen2.5-VL** | 7B-72B | ~75% JSON | Лидер open-source, multi-language | Apache 2.0 |
| **olmOCR** | 7B | ~73% | На базе Qwen2-VL, $190/1M страниц | Apache 2.0 |
| **InternVL2** | 1B-108B | ~72% | 8K контекст, медицина, видео | Apache 2.0 |
| **GOT-OCR 2.0** | 580M | ~70% | Компактная, быстрая | MIT |
| **Mistral-OCR** | - | 72.2% | Специализированная для OCR | - |

#### Рекомендация

**Qwen2.5-VL-7B** или **olmOCR** — лучший баланс качества/скорости для локального деплоя:
- Поддержка Markdown output
- Таблицы, формулы, рукописный текст
- Multi-column layouts
- Открытые веса и код

### B. Layout Detection (анализ макета)

#### Сравнение моделей

| Модель | mAP | Скорость | Особенности | Применение |
|--------|-----|----------|-------------|------------|
| **DocLayout-YOLO** | 79.7% | 120 FPS | Специально для документов | ✅ Рекомендуется |
| **YOLO v12** | 76.2%* | 100 FPS | Универсальная, новая | Требует дообучение |
| **YOLO v11** | 74.5% | 130 FPS | Стабильная, production | Альтернатива |
| **LayoutLMv3** | 78.3% | 15 FPS | Transformer-based | Высокая точность |
| **Surya** | 75%* | 80 FPS | Multilingual OCR+Layout | Комплексное решение |

*На DocLayNet dataset

#### DocLayout-YOLO — детали

```python
# Установка
pip install doclayout-yolo

# Использование
from doclayout_yolo import YOLOv10

model = YOLOv10("doclayout_yolo_docstructbench_imgsz1024.pt")
results = model.predict("document.png", imgsz=1024)

# Категории: text, title, figure, table, caption, etc.
```

**Преимущества:**
- 19 категорий layout (text, title, figure, table, caption, list, footer, header...)
- Предобученная на DocSynth-300K
- Быстрая (YOLO backbone)
- Open source (AGPL-3.0)

### C. Table Detection & Structure Recognition

| Инструмент | Accuracy | Тип | Особенности |
|------------|----------|-----|-------------|
| **PP-StructureV2 (SLANeXt)** | 69.65% | Rule+ML | PaddlePaddle, wired/wireless tables |
| **Table Transformer (TATR)** | 82.3% | Transformer | Microsoft, DETR-based |
| **DocLayout-YOLO** | 75.2% | YOLO | Детекция границ таблиц |
| **Marker** | ~70% | Hybrid | Конвертация PDF→Markdown |

#### Рекомендация

**Table Transformer (TATR)** для structure recognition + **DocLayout-YOLO** для detection.

### D. Комплексные решения (парсинг PDF)

| Решение | Подход | Плюсы | Минусы |
|---------|--------|-------|--------|
| **Docling** (IBM) | Pipeline | Все форматы, LF standard | Сложная настройка |
| **Marker** | Hybrid | Простой, Markdown output | Медленнее VLM |
| **MinerU** | Pipeline | Высокая точность | Требует GPU |
| **Unstructured** | Pipeline | Enterprise-ready | Проприетарный |
| **olmOCR** | VLM | Быстрый, дешевый | Только PDF |

### E. Рекомендуемый стек

```
┌─────────────────────────────────────────────────────────┐
│                   РЕКОМЕНДУЕМЫЙ СТЕК                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Layout Detection:  DocLayout-YOLO                   │
│     - 19 категорий, быстрый, open source                │
│                                                         │
│  2. OCR Engine:        Qwen2.5-VL-7B или olmOCR         │
│     - Замена DeepSeek-OCR                               │
│     - Markdown output, таблицы, формулы                 │
│                                                         │
│  3. Table Structure:   Table Transformer (TATR)         │
│     - Точное распознавание ячеек                        │
│                                                         │
│  4. Fallback OCR:      PaddleOCR (CPU)                  │
│     - Когда GPU недоступен                              │
│                                                         │
│  5. Альтернатива:      Docling                          │
│     - Если нужна поддержка всех форматов               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## План развития

### ЭТАП 0: Quick Wins (2-3 дня) ✅ ЗАВЕРШЕН

**Цель:** Улучшить качество парсинга, добавить метаданные для будущего графа.

#### 0.1 Интеграция DocLayout-YOLO ✅

**Реализовано:** `scripts/pdf_to_context/extractors/layout_detector.py`

```python
from scripts.pdf_to_context.extractors import get_layout_detector

# Получить детектор (graceful degradation)
LayoutDetector, is_available = get_layout_detector()

if is_available():
    detector = LayoutDetector(confidence_threshold=0.25)
    elements = detector.detect(image_bytes, page_num=0)
    
    for elem in elements:
        print(f"{elem.category.value}: {elem.confidence:.2f}")
```

**Файлы:**
- [x] `scripts/pdf_to_context/extractors/layout_detector.py` — ✅ создан
- [x] `scripts/pdf_to_context/extractors/__init__.py` — ✅ обновлен
- [ ] `scripts/pdf_to_context/pipeline.py` — интеграция (следующий шаг)

#### 0.2 Альтернативный VLM OCR (Qwen2.5-VL) ✅

**Реализовано:** `scripts/pdf_to_context/ocr_service/qwen_service.py`

```python
from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory

# Явный выбор Qwen VL
service = OCRServiceFactory.create(service_type="qwen")

# Или через list_available_services()
services = OCRServiceFactory.list_available_services()
print(services)  # {'deepseek': {...}, 'paddle': {...}, 'qwen': {...}}
```

**Файлы:**
- [x] `scripts/pdf_to_context/ocr_service/qwen_service.py` — ✅ создан
- [x] `scripts/pdf_to_context/ocr_service/factory.py` — ✅ обновлен

#### 0.3 Тесты ✅

**Реализовано:** `scripts/tests/test_stage0_components.py`

```bash
python3 scripts/tests/test_stage0_components.py
# Ran 15 tests in 0.406s - OK
```

**Проверено:**
- [x] LayoutDetector graceful degradation
- [x] QwenVLService graceful degradation  
- [x] OCRServiceFactory обратная совместимость
- [x] Существующие скрипты работают

#### 0.4 Виртуальное окружение venv ✅

**Реализовано:** `venv/` с полной поддержкой RTX 5080 (Blackwell, sm_120)

| Компонент | Версия | Статус |
|-----------|--------|--------|
| **PyTorch** | 2.10.0+cu129 | ✅ Полная поддержка sm_120 |
| **CUDA** | 12.9 | ✅ Нативная |
| **transformers** | 5.0.0 | ✅ |
| **accelerate** | 1.12.0 | ✅ |
| **pdfplumber** | 0.11.9 | ✅ |

```bash
# Использование
cd /home/budnik_an/Obligations
source venv/bin/activate
python3 scripts/utils/run_document.py input/document.pdf
```

**Проверено:**
- [x] PyTorch видит GPU без warnings
- [x] CUDA compute test проходит
- [x] Все 15 тестов прошли
- [x] Qwen VL OCR доступен

#### 0.5 Docker инфраструктура для OCR ✅

**Реализовано:** Микросервисная архитектура для распределённого OCR

```
┌─────────────────────────────────────────────────────────┐
│  Локальная машина                                       │
│  ├── qwen_local → Qwen2-VL-2B (16GB VRAM)             │
│  ├── deepseek → DeepSeek-OCR локально (8GB VRAM)      │
│  ├── qwen_remote → Docker Qwen (7B+)                   │
│  └── deepseek_remote → Docker DeepSeek                 │
└─────────────────────────────────────────────────────────┘
              ↓ HTTP :8001 (Qwen)    ↓ HTTP :8000 (DeepSeek)
┌─────────────────────────────────────────────────────────┐
│  Docker сервисы (любая GPU: 4080/5080/5090/H100)       │
│  ├── qwen-vlm-service (Qwen2-VL-7B)                    │
│  └── deepseek-ocr-service (DeepSeek-OCR 3B)           │
└─────────────────────────────────────────────────────────┘
```

**Компоненты:**

| Сервис | Файлы | Порт |
|--------|-------|------|
| **Qwen VLM** | `docker/qwen-vlm-service/` | 8001 |

### Финальная архитектура OCR (27.01.2026)

```
┌────────────────────────────────────────────────────────────────┐
│  DOCKER (универсальный)                                        │
│  └── Qwen2-VL-2B → порт 8001                                  │
│      • default: Ada GPU (RTX 4080/4090)                        │
│      • blackwell: Blackwell GPU (RTX 5070/5080/5090)          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  ЛОКАЛЬНЫЕ СЕРВИСЫ (специфические задачи)                      │
│  ├── DeepSeek-OCR → порт 8000                                  │
│  │   • Требует flash_attn (компиляция под GPU)                │
│  │   • Дает bbox координаты                                   │
│  └── Qwen2-VL-7B → локально                                   │
│      • Требует 24GB+ VRAM                                     │
│      • Лучшее качество                                        │
└────────────────────────────────────────────────────────────────┘
```

**Docker профили (только Qwen 2B):**

| Профиль | VRAM | GPU | Команда |
|---------|------|-----|---------|
| **default** | ~5GB | Ada (RTX 4080/4090) | `docker compose up` |
| **blackwell** | ~5GB | Blackwell (RTX 5070/5080/5090) | `docker compose --profile blackwell up` |

**⚠️ DeepSeek и Qwen 7B — только локально!**

**Причины:**
- DeepSeek без flash_attn → CUDA OOM даже на 16GB
- Qwen 7B → требует 24GB+ VRAM
- Qwen 2B работает через SDPA без flash_attn → универсальный

**Сравнение OCR сервисов:**

| Параметр | Qwen 2B (Docker) | Qwen 7B (Local) | DeepSeek (Local) |
|----------|------------------|-----------------|------------------|
| VRAM | ~5GB | ~14GB | ~8GB |
| Flash Attention | Не нужен | Не нужен | **Обязателен** |
| Bbox координаты | ❌ | ❌ | ✅ |
| Кириллица | ✅ | ✅ | ⚠️ транслит |
| Docker | ✅ | ❌ | ❌ |
| Скорость | 1.95s | — | 1.29s |

**Factory API:**

```python
# Qwen (Docker или локальный)
ocr = OCRServiceFactory.create(service_type="qwen")

# DeepSeek (только локальный)
ocr = OCRServiceFactory.create(service_type="deepseek")
```

**Статус Qwen:**
- [x] FastAPI сервис создан
- [x] Dockerfile готов
- [x] docker-compose.yml с профилями (default, blackwell)
- [x] QwenRemoteService клиент
- [x] Factory обновлён
- [x] Все 15 тестов проходят
- [x] **Docker образ 2B-cu128 собран и протестирован на RTX 5080** ✅
- [x] **Docker Desktop (Windows) протестирован** ✅
  - Docker Desktop 29.0.1 + WSL2
  - GPU passthrough работает (RTX 5080)
  - OCR тест: 1.95s, GPU Utilization 53%
  - Flash Attention: отключен (не критично для 2B)
- [ ] Тест 7B локально на RTX 5090 (опционально)

**Статус DeepSeek:**
- [x] **Локальный DeepSeek — рекомендуемое решение** ✅
  - flash_attn 2.7.3 + torch 2.9.0+cu128
  - OCR: 1.29s (быстрее Qwen)
  - BBox координаты: ✅
  - Кириллица: ⚠️ транслитерация
- [x] Docker профили удалены (flash_attn несовместим с Docker)
- [x] Документация обновлена

**Рекомендации по GPU:**

| GPU | VRAM | Docker | Локально |
|-----|------|--------|----------|
| RTX 5070 | 8GB | Qwen 2B (`blackwell`) | — |
| RTX 4080/5080 | 16GB | Qwen 2B + DeepSeek | Стандарт |
| RTX 4090/5090 | 24GB | Qwen 7B + DeepSeek | Полная конфигурация |
| H100/A100 | 40-80GB | Все модели | Enterprise |

#### 0.6 Обогащение IRBlock метаданными (TODO)

```python
# Расширить scripts/pdf_to_context/ir/models.py

@dataclass
class IRBlock:
    # ... существующие поля ...
    
    # Новые поля для графа
    entities: List[str] = field(default_factory=list)
    section_path: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    layout_category: str = ""  # От DocLayout-YOLO
```

**Файлы:**
- [ ] `scripts/pdf_to_context/ir/models.py`
- [ ] `scripts/pdf_to_context/ir/section_extractor.py`

#### 0.7 Граф документов СМК (публичный интерфейс) ✅

**Реализовано:** `scripts/document_graph/` — система классификации и визуализации документов по бизнес-процессам

**Методология (из РК01-2017-07):**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         СИСТЕМА МЕНЕДЖМЕНТА КАЧЕСТВА                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│  М - ПРОЦЕССЫ МЕНЕДЖМЕНТА           │  Б - ПРОЦЕССЫ ЖИЗНЕННОГО ЦИКЛА           │
│  ├── М1: Анализ и оценка            │  ├── Б1: Организация перевозок           │
│  └── М2: Планирование качества      │  ├── Б5: Взаимодействие с потребителями  │
│                                     │  ├── Б6: Планирование и бюджетирование   │
│  В - ПРОЦЕССЫ ОБЕСПЕЧЕНИЯ           │  ├── Б7: Управление закупками            │
│  ├── В1: Авиационная безопасность   │  └── Б8: Управление полетами             │
│  ├── В2: Безопасность полетов       │                                          │
│  ├── В4: Менеджмент персонала       │  Кодирование: ТИП-ПРОЦЕСС.НОМЕР-ВЕРСИЯ   │
│  ├── В5: Инфраструктура             │  Пример: ДП-М1.020-06                    │
│  ├── В6: Летная годность, ТО ВС     │          ├── ДП = Документация процесса  │
│  ├── В7: Охрана труда               │          ├── М1 = Группа + Процесс       │
│  └── В8: Экологический менеджмент   │          ├── 020 = Номер документа       │
│                                     │          └── 06 = Версия                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Использование:**

```bash
# Построить граф из папки с документами
python3 scripts/document_graph/run_graph.py

# С указанием путей
python3 scripts/document_graph/run_graph.py --input input2/BND/pdf --output output/my_graph
```

**Результаты (27.01.2026):**

| Метрика | Значение |
|---------|----------|
| **Документов** | 290 |
| **Процессов** | 14 |
| **Узлов графа** | 307 |
| **Связей** | 231 |

**Статистика по группам:**
- Процессы обеспечения (В): 123 документа
- Процессы жизненного цикла (Б): 50 документов
- Процессы менеджмента (М): 42 документа

**Топ-5 процессов:**
1. В7 (Охрана труда): 63 документа
2. М1 (Анализ и оценка): 41 документ
3. Б1 (Организация перевозок): 26 документов
4. В4 (Менеджмент персонала): 23 документа
5. В6 (Летная годность): 19 документов

**Файлы:**
- [x] `scripts/document_graph/__init__.py` — ✅
- [x] `scripts/document_graph/models.py` — модели данных (Document, Process, Graph)
- [x] `scripts/document_graph/parser.py` — парсер кодов документов
- [x] `scripts/document_graph/graph_builder.py` — генератор графа + HTML визуализатор
- [x] `scripts/document_graph/cli.py` — CLI интерфейс
- [x] `scripts/document_graph/run_graph.py` — скрипт запуска

**Выходные файлы:**
- [x] `scripts/tools/graph_data.json` — данные графа (176KB)
- [x] `scripts/tools/graph_viewer.html` — интерактивный визуализатор (195KB)

**HTML Визуализатор (публичный интерфейс):**
- Cytoscape.js для рендеринга графа
- Фильтры по группам процессов (М/Б/В)
- Поиск по коду документа
- Подсветка связей при клике
- Информационная панель
- Статистика
- **Работает как статический HTML** — можно открыть в любом браузере

```
🌐 Откройте в браузере:
   file:///home/budnik_an/Obligations/scripts/tools/graph_viewer.html
```

---

### ЭТАП 1: Data Layer (1 неделя)

**Цель:** Создать структурированные данные для построения графа.

#### 1.1 Парсеры RACI/Pipeline/BPMN

| Парсер | Вход | Выход |
|--------|------|-------|
| RACIParser | `*_RACI.md` | `List[RACIEntry]` |
| PipelineParser | `*_Pipeline.md` | `List[PipelineActivity]` |
| BPMNParser | `*.bpmn` | `List[BPMNElement], List[BPMNFlow]` |

```python
# scripts/graph/parsers/raci_parser.py

@dataclass
class RACIEntry:
    section: str      # "п.7.2"
    activity: str     # "Подготовка документа"
    responsible: str  # Роль с R
    accountable: str  # Роль с A
    consulted: List[str]
    informed: List[str]
```

**Файлы:**
- [ ] `scripts/graph/__init__.py`
- [ ] `scripts/graph/models.py`
- [ ] `scripts/graph/parsers/raci_parser.py`
- [ ] `scripts/graph/parsers/pipeline_parser.py`
- [ ] `scripts/graph/parsers/bpmn_parser.py`

#### 1.2 Унифицированная модель графа

```python
# scripts/graph/models.py

class NodeType(Enum):
    ROLE = "role"
    TASK = "task"
    DOCUMENT = "document"
    PROCESS = "process"
    SECTION = "section"
    GATEWAY = "gateway"

class EdgeType(Enum):
    PERFORMS = "performs"      # Роль → Задача
    APPROVES = "approves"      # Роль → Задача
    CREATES = "creates"        # Задача → Документ
    FOLLOWS = "follows"        # Задача → Задача
    CONTAINS = "contains"      # Процесс → Задача
    REFERENCES = "references"  # Раздел → Раздел

@dataclass
class ProcessGraph:
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    metadata: Dict
```

---

### ЭТАП 2: Basic Graph (1-2 недели)

**Цель:** Построить граф знаний из распарсенных данных.

#### 2.1 GraphBuilder

```python
# scripts/graph/builder.py

class GraphBuilder:
    def build_from_process(self, process_dir: str) -> ProcessGraph:
        # 1. Парсинг RACI → роли + связи
        # 2. Парсинг Pipeline → задачи + зависимости
        # 3. Парсинг BPMN → flows + gateways
        # 4. Объединение в единый граф
        pass
    
    def to_networkx(self, graph: ProcessGraph) -> nx.DiGraph:
        # Конвертация для анализа
        pass
```

#### 2.2 Визуализация

```python
# scripts/graph/visualizer.py

class GraphVisualizer:
    def to_html(self, G: nx.DiGraph, output_path: str):
        # Интерактивный HTML через pyvis
        pass
    
    def to_graphml(self, G: nx.DiGraph, output_path: str):
        # Экспорт для Neo4j
        pass
```

#### 2.3 CLI

```bash
# Использование
python scripts/utils/build_graph.py output/ДП-М1.020-06 -o graph.html
```

---

### ЭТАП 3: Vector RAG (2 недели)

**Цель:** Базовая RAG-система с векторным поиском.

#### Компоненты

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| **Chunker** | LangChain / Custom | Разбиение OCR на чанки |
| **Embeddings** | `intfloat/multilingual-e5-base` | Векторизация |
| **Vector Store** | ChromaDB | Хранение векторов |
| **BM25** | `rank_bm25` | Лексический поиск |
| **Reranker** | `cross-encoder/ms-marco-MiniLM` | Переранжирование |

#### Архитектура

```
Query → [BM25 + Dense] → RRF Fusion → Rerank → Context → LLM → Answer
```

---

### ЭТАП 4: Graph RAG (2-3 недели)

**Цель:** Полноценный Graph RAG с Neo4j.

#### Компоненты

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| **Graph Store** | Neo4j | Хранение графа |
| **NER** | spaCy / Custom | Извлечение сущностей |
| **Graph Retriever** | Cypher queries | Multi-hop поиск |
| **Hybrid Fusion** | RRF | Объединение vector + graph |

#### Архитектура HybridRAG

```
Query
  │
  ├──► NER → Entities → Cypher Query → Graph Results
  │
  └──► Embedding → Vector Search → Dense Results
                    │
                    ▼
              RRF Fusion
                    │
                    ▼
              Cross-Encoder Rerank
                    │
                    ▼
               Context + LLM
                    │
                    ▼
                 Answer
```

---

## Зависимости

### Новые зависимости (requirements.txt)

```txt
# Layout Detection
doclayout-yolo>=0.0.4

# VLM OCR (альтернатива DeepSeek)
transformers>=4.40.0
qwen-vl-utils>=0.0.8

# Graph
networkx>=3.0
pyvis>=0.3.0
neo4j>=5.0.0

# RAG
chromadb>=0.4.0
sentence-transformers>=2.2.0
rank-bm25>=0.2.2

# NLP
spacy>=3.7.0

# Web UI
fastapi>=0.104.0
uvicorn>=0.24.0

# Optional
docling>=0.1.0  # Альтернативный парсер
```

### GPU Requirements

| Модель | VRAM | Примечание |
|--------|------|------------|
| DocLayout-YOLO | 2 GB | Быстрый inference |
| Qwen2.5-VL-7B | 16 GB | Можно INT4 quantization |
| olmOCR | 14 GB | На базе Qwen2-VL |
| DeepSeek-OCR | 8 GB | Текущее решение |

---

## Структура файлов после реализации

```
scripts/
├── pdf_to_context/          # ✅ Существует
│   ├── extractors/
│   │   ├── layout_detector.py    # 🆕 ЭТАП 0
│   │   └── ...
│   └── ocr_service/
│       ├── qwen_service.py       # 🆕 ЭТАП 0
│       └── ...
│
├── document_graph/          # ✅ ЭТАП 0.7 — Граф документов СМК
│   ├── __init__.py
│   ├── models.py            # Document, Process, Graph модели
│   ├── parser.py            # Парсер кодов документов
│   ├── graph_builder.py     # Генератор графа + HTML визуализатор
│   ├── cli.py               # CLI интерфейс
│   └── run_graph.py         # Скрипт запуска
│
├── graph/                   # 🆕 ЭТАП 1-2 — Граф из RACI/Pipeline/BPMN
│   ├── __init__.py
│   ├── models.py
│   ├── builder.py
│   ├── visualizer.py
│   ├── neo4j_store.py       # ЭТАП 4
│   └── parsers/
│       ├── raci_parser.py
│       ├── pipeline_parser.py
│       └── bpmn_parser.py
│
├── rag/                     # 🆕 ЭТАП 3-4
│   ├── __init__.py
│   ├── chunker.py
│   ├── vector_store.py
│   ├── hybrid_retriever.py
│   ├── graph_retriever.py   # ЭТАП 4
│   ├── reranker.py
│   └── pipeline.py
│
└── utils/
    ├── build_graph.py       # 🆕 ЭТАП 2
    ├── rag_query.py         # 🆕 ЭТАП 3
    └── ...
```

---

## Ссылки

### Исследования

- [OmniDocBench (CVPR 2025)](https://arxiv.org/pdf/2412.07626) — бенчмарк парсинга документов
- [DocLayout-YOLO](https://arxiv.org/html/2410.12628v1) — layout detection
- [olmOCR](https://olmocr.allenai.org/blog) — эффективный VLM OCR
- [HybridRAG (BlackRock & NVIDIA)](https://arxiv.org/abs/2408.xxxxx) — граф + векторы

### Инструменты

- [Qwen2.5-VL](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)
- [DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO)
- [Docling](https://github.com/DS4SD/docling)
- [ChromaDB](https://www.trychroma.com/)
- [Neo4j](https://neo4j.com/)

---

**Автор:** PDFtoBPMN Project  
**Дата:** 26.01.2026
