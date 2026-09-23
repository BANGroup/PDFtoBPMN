# Агентная архитектура PDFtoBPMN v2.1

> 3 агента + LangGraph (внутренний граф состояния) + governance  
> Паттерн из Helicomponents: ownership по путям, контракт задачи, минимальный дифф

---

## 1. Три агента

```
┌───────────────────────────────────────────────────┐
│                  GOVERNANCE                        │
│  DECISIONS.md │ .cursor/rules │ LangGraph state   │
│  (нельзя менять без human approval)               │
└───────────┬───────────────────────┬───────────────┘
            │ читает               │ читает
            ▼                      ▼
┌──────────────────┐     ┌──────────────────┐
│   ORCHESTRATOR   │────→│     CODER        │
│                  │     │                  │
│ Plan Mode        │     │ Agent Mode       │
│ Opus 4.6         │     │ Sonnet 4.6       │
│                  │     │                  │
│ МОЖЕТ:           │     │ МОЖЕТ:           │
│  планировать     │     │  писать код      │
│  декомпозировать │     │  запускать pytest │
│  проверять diff  │     │  рефакторить     │
│                  │     │                  │
│ НЕ МОЖЕТ:        │     │ НЕ МОЖЕТ:        │
│  писать код      │     │  менять архитек. │
│  менять файлы    │     │  добавлять deps  │
│  запускать скрипт│     │  создавать модули│
│  менять rules    │     │  менять rules    │
│  менять docs/*   │     │  менять docs/*   │
└────────┬─────────┘     └──────────────────┘
         │ командует
         ▼
┌──────────────────┐
│     SCRIBE       │
│                  │
│ Agent Mode       │
│ Sonnet 4.6       │
│                  │
│ МОЖЕТ:           │
│  docs/**         │
│  DECISIONS.md    │
│  CURRENT_STATE   │
│  changelog.md    │
│  tests/fixtures/ │
│  LangGraph state │
│  запускать valid.│
│                  │
│ НЕ МОЖЕТ:        │
│  scripts/**      │
│  core/**         │
│  .cursor/rules   │
└──────────────────┘
```

### Orchestrator — "архитектор"
- Планирует задачу: цель, scope, non-goals, инварианты, критерии успеха.
- Декомпозирует на подзадачи для coder.
- Проверяет diff от coder (ревью).
- Командует scribe обновить состояние.
- **Жёстко запрещено:** код, файлы, запуски, изменение rules.
- **Модель:** Opus 4.6 (Plan Mode).

### Coder — "исполнитель"
- Реализует строго по плану orchestrator'а.
- Сдаёт отчёт: что изменено, что не трогали, что проверить, риски.
- Запускает pytest.
- **Жёстко запрещено:** архитектурные решения, новые зависимости, новые модули без плана.
- **Модель:** Sonnet 4.6 (Agent Mode).

### Scribe — "писарь / валидатор"
- Ведёт LangGraph state (граф разработки).
- Обновляет DECISIONS.md, CURRENT_STATE.md, changelog.md.
- Запускает валидации (pytest, RAGAS метрики, schema checks).
- Ведёт Gold Standard fixtures.
- **Жёстко запрещено:** production код (scripts/, core/).
- **Модель:** Sonnet 4.6 (Agent Mode).

---

## 2. LangGraph — внутренний граф состояния

НЕ внешний API. НЕ batch pipeline. Это **memory проекта** — персистентный граф, в который scribe пишет по команде orchestrator'а.

