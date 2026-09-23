# Архитектура PDFtoBPMN v2.1 — Organizational Knowledge Graph

> **Ветка:** `v2-graphrag`  
> **Дата:** 18.03.2026  
> **Версия:** 2.1.1 (graph-as-SSOT pivot)  
> **Принцип:** граф — единственный источник истины; BPMN, RAG, management views — рендеры из графа  
> **Изменения v2.1 → v2.1.1:**  
> - Граф = SSOT (не компонент RAG, а продукт)  
> - Два контура сливаются: один pipeline, один граф, разные views  
> - ProcessSpec = BPMN-oriented projection из графа  
> - Management views (RACI, KPI, controls, risks) = graph queries  
> - BI enrichment layer (phase 5+)
> 
> **Сохранено из v2.1:**  
> - Весь стек инструментов (Docling, OCR, BGE-M3, ChromaDB, reranker)  
> - Document authority model  
> - Business Studio GUID sync  
> - 13 typed artifacts + provenance  
> - Все решения по парсингу составных PDF

---

## 1. Ключевой принцип: Graph as SSOT

### 1.1 Бизнес-контекст

Текущее состояние: 410 документов СМК в PDF — разрозненные, без связей, без навигации. Цель — не просто "распарсить PDF", а создать **машиночитаемую модель организации**: процессы, роли, ответственности, метрики, контроли, риски — в одном графе, из которого автоматически рендерятся все нужные представления.

Это прикладной характер Wide QMS на основе Quality 4.0: "соединить островки в архипелаг — общий dashboard, единая аналитика, cross-functional visibility."

### 1.2 Архитектура: один pipeline, один граф, разные views

```
                 PDF / DOCX / XLSX (русский, 410 документов)
                          │
                ┌─────────▼──────────┐
                │    INGESTION        │
                │                     │
                │  Docling + OCR      │
                │  (EasyOCR/RapidOCR) │
                │  Page Classifier    │
                │  Document Authority │
                └─────────┬──────────┘
                          │
                   DoclingDocument
                   + authority rank
                          │
                ┌─────────▼──────────┐
                │  TYPED EXTRACTION   │
                │  13 artifact types  │
                │  + provenance       │
                │  + confidence       │
                └─────────┬──────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
   ┌──────────────────┐    ┌──────────────────┐
   │ ORGANIZATIONAL    │    │ TEXT INDEX        │
   │ KNOWLEDGE GRAPH   │    │ (ChromaDB)        │
   │ (SSOT)            │    │                   │
   │                   │    │ Hierarchical      │
   │ Nodes: 13 types   │    │ chunks + BGE-M3   │
   │ Edges: typed rels │    │ dense + sparse    │
   │ Authority on each │    │ metadata filter   │
   └────┬──┬──┬──┬─────┘    └────────┬──────────┘
        │  │  │  │                   │
        │  │  │  └─────────┐         │
        ▼  ▼  ▼            ▼         ▼
     BPMN RACI KPI    RAG Retrieval
     view view view   (graph + text)
        │  │  │            │
        └──┴──┘            │
           │               │
    Business Studio    Response + Citations
    + Camunda          + Authority notes
    + HTML portal
    + PDF-A
```

### 1.3 Два хранилища, одна истина

| Хранилище | Что хранит | Для чего | Откуда |
|-----------|-----------|---------|--------|
| **Organizational Graph** (SSOT) | Typed nodes + typed edges + provenance + authority | BPMN rendering, RACI, KPI, controls, management views, graph traversal в RAG | Typed extraction |
| **ChromaDB** (text index) | Hierarchical chunks + BGE-M3 vectors + metadata | Free-form text search в RAG, context для response builder | Chunking |

Оба заполняются из **одного extraction** — не два pipeline. Graph получает structured artifacts (nodes + edges), ChromaDB получает text chunks. При query — оба используются для retrieval, результаты сливаются в RRF fusion.

### 1.4 Views из графа (не отдельные pipelines)

Все management views рендерятся из graph queries:

```
BPMN view:    SELECT roles, steps, decisions, flows WHERE doc = X
              → Roles → Lanes, Steps → Tasks, Decisions → Gateways
              → BPMN XML → Layout → BS GUID inject → .bs.bpmn

RACI view:    SELECT roles, steps, raci_edges WHERE doc = X
              → RACI matrix (R/A/C/I per step per role)

KPI view:     SELECT kpi_nodes, measures_edges, targets WHERE org_unit = X
              → KPI dashboard (name, formula, target, owner)

Control view: SELECT controls, controlled_steps, risks WHERE scope = X
              → Control coverage matrix

Risk view:    SELECT risks, controls, kpi WHERE domain = X
              → Risk register with linked controls and indicators

RAG view:     query → graph traversal + text search → RRF → rerank → response
```

ProcessSpec = BPMN-oriented projection. Не отдельный intermediate format, а **запрос к графу** с рендером в BPMN XML.

### 1.5 Что это даёт бизнесу (Wide QMS / Quality 4.0)

Один и тот же граф, четыре линзы:
- **QMS** (ISO 9001): процессы, PDCA, несоответствия, улучшения
- **SMS** (ICAO): hazards, risks, barriers, safety performance
- **COSO**: controls, governance, risk appetite, assurance
- **Performance**: KPI actual vs target (enriched from DWH/BI)

Изменение процесса — обновление графа, автоматическая перегенерация всех views. Не "утвердить новый PDF", а "обновить граф → BPMN пересобрался → RACI обновился → KPI привязались".

---

## 1.6 Что НЕ меняется от v2.1

Все инструменты, решения по парсингу, OCR, BS sync, authority model — **остаются как есть**. Graph-as-SSOT — надстройка, не замена:

---

## 2. Document Authority Model

### 2.1 Проблема

