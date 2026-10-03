"""Обвязка Cursor, Claude Code и Codex не разошлась (TASK-020, D-042; D-046)."""

import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_harness_in_sync():
    r = subprocess.run(
        [sys.executable, str(ROOT / ".cursor/state/harness_sync.py"), "--check"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_codex_files_parse():
    cards = sorted((ROOT / ".codex/agents").glob("*.toml"))
    assert cards
    for p in cards:
        card = tomllib.loads(p.read_text(encoding="utf-8"))
        assert card["name"] == p.stem and card["description"] and card["developer_instructions"]
    hooks = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    cmd = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "safety_guard.py" in cmd and "--codex" in cmd