```python
# .cursor/state/dev_graph.py

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Annotated
import operator
import json
from datetime import datetime

class DevState(TypedDict):
    """Состояние разработки — персистентное между сессиями."""
    
    # Текущая фаза и задача
    phase: str                    # "0_poc" | "1_ingestion" | "2_extraction" | ...
    current_task: str             # Описание текущей задачи
    task_status: str              # planned | in_progress | review | done | blocked
    
    # Решения (append-only лог)
    decisions: Annotated[list, operator.add]
    # Каждое: {"id": "D-007", "date": "...", "title": "...", 
    #          "context": "...", "decision": "...", "alternatives_rejected": [...]}
    
    # Компоненты и их статус
    components: dict
    # {"ingestion": {"status": "done", "tests_pass": true, "last_updated": "..."},
    #  "extraction": {"status": "in_progress", "tests_pass": false},
    #  "bpmn": {"status": "planned"}}
    
    # Валидации
    validations: Annotated[list, operator.add]
    # {"date": "...", "type": "pytest", "result": "pass", "details": "..."}
    
    # Блокеры
    blockers: list
    # [{"description": "Нет доступа к BS для bootstrap", "since": "..."}]
    
    # Лог действий (последние N)
    action_log: Annotated[list, operator.add]

# Nodes — scribe вызывает эти функции
def log_decision(state, decision: dict):
    """Зафиксировать архитектурное решение."""
    decision["date"] = datetime.now().isoformat()
    return {"decisions": [decision]}

def update_component(state, component: str, status: str, tests_pass: bool):
    """Обновить статус компонента."""
    components = state["components"].copy()
    components[component] = {
        "status": status, 
        "tests_pass": tests_pass,
        "last_updated": datetime.now().isoformat()
    }
    return {"components": components}

def log_validation(state, validation: dict):
    """Записать результат валидации."""
    validation["date"] = datetime.now().isoformat()
    return {"validations": [validation]}

def log_action(state, action: str):
    """Записать действие в лог."""
    return {"action_log": [{"action": action, "date": datetime.now().isoformat()}]}

# Persistence: JSON файл, не внешний сервис
class JsonCheckpointer:
    """Сохраняет состояние в .cursor/state/dev_state.json"""
    STATE_FILE = ".cursor/state/dev_state.json"
    
    def save(self, state: DevState):
        with open(self.STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def load(self) -> DevState:
        try:
            with open(self.STATE_FILE) as f:
                return json.load(f)
        except FileNotFoundError:
            return self._initial_state()
    
    def _initial_state(self) -> DevState:
        return {
            "phase": "0_poc",
            "current_task": "",
            "task_status": "planned",
            "decisions": [],
            "components": {},
            "validations": [],
            "blockers": [],
            "action_log": []
        }
```

### Что scribe пишет в граф:
```
Orchestrator: "Решили использовать RapidOCR вместо EasyOCR"
  → Scribe: log_decision({
      "id": "D-012",
      "title": "OCR: RapidOCR",
      "context": "POC показал 94% vs 91% на кириллице",
      "decision": "RapidOCR через Docling RapidOcrOptions",
      "alternatives_rejected": ["EasyOCR — 91%", "Tesseract — забракован ранее"]
    })

Orchestrator: "Coder закончил ingestion, запусти валидацию"
  → Scribe: log_validation({
      "type": "pytest",
      "scope": "test_ingestion.py", 
      "result": "pass",
      "details": "12/12 tests, 0.3s"
    })
  → Scribe: update_component("ingestion", "done", tests_pass=True)

Orchestrator: "Переходим к Фазе 2"
  → Scribe: state["phase"] = "2_extraction"
  → Scribe: обновить CURRENT_STATE.md
```

### Зачем это нужно:
1. **Orchestrator не дрейфует** — перед планированием читает `dev_state.json` и `DECISIONS.md`, не переспрашивает "а что мы решили про OCR?"
2. **Новая сессия = полный контекст** — scribe поддерживает `CURRENT_STATE.md` актуальным, orchestrator читает его в начале сессии
3. **Аудит** — decisions append-only, видно кто когда что решил и почему

---

## 3. Governance — защита от дрейфа

### 3.1 Правила, которые нельзя обойти (00_global_always.mdc)

```
Даже orchestrator обязан:
- Прочитать DECISIONS.md перед предложением альтернативы существующему решению
- Прочитать CURRENT_STATE.md перед планированием
- Указать в плане: non-goals (что НЕ менять)
- Ограничить задачу одной подсистемой
- Запросить human approval на: новые зависимости, новые модули, изменение rules
```

### 3.2 Контракт задачи (паттерн из Helicomponents)