PDF — корпоративный утверждённый источник. DOCX — может быть черновик, старая редакция, рабочая копия. Без модели доверия RAG смешает "действующую норму" и "старый черновик".

### 2.2 Модель

```yaml
# Семейство документов
document_family:
  code: "РД-Б7.004"                    # Код без версии
  title: "Управление договорной деятельностью"
  
  versions:
    - version: "06"
      format: pdf
      authority: canonical               # canonical / draft / superseded / archived
      source_file: "input/РД-Б7.004-05.pdf"  
      effective_date: "2024-03-15"
      status: active                     # active / inactive
      
    - version: "05"
      format: docx
      authority: superseded              # Заменён версией 06
      source_file: "input/РД-Б7.004-05_v05.docx"
      effective_date: "2022-01-10"
      status: inactive

  authority_rules:
    - "PDF всегда приоритетнее DOCX при одинаковой версии"
    - "Более поздняя effective_date приоритетнее"
    - "canonical > draft > superseded > archived"
```

### 2.3 Как это влияет на RAG

```
Запрос: "Кто отвечает за согласование договора?"

Retrieval находит:
  [1] РД-Б7.004-06.pdf, п.7.3: "Руководитель ПФМ"     authority: canonical
  [2] РД-Б7.004-05.docx, п.7.3: "Начальник отдела"     authority: superseded

RAG ответ:
  "Руководитель ПФМ отвечает за согласование [РД-Б7.004-06, п.7.3].
   Примечание: в предыдущей редакции (v05) эту функцию выполнял 
   Начальник отдела [РД-Б7.004-05, п.7.3, superseded]."
```

### 2.4 Conflict detection

```python
class ConflictDetector:
    def detect(self, family: DocumentFamily) -> list[Conflict]:
        """Находит расхождения между версиями одного документа."""
        # Для каждой пары (canonical, other):
        #   - Сравнить роли: новые, удалённые, изменённые
        #   - Сравнить activities: новые шаги, удалённые, переименованные
        #   - Сравнить definitions: изменённые определения
        # Результат: list[Conflict] с severity и рекомендацией
```

---

## 2.5 OCR: выбор движка для кириллицы

### Что уже работает в репо

Текущий pipeline использует:
- **DeepSeek-OCR** — основной, через vLLM микросервис (GPU, отдельный сервис)
- **PaddleOCR** — fallback, `lang='ru'`, CPU, "88-93% точность для русского" (проверено)
- **Qwen2.5-VL** — альтернатива для описания графики

### Кандидаты для v2.1 (через Docling)

Docling поддерживает 4 OCR backend'а нативно:

| Backend | Кириллица | GPU | Docling интеграция | Особенности |
|---------|-----------|-----|-------------------|-------------|
| **EasyOCR** | `lang=['ru','en']` | CUDA | Нативная (`EasyOcrOptions`) | CRAFT detector, CRNN recognizer, хорошая точность |
| **RapidOCR** | `lang='ru'` | CPU/ONNX | Нативная (`RapidOcrOptions`) | Порт PaddleOCR на ONNX Runtime, без PaddlePaddle |
| Tesseract | `lang='rus'` | CPU only | Нативная (`TesseractOcrOptions`) | Слабый на сложных layout, медленный |
| macOS OCR | — | — | Нативная | Только macOS, не для production |

**Tesseract исключён:** проверен ранее, неудовлетворительное качество на русском тексте СМК (особенно с таблицами и штампами). Подтверждено community: "Tesseract excels on individual characters while EasyOCR works best on complete words".

### EasyOCR vs RapidOCR (PaddleOCR) — ключевые отличия

```
EasyOCR:
  + CRAFT text detector — лучше находит текст в сложных сценах
  + Простая интеграция с Docling (одна строка)
  + Хорошая точность на кириллице
  - Медленнее на CPU (PyTorch inference)
  - Нет layout analysis (только text detection + recognition)
  - Хуже на таблицах и формах

RapidOCR (порт PaddleOCR):
  + Модели PaddleOCR PP-OCRv5 (SOTA, май 2025)
  + Быстрый на CPU (ONNX Runtime)
  + PaddleOCR уже проверен в репо на русском (88-93%)
  + PP-OCRv5 поддерживает кириллицу явно (Cyrillic script)
  + Лучше на сложных layout (slanted text, таблицы)
  - Менее зрелая интеграция с Docling
```

### Решение: POC определяет

```
POC Фаза 0 — тест обоих на 10 реальных документах:

Тест 1: Нативный текст (копируемый) — baseline
Тест 2: Сканированные страницы — чистый OCR
Тест 3: Смешанные страницы (скан + натив в одном PDF)
Тест 4: Таблица RACI (merged cells, multiline)
Тест 5: Графика с русским текстом (блок-схема)

Метрика: Levenshtein similarity с ручной транскрипцией
Порог: >= 95% на тестах 1-2, >= 90% на тестах 3-5
```

---

## 2.6 Парсинг составных PDF: специальные компоненты

### Три проблемы, не покрытые Docling из коробки

**1. Смешанные страницы (ВЫСОКИЙ РИСК)**

Docling использует `bitmap_area_threshold` (дефолт 0.75) per-page: если > 75% площади — растр, запускается OCR. Это whole-page решение, не умеет обрабатывать полстраницы нативно, полстраницы OCR.

Решение: `page_classifier.py` — классифицирует страницы перед парсингом:
- **content** — основной текст (нативный или OCR)
- **approval_sheet** — лист согласования (исключить из extraction, сохранить metadata)
- **appendix** — приложения (формы, шаблоны)
- **cover** — титульная страница

`adaptive_ocr.py` — снижает `bitmap_area_threshold` до 0.5 для document type = СМК.

**2. Таблицы через несколько страниц (СРЕДНИЙ РИСК)**

Docling/TableFormer не склеивает таблицы между страницами. RACI-матрица на 2 страницах → два фрагмента.

