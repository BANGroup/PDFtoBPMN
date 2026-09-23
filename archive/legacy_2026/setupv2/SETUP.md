# PDFtoBPMN v2.1 — Инструкция развёртывания

> **АРХИВНАЯ КОПИЯ.** Содержимое этой папки развёрнуто в корень проекта (ветка `v2-graphrag`, коммит 18.03.2026). Актуальные файлы находятся в корне: `.cursor/`, `core/`, `scripts/`, `docs/`, `tests/`, `pyproject.toml`, `bootstrap.sh`. Эта папка сохранена как reference оригинального setup-пакета.

## Два шага: распаковать → запустить

### Шаг 1: Распаковать в папку проекта

```bash
# Если проект новый:
mkdir PDFtoBPMN && cd PDFtoBPMN && git init

# Если проект существует (https://github.com/BANGroup/PDFtoBPMN):
cd PDFtoBPMN

# Распаковать архив (перезаписать существующие файлы):
unzip pdftobpmn_v2.1_setup.zip -o
# или если tar.gz:
tar xzf pdftobpmn_v2.1_setup.tar.gz
```

### Шаг 2: Запустить bootstrap

```bash
bash bootstrap.sh
```

Bootstrap делает:
1. Создаёт ветку `v2-graphrag`
2. `pip install langgraph langchain-core pydantic pyyaml`
3. `chmod +x .cursor/hooks/*.py`
4. Инициализирует `dev_state.sqlite` (LangGraph)
5. Запускает `pytest tests/test_dev_graph.py`

Всё. Теперь открыть Cursor AI и набрать `/start`.

---

## Что внутри архива

### Фаза 1: Мультиагент (работает сразу после bootstrap)

```
.cursor/
├── rules/                          # Governance (human-only zone)
│   ├── 00_global_always.mdc        # Safety, ownership, HITL
│   ├── project.mdc                 # Architecture summary
│   ├── 10_ingestion.mdc            # Docling, OCR, tables
│   ├── 20_extraction.mdc           # 13 types, typed extraction
│   ├── 30_bpmn_and_bs.mdc          # BPMN, GUID, BS sync
│   ├── 40_rag.mdc                  # Retrieval, authority
│   └── 50_quality.mdc              # Tests, metrics
│
├── agents/                         # 4 агента
│   ├── orchestrator.md             # Opus 4.6, 0.2 — plan, review, dispatch
│   ├── coder.md                    # Auto/Composer 1.5, 0.4 — code per plan
│   ├── validator.md                # Composer 1.5, 0.0 — gates (pre+post)
│   └── scribe.md                   # Composer 1.5, 0.0 — docs + state
│
├── hooks/                          # Enforcement (блокировка без handoff)
│   ├── hooks.json                  # 4 hook events
│   ├── check_handoff.py            # beforeSubmitPrompt — нет handoff → block
│   ├── block_orchestrator_code.py  # beforeShellExecution — python/pytest → block
│   ├── check_ownership.py          # afterFileEdit — вне зоны → block
│   └── record_stop.py              # stop — лог + warn если H5 missing
│
├── state/                          # LangGraph (local SQLite)
│   ├── dev_graph.py                # Project memory: decisions, handoffs, components
│   └── batch_graph.py              # Batch pipeline (Phase 4)
│
├── commands/
│   └── start.md                    # /start — первая команда orchestrator'у
│
└── plans/                          # Orchestrator создаёт TASK-NNN.md здесь
```

### Фаза 2: Архитектура (скелет для начала разработки)

```
docs/
├── Architecture_v2.1.md            # Source of truth (1060 строк)
├── Agent_Architecture.md           # 4 agents + hooks + LangGraph
├── Handoff_Protocol.md             # H1-H9 + enforcement
├── DECISIONS.md                    # 10 решений (append-only)
├── CURRENT_STATE.md                # Текущее состояние
├── changelog.md                    # История изменений
├── Gold_Standard_Methodology.md    # Методология оценки
└── Testing_and_Metrics.md          # Метрики качества

core/                               # Types и protocols (готовы к реализации)
├── __init__.py
├── knowledge_types.py              # 13 KnowledgeType + Provenance
├── edge_types.py                   # 18 EdgeType (RACI, sequence, decision...)
└── stores.py                       # GraphStore + VectorStore Protocol

scripts/                            # Пустые папки — coder заполняет по планам
├── ingestion/
├── extraction/rule_based/
├── extraction/llm_based/
├── graph/
├── rag/
├── views/
├── business_studio/
└── gold/

tests/
├── test_dev_graph.py               # LangGraph state tests (6 тестов)
└── fixtures/gold/                  # Gold Standard документы (TBD)

poc/                                # POC скрипты (Phase 0)
input/                              # PDF/DOCX документы (не в git)
output/                             # Результаты (не в git)

pyproject.toml                      # langgraph + все зависимости
bootstrap.sh                        # Одноразовый setup
.gitignore
```

---

## Как работать после bootstrap

### Цикл задачи

```
1. Human: описать задачу orchestrator'у
2. Orchestrator: прочитать state → создать план TASK-NNN
3. Validator (pre-gate): план vs DECISIONS? scope? ownership?
4. Orchestrator → Coder: dispatch с планом
5. Coder: реализовать строго по плану
6. Validator (post-gate): pytest? scope? docs?
7. Orchestrator → Scribe: записать результат
8. Orchestrator → Human: доклад + git commit cmd
9. Human: git commit -m "TASK-NNN: description"
```

### Модели и температуры

| Агент | Модель | Temp | Cursor Mode |
|-------|--------|------|-------------|
| Orchestrator | claude-opus-4-6 | 0.2 | Plan Mode |
| Coder | Auto (Composer 1.5) | 0.4 | Agent Mode |
| Validator | Composer 1.5 | 0.0 | Agent Mode |
| Scribe | Composer 1.5 | 0.0 | Agent Mode |

### Git model

```
Ветка: v2-graphrag
1 задача = 1 коммит
Human коммитит после доклада H9
Merge в main: по phase governance gate
```

---

## Фазы разработки (из Architecture_v2.1.md)

```
Фаза 0 (1 нед):   POC + Gold Standard (7 POC параллельно)
Фаза 1 (2-3 нед):  Core + Ingestion + Authority
Фаза 2 (3-4 нед):  Extraction + Graph population
Фаза 3 (4-5 нед):  RAG + Views (unified)
Фаза 4 (3-4 нед):  BS sync + Batch 410 docs
Фаза 5 (отложена): Enrichment + API + UI

Итого: ~17 недель
```
