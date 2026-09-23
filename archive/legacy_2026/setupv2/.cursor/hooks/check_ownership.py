#!/usr/bin/env python3
"""
Hook: afterFileEdit — проверяет ownership зоны.

Правила:
  coder:      scripts/**, core/**, poc/**, tests/** (код)
  scribe:     docs/**, .cursor/state/**, tests/fixtures/gold/**
  validator:  (read-only, не создаёт файлы)
  orchestrator: .cursor/plans/** только

Если агент отредактировал файл вне своей зоны → BLOCK.
"""

import json
import os
import sys
from pathlib import Path

HOOKS_LOG = Path(".cursor/hooks.log")

# Ownership zones
ZONES = {
    "coder": [
        "scripts/**",
        "core/**",
        "poc/**",
        "tests/**",
    ],
    "scribe": [
        "docs/**",
        ".cursor/state/**",
        "tests/fixtures/gold/**",
    ],
    "orchestrator": [
        ".cursor/plans/**",
    ],
    "validator": [],  # validator не должен менять файлы
}

# Зоны, которые НИКТО не может менять (кроме human)
PROTECTED = [
    ".cursor/rules/**",
    ".cursor/hooks/**",
    "pyproject.toml",
    "requirements*.txt",
]


def log(msg: str):
    with open(HOOKS_LOG, "a") as f:
        f.write(f"[check_ownership] {msg}\n")


def matches_glob(filepath: str, pattern: str) -> bool:
    """Проверка glob паттерна (упрощённая)."""
    from fnmatch import fnmatch
    return fnmatch(filepath, pattern)


def is_allowed(agent: str, filepath: str) -> bool:
    """Проверить что агент может трогать этот файл."""
    # Protected files — никто
    for pattern in PROTECTED:
        if matches_glob(filepath, pattern):
            return False

    # Agent's zones
    allowed_patterns = ZONES.get(agent, [])
    for pattern in allowed_patterns:
        if matches_glob(filepath, pattern):
            return True

    return False


def main():
    stdin_data = {}
    try:
        stdin_data = json.loads(sys.stdin.read())
    except Exception:
        pass

    agent = os.environ.get("CURSOR_AGENT_NAME", "unknown")
    
    # Если агент не определён — пропускаем (вероятно human в IDE)
    if agent == "unknown":
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Получаем изменённый файл из stdin (Cursor передаёт в afterFileEdit)
    edited_file = stdin_data.get("file_path", "")
    if not edited_file:
        # Попробовать из env
        edited_file = os.environ.get("TOOL_INPUT_FILE_PATH", "")

    if not edited_file:
        log(f"WARN: no file path in hook input, skipping")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Нормализовать путь
    edited_file = str(Path(edited_file).relative_to(Path.cwd()))

    if is_allowed(agent, edited_file):
        log(f"PASS: {agent} → {edited_file}")
        print(json.dumps({"continue": True}))
        sys.exit(0)
    else:
        msg = (
            f"BLOCKED: '{agent}' edited '{edited_file}' — outside ownership zone. "
            f"Allowed zones for {agent}: {ZONES.get(agent, [])}"
        )
        log(f"BLOCK: {msg}")
        print(json.dumps({
            "continue": False,
            "stopReason": msg,
            "systemMessage": msg,
        }))
        sys.exit(2)


if __name__ == "__main__":
    main()
