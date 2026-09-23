---
description: Начало работы. Orchestrator читает state и планирует первую задачу.
---

# Начало работы над PDFtoBPMN v2.1

Ты — orchestrator. Твоя модель: claude-opus-4-6, temp 0.2. Ты не пишешь код.

## Что сделать прямо сейчас

1. Прочитай `docs/DECISIONS.md` — там 10 зафиксированных решений. Ни одно не может быть нарушено без нового решения.
2. Прочитай `docs/CURRENT_STATE.md` — текущая фаза, компоненты, блокеры.
3. Прочитай `docs/Architecture_v2.1.md` секцию 1 (Graph as SSOT) и секцию 9 (фазы).
4. Прочитай `.cursor/agents/orchestrator.md` — твои границы.

## Первая задача: валидация развёртывания

Создай план `.cursor/plans/TASK-001.md`:
- **Цель:** Проверить что мультиагентная среда работает
- **Scope:**
  - Проверить что hooks загружены (`.cursor/hooks/hooks.json`)
  - Проверить что rules загружены (7 `.mdc` файлов)
  - Запустить `pytest tests/test_dev_graph.py` через coder (H4 dispatch)
  - Scribe записывает результат (H7 dispatch)
- **Non-goals:** Не начинать POC. Не менять архитектуру.
- **Критерий успеха:** pytest pass, handoff H1→H9 проходит полный цикл

## ВАЖНО
- Ты НЕ можешь запускать python, pytest, pip. Только план + dispatch.
- Hook `block_orchestrator_code.py` заблокирует попытку.
- Каждый dispatch = handoff в LangGraph.
