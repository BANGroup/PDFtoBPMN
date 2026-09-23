# Текущее состояние

## Фаза: 0_setup (мультиагент + архитектура)
## Задача: донастройка мультиагента и MCP
## Статус: completed
## Ветка: v2-graphrag

### Компоненты
- ✅ **cursor_rules**: 7 .mdc файлов (v1 удалены, v2 синхронизированы с DECISIONS)
- ⚠ **cursor_hooks**: hooks.json.disabled (D-036 — несовместимы с Task-sub-agents; скрипты сохранены как dormant)
- ✅ **cursor_agents**: 5 агентов (orchestrator, coder, validator, scribe, extractor) — обновлены: checkpoint, fast-track, out-of-scope, validator 3 режима (D-019)
- 🗄 **langgraph_state** (архивировано, TASK-019 P2): dev_graph + batch_graph — pip install OK, 6/6 тестов pass. `dev_graph.py`, `dev_state.sqlite`, `bootstrap.sh`, `tests/test_dev_graph.py` → `archive/legacy_2026/state_langgraph/`; `batch_graph.py` оставлен (заготовка пакетного конвейера); зависимость `langgraph` в `pyproject.toml` не тронута
- ✅ **lite KG (журнал действий агентов)**: `.cursor/kg/events.jsonl` (только дописывание) + CLI `.cursor/state/kg.py` (`add` / `query` / `export changelog|state` / `import-docs`); `tests/test_kg.py` — 7 тестов (TASK-019 P2)
- ✅ **docs**: Architecture_v2.1, DECISIONS (D-001..D-019), Handoff Protocol (обновлён: iteration, checkpoint, fast-track, validation_mode) — готовы
- ✅ **core_types**: KnowledgeType (13), EdgeType (19), GraphStore/VectorStore Protocol — импорт OK
- ✅ **docling**: v2.80.0 — парсит PDF, таблицы, структуру
- ✅ **easyocr**: v1.7.2 — OCR winner (D-012), lang=["ru","en"], GPU
- ✅ **mcp_domino**: два MCP-сервера Domino KEEP — db01 (ЭСЗ, СУБП) + db02 (БНД dflib, 1380 документов, 247 уникальных номеров)
- ✅ **mcp_superset**: Superset API (bi.utair.io)
- ✅ **mcp_jira**: Jira Server (jira.utair.ru)
- ✅ **mcp_singularity**: Singularity App
- ✅ **bnd_sync**: ночная сборка корпуса БНД (cron 01:00, `scripts/ingestion/bnd_sync/`, логи `data/bnd_sync/logs/`); отчёт — бот ДВК (Mattermost DM, 3 получателя: budnik_an, lavrova_tv, bachurina_iv)

### Сделано
- Bootstrap v2.1 выполнен (ветка v2-graphrag, 2 коммита)
- SqliteSaver API исправлен (langgraph v1.1+ совместимость)
- dev_state.sqlite инициализирован (phase: 0_setup) — архивирован в `archive/legacy_2026/state_langgraph/` (TASK-019 P2)
- setupv2/ сохранён как архивная копия
- TASK-001 валидация: 11/11 проверок PASS
- TASK-002 POC OCR: EasyOCR победитель (D-012), RapidOCR отклонён (18-31% на русском)
  - docling 2.80.0 + easyocr 1.7.2 + rapidocr 3.7.0 + onnxruntime 1.23.2 установлены
  - 2 PDF протестированы, 5 сценариев x 2 OCR = 10 прогонов
  - Артефакты: poc/poc_ocr_comparison.py, poc/ocr_comparison_report.json
- TASK-003 POC Graph Population: NetworkXGraphStore реализован, все критерии PASS
  - NetworkXGraphStore: 10 методов (add_artifact, add_relation, query_process, query_raci, query_kpi, query_controls, query_for_rag, query_neighbors, save, load)
  - Fixture: 17 артефактов (5 Role, 8 ProcessStep, 2 DecisionRule, 2 InputOutput), 31 relation
  - query_process: 5 ролей, 8 шагов, 2 решения, 9 потоков — структура пригодна для BPMN compiler
  - query_raci: 90% совпадение с существующим КД-РГ-039-05_RACI.md (порог 80% — PASS)
  - Round-trip save/load: JSON 17.6KB, без потерь — PASS
  - Артефакты: poc/poc_graph_population.py, poc/fixtures/kd_rg_039_05_artifacts.json, poc/graph_КД-РГ-039-05.json
- TASK-004 POC Document Authority: парсер кодов + реестр семейств + conflict detection
  - DocumentCodeParser: 10 паттернов, 323/323 = 100% распознавание кодов
  - DocumentRegistry: 329 семейств, 369 документов, 11 типов (ДП, РГ, ИОТ, РД, СТ, РИ, РК, СТО, ПР, TPM, unknown)
  - Authority resolver: canonical/superseded/draft, 1 мультиверсионное семейство (РИ-М1.005)
  - Conflict detection: 9 дубликатов между output/[код]/ и ocr_full_run/
  - Артефакты: poc/poc_document_authority.py, poc/document_registry.json