Решение: `cross_page_table_merger.py` — если таблица обрывается внизу страницы и продолжается вверху следующей (одинаковое количество колонок, похожие заголовки), склеить.

`raci_table_detector.py` — распознаёт RACI по характерному паттерну (колонки R/A/C/I или Р/О/К/И), парсит специализированно с сохранением иерархии merged cells.

**3. Векторная графика (СРЕДНИЙ РИСК)**

Блок-схемы в Word/Visio → PDF: набор path/rect/text объектов. Docling видит их как отдельные text spans, не группирует.

Решение: `vector_graphics_detector.py` — если на странице > N path-объектов в компактной области → это диаграмма → рендер в растр (DPI 400) → Qwen VLM описывает содержание.

---

## 3. Typed Information Extraction

### 3.1 Почему не NER

NER распознаёт именованные сущности (имена, организации, места). Нам нужен **typed information extraction** — извлечение типизированных артефактов знаний, каждый со своей схемой, правилами валидации и provenance.

### 3.2 Типы артефактов

```python
# core/knowledge_types.py

class KnowledgeType(Enum):
    DEFINITION      = "definition"       # Термин + определение
    ABBREVIATION    = "abbreviation"     # Сокращение + расшифровка
    KPI             = "kpi"              # Показатель + формула + целевое
    FORMULA         = "formula"          # Математическая/бизнес формула
    ROLE            = "role"             # Должность/роль + зона ответственности
    ORG_UNIT        = "org_unit"         # Подразделение
    SYSTEM          = "system"           # ИС / программный продукт
    PROCESS_STEP    = "process_step"     # Шаг процесса
    DECISION_RULE   = "decision_rule"    # Условие ветвления (если...то...иначе)
    DOCUMENT_REF    = "document_ref"     # Ссылка на другой документ
    CONTROL         = "control"          # Контрольная процедура / проверка
    INPUT_OUTPUT    = "input_output"     # Вход/выход процесса (документ, данные)
    FORM_TEMPLATE   = "form_template"    # Форма / шаблон из приложений

@dataclass
class KnowledgeArtifact:
    """Базовый класс для всех типизированных артефактов."""
    id: str
    type: KnowledgeType
    content: dict                        # Типоспецифичные поля
    provenance: Provenance               # Откуда извлечено
    confidence: float                    # 0.0 - 1.0
    document_authority: str              # canonical / superseded / draft

@dataclass
class Provenance:
    """Трассировка к исходному документу."""
    document_code: str                   # РД-Б7.004-06
    document_version: str                # 06
    section: str                         # п.7.2
    paragraph: int                       # Абзац 3
    page: int                            # Страница 12
    quote: str                           # Точная цитата
    extraction_method: str               # regex / spacy / llm / manual
```

### 3.3 Типоспецифичные схемы

```yaml
# Примеры content для каждого типа

Definition:
  term: "ПФМ"
  definition: "Подразделение финансового менеджмента"
  scope: "В рамках данного документа"

KPI:
  name: "Срок подготовки договора"
  formula: "Дата подписания - Дата инициирования"
  target_value: "15 рабочих дней"
  measurement_unit: "рабочие дни"
  frequency: "ежемесячно"
  owner_role: "role_pfm_head"

DecisionRule:
  condition: "Обоснование достаточно"
  if_true: "Перейти к подготовке договора (п.7.2)"
  if_false: "Возврат на доработку инициатору"
  gateway_type: "exclusive"

Role:
  name: "Руководитель ПФМ"
  department: "Подразделение финансового менеджмента"
  responsibilities: ["Согласование договоров", "Контроль бюджета"]
  raci_pattern: "Typically A or R for contract activities"

DocumentRef:
  target_code: "КД-РГ-039-05"
  target_title: "Претензионно-исковая работа"
  context: "При возникновении споров по договору"
  relationship: "extends"              # extends / references / supersedes / conflicts
```

### 3.4 Extractor architecture

```
DoclingDocument
       │
       ▼
┌──────────────────────────────────────────────┐
│         Typed Extraction Pipeline             │
│                                               │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ Rule-based   │  │ LLM-based            │  │
│  │ extractors   │  │ extractors            │  │
│  │              │  │                       │  │
│  │ - Definition │  │ - ProcessStep         │  │
│  │   (regex)    │  │ - DecisionRule        │  │
│  │ - Abbreviation│  │ - Role responsibilities│ │
│  │   (regex)    │  │ - KPI extraction      │  │
│  │ - DocumentRef│  │ - Control detection   │  │
│  │   (regex)    │  │ - Input/Output        │  │
│  │ - Formula    │  │                       │  │
│  │   (pattern)  │  │  LLM: Claude API      │  │
│  └──────┬──────┘  └──────────┬───────────┘  │
│         │                    │               │
│         └────────┬───────────┘               │
│                  ▼                            │
│     ┌─────────────────────┐                  │
│     │ Artifact Assembler   │                  │
│     │ + Provenance Tracker │                  │
│     │ + Confidence Scorer  │                  │
│     └──────────┬──────────┘                  │
│                │                              │
└────────────────┼──────────────────────────────┘
                 │
                 ▼
        list[KnowledgeArtifact]
        (с типом, provenance, confidence)
```

**Принцип:** Всё что можно извлечь детерминированно (definitions, abbreviations, document refs, formulas) — делаем regex/pattern. LLM используем только для того, что требует понимания контекста (process steps, decision rules, role responsibilities).

---

## 4. Unified pipeline: Graph + Text Index

Один extraction pipeline фидит **оба хранилища** — не два контура:

