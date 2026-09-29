"""Обвязка Cursor и Claude Code не разошлась (TASK-020, D-042)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_harness_in_sync():
    r = subprocess.run(
        [sys.executable, str(ROOT / ".cursor/state/harness_sync.py"), "--check"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