- TASK-005 POC Page Classifier: rule-based классификатор страниц PDF
  - 4 типа: cover, content, appendix, approval_sheet
  - Тестирование на 5 реальных PDF (397 страниц): cover 10 (2.5%), content 344 (86.6%), appendix 40 (10.1%), approval_sheet 3 (0.8%)
  - Эвристики: ключевые слова, позиция страницы, плотность текста, OCR-паттерны
  - Артефакт: poc/poc_page_classifier.py
- TASK-006 POC Qwen VLM: описание графики из PDF через Qwen2-VL-2B
  - GPU: RTX 5080, модель Qwen2-VL-2B-Instruct (4.2GB VRAM)
  - 3 PDF, 15 страниц с графикой, 30 промптов (общий + BPMN)
  - Среднее время inference: 14.4с/промпт, загрузка модели: 6.3с
  - Качество 2B модели: извлекает текст с титульных страниц, но слаба на реальных схемах (галлюцинации, зацикливание)
  - Вывод: для production нужна 7B модель; 2B — только для быстрых проверок
  - Артефакт: poc/poc_qwen_graphics.py

- TASK-007 OCR/VLM Benchmark: 7 моделей протестированы на 18 страницах из 4 PDF (D-018)
  - DeepSeek-OCR v1 — лидер (baseline, 100%)
  - GLM-OCR — лучший баланс скорость/качество (63.2%, 10.6с/стр, 2.1GB VRAM)
  - DeepSeek-OCR v2 — хуже v1 на наших документах (51.3%, зацикливание генерации — known issue)
  - GOT-OCR2 — экономичный (51.1%, 1GB VRAM), но плохо с кириллицей
  - PaddleOCR-VL-1.5 — аномально медленный (189.7с/стр)
  - SmolDocling-256M — слишком маленький (31.7%)
  - EasyOCR (Docling) — обрабатывает целый PDF, прямое сравнение невозможно
  - Инфраструктура: 3 venv (DeepSeek-OCR/venv, venv, ocr_bench_venv)
  - Артефакты: poc/benchmark_results/ (7 JSON + summary.json), poc/bench_*.py (9 скриптов)

### Донастройка мультиагента (29.03.2026)
- Handoff Protocol обновлён: IterationCount в H4/H5/H9, checkpoint перед retry, fast-track цикл, validation_mode в H2/H5
- Validator: 3 режима (pre, code, bpmn) — BPMN review готов к Фазе 3B
- Все 5 agents: добавлена секция "Зона другого агента" (перекрёстные ссылки)
- Orchestrator: checkpoint перед retry, fast-track правила
- 00_global_always.mdc: расширена секция "Разрешено без согласования" (auto-approved class)
- Исправлены опечатки dev_state.json → dev_state.sqlite в orchestrator.md и scribe.md

### Донастройка MCP (29.03.2026)
- Добавлен MCP-сервер `domino-keep-bnd` (domino-db02.utair.ru:8880) — База Нормативных Документов
- БНД (dflib.nsf): 97 views, 1380 записей, 247 уникальных номеров документов
- Типы НД: КД (136), ДП (32), РГ (22), РД (19), РИ (12), СТ (11), ДВС (5), ИОТ (3)
- View `(DocumentByNumberForAll)` — действующие документы, поля: DocNum, DocDate, DocDateActual, DocSubject, @unid
- Старый `domino-keep` (db01) — ЭСЗ (dfesz24-26), Контроль, СУБП — без изменений

### Разведка структуры БНД (29.03.2026, D-020)
- **Три типа вложений**: PDF-образы (`v_ImagesForDocRead`), Word-проекты (`v_ImagesForDoc`), ссылки ImageLink (РПП, РОНО)
- **PDF-образы**: ~18 254 записей, Form: Image, привязаны через ParentUIN, содержат $FILES с PDF
- **Word-проекты**: ~1928 действующих (.doc/.docx), фильтр `$13 == "Действующий"`, 135 НД с Word + PDF
- **Составные документы** — множество карточек (основная + N изменений):
  - КД-РД-В3.049-01 «РОНО»: 73 карточки, 8 частей по типам ВС, 216 PDF + 317 Word
  - ПР-073-15 «Учетная политика»: 15 карточек, 6+ частей, 16 PDF-эталонов + 28 PDF изменений + 24 Word
- **Эталоны** — актуальные полные версии частей в основной карточке (имя содержит "Эталон №N для ознакомления")
- **Стратегия**: эталоны из основной карточки → Word (Действующий) → Docling; ImageLink — отложено
- **ImageLink** (Form: ImageLink): для составных документов (РПП), поле Link = rich text, требует дополнительного исследования

