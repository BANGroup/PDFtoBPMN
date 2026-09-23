#!/usr/bin/env python3
"""
Hook: stop — когда агент завершает сессию.

Логика:
  1. Определить агента и статус (completed/aborted/error)
  2. Записать в LangGraph action_log
  3. Если coder завершил без post-gate handoff → предупреждение
  4. Лог в .cursor/hooks.log
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HOOKS_LOG = Path(".cursor/hooks.log")
STATE_DB = Path(".cursor/state/dev_state.sqlite")


def log(msg: str):
    with open(HOOKS_LOG, "a") as f:
        ts = datetime.now().isoformat(timespec="seconds")
        f.write(f"[{ts}] [record_stop] {msg}\n")


def record_to_state(agent: str, status: str):
    """Записать завершение сессии в dev_state через прямой SQL.
    
    Не используем DevGraph API чтобы не тянуть langgraph в hook.
    Пишем в отдельную таблицу session_log (создаём если нет).
    """
    if not STATE_DB.exists():
        log("WARN: state DB not found, skipping recording")
        return

    try:
        import sqlite3
        conn = sqlite3.connect(str(STATE_DB))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent TEXT NOT NULL,
                status TEXT NOT NULL,
                note TEXT DEFAULT ''
            )
        """)
        conn.execute(
            "INSERT INTO session_log (timestamp, agent, status) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), agent, status)
        )
        conn.commit()
        conn.close()
        log(f"Recorded: {agent} → {status}")
    except Exception as e:
        log(f"ERROR recording: {e}")


def check_missing_handoff(agent: str):
    """Проверить: если coder завершил, был ли H5 (code → validator)?"""
    if agent != "coder" or not STATE_DB.exists():
        return

    try:
        import sqlite3
        conn = sqlite3.connect(str(STATE_DB))
        cursor = conn.execute(
            "SELECT checkpoint FROM checkpoints ORDER BY rowid DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return

        state = json.loads(row[0])
        handoffs = state.get("channel_values", {}).get("handoffs", [])
        current_task = state.get("channel_values", {}).get("current_task", "")

        # Ищем H5 (coder → validator) для текущей задачи
        has_h5 = any(
            h.get("handoff_id") == "H5" and current_task in h.get("task", "")
            for h in handoffs
        )

        if not has_h5:
            log(
                f"WARNING: Coder session ended but H5 (code → validator) "
                f"not found for '{current_task}'. "
                f"Code was submitted without going through post-gate!"
            )

    except Exception as e:
        log(f"ERROR checking handoff: {e}")


def main():
    stdin_data = {}
    try:
        stdin_data = json.loads(sys.stdin.read())
    except Exception:
        pass

    agent = os.environ.get("CURSOR_AGENT_NAME", "unknown")
    status = stdin_data.get("status", "unknown")  # completed | aborted | error

    log(f"Agent '{agent}' stopped with status '{status}'")

    record_to_state(agent, status)
    check_missing_handoff(agent)

    # stop hook не блокирует — сессия уже завершена
    sys.exit(0)


if __name__ == "__main__":
    main()
