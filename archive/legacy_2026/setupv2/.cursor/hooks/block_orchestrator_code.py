#!/usr/bin/env python3
"""
Hook: beforeShellExecution — блокирует orchestrator от запуска кода.

Orchestrator НЕ может:
  - python/python3 (запуск скриптов)
  - pytest (запуск тестов)
  - pip/pip3 (установка зависимостей)
  - git add/commit/push (только human коммитит)
  - cat/sed/awk на scripts/core (чтение через Cursor search, не shell)

Orchestrator МОЖЕТ:
  - cat/less на docs/, .cursor/plans/, .cursor/state/
  - ls, find, grep (навигация)
"""

import json
import os
import re
import sys
from pathlib import Path

HOOKS_LOG = Path(".cursor/hooks.log")

# Команды, запрещённые для orchestrator
BLOCKED_COMMANDS = [
    r"^python[23]?\s",
    r"^pytest\s",
    r"^pip[23]?\s",
    r"^pip\s+install",
    r"^git\s+(add|commit|push|merge|rebase|reset)",
    r"^node\s",
    r"^npm\s",
    r"^make\s",
    r"^docker\s",
    r"^chmod\s",
    r"^rm\s",
    r"^mv\s",
    r"^cp\s.*\s(scripts|core|tests|poc)/",
    r"^sed\s.*\s(scripts|core|tests|poc)/",
    r"^touch\s.*(\.py|\.yaml|\.json)",
]

# Паттерны файловых операций на код-директории
CODE_DIRS = ["scripts/", "core/", "tests/", "poc/"]


def log(msg: str):
    with open(HOOKS_LOG, "a") as f:
        f.write(f"[block_orch_code] {msg}\n")


def is_code_command(command: str) -> tuple[bool, str]:
    """Проверить: это кодинг-команда?"""
    cmd = command.strip()

    for pattern in BLOCKED_COMMANDS:
        if re.match(pattern, cmd):
            return True, f"Matches blocked pattern: {pattern}"

    # Проверить: cat/less/head на code directories
    for d in CODE_DIRS:
        if re.search(rf"(cat|less|head|tail|nano|vim|vi)\s+.*{d}", cmd):
            return True, f"File read on code dir via shell: {d}"

    return False, ""


def main():
    stdin_data = {}
    try:
        stdin_data = json.loads(sys.stdin.read())
    except Exception:
        pass

    agent = os.environ.get("CURSOR_AGENT_NAME", "unknown")

    # Только orchestrator блокируется этим хуком
    if agent != "orchestrator":
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Получить команду из stdin
    command = stdin_data.get("command", "")
    if not command:
        command = os.environ.get("SHELL_COMMAND", "")

    if not command:
        log("WARN: no command in hook input")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    blocked, reason = is_code_command(command)

    if blocked:
        msg = (
            f"BLOCKED: Orchestrator attempted shell command: '{command}'. "
            f"Reason: {reason}. "
            f"Orchestrator must not code, run scripts, or modify files. "
            f"Dispatch to coder or validator instead."
        )
        log(f"BLOCK: {msg}")
        print(json.dumps({
            "continue": False,
            "stopReason": msg,
            "systemMessage": (
                "You are the orchestrator. You cannot run code or scripts. "
                "Dispatch this task to the coder agent via handoff H4."
            ),
        }))
        sys.exit(2)

    log(f"PASS: orchestrator shell '{command}' allowed")
    print(json.dumps({"continue": True}))
    sys.exit(0)


if __name__ == "__main__":
    main()