### Следующее
- Фаза 0 POC завершена. Следующий шаг: планирование Фазы 1 (production pipeline).
- OCR стратегия определена (D-018): DeepSeek-OCR v1 primary, GLM-OCR fast fallback.
- Ансамбль OCR моделей — Фаза 2.
- Qwen-7B VLM тестирование — на машине с RTX 5090 (дома).
- Интеграция с БНД (dflib) через MCP — синхронизация реестра документов с Lotus Notes.
- **БНД ingestion pipeline**: скачивание эталонов PDF + действующих Word из dflib → Docling parsing → graph population.
- **ImageLink исследование**: уточнить с админом доступ к РПП и другим документам с Form: ImageLink.
- Отложено: POC 2 (LightRAG, нет API) → Фаза 3, POC 5 (BS) → Фаза 4
- **TASK-008 cup_dashboard**: Фаза 1 (split xlsm) — ✅ done (PASS retry 3/3, артефакты в output/january_split/). Фаза 2 (self-contained HTML) — ⛔ superseded by TASK-009 (D-024).
- **TASK-009 cup_dashboard live**: ✅ **ЗАКРЫТА** (Phases A+B+C+D+E завершены). Дашборд готов к деплою на `/info/tsup/`. Известные GAP'ы: `rz_causes_2019` отложен (D-026), `rz_causes_*.year = NULL` (нет маппинга из источника), `pps_column1_unknown` (анонимная колонка), `avg_load_factor` 2026 = NULL (не заполнено в источнике).
- **cup_dashboard (todo repo)**: деплой на `/info/tsup/` — следующий шаг после merge-ready (артефакты: `cup_dashboard/{etl,core,static,deploy}/*`, см. DEPLOY.md).

### Подпроекты (вне core PDFtoBPMN pipeline)
| Подпроект | Репо | Статус | Описание |
|-----------|------|--------|----------|
| `cup_dashboard/` | Obligations | ✅ done (TASK-009 Phase A–E) | ETL-слой и design reference. 533 344 строк в `cup.flights`. SOT: `cup_dashboard/etl/data_inventory.md`. Решения: D-021, D-022, D-024, D-025, D-026, D-027, D-028. |
| `todo/cup_dashboard` | todo (cross-repo) | ready to deploy | Live-дашборд: FastAPI + ECharts SPA + Docker. Публикация: /info/tsup/. Паттерн: sfv_dashboard. Ref: TASK-009. D-023 (cross-repo policy). `info.html`: добавлена секция "Производство" с карточкой. |

### Связанные репо
| Репо | Путь | Роль |
|------|------|------|
| Obligations (этот) | `/home/budnik_an/Obligations/` | Основной — pipeline, ETL, docs, rules |
| todo | `/home/budnik_an/todo/` | Cross-repo dependency: публикация дашбордов (sfv_dashboard, cup_dashboard). D-023 регулирует взаимодействие. |

### TASK-012 (2026-05-14): Матчинг 732 ↔ ЦУП ↔ MER + дельта-CSV для Меридиана
**Цель:** Построить сквозной маппинг MER-кодификатора ЮТэйр на IATA-732 через промежуточный IATA-730, добавить UI-бейджи в дерево таксономии и сформировать CSV с операциями для апгрейда справочника Меридиана.

**Результат:** Реализованы Phases P0–P5 + iter-3 (ATFM-override). Артефакты опубликованы в `/info/iata732/`.

**Ключевые цифры (iter-3):**
- Маппинг 732: 4493 узла, из них 484 full match / 4009 partial / 0 gap.
- MER: 90 записей, 9 override (сдвиг Excel r72–r80), 2 internal_utair (82.1 «Ковёр», 83.1 «правительственные»).
- Дельта-CSV: 493 строки — ADD=3, REMAP=484, DEPRECATE=6.
  *(iter-3: REMAP +3, DEPRECATE −3 — ATFM-коды AT/AX/AE/AW/AM/AS перепривязаны через IATA730_ATFM_TO_732 вместо code2_index)*

