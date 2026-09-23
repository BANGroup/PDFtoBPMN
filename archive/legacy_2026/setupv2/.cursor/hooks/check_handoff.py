#!/usr/bin/env python3
"""
Hook: beforeSubmitPrompt — проверяет что handoff записан перед работой агента.

Логика:
  1. Определить текущего агента (из env или transcript)
  2. Проверить в dev_state.sqlite: последний handoff TO этого агента существует
  3. Если нет → BLOCK (exit 2, continue=false)

Cursor вызывает перед каждым промптом к модели.
Exit 0 = proceed, Exit 2 = block.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

STATE_DB = Path(".cursor/state/dev_state.sqlite")
HOOKS_LOG = Path(".cursor/hooks.log")


def log(msg: str):
    with open(HOOKS_LOG, "a") as f:
        f.write(f"[check_handoff] {msg}\n")


def get_current_agent() -> str:
    """Определить агента из env переменной (ставится в agent .md config)."""
    return os.environ.get("CURSOR_AGENT_NAME", "unknown")


def get_last_handoff_to(agent: str) -> dict | None:
    """Последний handoff к этому агенту из LangGraph state."""
    if not STATE_DB.exists():
        return None

    try:
        conn = sqlite3.connect(str(STATE_DB))
        # LangGraph SqliteSaver хранит state как JSON в checkpoints table
        # Читаем напрямую — это локальная SQLite, не API
        cursor = conn.execute(
            "SELECT checkpoint FROM checkpoints ORDER BY rowid DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        state = json.loads(row[0])
        handoffs = state.get("channel_values", {}).get("handoffs", [])

        # Последний handoff TO этого агента
        for h in reversed(handoffs):
            if h.get("to_agent") == agent:
                return h
        return None

    except Exception as e:
        log(f"ERROR reading state: {e}")
        return None


def get_current_task() -> str:
    """Текущая задача из state."""
    if not STATE_DB.exists():
        return ""
    try:
        conn = sqlite3.connect(str(STATE_DB))
        cursor = conn.execute(
            "SELECT checkpoint FROM checkpoints ORDER BY rowid DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            state = json.loads(row[0])
            return state.get("channel_values", {}).get("current_task", "")
    except Exception:
        pass
    return ""


def main():
    # Читаем stdin от Cursor (JSON с transcript_path и т.д.)
    stdin_data = {}
    try:
        stdin_data = json.loads(sys.stdin.read())
    except Exception:
        pass

    agent = get_current_agent()

    # Orchestrator — всегда может работать (первый в цепочке, получает от human)
    if agent in ("orchestrator", "unknown"):
        log(f"PASS: {agent} always allowed")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Coder, Scribe, Validator — проверяем handoff
    last_handoff = get_last_handoff_to(agent)

    if last_handoff is None:
        # Нет записи о handoff → BLOCK
        task = get_current_task()
        msg = (
            f"BLOCKED: No handoff recorded to '{agent}'. "
            f"Task: {task}. "
            f"Orchestrator must dispatch via handoff protocol before {agent} can work."
        )
        log(f"BLOCK: {msg}")
        print(json.dumps({
            "continue": False,
            "stopReason": msg,
        }))
        sys.exit(2)

    # Handoff существует — проверяем что task совпадает
    current_task = get_current_task()
    handoff_task = last_handoff.get("task", "")

    if current_task and handoff_task and current_task != handoff_task:
        msg = (
            f"BLOCKED: Handoff to '{agent}' is for '{handoff_task}', "
            f"but current task is '{current_task}'. Stale handoff?"
        )
        log(f"BLOCK: {msg}")
        print(json.dumps({
            "continue": False,
            "stopReason": msg,
        }))
        sys.exit(2)

    log(f"PASS: {agent} has valid handoff {last_handoff.get('handoff_id', '?')}")
    print(json.dumps({"continue": True}))
    sys.exit(0)


if __name__ == "__main__":
    main()
