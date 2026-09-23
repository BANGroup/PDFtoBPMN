# TASK-019: лёгкая обвязка агентов (из cube/Helicomponents) + граф действий агентов

## Контекст
- Проект — контур управления НД: парсинг, граф, BPMN, справочники, нормоконтроль, интеграции BS/Lotus. Нужна обвязка по размеру задачи, без тяжёлой машинерии cube.
- Сейчас: цепочка H1–H9 и лимит «≤3 файлов, ≤150 строк» на практике обходятся исключениями (TASK-017); карточки агентов на устаревших моделях (`claude-opus-4-6`, `claude-sonnet-4-6`, `composer-1.5`); хуки отключены (D-036); граф разработки LangGraph (`.cursor/state/dev_state.sqlite`) заброшен с 04.05, бинарный, тест `tests/test_dev_graph.py` не в git и не запускается.
- Решения human 23.09.2026: лёгкая часть из cube (уровни риска, базовые принципы, короткий handoff, safety_guard с тестами, навык data-researcher, обновить карточки); лёгкий граф действий в JSONL вместо LangGraph; поэтапно.

## Не входит
Гейты pre_gate/pre_close, Agent KG cube (19,6 МБ, 640 workflows), сериализация субагентов, учёт токенов, FLAME/ClickHouse/BI-as-code, хуки, зависящие от графа.

## Фазы (каждая — отдельный коммит)

### P1. Правила и карточки агентов
1. `00_global_always.mdc`: цепочку H1–H9 и лимит «≤3 файлов/150 строк» заменить уровнями риска:
   - `low` — обратимое, `.cursor/**`/docs/отчёты/ output: план в 2–3 строки в чате, короткий handoff (`Цель | Изменения | Факты | Риск | Дальше`), без gates.
   - `medium` — код в `scripts/**`/`core/**`, cron, интеграции только на чтение: план в `.cursor/plans/`, validator post-gate, запись scribe.
   - `high` — схема графа/публичный контракт (каталоги портала), удаление, запись во внешние системы (BS/Lotus/Domino), нормативные справочники: план + согласование human до реализации + validator + scribe.
   Неясно → уровень выше.
2. Базовые принципы из cube `00_core_always`: блокировка — стоп и вопрос, а не обходной путь; посторонний дефект не расширяет задачу молча; не править правила/хуки ради своей задачи; дешёвые проверки данных — до реализации; коммит/пуш — по команде human.
3. Ревью: находки с уровнем доказательства L1 (вывод/код возврата) … L4 (суждение по коду); блокирует только L1–L3 или L4 с названной проверкой. Автор и проверяющий — модели разных семейств.
4. `project.mdc`, `.cursorrules`, `.cursor/agents/*.md`: актуальные модели (выбор human), убрать упоминания LangGraph-состояния.
→ verify: `rg "4\.6|composer-1\.5|H1:|≤3 файлов" .cursor .cursorrules` пусто; human читает дифф правил (`.cursor/rules/**` — HUMAN ONLY, правка по поручению 23.09).

### P2. Граф действий агентов (lite KG)
1. `.cursor/kg/events.jsonl` — append-only, одна запись на строку: `ts, type (task|decision|change|run|finding|handoff), task, agent, model, summary, refs{files,decisions}, evidence, risk`.
2. `.cursor/state/kg.py` (~150 строк, stdlib): `add`, `query --task/--file/--decision/--type`, `export changelog|state`. Тесты `tests/test_kg.py`.
3. Начальное наполнение: D-001…D-040 из `docs/DECISIONS.md` (ссылками, текст остаётся в DECISIONS), TASK-001…TASK-019 из `.cursor/plans/`, события TASK-017/018 с коммитами.
4. LangGraph (`dev_graph.py`, `batch_graph.py`, `dev_state.sqlite`, `tests/test_dev_graph.py`) → `archive/legacy_2026/state_langgraph/`; карточка scribe: запись в KG при закрытии задачи.
→ verify: pytest; `kg.py query --file scripts/ingestion/bnd_sync/download_bnd_corpus.py` возвращает TASK-017; `export changelog` воспроизводит TASK-017/018.

### P3. safety_guard
1. Из cube: `safety_guard.py` + `hook_io.py` + `shell_parse.py` + тесты, без ClickHouse-части. Блок: `rm -rf`, `git reset --hard`, force-push, удаление ветки на remote, `git clean -f`, `checkout/restore` рабочей копии, правка `.env*`/ключей/сертификатов.
2. `.cursor/hooks.json` — только этот хук (`preToolUse`, ответ через `permission`); старые 4 хука остаются dormant.
→ verify: тесты; **отрицательный контроль**: заведомо запрещённая команда фактически остановлена Cursor (не только запись в лог). Следствие: правку `.env` дальше делает human или по явному одобрению.

### P4. Навык data-researcher
`.cursor/skills/data-researcher/SKILL.md` — адаптация из todo под контур НД: Lotus/Domino (БНД, РПП, ЭСЗ), Business Studio, Jira, Superset — только чтение, шаблон промпта с критериями приёмки, «нет данных — так и сказать» (Rule 0).
→ verify: навык виден в списке, пробный запрос-исследование по одному документу БНД.

## Risks
- safety_guard fail-closed может заблокировать легитимную работу — поэтому отрицательный и положительный контроль до включения.
- Двойной источник истины: тексты решений — только `DECISIONS.md`, KG ссылается по D-номеру.