**ATFM-override (D-034):**
- Коды AT/AX/AE/AW/AM/AS → явный словарь `IATA730_ATFM_TO_732` → IATA-732 G7/Z/* (stakeholders O/P/Q/S).
- `code2_index` применяется только как fallback для остальных кодов.

**Уточнение внутренних кодов ЮТэйр (D-035):**
- **82.1 «режим Ковёр»**: угроза дронов + военные риски → IATA-732 `G7/Z/P · military activity` (stakeholder T); alt: `G7/Z/R · additional security event` (stakeholder S).
- **83.1**: правительственные ограничения (VIP-борт) → IATA-732 `G7/Z/I · special flights/VIP` (stakeholder O).

**Ключевые артефакты:**
- `webBI/iata732/static/matching.json` — полный маппинг 732/ЦУП/MER (2.5 MB minified).
- `webBI/iata732/static/meridian_upgrade_v1.csv` — дельта-операции для импорта в Меридиан.
- `output/cup_codifier/build_matching_json.py` — ATFM-словарь + изменён порядок проверок в `enrich_mer_entries`.
- Кнопка «⤓ CSV для апгрейда Меридиана» в шапке `/info/iata732/`.

**Открытые риски:**
- ⚠ 6 IATA-730 кодов (orphan) не имеют пары в черновике IATA-732 → DEPRECATE в CSV.
- ⚠ 83.1 «правительственные ограничения» (VIP) имеет 2 кандидата (CXM / CXR) — финальный выбор за разработчиком Меридиана.

**Решения:** D-032 (override-таблица Excel), D-033 (формат дельта-CSV), D-034 (ATFM-приоритет), D-035 (семантика 82.1/83.1).

**Update 2026-05-14:** matching.json теперь служит SSOT для overlay вкладки «Структура» (см. D-037).

### TASK-013 (2026-05-14) — синхронизация overlay со SSOT
- `cup_overlay.json` теперь строится из `matching.json` (D-037).
- Coverage: 34/56 (60.7%) → 37/56 (66.1%).
- Финальный GAP-list (19 узлов uncovered, честные пробелы по Rule 0):
  - `G:G4`
  - Процессы: `P:G1/B`, `P:G2/H`, `P:G3/I`, `P:G3/J`, `P:G3/K`, `P:G3/L`,
    `P:G4/N`, `P:G4/O`, `P:G5/Q`, `P:G5/S`, `P:G5/U`, `P:G6/V`, `P:G7/X`, `P:G7/Y`.
  - Stakeholders: `S:M` (airline operator/handler), `S:R` (catering/cabin),
    `S:Z` (structural catch-all — not attributable).
  - Sub-airline: `U:D` (нет такого разряда у ЮТэйр).
- Эти узлы остаются uncovered, потому что в ЦУП-кодификаторе для них нет ни
  прямого ЦУП-кода, ни через MER expert-маппинг (Rule 0: не выдумываем связки).

**Мелкие правки в цикле TASK-013:**
- Убран «(2028)» из заголовка Sankey, версий JSON и карточки IATA-732 в `info.html`.
- Service Worker кэш бамп: `portal-v1 → portal-v2` (инвалидация браузерного кэша после правки info.html).
- Почищены устаревшие комментарии «(2028)», «FUTURE STANDARD» в коде и CSS.
- `hooks.json` → `hooks.json.disabled` (D-036).

### TASK-014 (2026-05-15) — AMOS-layer mapping (paper analysis)

Цель: закрыть разрыв между IATA-732 («кто/этап») и фактической технической
причиной задержки («какая система ВС отказала») через семантический маппинг
174 строк зоны 2 кодификатора ЦУП на AMOS APN/таблицы/ATA chapters — без
подключения к боевой БД AMOS.

**Источники анализа** (статика):
- `webBI/amos-help/index.html` — TOC из 457 APN (TC EN+RU);
- `webBI/amos-db-explorer.html` — 324 Oracle-модуля AMOS;
- `webBI/amos-apn-analytics.md` — 25 used APN (для force-include).

**Артефакты:**
- `scripts/build_amos_apn_catalog.py` → `output/amos_layer/amos_apn_catalog.json` (90 релевантных APN из 457).
- `scripts/build_cup_zone2_to_amos.py` → `output/amos_layer/cup_zone2_to_amos.{json,csv}` (175 строк зоны 2: 68 ata_amos / 48 iata732_process / 19 iata732_stakeholder / 29 out_of_scope / 10 section_header / 1 empty; 26 ATA chapters).
- `scripts/build_mer_amos_sources.py` → `output/amos_layer/mer_amos_sources.{json,csv}` (80 MER: 9 AMOS-relevant + 71 not-AMOS с reason).
- `docs/reports/cup_zone2_amos_mapping_v1.md` — итоговый отчёт.

**Aircraft-centric chain** (D-038): обращение к AMOS всегда идёт от ВС
(хвостовой номер) и **обратно** к причине отказа — 6 фиксированных шагов:
`aircraft (APN 0308) → workorder (APN 1418) → ata_chapter (spec2k) →
defect_cause (APN 0354) → mel_or_close (APN 0273, опц.) → reliability
aggregation (APN 0399, опц.)`.

**9 AMOS-relevant MER:** 41 НМЧ (TD), 42 НМЧ (TM), 44 НМЧ (TS), 45 СБОЙ (TA),
46 НМЧ (TC), 47 СБОЙ (TL), 48 ПРЧ (TV), 51 ПВС (DF), 52 ПВС (DG). Остальные
71 — handling/pax/cargo/crew/weather/ATFM/security/документы — описаны IATA-732
без помощи AMOS.

**Анти-цели соблюдены:** физических подключений к AMOS нет, все `_table_hint`
и `_field_hint` помечены как hint.

### TASK-015 (2026-05-15) — публикация AMOS-слоя в дашборд + актуализация

Цель: вывести результаты TASK-014 в живой дашборд `/info/iata732/` отдельной
вкладкой и встроить has_amos_source в tooltip Sankey overlay.

**Data merge (Obligations):**
- `build_matching_json.py` v1.0 → v1.1: новое поле `amos_layer` в `by_mer_code`
  (relevant, primary_apn, primary_table, primary_field, chain_steps_used,
  not_amos_reason); поле `has_amos_source` в `by_iata732_node`
  (57/4 493 узлов IATA-732).
- `build_cup_overlay_json.py`: новые поля `has_amos_source` (16/56 overlay-узлов
  Sankey) и `ata_distribution` (агрегация строк зоны 2 ЦУП по ATA chapter
  для covered узлов).
- `scripts/build_iata732_data_package_v2.py` — новый скрипт-перепаковщик:
  собирает zip-пакет v2 (233 KB) из 14 файлов: 7 базовых + 5 AMOS + отчёт +
  README v2.
- `output/iata732/iata732_data_package_v2_README.md` — README v2 (8.6 KB):
  что нового, что в архиве, ключевые цифры, таблица 9 AMOS-relevant MER.

**Frontend (todo/webBI):**
- `webBI/iata732/static/` синхронизирован: matching.json и cup_overlay.json
  пересобраны; 3 новых JSON (mer_amos_sources, cup_zone2_to_amos,
  amos_apn_catalog), 1 MD (cup_zone2_amos_mapping_v1.md), v2 zip + README,
  v1 zip + README удалены.
- `index.html`: 4-я вкладка `tab-amos` → `<section id="amos">` с
  KPI-блоком, Aircraft-centric chain (6 нод), таблицей 9 AMOS-relevant MER,
  деревом ATA chapters, блоком download-ссылок.
- `app.js`: 3 новых fetch (mer_amos_sources / cup_zone2_to_amos /
  amos_apn_catalog), глобал `AMOS = { merSources, zone2, catalog }`,
  функция `renderAmosLayer()` (KPI + chain + MER table + ATA tree),
  switchTab('amos'), tooltip Sankey для нод с `has_amos_source` (показывает
  APN 1418 Workorder + ATA distribution).
- `style.css` (+178 строк): `.amos-kpi-grid`, `.amos-chain*`,
  `.amos-mer-table`, `.amos-ata-tree`, responsive до 700px.

**Publish:**
- `webBI/info.html`: карточка IATA-732 обновлена («Таксономия задержек +
  AMOS-слой»), добавлена новая карточка в секции AMOS/SAP с прямой ссылкой
  на отчёт.
- `webBI/sw.js`: `portal-v2 → portal-v3` (инвалидация SW-кеша).

**Ключевые цифры:**
- 9 / 80 MER семантически в AMOS · 68 строк зоны 2 → AMOS · 26 ATA chapters
  покрыты · 57 узлов IATA-732 с `has_amos_source` · 16 overlay-узлов Sankey
  с AMOS-инфо в tooltip · 90 / 457 APN AMOS Guide релевантны.

**Анти-цели соблюдены:** существующие 3 вкладки (О стандарте/Структура/
Таксономия) не тронуты кроме одной строки в tooltip Sankey; никаких новых
зависимостей (ECharts уже подключён); физического подключения к AMOS нет.

**Решения:** D-038 (Aircraft-centric AMOS chain — стандартный lookup-pattern).

### TASK-016 (2026-05-18) — Copilot Readiness дашборды для оперативной смены ЦУП

**Цель:** привести два существующих дашборда ЦУП и один новый мокап к честной картине Rule 0 после кросс-чека двух независимых субагентов (Opus 4.7 / GPT-5.5), которые подтвердили: счёт источников B-петли «27 = 16+8+3» был неверен, критпуть нужно расширить с GAP-03+GAP-10 до +GAP-08, и нужен оперативный shift board, а не одна карточка.

**План:** `.cursor/plans/TASK-016_copilot_readiness_dashboards.md` — три шага, последовательно.

**Результат:**

**Шаг 1 — `docs/dashboards/tsup_as_is_dashboard.html`** (+197/-33 строк, 1 файл):
- Вкладка `5. AI Readiness & Roadmap` → `5. Copilot Readiness — B-петля`.
- Блок «Сильные / Узкие места» заменён на «Срез B-петли — 19 / 27 источников» с двумя цифрами одновременно (строгий §6 каталога: 14g/4y/1r + 3 org-входа · расширенный §1–§4: 18g/8y/1r).
- Каждый source-ID — цветовой бейдж (зелёный/жёлтый/красный по `data_sources_catalog_TsUP.md`).
- Явные плашки: «убрано из B-петли как A-петля» (SYS-LOTUS, VOICE-RADIO, MAN-LOG-SHIFT, DOC-ACT-DELAY, DOC-ERP-CARDS) и «возвращено в green» (FEED-SITA, DOC-KYFO-LOG).
- Новый блок «GAP-карта Severity×Effort» — 3×3 grid с drill-down (клик по пилюле скроллит к карточке GAP с подсветкой).
- Критпуть расширен до GAP-03 + GAP-10 + **GAP-08** (визуально обведён красной рамкой).
- GAP-05 переразмечен как Phase 0 quick win (зелёная левая граница, отдельной плашкой).
- GAP-08 переразмечен как критпуть (красная левая граница).
- Дорожная карта пересобрана: Phase 0 = GAP-05; Phase 1 = критпуть PoC + параллельно GAP-04/07; Phase 2/3/4 уточнены.
- Добавлены ссылки на `Operational_Regularity_AS-IS.bpmn`, `cup_zone2_amos_mapping_v1.md`, `matching.json`.

**Шаг 2 — cross-repo `todo/webBI/cup-tsup/`** (+177 строк, 3 файла, D-023):
- KPI-плитка `trace-kpi` в самом верху вкладки «Сводка»: `0 / 533 344 = 0%` с пометкой `⚠ GAP-03`, пояснением Rule 0, ссылкой `подробнее →` на якорь `#gap03` в AS-IS дашборде.
- Codifier-блок под графиком «Топ-15 причин задержек»: 4 строки маппинга `ЦУП → IATA-732 / MER / AMOS` + явная пометка `⊘ n/a` для категорий без прямого соответствия (ППС М/У, ППС ПОО). Ссылки на `/info/iata732/` и AMOS-отчёт.
- SW cache bump: `portal-v3 → portal-v4` (инвалидация браузерных кэшей после деплоя).

**Шаг 3 — `docs/dashboards/b2_shift_board_mockup.html`** (новый файл, 491 строка):
- Standalone HTML без сервера, тёмная тема в стилистике `tsup_as_is_dashboard.html`.
- Главный экран — **Очередь смены** (Shift Board): 7 фиктивных активных отклонений с SLA-таймерами, severity, GAP-флагами. Клик по строке → drill-down в карточку.
- **Карточка рейса B2** — 5 панелей (Состояние ВС / Экипаж / Пассажиры и коммерция / Внешний контур / Журнал решений). По умолчанию открыт UT-1805 как самый срочный.
- Панель «Журнал решений B2» — **пустая форма с явной пометкой ⚠ GAP-03**, демонстрирует, чего сегодня нет в системах. Все поля как `⊘ n/a — поле существует в дизайне, но не пишется`.
- **Freshness-панель сбоку** — материализация GAP-10: timestamps по 7 системам, плашка `⚠ DESYNC обнаружен` с конкретным расхождением «продано/чек-ин/borda = 168/142/165».
- Контекст смены с явными отметками GAP-05 (бумажный журнал) и GAP-01 (голос не фиксируется).
- Блок «Что мог бы добавить co-pilot» — три фазы (0/1/2) с конкретными возможностями.
- Sticky-баннер сверху и footer Rule 0 disclaimer: «MOCKUP — все данные фиктивные».

**Кросс-чек и расхождения с первичной аналитикой (зафиксировано в плане TASK-016):**
- Счёт 27 (16/8/3) был неверен — оба агента независимо получили 19 строгих ID + 3 org-входа (§6) или 27 расширенно (§1–§4) с разбивкой 18g/8y/1r.
- Я (orchestrator) ошибочно включил A-петельные источники в B-петлю — исправлено в Шаге 1.
- Карточка рейса B2 как первый экран — недостаточный артефакт; Shift Board первичен (Opus 4.7 / GPT-5.5 согласны) — реализовано в Шаге 3.
- GAP-08 добавлен в критпуть (был GAP-03+GAP-10, стал +GAP-08).
- AMOS-слой и IATA-732 кодификатор встроены как provenance, не как новые выводы (Шаг 2).

**Предварительные решения (требуют human-подтверждения для перевода в постоянные D-039+):**
- **D-39 (предв.):** счёт источников B-петли — две цифры одновременно (строгий §6 / расширенный §1–§4). Это правильное представление по Rule 0 — единый KPI «X% green» маскирует разрыв.
- **D-40 (предв.):** `decision_traceability` как постфактум-метрика на live cup_dashboard — UI-плэйсхолдер до закрытия GAP-03, без правки SQL-схемы.

**Open questions для human:**
- Q1 — двигаем ли D-39/D-40 в постоянные?
- Q2 — мокап шага 3 показывать НС ЦУП на ближайшей встрече или ждать переработки по фидбеку?

**Шаг 4 (само-ревью 2026-05-18) — Utair brand + деплой в портал todo:**
- Самопроверка выявила 4 проблемы: битая ссылка `../../input2/...` (Nextcloud-symlink), GitHub-стиль вместо корпоративного, AS-IS дашборд недоступен на портале, ссылка GAP-03 из cup-tsup — статичный текст-плейсхолдер.
- В обоих файлах `docs/dashboards/*.html` применён корпоративный Utair brand: палитра (`--utair-blue/red/yellow/green/orange/grey`), шрифт Suisse Intl (через `@font-face` из локальной копии в `docs/dashboards/assets/SuisseIntl-Regular.otf`), синяя sticky-шапка с белым логотипом `utair_sign_white`, опциональный переключатель тёмной темы. Mermaid перерисовывается под выбранную тему.
- Битая ссылка `ANALYSIS_AS-IS_RCA_и_Сбойные.md` (Nextcloud-черновик 70KB) убрана из кликабельных артефактов, заменена на некликабельный блок с пометкой «внешний · хранится в Nextcloud команды, не публикуется на портал». То же для `matching.json` 4.4MB — пометка «локально». Rule 0 соблюдён (показано откуда), пользователь не получает 404.
- Полный деплой в портал (cross-repo `todo/`):
  - `todo/webBI/tsup-as-is/index.html` + `static/` (копии `data_sources_catalog_TsUP.md`, `knowledge_gaps_TsUP.md`, `ontology_TsUP.yaml`, `cup_zone2_amos_mapping_v1.md`, 3 BPMN) — все относительные пути переписаны на `static/...`, шрифт и логотип через общий `/SuisseIntl-Regular.otf` и `/sign_white.png`. Добавлены portal-nav header и хлебные крошки.
  - `todo/webBI/tsup-b2-mockup/index.html` — то же; кросс-ссылки на md ведут в `/info/tsup-as-is/static/`, ссылка на AS-IS — на `/info/tsup-as-is/`.
  - `todo/backend/app.py`: роуты `/info/tsup-as-is/` и `/info/tsup-b2-mockup/` + StaticFiles mount по образцу `IATA-732`.
  - `todo/webBI/info.html`: две карточки в разделе «Производство» (иконки 🧩 для методологии, 📋 для мокапа).
  - `todo/webBI/cup-tsup/index.html`: ссылка GAP-03 теперь кликабельная `<a href="/info/tsup-as-is/#gap03">` с hover-стилем. Соответствующий CSS обновлён в `cup-tsup/static/style.css` (синий цвет, dashed→solid border на hover).
  - `todo/webBI/sw.js`: `portal-v5 → portal-v6`.
- Все 9 затронутых файлов прошли ReadLints без ошибок. Балансы `<div>` тэгов проверены (open=close=298 для AS-IS, 193 для B2). Каждая ссылка `static/...` и `/info/tsup-as-is/static/...` проверена на существование файла.

**Файлы (не закоммичены, ожидают review human):**
- Obligations:
  - `.cursor/plans/TASK-016_copilot_readiness_dashboards.md` (новый)
  - `docs/dashboards/tsup_as_is_dashboard.html` (+197/-33 шаг 1, +brand шаг 4)
  - `docs/dashboards/b2_shift_board_mockup.html` (новый шаг 3, +brand шаг 4)
  - `docs/dashboards/assets/` (новая папка: `SuisseIntl-Regular.otf`, `sign_white.png`, `utair_sign_blue_rgb.png`)
- todo (портал, cross-repo):
  - `webBI/tsup-as-is/` (новая папка, 5 файлов · index.html + 4 docs)
  - `webBI/tsup-as-is/static/bpmn/` (3 BPMN-файла)
  - `webBI/tsup-b2-mockup/` (новая папка, index.html)
  - `backend/app.py` (+60 строк, 2 новых роута)
  - `webBI/info.html` (+2 карточки)
  - `webBI/cup-tsup/index.html` (ссылка GAP-03 → href)
  - `webBI/cup-tsup/static/style.css` (hover для `.trace-kpi-note-tag`)
  - `webBI/sw.js` (`portal-v5 → portal-v6`)

### TASK-017 (23.09.2026) — перенос ночной сборки корпуса БНД из todo в Obligations

**Цель:** сборка корпуса, прогоны и отчёт (изначально Telegram, с 23.09.2026 — бот ДВК в Mattermost) переехали из todo в Obligations; ошибки зеркала исправлены; портал todo продолжает получать каталоги без перерыва.

**Результат:** Все фазы P0–P4 выполнены. Переключение cron прошло в окне между прогонами 23.09.2026.

**Состояние на 23.09.2026 10:10:**
- БНД: 358 документов, РПП: 476 записей.
- Зеркало: 6 751 файл / 8,9 ГБ в manifest (9,4 ГБ на диске; было 25 ГБ).
- Карантин `data/bnd_sync/quarantine/20260923/` — 7 048 файлов (~16 ГБ): дубли, старые версии, папки после смены даты изменения/переклассификации, два `*.bloated` по 2,4 ГБ.
  - ⚠ В карантине — единственные копии вложений 16 временных изменений РПП (TR MEL), которые Domino сейчас отдаёт без вложения.
  - Удаление карантина — **не раньше 30.09.2026, только по команде human**.

**Структура:**
- `scripts/ingestion/bnd_sync/` — `run_nightly.py`, `cron_nightly.sh`, `build_doc_catalog.py`, `build_rpp_catalog.py`, `download_bnd_corpus.py`, `tg_report.py`.
- `data/bnd_corpus/` — зеркало (перенесено `mv` из todo; в `todo/data/bnd_corpus` — symlink).
- `data/bnd_sync/logs/` — логи прогонов; `data/bnd_sync/crontab.backup.20260923` — бэкап crontab.
- Каталоги пишутся в `BND_WEBBI_DIR` (дефолт `/home/budnik_an/todo/webBI`) атомарно.
- `.cursor/rules/60_todo_portal.mdc` — правило для работ с порталом todo из Obligations.

**Тесты:** `tests/test_bnd_sync.py` — 14 passed. ⚠ Файл попадает под `.gitignore` (`test_*.py`) — при коммите нужен `git add -f`.

**Следующие шаги:**
- Контроль 7 ночных прогонов (до 30.09.2026); при всех зелёных — разрешить удаление карантина.
- P5 — удаление старых скриптов из todo (коммит делает human): `tools/cron_catalog_rebuild.sh`, `tools/catalog_daily_rebuild.py`, `lotus-mcp/build_doc_catalog.py`, `build_rpp_catalog.py`, `download_bnd_corpus.py`.
- Подключить `data/bnd_corpus/manifest.json` как вход ingestion PDFtoBPMN (отдельная задача).

**Отчёт (23.09.2026 12:15, D-040):** Telegram-отчёт отключён (`TELEGRAM_*` удалены из `.env`). Отчёт уходит личными сообщениями от бота ДВК (Hermes, профиль `mm`, пользователь-бот `dvk`, Mattermost team.utair.io) трём получателям: `budnik_an`, `lavrova_tv`, `bachurina_iv`. Переменные: `MATTERMOST_URL`, `MATTERMOST_TOKEN`, `BND_REPORT_MM_USERS`. Прогон 12:17 — «ММ: отправлено 3/3». Тесты: 14 passed.

**Решение:** D-039, D-040.

### TASK-019 (23.09.2026) — лёгкая обвязка агентов + журнал действий агентов

- ✅ **P1** (d618549): уровни риска и базовые принципы вместо цепочки H1–H9; актуальные модели агентов.
- ✅ **P2** (коммит будет, пока не закоммичено): журнал действий агентов (lite KG) вместо LangGraph-графа.
  - `.cursor/kg/events.jsonl` + CLI `.cursor/state/kg.py` (`add` / `query` / `export changelog|state` / `import-docs`); `tests/test_kg.py` — 7 тестов.
  - Импорт: 39 решений из `docs/DECISIONS.md`, 13 планов из `.cursor/plans/`, события TASK-017/018/019.
  - LangGraph-граф разработки (`dev_graph.py`, `dev_state.sqlite`, `bootstrap.sh`, `tests/test_dev_graph.py`) → `archive/legacy_2026/state_langgraph/`; `batch_graph.py` оставлен; `langgraph` в `pyproject.toml` не тронут.
  - Исполнители: coder — Grok 4.7 (`grok-4.7-high-fast`), validator — GPT-5.6 Sol (`gpt-5.6-sol-high`), 2 итерации.
  - Находки validator (обе L3, исправлены в итерации 2; тесты сначала падали на старом коде): `add --ts 2026-99-99T99:99:99Z` принимался; `query --file` по файлу внутри папки-ссылки не находил событие.
  - Проверки: pytest tests — 21 passed; pyflakes чисто; validator PASS (итерация 2).
- ⏳ **P3**: `safety_guard` — впереди.
- ⏳ **P4**: навык `data-researcher` — впереди.

**Известный пропуск источника (Rule 0, ⚠ GAP):** в `docs/DECISIONS.md` нет решения D-029 — 39 заголовков при последнем D-040; D-031 стоит после D-033. Не достраивается; в журнал импортированы только существующие 39.

### Блокеры
- Нет

### Последние handoff'ы (актуальные)
- H1: Human → Orchestrator (18.03.2026) — /start, валидация развёртывания
- H9: Orchestrator → Human (18.03.2026) — TASK-001 completed, 11/11 PASS
- H9: Orchestrator → Human (18.03.2026) — TASK-002 completed, EasyOCR winner (D-012)
- H9: Orchestrator → Human (18.03.2026) — TASK-003 completed, Graph Population POC all PASS
- H9: Orchestrator → Human (18.03.2026) — TASK-004 completed, Document Authority POC all PASS
- H9: Orchestrator → Human (18.03.2026) — TASK-005 completed, Page Classifier POC 397 pages classified
- H9: Orchestrator → Human (19.03.2026) — TASK-006 completed, Qwen VLM POC: 2B работает, для production нужна 7B
- H10: Orchestrator → Human (20.03.2026) — TASK-007 completed, OCR/VLM Benchmark: 7 моделей, D-018
- Human (29.03.2026) — Донастройка мультиагента: D-019, обновление протоколов и агентов
- Human (29.03.2026) — Донастройка MCP: domino-keep-bnd (db02, dflib) подключён
- Human (29.03.2026) — Разведка структуры БНД: 3 типа вложений, составные документы, стратегия extraction (D-020)
- H9: Scribe → Human (14.05.2026) — TASK-012 completed, P0–P5: matching.json + meridian_upgrade_v1.csv + UI-бейджи + кнопка экспорта; D-032, D-033
- H7: Orchestrator → Scribe (04.05.2026) — TASK-008 decisions: D-021, D-022; cup_dashboard planned
- H7: Orchestrator → Scribe (04.05.2026) — TASK-009 decisions: D-023 (cross-repo), D-024 (live instead of self-contained), D-025 (CH schema cup.flights); cup_dashboard in_progress (Phase A)
- H7: Human → Scribe (04.05.2026) — TASK-009 D-026: scope iteration 1 подтверждён (6 data_layer), Phase A.1 закрыта, Phase A.2 начата
- H7: Orchestrator → Scribe (04.05.2026) — TASK-009 финализация: D-027 (NOT NULL ORDER BY keys), D-028 (numeric coercion); Phases A+B+C+D+E закрыты; дашборд: 533 344 строк, FastAPI + ECharts, готов к деплою на /info/tsup/
- H8: Scribe → Human (23.09.2026) — TASK-017 зафиксирован: D-039 добавлен в DECISIONS.md; ✅ bnd_sync в CURRENT_STATE.md; 13 тестов passed; карантин до 30.09.2026
- H7→H8: Scribe (23.09.2026 12:20) — D-040 зафиксирован: Telegram → Mattermost (бот ДВК, DM, 3 получателя); DECISIONS.md D-040 добавлен; CURRENT_STATE.md bnd_sync и TASK-017 обновлены; 14 тестов passed
- H7→H8: Scribe (23.09.2026) — TASK-019 P2 зафиксирован: 3 события в `.cursor/kg/events.jsonl` (2 finding L3, 1 change); ✅ lite KG в CURRENT_STATE.md; langgraph_state помечен архивированным; пропуск D-029 отмечен; DECISIONS.md без изменений
