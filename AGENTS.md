# Obligations (PDFtoBPMN v2.1) — Codex

Обвязка агентов общая с Cursor и Claude Code (TASK-020, D-042; Codex — D-046). Источник истины — `.cursor/`; здесь только подключение.

## Правила (общие, всегда) — прочитать в начале сессии
Codex не подгружает файлы по ссылкам сам: перед первой задачей прочитай целиком
- `.cursor/rules/00_global_always.mdc`
- `.cursor/rules/00_rule_zero_vacuum.mdc` (Rule 0 — выше всех правил)
- `.cursor/rules/project.mdc`

## Правила по области — прочитать перед работой с файлами
| Файлы | Правило |
|---|---|
| `scripts/ingestion/**`, `poc/poc_ocr_*`, `poc/poc_page_*` | `.cursor/rules/10_ingestion.mdc` |
| `scripts/ingestion/bnd_sync/**` | `.cursor/rules/60_todo_portal.mdc` |
| `scripts/extraction/**`, `core/*` | `.cursor/rules/20_extraction.mdc` |
| `scripts/bpmn/**`, `scripts/business_studio/**`, `*.bpmn` | `.cursor/rules/30_bpmn_and_bs.mdc` |
| `scripts/rag/**`, `scripts/graph/**` | `.cursor/rules/40_rag.mdc` |
| `tests/**`, `scripts/gold/**`, `docs/reports/**` | `.cursor/rules/50_quality.mdc` |

## Отличия среды Codex
- **orchestrator** — основной чат. Субагенты — `.codex/agents/*.toml` (coder, validator, scribe, extractor): тексты ролей из `.cursor/agents/`. Модель в карточках не задаётся — субагенты работают на модели текущей сессии Codex.
- **Навыки** — `.agents/skills/`: копии `.cursor/skills/*` и `source-command-<имя>` из команд `.cursor/commands/*.md` (в Codex нет команд; `start` — навык `source-command-start`).
- **Модели разных семейств**: в Codex все модели одного семейства (GPT). Для `low`/`medium` validator — субагент Codex; для `high` обязательна проверка validator'ом другого семейства (Claude Code — Opus, или Cursor), до неё задача не закрывается.
- **Журнал** — тот же `.cursor/kg/events.jsonl`; в `kg.py add` всегда `--model <id модели сессии Codex>`.
- **Охранник** — тот же `.cursor/hooks/safety_guard.py`, подключён в `.codex/hooks.json` с флагом `--codex` (Bash и правки `apply_patch`/`Edit`/`Write`). Codex запускает хук только после того, как human проверит и одобрит его определение (trust); отказ охранника — стоп и вопрос human.

## Синхронизация обвязки
Обвязку правит только Claude Code по команде human (D-042), всегда во всех наборах. Codex обвязку не правит — если нужна правка, скажи human.
- Тексты ролей — только в `.cursor/agents/*.md`; навыки — `.cursor/skills/`; команды — `.cursor/commands/`; модели — `.cursor/state/harness_models.json`.
- После любой правки: `python3 .cursor/state/harness_sync.py` — пересобирает `.claude/agents`, `.claude/skills`, `.codex/agents`, `.agents/skills`, `.codex/hooks.json` и поле `model` в карточках Cursor.
- `tests/test_harness_sync.py` падает, если наборы разошлись. Сгенерированные файлы (`.codex/agents/*.toml`, `.agents/skills/*`, `.codex/hooks.json`) руками не править.