```
DoclingDocument + Authority
          │
          ▼
   Typed Extraction (13 типов, Claude API)
          │
          ├──────────────────────────────────┐
          ▼                                  ▼
   ┌──────────────────┐             ┌───────────────┐
   │ GRAPH POPULATION │             │ TEXT INDEXING  │
   │                  │             │               │
   │ Artifacts → nodes│             │ Hierarchical  │
   │ Relations → edges│             │ chunks        │
   │ (RACI, sequence, │             │ + BGE-M3      │
   │  decision, meas.)│             │ dense + sparse│
   │ Each node:       │             │ Metadata:     │
   │  provenance      │             │  doc_code     │
   │  authority       │             │  section      │
   │  confidence      │             │  authority    │
   │                  │             │  artifact_types│
   └──────┬───────────┘             └───────┬───────┘
          │                                 │
          │ Graph DB                        │ ChromaDB
          │ (SQLite/NetworkX)               │ (vectors)
          │                                 │
          ├─── Views (BPMN, RACI, KPI) ◄────┘
          │                                 │
          └─────────────┬───────────────────┘
                        ▼
              ┌──────────────────┐
              │ Hybrid Retrieval │
              │                  │
              │ Query analysis → │
              │ routing:         │
              │  structured → graph
              │  text → chunks   │
              │  mixed → both    │
              │                  │
              │ → RRF fusion     │
              │ → authority bias │ ← canonical boost
              │ → bge-reranker   │ ← ОТДЕЛЬНАЯ модель
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ Response Builder │
              │ (Claude API)     │
              │                  │
              │ graph context    │
              │ + text chunks    │
              │ → citations      │
              │ → authority note │
              │ → conflict warn  │
              └──────────────────┘
```

**Authority bias в retrieval:** canonical результаты получают boost при RRF fusion. Superseded включаются только если запрос явно про версионность или canonical не содержит ответа.

**Query routing:**
```
"Кто отвечает за согласование?"       → graph (Role → RACI edges)
"Опиши порядок действий при отказе"   → text chunks + graph context
"Все KPI подразделения X"              → graph (KPI nodes → measures → OrgUnit)
"Чем v06 отличается от v05?"          → graph (conflict detection) + text (diff)
```

---

## 5. Views из графа

### 5.1 BPMN view (Process Model)

Graph query: `SELECT roles, steps, decisions, flows WHERE doc = X AND authority = canonical`

```
Graph query result
        │
        ▼
  BPMN Compiler (код, не AI)
  Roles → Lanes
  Steps → Tasks  
  Decisions → Gateways
  I/O → Data Objects
  Flow edges → SequenceFlow
        │
        ▼
  Layout engine (абсолютные координаты)
        │
        ▼
  Camunda validation (C7/C8 schema)
        │
        ▼
  BS GUID injection (из bs_guid_registry.yaml)
  BS coordinate adapter
        │
        ├──────────┐
        ▼          ▼
  .bs.bpmn    KPI Excel
  (import)    (supplement)
```

BPMN генерируется **только для canonical документов**. Нет смысла строить BPMN из черновика.

### 5.2 RACI view

Graph query: `SELECT roles, steps, raci_edges WHERE doc = X`
→ RACI matrix (R/A/C/I per step per role) → RACI.md / DOCX

### 5.3 KPI view

Graph query: `SELECT kpi_nodes, measures_edges, targets WHERE org_unit = X`
→ KPI dashboard (name, formula, target, owner, actual — если есть BI enrichment)

### 5.4 Control coverage view

Graph query: `SELECT controls, controlled_steps, risks WHERE scope = X`
→ Control matrix → gap analysis (шаги без контролей)

### 5.5 Risk register view

Graph query: `SELECT risks, controls, kpi WHERE domain = X`
→ Risk register с привязанными контролями и индикаторами

### 5.6 Enrichment layer (Phase 5+, future)

```
Corporate DWH / BI
        │
        ▼ (scheduled sync)
  KPI nodes get actual values
  (actual vs target)
        │
        ▼
  Alerts: KPI deviation > threshold
  Dashboard: real-time status
```

---

## 5.7 Business Studio Sync — детальная механика

### Как BS работает с BPMN (по документации BS Docs 6)

BS поддерживает стандартный BPMN 2.0 XML — тот же формат, что генерируют Camunda Modeler и bpmn-js. Никакого проприетарного расширения формата нет.

**Центральная механика: GUID-матчинг.**

При импорте BS проверяет каждый объект по параметру `guid`:

```
GUID совпадает + объект в том же месте иерархии → ОБНОВЛЯЕТСЯ целиком
GUID совпадает + объект в ДРУГОМ месте иерархии → ДУБЛИКАТ (новый объект!)
GUID не найден → создаётся новый объект в папке "BPMN" в корне справочника
```

Три типа объектов сопоставляются по guid:
1. **Единицы деятельности** (процессы, подпроцессы) — id в `<bpmn:process>`
2. **Оргединицы** (роли, подразделения) — id в `<bpmn:lane>` / `<bpmn:participant>`
3. **Функциональные объекты** (системы, документы) — если guid найден в БД, используется существующий

**Координаты фигур:** BS поддерживает абсолютные и относительные. При импорте из внешней системы использовать **абсолютные**. layout_engine.py должен генерировать BPMNDiagram с координатами, совместимыми с размерами холста BS.

**Что НЕ передаётся через BPMN:**
- Связанные показатели (KPI), формулы, целевые значения
- Документы-входы/выходы как объекты справочника
- Метаданные СМК (версия, дата утверждения)
- Определения и сокращения

Для передачи этих данных нужен **дополнительный канал**: настраиваемый XML-импорт (Администрирование → Импорт/Экспорт → Пакеты импорта) или Excel-импорт.

### Архитектура модуля scripts/business_studio/

