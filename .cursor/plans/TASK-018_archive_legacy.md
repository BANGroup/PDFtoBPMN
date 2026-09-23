# TASK-018: архив неиспользуемых наработок (legacy_2026)

## Цель
Расчистить корень проекта от наработок, не относящихся к контуру НД или замещённых. Ничего не удаляется: отслеживаемое — `git mv` в `archive/legacy_2026/` (остаётся в репозитории), неотслеживаемое — `mv` туда же.

## Решения human (23.09.2026)
- Отслеживаемые файлы — `git mv` в отслеживаемую `archive/legacy_2026/`.
- OCR не парковать: `DeepSeek-OCR/`, `ocr_bench_venv/`, `vllm_venv/`, `docker/` (сервисы qwen-vlm, deepseek-ocr), `poc/bench_*`, `yolov8l-worldv2.pt`, `scripts/utils/train_diagram_detector.py` — остаются. Локальный фоллбэк к OCR-стеку PowerHome — отдельное обсуждение.

## Состав
| Что | Почему |
|---|---|
| `setupv2/` | архивная копия бутстрапа v2.1 (в CURRENT_STATE так и помечена) |
| `app/sfv_dashboard/` | дашборд onboard sales — живёт в todo, к контуру НД не относится |
| `cup_dashboard/` | ЦУП-дашборд перенесён в todo (TASK-009, D-023) |
| `scripts/finance_parsers/`, `scripts/finance_parser/` | финансовые парсеры, не контур НД; последние изменения 11.2025–02.2026 |
| `setup.sh` | setup v1 (создание input/output), замещён `bootstrap.sh` |

## Шаги → verify
1. `.gitignore`: `archive/` → `archive/*` + `!archive/legacy_2026/` → verify: `git check-ignore archive/legacy_2026/x` пусто, `git check-ignore archive/v1_cursor_backup_20260318` срабатывает.
2. `git mv` / `mv` по таблице, `archive/legacy_2026/README.md` с таблицей «что и почему» → verify: `git status` — только renames + README + .gitignore.
3. README.md: ссылка `archive/finance_parsers/` → `archive/legacy_2026/scripts/finance_parsers/` → verify: `rg`.
4. `pytest tests/` — PASS; `rg` ссылок на старые пути в живом коде нет.

## Risks
- Исторические ссылки в `docs/DECISIONS.md` (append-only), `Changelog.md`, `poc/_update_state_task009.py` остаются на старые пути — это история.
