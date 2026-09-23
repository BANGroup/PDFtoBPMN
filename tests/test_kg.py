"""Журнал .cursor/state/kg.py: add, query, import-docs, export."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KG = ROOT / ".cursor" / "state" / "kg.py"


def run(events: Path, args: list[str], extra: dict | None = None):
    env = os.environ.copy()
    env["KG_EVENTS"] = str(events)
    env.pop("KG_ROOT", None)
    if extra:
        env.update(extra)
    return subprocess.run(
        [sys.executable, str(KG), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_add_and_query_by_task_file_decision_type(tmp_path):
    events = tmp_path / "events.jsonl"
    add = run(events, [
        "add", "--type", "change", "--task", "TASK-017", "--agent", "orchestrator",
        "--summary", "Сборка корпуса перенесена", "--commit", "d29ce39",
        "--file", "scripts/ingestion/bnd_sync/",
        "--link-decision", "D-039", "--link-decision", "D-040",
        "--ts", "2026-09-23T07:30:00Z",
    ])
    assert add.returncode == 0, add.stderr
    run(events, [
        "add", "--type", "run", "--task", "TASK-018", "--agent", "orchestrator",
        "--summary", "Другая задача", "--ts", "2026-09-23T08:00:00Z",
    ])

    by_task = run(events, ["query", "--task", "TASK-017"])
    assert by_task.returncode == 0
    assert "TASK-017" in by_task.stdout
    assert "d29ce39" in by_task.stdout
    assert "TASK-018" not in by_task.stdout

    by_file = run(events, ["query", "--file", "scripts/ingestion/bnd_sync"])
    assert "d29ce39" in by_file.stdout
    assert "Другая задача" not in by_file.stdout

    by_decision = run(events, ["query", "--decision", "D-040"])
    assert "TASK-017" in by_decision.stdout
    assert "Сборка корпуса перенесена" in by_decision.stdout

    by_type = run(events, ["query", "--type", "run"])
    assert "TASK-018" in by_type.stdout
    assert "d29ce39" not in by_type.stdout

    as_json = run(events, ["query", "--task", "TASK-017", "--json"])
    payload = json.loads(as_json.stdout)
    assert payload[0]["decisions"] == ["D-039", "D-040"]
    assert payload[0]["commit"] == "d29ce39"


def test_validation_leaves_file_untouched(tmp_path):
    events = tmp_path / "events.jsonl"
    seed = run(events, [
        "add", "--type", "handoff", "--summary", "исходная запись",
        "--ts", "2026-09-23T01:00:00Z",
    ])
    assert seed.returncode == 0, seed.stderr
    before = events.read_bytes()
    cases = [
        ["add", "--type", "nope", "--summary", "плохо"],
        ["add", "--type", "change", "--task", "TASK-1", "--summary", "плохо"],
        ["add", "--type", "decision", "--decision", "D-99", "--summary", "плохо"],
        ["add", "--type", "change", "--summary", "   "],
    ]
    for args in cases:
        result = run(events, args)
        assert result.returncode == 2, args
        assert result.stderr
        assert events.read_bytes() == before


def test_import_docs_idempotent_and_kg_root(tmp_path):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / ".cursor" / "plans").mkdir(parents=True)
    (root / "docs" / "DECISIONS.md").write_text(
        "\n".join([
            "# Решения",
            "## D-001: Граф как источник (18.03.2026)",
            "Текст решения не копировать.",
            "## D-002: Формат даты ISO (2026-05-04)",
            "## D-003: Без даты в заголовке",
            "",
        ]),
        encoding="utf-8",
    )
    plan = root / ".cursor" / "plans" / "TASK-012.md"
    plan.write_text("# TASK-012 — Матчинг фикстуры\n\nтело\n", encoding="utf-8")
    events = tmp_path / "events.jsonl"

    first = run(events, ["import-docs", "--root", str(root)])
    assert first.returncode == 0, first.stderr
    assert "добавлено 4, пропущено 0" in first.stdout
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    by_dec = {row["decision"]: row for row in rows if row["type"] == "decision"}
    assert by_dec["D-001"]["summary"] == "Граф как источник"
    assert by_dec["D-001"]["ts"] == "2026-03-18T00:00:00Z"
    assert by_dec["D-001"]["agent"] == "scribe"
    assert "Текст решения" not in json.dumps(rows, ensure_ascii=False)
    assert by_dec["D-002"]["ts"] == "2026-05-04T00:00:00Z"
    assert by_dec["D-003"]["summary"] == "Без даты в заголовке"
    task = next(row for row in rows if row["type"] == "task")
    assert task["task"] == "TASK-012"
    assert task["status"] == "planned"
    assert task["evidence"] == "import"
    assert task["summary"] == "Матчинг фикстуры"
    assert task["files"] == [".cursor/plans/TASK-012.md"]

    second = run(events, ["import-docs", "--root", str(root)])
    assert "добавлено 0, пропущено 4" in second.stdout
    assert len(events.read_text(encoding="utf-8").splitlines()) == 4

    other = tmp_path / "via-env.jsonl"
    via_env = run(other, ["import-docs"], {"KG_EVENTS": str(other), "KG_ROOT": str(root)})
    assert via_env.returncode == 0, via_env.stderr
    assert "добавлено 4, пропущено 0" in via_env.stdout


def test_export_changelog_contains_task_and_commit(tmp_path):
    events = tmp_path / "events.jsonl"
    run(events, [
        "add", "--type", "task", "--task", "TASK-017", "--status", "done",
        "--summary", "Перенос сборки", "--ts", "2026-09-23T07:40:00Z",
    ])
    run(events, [
        "add", "--type", "change", "--task", "TASK-017", "--commit", "d29ce39",
        "--link-decision", "D-039", "--summary", "Сборка перенесена",
        "--ts", "2026-09-23T07:30:00Z",
    ])
    exported = run(events, ["export", "changelog", "--since", "2026-09-23"])
    assert exported.returncode == 0, exported.stderr
    assert "## TASK-017 — Перенос сборки" in exported.stdout
    assert "d29ce39" in exported.stdout
    assert "D-039" in exported.stdout


def test_broken_line_is_skipped_with_warning(tmp_path):
    events = tmp_path / "events.jsonl"
    good = {
        "agent": "orchestrator", "commit": None, "decision": None, "decisions": [],
        "evidence": None, "files": [], "level": None, "model": None, "risk": None,
        "status": None, "summary": "живая запись", "task": "TASK-001",
        "ts": "2026-09-23T00:00:00Z", "type": "handoff",
    }
    events.write_text("это не json\n" + json.dumps(good, ensure_ascii=False) + "\n", encoding="utf-8")
    result = run(events, ["query", "--task", "TASK-001"])
    assert result.returncode == 0, result.stderr
    assert "строка 1" in result.stderr
    assert "живая запись" in result.stdout
    assert "это не json" in events.read_text(encoding="utf-8")


def test_invalid_ts_and_since_do_not_touch_file(tmp_path):
    events = tmp_path / "events.jsonl"
    seed = run(events, [
        "add", "--type", "handoff", "--summary", "исходная запись",
        "--ts", "2026-09-23T01:00:00Z",
    ])
    assert seed.returncode == 0, seed.stderr
    before = events.read_bytes()
    bad_ts = run(events, [
        "add", "--type", "change", "--summary", "битая дата",
        "--ts", "2026-99-99T99:99:99Z",
    ])
    assert bad_ts.returncode == 2
    assert bad_ts.stderr
    assert events.read_bytes() == before
    bad_since = run(events, ["query", "--since", "2026-99-99"])
    assert bad_since.returncode == 2
    assert bad_since.stderr
    assert events.read_bytes() == before


def test_query_file_matches_directory_prefix(tmp_path):
    events = tmp_path / "events.jsonl"
    add = run(events, [
        "add", "--type", "change", "--task", "TASK-017", "--commit", "d29ce39",
        "--summary", "Сборка корпуса перенесена",
        "--file", "scripts/ingestion/bnd_sync/",
        "--ts", "2026-09-23T07:30:00Z",
    ])
    assert add.returncode == 0, add.stderr
    hit = run(events, [
        "query", "--file", "scripts/ingestion/bnd_sync/download_bnd_corpus.py",
    ])
    assert hit.returncode == 0, hit.stderr
    assert "TASK-017" in hit.stdout
    assert "d29ce39" in hit.stdout
    dotted = run(events, [
        "query", "--file", "./scripts/ingestion/bnd_sync/download_bnd_corpus.py",
    ])
    assert "d29ce39" in dotted.stdout