```
scripts/business_studio/
├── bs_guid_registry.py        # Реестр guid из BS (bootstrap + обновление)
├── bs_bootstrap.py            # Одноразовый: экспорт из BS → парсинг → реестр
├── bpmn_guid_injector.py      # BPMN XML + реестр → BPMN с правильными guid
├── bs_coordinate_adapter.py   # Калибровка координат под холст BS
├── bs_supplementary_export.py # KPI, документы, показатели → XML/Excel пакет
├── bs_importer.py             # Автоматизация импорта (если BS API доступен)
├── sync_validator.py          # Round-trip: export BS → diff с нашим BPMN
└── bs_config.yaml             # Настройки: иерархия, целевая группа, координаты
```

### Процесс синхронизации

```
ПЕРВИЧНАЯ НАСТРОЙКА (один раз):

  1. Экспортировать из BS все процессы в BPMN-файлы
  2. bs_bootstrap.py парсит файлы → извлекает guid для:
     - Каждого процесса (process id → guid)
     - Каждой оргединицы (lane name → guid)
     - Каждого функционального объекта (data object → guid)
  3. Сохраняет в bs_guid_registry.yaml:

     processes:
       "Б7.004":
         guid: "{12345-abcd-efgh-6789}"
         bs_hierarchy: "Деятельность/Бизнес-процессы/Б7"
     
     org_units:
       "Руководитель ПФМ":
         guid: "{aaaa-bbbb-cccc-dddd}"
         bs_reference: "Оргединицы/ПФМ/Руководитель"
     
     functional_objects:
       "Служебная записка":
         guid: "{eeee-ffff-1111-2222}"

  4. Калибровка координат: экспортировать из BS диаграмму,
     определить диапазоны X/Y, сохранить в bs_config.yaml

ГЕНЕРАЦИЯ BPMN ДЛЯ BS:

  Graph query: roles, steps, decisions, flows WHERE doc = X
        │
        ▼
  bpmn_compiler.py          # Graph → BPMN XML (generic)
        │
        ▼
  bpmn_guid_injector.py     # Подставляет guid из реестра:
        │                     - Известная роль → её guid из BS
        │                     - Новая роль → новый uuid (будет создана в BS)
        ▼
  bs_coordinate_adapter.py  # Пересчитывает координаты под холст BS
        │
        ▼
  [Документ].bs.bpmn        # BPMN файл, готовый к импорту в BS

ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ (не через BPMN):

  Graph query: KPI, docs, indicators WHERE doc = X
        │
        ▼
  bs_supplementary_export.py  # Генерирует:
        │                       - KPI → Excel/XML для пакета импорта BS
        │                       - Документы-входы/выходы → Excel
        │                       - Показатели → Excel
        ▼
  [Документ]_bs_supplement.xlsx

ИМПОРТ В BS:

  1. Импортировать [Документ].bs.bpmn через меню BPMN
     → Процесс обновляется (если guid совпадает) или создаётся
  2. Импортировать [Документ]_bs_supplement.xlsx через пакет импорта
     → KPI, документы, показатели привязываются к процессу
```

### Round-trip test

```python
class BSSyncValidator:
    def validate_roundtrip(self, our_bpmn: str, bs_exported_bpmn: str) -> Report:
        """
        Сравнивает наш BPMN с тем, что BS экспортировал обратно.
        Фиксирует:
          - Потерянные элементы (наши есть, в BS нет)
          - Лишние элементы (в BS есть, наших нет)
          - Сдвиг координат (>10px = проблема)
          - GUID дрифт (id изменился после импорта)
        """
```

---

## 6. Общий Storage Layer

```python
# core/stores.py

class GraphStore(Protocol):
    """Organizational Knowledge Graph — SSOT.
    NetworkX + SQLite сейчас, graph DB потом."""
    
    # --- Write (extraction pipeline) ---
    def add_artifact(self, artifact: KnowledgeArtifact) -> str: ...
    def add_relation(self, source: str, target: str, 
                     rel_type: str, props: dict = {}) -> None: ...
    def delete_by_document(self, doc_code: str) -> None: ...
    
    # --- Read: general ---
    def query_neighbors(self, node_id: str, hops: int = 1,
                        edge_types: list[str] | None = None) -> list: ...
    def query_by_type(self, artifact_type: KnowledgeType) -> list: ...
    def query_by_document(self, doc_code: str) -> list: ...
    
    # --- Read: BPMN view ---
    def query_process(self, doc_code: str) -> dict:
        """Roles, steps, decisions, flows для BPMN rendering.""" ...
    
    # --- Read: RACI view ---
    def query_raci(self, doc_code: str) -> list[dict]:
        """Role × Step × RACI type matrix.""" ...
    
    # --- Read: KPI view ---
    def query_kpi(self, org_unit: str | None = None) -> list[dict]:
        """KPI nodes + measures edges + targets.""" ...
    
    # --- Read: Control coverage ---
    def query_controls(self, scope: str | None = None) -> list[dict]:
        """Controls + controlled steps + gaps.""" ...
    
    # --- Read: RAG traversal ---
    def query_for_rag(self, entities: list[str], 
                      edge_types: list[str] | None = None,
                      max_hops: int = 2) -> list[dict]:
        """Structured context for RAG response builder.""" ...
    
    # --- Persistence ---
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...

class NetworkXGraphStore(GraphStore):
    """MVP реализация: NetworkX in-memory + SQLite/JSON persistence."""
    ...

# Будущие реализации:
# class FalkorDBGraphStore(GraphStore): ...
# class PostgresAGEGraphStore(GraphStore): ...
```

```python
class VectorStore(Protocol):
    """Абстракция над vector store. ChromaDB сейчас, Qdrant потом."""
    def index(self, chunks: list[Chunk]) -> None: ...
    def search_dense(self, query: str, top_k: int) -> list[Result]: ...
    def search_sparse(self, query: str, top_k: int) -> list[Result]: ...
    def delete_by_document(self, doc_code: str) -> None: ...
```

