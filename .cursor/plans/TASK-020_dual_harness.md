# TASK-020: общая обвязка для Cursor и Claude Code

Уровень риска: **high** (правка `.cursor/rules/**` и fail-closed охранника). Согласовано human 29.09.2026 в чате Claude Code.

## Контекст
- Обвязка (TASK-019) живёт только в `.cursor/`. Со стороны Claude Code нет ничего: ни `CLAUDE.md`, ни `.claude/settings.json`, ни субагентов; охранник Claude Code не защищает.
- Решение human 29.09.2026: обвязка общая — правила, тексты ролей, навыки, планы, журнал `.cursor/kg/events.jsonl`, `safety_guard.py`. Свои у каждой среды — файлы настроек и выбор моделей. Правит обвязку только Claude Code, и всегда в обоих наборах настроек.
- Модели Claude Code (согласовано): orchestrator — модель чата; coder — Sonnet 5; validator — Opus 5.5; scribe — Haiku 4.5; extractor — Opus 5.5.
- Правило «автор и проверяющий — разные семейства» в Claude Code невыполнимо: `low`/`medium` — validator Opus; `high` — обязательная проверка GPT-валидатором в Cursor.

## Не входит
Сборка канона НД (отдельная задача), изменение логики самого охранника, новые роли, переписывание текстов карточек.

## Шаги
1. **Таблица моделей** `.cursor/state/harness_models.json`: роль → модель Cursor, модель Claude Code.
   → verify: JSON читается, роли совпадают с `.cursor/agents/*.md`.
2. **Генератор** `.cursor/state/harness_sync.py`: `.claude/agents/<роль>.md` = заголовок Claude Code (name, description, model из таблицы) + тело карточки Cursor; поле `model` в карточках Cursor — из той же таблицы; навыки `.claude/skills/<имя>` — симлинк на `.cursor/skills/<имя>`. Режим `--check` — выход 1 при расхождении.
   → verify: `harness_sync.py && harness_sync.py --check` → 0; ручная правка одной стороны → `--check` = 1.
3. **Тест расхождения** `tests/test_harness_sync.py`: `--check` на репозитории проходит.
   → verify: pytest.
4. **Охранник**: `safety_guard.py` с флагом `--claude` (задаётся в `.claude/settings.json`) принимает вход Claude Code (`Bash`, `Edit`/`Write`/`MultiEdit`/`NotebookEdit`) и отвечает в формате Claude Code (`hookSpecificOutput.permissionDecision`). Вход Cursor — без изменений. Тесты на оба формата.
   → verify: pytest (старые тесты зелёные, новые на Claude-формат); **отрицательный контроль** в Claude Code: `git reset --hard`, `rm -rf`, запись в `.env` на площадке в `/tmp` фактически остановлены.
5. **`.claude/settings.json`**: PreToolUse → `safety_guard.py` на `Bash|Edit|Write|MultiEdit|NotebookEdit`. В `.gitignore` — локальные файлы Claude Code (`.claude/settings.local.json`, `.claude/scheduled_tasks.lock`).
6. **`CLAUDE.md`**: импорт `.cursor/rules/*.mdc`, отличия среды (субагенты `.claude/agents`, модели, журнал с `--model`), правило синхронизации.
7. **Правила** (`.cursor/rules/**`, по поручению human 29.09): в `00_global_always.mdc` — ownership обвязки и правило синхронизации, исключение по семействам моделей; в `project.mdc` и `.cursorrules` — вторая среда.
   → verify: human читает дифф правил.
8. **Scribe**: решение D-042, события в журнал, `CURRENT_STATE`.

## Risks
- Охранник fail-closed: ошибка в адаптере Claude Code может заблокировать работу или пропустить опасное — поэтому тесты на оба формата и отрицательный контроль в обеих средах (Cursor-формат покрыт старыми тестами).
- Claude Code при падении хука с кодом ≠ 2 может пропускать вызов (fail-open) — зафиксировать фактическое поведение.
- Кросс-семейная проверка для `high` зависит от Cursor: пока GPT-валидатор не прогнан, задача не закрывается.

## Post-gate GPT (Cursor, 29.09)
- FAIL по документации (L3): неверные цифры тестов в журнале и `CURRENT_STATE` → корректирующие события и правка `CURRENT_STATE`.
- Cursor читает и `.claude/settings.json` (лог хуков Cursor: «Claude project config path»), поэтому в Cursor охранник вызывается дважды — нативно и с `--claude`. Оба вызова исправны (код 0), решения совпадают; дубль оставлен: нативный вызов Cursor покрывает `ApplyPatch`/`Delete`, которых нет в matcher Claude Code.
