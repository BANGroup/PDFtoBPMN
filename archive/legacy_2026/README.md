# legacy_2026 — архив наработок (TASK-018, 23.09.2026)

Перенесено из корня проекта без удаления: не относится к контуру НД или замещено. История файлов сохранена (`git log --follow`).

| Что | Было | Почему в архиве |
|---|---|---|
| `setupv2/` | `setupv2/` | архивная копия бутстрапа v2.1 (сам `bootstrap.sh` — в `state_langgraph/`) |
| `app/sfv_dashboard/` | `app/sfv_dashboard/` | дашборд onboard sales, живёт в todo |
| `cup_dashboard/` | `cup_dashboard/` | ЦУП-дашборд перенесён в todo (TASK-009, D-023) |
| `scripts/finance_parsers/` | `scripts/finance_parsers/` | финансовые парсеры, не контур НД |
| `scripts/finance_parser/` | `scripts/finance_parser/` | тесты парсеров (не в git: `.gitignore` — `test_*.py`) |
| `setup.sh` | `setup.sh` | setup v1, замещён `bootstrap.sh` |
| `state_langgraph/` | `.cursor/state/dev_graph.py`, `dev_state.sqlite`, `bootstrap.sh`, `tests/test_dev_graph.py` | граф разработки LangGraph заброшен с 04.05.2026, заменён журналом `.cursor/kg/events.jsonl` (TASK-019 P2) |

OCR-наработки (`DeepSeek-OCR/`, `ocr_bench_venv/`, `vllm_venv/`, `docker/`, `poc/bench_*`, модель yolov8) намеренно оставлены в проекте: тема актуальна.