```
Файловая структура хранения (410 документов):

output/
├── registry.yaml                   # Реестр семейств документов + authority
├── graph/
│   ├── org_graph.db                # Organizational graph (SSOT) — SQLite
│   ├── org_graph.json              # JSON export для debug/portability
│   └── metadata.json               # Статистика (nodes, edges, coverage)
├── vectors/
│   ├── chroma_db/                  # ChromaDB persistence (text index)
│   └── index_metadata.json         # Какие документы проиндексированы
├── conflicts/
│   └── conflict_report.yaml        # Конфликты между версиями
└── [код_документа]/
    ├── artifacts.json              # KnowledgeArtifacts из документа
    ├── [код].bpmn                  # BPMN view (rendered from graph)
    ├── [код].bs.bpmn               # BPMN с BS GUIDs
    ├── [код]_RACI.md               # RACI view (rendered from graph)
    ├── [код]_Pipeline.md           # Pipeline view (rendered from graph)
    ├── [код]_bs_supplement.xlsx    # KPI/docs для BS Excel import
    └── [код].md                    # MD документация
```

**Примечание:** ProcessSpec как отдельный файл убран. BPMN-oriented projection выполняется graph query → BPMN compiler напрямую. Промежуточный YAML не нужен — граф и есть source of truth.

---

## 7. Обновлённый стек компонентов

| Компонент | Решение | Лицензия | Слой |
|-----------|---------|----------|------|
| Document parsing | Docling + docling-parse | MIT | Ingestion |
| OCR | EasyOCR или RapidOCR (выбор по POC) | Apache 2.0 | Ingestion |
| Authority model | Собственный (core/) | — | Ingestion |
| Typed extraction (rule-based) | regex + spaCy | MIT | Extraction |
| Typed extraction (LLM-based) | Claude API (Sonnet 4.6) | Anthropic API | Extraction |
| Org. knowledge graph (SSOT) | NetworkXGraphStore + SQLite | BSD-3 | Graph |
| Vector store (text index) | ChromaDB → Qdrant | Apache 2.0 | Text index |
| Embeddings (retrieval) | BGE-M3 | MIT | Text index |
| Reranking | bge-reranker-v2-m3 | MIT | Retrieval |
| RAG framework | LightRAG (после POC) | MIT | Retrieval |
| RAG evaluation | RAGAS | MIT | Quality |
| BPMN view renderer | Собственный (scripts/bpmn/) | — | Views |
| BPMN validation | lxml + Camunda schema | MIT | Views |
| Business Studio sync | Собственный (scripts/bs/) | — | Views |
| BS supplementary | openpyxl (Excel export) | MIT | Views |
| RACI/KPI/Control views | Собственный (scripts/views/) | — | Views |
| VLM графика | Qwen2.5-VL-7B (локально) | Apache 2.0 | Ingestion |
| LLM (dev) | Cursor AI: Opus 4.6 / Auto / Composer 1.5 | Cursor подп. | Dev |
| LLM (batch/runtime) | Claude API: `claude-sonnet-4-6` | Anthropic API | Batch |
| Dev state | LangGraph + SQLite | MIT | Governance |
| Оркестрация (dev) | Cursor AI 4 agents | — | Dev |

### 7.1 LLM-стратегия: Cursor + Claude API

```
РАЗРАБОТКА (Cursor AI, 4 агента):
  ─ orchestrator:   Opus 4.6, temp 0.2 (Plan Mode)
  ─ coder:          Auto / Composer 1.5, temp 0.4 (Agent Mode)
  ─ validator:      Composer 1.5, temp 0.0 (Agent Mode)
  ─ scribe:         Composer 1.5, temp 0.0 (Agent Mode)

ФАЗА 4 (batch 410 документов): Claude API
  ─ Typed extraction:     claude-sonnet-4-6 (API, программный вызов)
  ─ Gold Standard drafts: claude-sonnet-4-6 (API)
  ─ VLM графика:          Qwen2.5-VL-7B (локально, GPU)

ФАЗА 5 (runtime API): Claude API
  ─ RAG generation:       claude-sonnet-4-6 (API)
  ─ Typed extraction:     claude-sonnet-4-6 (API)
  ─ Сложный анализ:       claude-opus-4-6 (API, при необходимости)

Стоимость Claude API (batch processing):
  Sonnet 4.6: $3 input / $15 output per 1M tokens
  410 документов × ~50K tokens = ~20M tokens input
  Оценка: ~$60 input + ~$150 output = ~$210 за полный batch

Единственная локальная модель: Qwen2.5-VL-7B (Apache 2.0)
  ─ Описание графики из документов (VLM задача)
  ─ Требует GPU с ~16GB VRAM
  ─ Claude API не поддерживает VLM для описания произвольных изображений
    в pipeline-режиме — только через chat
```

---

## 8. Структура проекта v2.1