Orchestrator создаёт `.cursor/plans/TASK-NNN.md`:
```markdown
# TASK-042: Реализовать page_classifier.py

## Цель
Классификация страниц PDF: content / approval_sheet / appendix / cover

## Scope
- НОВЫЙ: scripts/ingestion/page_classifier.py
- ИЗМЕНИТЬ: scripts/ingestion/docling_adapter.py (вызов classifier перед OCR)
- ТЕСТЫ: tests/test_ingestion.py::test_page_classifier

## Non-goals
- НЕ менять OCR pipeline
- НЕ менять chunker
- НЕ менять authority_resolver

## Инварианты
- DoclingDocument output format не меняется
- Existing tests не ломаются

## Критерии успеха
- classifier accuracy >= 90% на 30 тестовых страницах
- approval_sheet pages исключены из extraction output
- pytest green

## Ownership
- scripts/ingestion/** → coder
- tests/ → coder
- docs/ → scribe (после приёмки)
```

### 3.3 Защита от orchestrator rot

```
Проблема: orchestrator со временем начинает:
  - забывать прошлые решения
  - предлагать то, что уже отклонили
  - расширять scope задачи
  - "помогать" coder'у кодить

Защита:

1. DECISIONS.md — append-only, orchestrator ОБЯЗАН прочитать перед планированием.
   Scribe проверяет: план не противоречит существующим решениям.

2. CURRENT_STATE.md — scribe обновляет после каждой задачи.
   Orchestrator ОБЯЗАН прочитать в начале сессии.

3. Максимум 3 итерации на задачу.
   После 3 неудач → human decision (переформулировать или отложить).

4. Scope lock: план фиксирует non-goals.
   Coder отклоняет запросы за пределами scope.
   Scribe проверяет что diff соответствует плану.

5. Rules immutable: .cursor/rules/*.mdc меняются ТОЛЬКО через:
   orchestrator предлагает → human утверждает → scribe фиксирует.
```

### 3.4 Ownership по путям (из Helicomponents)

```
Ingestion:  scripts/ingestion/** → coder
Extraction: scripts/extraction/**, core/** → coder
BPMN:       scripts/bpmn/**, scripts/business_studio/** → coder
RAG:        scripts/rag/** → coder
Tests:      tests/** → coder (код) + scribe (fixtures, reports)
Docs:       docs/** → scribe
State:      .cursor/state/** → scribe
Plans:      .cursor/plans/** → orchestrator
Rules:      .cursor/rules/** → human only
POC:        poc/** → coder
Gold:       tests/fixtures/gold/** → scribe
```

---

## 4. Workflow (типовой цикл)

```
1. Orchestrator читает CURRENT_STATE.md + DECISIONS.md
2. Orchestrator создаёт план .cursor/plans/TASK-NNN.md
3. Human утверждает план (или корректирует)
4. Coder реализует по плану
5. Coder сдаёт: diff + отчёт (что изменено, что проверить, риски)
6. Orchestrator ревьюит diff
7. Orchestrator командует scribe:
   - запустить валидации
   - обновить CURRENT_STATE.md
   - обновить changelog.md
   - записать решения в LangGraph state
8. Scribe проверяет: diff ⊆ scope плана, tests pass, docs consistent
9. Human мердж
```

---

## 5. Файловая структура

```
.cursor/
├── rules/                      # Governance (human-only changes)
│   ├── 00_global_always.mdc    # Safety + invariants + human-in-the-loop
│   ├── project.mdc             # Architecture краткий + стек
│   ├── 10_ingestion.mdc        # Docling, OCR, tables
│   ├── 20_extraction.mdc       # 13 типов, provenance, ProcessSpec
│   ├── 30_bpmn_and_bs.mdc      # BPMN compiler, BS GUID sync
│   ├── 40_rag.mdc              # Hybrid retrieval, authority bias
│   └── 50_quality.mdc          # Tests, metrics, Gold Standard
├── agents/
│   ├── orchestrator.md         # Plan Mode, Opus 4.6, NO coding
│   ├── coder.md                # Agent Mode, Sonnet 4.6, NO architecture
│   └── scribe.md               # Agent Mode, Sonnet 4.6, docs + state + validation
├── plans/                      # Task contracts (orchestrator creates)
│   └── TASK-001.md
└── state/                      # LangGraph dev state (scribe maintains)
    ├── dev_graph.py             # State schema + functions
    └── dev_state.json           # Persisted state

docs/
├── Architecture_v2.1.md        # Source of truth
├── DECISIONS.md                # Append-only decision log
├── CURRENT_STATE.md            # What's done, what's next
└── changelog.md                # Chronological log
```
