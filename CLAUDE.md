# Obligations (PDFtoBPMN v2.1) — Claude Code

Обвязка агентов общая с Cursor и Codex (TASK-020, D-042; Codex — D-046, `AGENTS.md`). Источник истины — `.cursor/`; здесь только подключение.

## Правила (общие, всегда)
@.cursor/rules/00_global_always.mdc
@.cursor/rules/00_rule_zero_vacuum.mdc
@.cursor/rules/project.mdc

## Правила по области — прочитать перед работой с файлами
| Файлы | Правило |
|---|---|
| `scripts/ingestion/**`, `poc/poc_ocr_*`, `poc/poc_page_*` | `.cursor/rules/10_ingestion.mdc` |
| `scripts/ingestion/bnd_sync/**` | `.cursor/rules/60_todo_portal.mdc` |
| `scripts/extraction/**`, `core/*` | `.cursor/rules/20_extraction.mdc` |
| `scripts/bpmn/**`, `scripts/business_studio/**`, `*.bpmn` | `.cursor/rules/30_bpmn_and_bs.mdc` |
| `scripts/rag/**`, `scripts/graph/**` | `.cursor/rules/40_rag.mdc` |
| `tests/**`, `scripts/gold/**`, `docs/reports/**` | `.cursor/rules/50_quality.mdc` |

## Отличия среды Claude Code
- **orchestrator** — основной чат. Субагенты — `.claude/agents/` (coder, validator, scribe, extractor): тексты ролей из `.cursor/agents/`, модели из `.cursor/state/harness_models.json`.
- **Модели разных семейств**: в Claude Code все модели — Claude. Для `low`/`medium` validator — Opus; для `high` обязательна проверка GPT-валидатором в Cursor, до неё задача не закрывается.
- **Журнал** — тот же `.cursor/kg/events.jsonl`; в `kg.py add` всегда `--model <id модели>` (Claude Code пишет id Claude, Cursor — свой).
- **Охранник** — тот же `.cursor/hooks/safety_guard.py`, подключён в `.claude/settings.json` с флагом `--claude`.

## Синхронизация обвязки
Обвязку правит только Claude Code по команде human, и всегда во всех наборах (Cursor, Claude Code, Codex):
- тексты ролей — только в `.cursor/agents/*.md`; навыки — `.cursor/skills/`; команды — `.cursor/commands/`; модели — только в `.cursor/state/harness_models.json`;
- после любой правки: `python3 .cursor/state/harness_sync.py` (пересобирает `.claude/agents`, симлинки навыков, `.codex/agents/*.toml`, `.agents/skills/*`, `.codex/hooks.json`, поле `model` в карточках Cursor);
- `tests/test_harness_sync.py` падает, если наборы разошлись. Сгенерированные файлы (`.claude/agents/*.md`, `.codex/agents/*.toml`, `.agents/skills/*`, `.codex/hooks.json`) руками не править.