```
PDFtoBPMN/
├── core/                              # Общие модели и абстракции
│   ├── __init__.py
│   ├── knowledge_types.py             # KnowledgeType, KnowledgeArtifact, Provenance
│   ├── edge_types.py                  # EdgeType: RACI, sequence, decision, measures, controls
│   ├── document_authority.py          # DocumentFamily, authority rules, conflict detection
│   ├── ontology.py                    # NodeType, EdgeType, full schema
│   └── stores.py                      # GraphStore, VectorStore (Protocol)
│
├── scripts/
│   ├── ingestion/                     # ОБЩИЙ INGESTION (оба контура)
│   │   ├── docling_adapter.py         # Docling + OCR (EasyOCR или RapidOCR)
│   │   ├── page_classifier.py         # НОВЫЙ: content / approval / appendix / cover
│   │   ├── adaptive_ocr.py            # НОВЫЙ: bitmap_area_threshold по типу страницы
│   │   ├── header_filter.py           # Фильтрация колонтитулов
│   │   ├── raci_table_detector.py     # НОВЫЙ: специализированный RACI parser
│   │   ├── cross_page_table_merger.py # НОВЫЙ: склейка таблиц между страницами
│   │   ├── vector_graphics_detector.py # НОВЫЙ: path-объекты → render → VLM
│   │   ├── graphics_handler.py        # Qwen VLM описание
│   │   ├── chunker.py                 # Hierarchical chunking
│   │   └── authority_resolver.py      # PDF vs DOCX → authority rank
│   │
│   ├── extraction/                    # TYPED EXTRACTION (оба контура)
│   │   ├── __init__.py
│   │   ├── base_extractor.py          # BaseExtractor Protocol
│   │   ├── rule_based/                # Детерминированные (regex/pattern)
│   │   │   ├── definition_extractor.py
│   │   │   ├── abbreviation_extractor.py
│   │   │   ├── document_ref_extractor.py
│   │   │   ├── formula_extractor.py
│   │   │   └── form_template_extractor.py
│   │   ├── llm_based/                 # LLM-зависимые
│   │   │   ├── role_extractor.py
│   │   │   ├── process_step_extractor.py
│   │   │   ├── decision_rule_extractor.py
│   │   │   ├── kpi_extractor.py
│   │   │   ├── control_extractor.py
│   │   │   └── input_output_extractor.py
│   │   ├── artifact_assembler.py      # Сборка артефактов + provenance
│   │   └── graph_populator.py         # Артефакты → graph nodes + typed edges
│   │
│   ├── graph/                         # ORGANIZATIONAL GRAPH (SSOT)
│   │   ├── networkx_store.py          # NetworkXGraphStore implementation
│   │   ├── graph_builder.py           # Artifacts + relations → graph
│   │   ├── conflict_detector.py       # Конфликты между версиями
│   │   └── graph_queries.py           # BPMN/RACI/KPI/Control/RAG query interfaces
│   │
│   ├── rag/                           # RAG RETRIEVAL
│   │   ├── indexer.py                 # Chunks → ChromaDB
│   │   ├── retriever.py               # Hybrid: dense + sparse + graph traversal
│   │   ├── query_router.py            # structured → graph, text → chunks, mixed → both
│   │   ├── reranker.py                # bge-reranker-v2-m3
│   │   ├── authority_ranker.py        # Authority bias в результатах
│   │   └── response_builder.py        # LLM + citations + authority notes
│   │
│   ├── views/                         # VIEW RENDERERS (from graph)
│   │   ├── bpmn_compiler.py           # Graph query → BPMN XML (strict, code)
│   │   ├── layout_engine.py           # Алгоритмическая раскладка
│   │   ├── camunda_validator.py       # Schema validation (C7/C8 target)
│   │   ├── raci_renderer.py           # Graph query → RACI matrix (MD/DOCX)
│   │   ├── kpi_renderer.py            # Graph query → KPI dashboard data
│   │   ├── control_renderer.py        # Graph query → control coverage
│   │   └── pipeline_renderer.py       # Graph query → Pipeline.md
│   │
│   ├── business_studio/               # BUSINESS STUDIO SYNC
│   │   ├── bs_guid_registry.py        # Реестр guid: наши id → BS guid
│   │   ├── bs_bootstrap.py            # Одноразовый: парсинг экспорта BS → реестр
│   │   ├── bpmn_guid_injector.py      # BPMN XML + реестр → BPMN с guid из BS
│   │   ├── bs_coordinate_adapter.py   # Калибровка координат под холст BS
│   │   ├── bs_supplementary_export.py # KPI, документы → Excel для пакета импорта BS
│   │   ├── sync_validator.py          # Round-trip: наш BPMN vs экспорт из BS
│   │   └── bs_config.yaml             # Иерархия, группа импорта, размеры холста
│   │
│   ├── gold/                          # Gold Standard инструменты
│   │   ├── generate_draft.py
│   │   ├── validate.py
│   │   └── score_rag.py
│   │
│   ├── pdf_to_context/                # СОХРАНИТЬ: старый pipeline (read-only)
│   ├── document_graph/                # СОХРАНИТЬ: старый граф (read-only)
│   └── utils/                         # Batch processing
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_authority.py              # НОВЫЙ: версии и конфликты
│   ├── test_extraction_rule_based.py
│   ├── test_extraction_llm_based.py
│   ├── test_views.py
│   ├── test_bpmn_compiler.py          # Переименован: compiler, не generator
│   ├── test_rag.py
│   ├── test_business_studio.py        # НОВЫЙ: guid injection, coordinates, round-trip
│   │   # test_guid_registry_loads: реестр парсится без ошибок
│   │   # test_guid_injection: известные роли получают guid из реестра
│   │   # test_new_objects_get_uuid: новые объекты получают свежий uuid
│   │   # test_coordinates_in_range: координаты в пределах холста BS
│   │   # test_no_duplicate_on_reimport: повторный импорт → update, не create
│   │   # test_supplementary_excel: KPI/документы → валидный Excel для BS
│   └── fixtures/gold/
│
└── poc/
    ├── poc_ocr_comparison.py           # EasyOCR vs RapidOCR на 10 документах
    ├── poc_lightrag_russian.py         # LightRAG + Claude API
    ├── poc_qwen_graphics.py            # Qwen VLM описание
    ├── poc_authority_model.py          # Семейства документов
    ├── poc_bs_roundtrip.py             # BS export → guid → reimport
    └── poc_page_classifier.py          # Классификация страниц: content/approval/etc
```

---

## 9. Обновлённые фазы реализации

```
ФАЗА 0 (1 неделя): POC + Gold Standard
  POC 1: Docling + EasyOCR vs RapidOCR на русском (10 документов)
    → Levenshtein similarity: натив, скан, смешанный, таблица, графика
    → Победитель становится единственным OCR
  POC 2: LightRAG с Claude API — entity extraction на русском
  POC 3: Qwen2.5-VL-7B — описание графики
  POC 4: Document authority — определение семейств
  POC 5: BS round-trip — экспорт → парсинг guid → реимпорт
  POC 6: Page classifier — classification accuracy на 30 страницах
  POC 7: Graph population — typed artifacts → NetworkX → query BPMN/RACI
  Gold Standard: разметка 10 документов (параллельно)
  └→ Governance gate: решение по OCR, LightRAG, graph schema

ФАЗА 1 (2-3 недели): Core + Ingestion + Authority
  - core/knowledge_types.py (13 типов артефактов)
  - core/edge_types.py (RACI, sequence, decision, measures, controls)
  - core/document_authority.py (семейства, версии, conflict detection)
  - core/stores.py (GraphStore + VectorStore Protocol)
  - scripts/ingestion/docling_adapter.py (Docling + OCR победитель)
  - scripts/ingestion/page_classifier.py (content/approval/appendix/cover)
  - scripts/ingestion/adaptive_ocr.py (threshold по типу страницы)
  - scripts/ingestion/raci_table_detector.py (RACI parser)
  - scripts/ingestion/cross_page_table_merger.py (склейка таблиц)
  - scripts/ingestion/vector_graphics_detector.py (path → render → VLM)
  - scripts/ingestion/chunker.py (hierarchical + authority metadata)
  Тесты: ingestion quality + authority resolution vs Gold Standard

ФАЗА 2 (3-4 недели): Extraction + Graph population
  - scripts/extraction/rule_based/ (5 extractors)
  - scripts/extraction/llm_based/ (6 extractors, Claude API)
  - scripts/extraction/artifact_assembler.py (provenance + confidence)
  - scripts/extraction/graph_populator.py (artifacts → graph nodes + typed edges)
  - scripts/graph/networkx_store.py (GraphStore implementation)
  - scripts/graph/graph_builder.py (full graph from 410 docs)
  - scripts/graph/conflict_detector.py (межверсионные конфликты)
  - scripts/graph/graph_queries.py (BPMN/RACI/KPI/Control query interfaces)
  Тесты: extraction F1 по типу, graph completeness vs Gold Standard

ФАЗА 3 (4-5 недель): RAG + Views (unified, not two contours)

  Шаг 3.1: Text indexing
    - scripts/rag/indexer.py (chunks → ChromaDB, BGE-M3 dense+sparse)
    - Metadata: doc_code, section, authority, artifact_types

  Шаг 3.2: Retrieval pipeline
    - scripts/rag/query_router.py (structured → graph, text → chunks, mixed → both)
    - scripts/rag/retriever.py (hybrid: graph traversal + dense + sparse)
    - scripts/rag/reranker.py (bge-reranker-v2-m3, cross-encoder → top-5)
    - scripts/rag/authority_ranker.py (canonical boost +0.15)
    - scripts/rag/response_builder.py (Claude API + citations + authority notes)
    Тесты: RAGAS метрики на 50 gold-запросах

  Шаг 3.3: View renderers (from graph, not separate pipeline)
    - scripts/views/bpmn_compiler.py (graph query → BPMN XML, strict code)
    - scripts/views/layout_engine.py (алгоритмическая раскладка)
    - scripts/views/camunda_validator.py (C7/C8 schema check)
    - scripts/views/raci_renderer.py (graph query → RACI matrix)
    - scripts/views/kpi_renderer.py (graph query → KPI dashboard data)
    - scripts/views/control_renderer.py (graph query → control coverage)
    - scripts/views/pipeline_renderer.py (graph query → Pipeline.md)
    Тесты: BPMN validity, view consistency with graph, Gold Standard comparison

ФАЗА 4 (3-4 недели): Business Studio + Batch + Integration

  Шаг 4.1: BS Bootstrap (предусловие — доступ к BS)
    - Экспортировать из BS все существующие процессы в BPMN
    - bs_bootstrap.py → парсинг → bs_guid_registry.yaml
    - Калибровка координат: диапазоны X/Y холста BS → bs_config.yaml

  Шаг 4.2: GUID Injection + Coordinate Adapter
    - bpmn_guid_injector.py: graph node id → BS guid из реестра
    - bs_coordinate_adapter.py: пересчёт layout под холст BS
    - Тест: импортировать 1 процесс в BS → обновляется, не дублируется

  Шаг 4.3: Supplementary Export (KPI, документы — не через BPMN)
    - bs_supplementary_export.py: graph KPI/doc nodes → Excel пакет
    - Тест: импортировать пакет в BS → данные привязаны к процессу

  Шаг 4.4: Round-trip Validation
    - sync_validator.py: наш BPMN vs экспорт обратно из BS
    - Критерии: 0 потерянных элементов, 0 дубликатов, координаты ±10px

  Шаг 4.5: End-to-end + Batch (LangGraph batch_pipeline)
    - E2E: документ → ingestion → extraction → graph → views + RAG
    - Batch 410 документов (через batch_graph.py с HITL checkpoints)
    - Human review каждого BPMN view перед BS import

  └→ Governance gate: merge v2-graphrag → main

ФАЗА 5 (отложена): Enrichment + API + UI
  - Corporate DWH/BI → KPI nodes (actual vs target)
  - HTML portal rendering
  - PDF-A generation + electronic signature
  - REST API for graph queries
```

### Timeline

```
Неделя 1:       Фаза 0 — POC + Gold Standard
Неделя 2-4:     Фаза 1 — Core + Ingestion + Authority
Неделя 5-8:     Фаза 2 — Extraction + Graph population
Неделя 9-13:    Фаза 3 — RAG + Views (unified)
Неделя 14-17:   Фаза 4 — BS sync + Batch 410 docs
                └→ merge в main

Итого: ~17 недель
Фаза 3 шаги 3.1-3.3 последовательны (каждый зависит от предыдущего)
Фаза 4 требует доступ к Business Studio (bootstrap)
Фаза 5 после стабилизации основного pipeline
```
