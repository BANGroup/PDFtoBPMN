#!/usr/bin/env python3
"""Журнал действий агентов: append-only JSONL (.cursor/kg/events.jsonl)."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TYPES = ("task", "decision", "change", "run", "finding", "handoff")
RISKS = ("low", "medium", "high")
STATUSES = ("planned", "in_progress", "done", "parked")
LEVELS = ("L1", "L2", "L3", "L4")
BODY = ("change", "run", "finding")
TASK_RE = re.compile(r"^TASK-\d{3}$")
DEC_RE = re.compile(r"^D-\d{3}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SINCE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEC_HDR = re.compile(r"^## (D-\d{3}):\s+(\S.*)$")
DATE_TAIL = re.compile(r"^(.*)\s+\((\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\)\s*$")
PLAN_HDR = re.compile(r"^# (TASK-\d{3})\s*[:\u2014]\s+(\S.*)$")
FIELDS = (
    "agent", "commit", "decision", "decisions", "evidence", "files", "level",
    "model", "risk", "status", "summary", "task", "ts", "type",
)


def repo_root():
    return Path(__file__).resolve().parents[2]


def events_path():
    override = os.environ.get("KG_EVENTS")
    return Path(override) if override else repo_root() / ".cursor" / "kg" / "events.jsonl"


def fail(msg):
    print(f"ошибка: {msg}", file=sys.stderr)
    raise SystemExit(2)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def blank(value):
    text = (value or "").strip()
    return text or None


def date_to_ts(raw):
    if "-" in raw:
        year, month, day = raw.split("-")
    else:
        day, month, year = raw.split(".")
    return f"{year}-{month}-{day}T00:00:00Z"


def record(**kwargs):
    event = {key: ([] if key in ("decisions", "files") else None) for key in FIELDS}
    event.update(kwargs)
    return event


def load_events(path):
    if not path.is_file():
        return []
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            print(f"предупреждение: строка {number}: битая строка ({exc})", file=sys.stderr)
            continue
        if isinstance(obj, dict):
            found.append(obj)
        else:
            print(f"предупреждение: строка {number}: ожидался объект JSON", file=sys.stderr)
    return found


def append_event(path, event):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def one_of(value, allowed, label):
    if value is not None and value not in allowed:
        fail(f"{label} должен быть одним из: " + ", ".join(allowed))


def build_event(ns):
    if ns.type not in TYPES:
        fail("type должен быть одним из: " + ", ".join(TYPES))
    summary = (ns.summary or "").strip()
    if not summary:
        fail("summary пустой")
    task, decision = blank(ns.task), blank(ns.decision)
    if task and not TASK_RE.match(task):
        fail("task должен быть TASK-NNN")
    if decision and not DEC_RE.match(decision):
        fail("decision должен быть D-NNN")
    if ns.type == "decision" and decision is None:
        fail("для type=decision обязателен --decision")
    links = []
    for item in ns.link_decision or []:
        item = item.strip()
        if not DEC_RE.match(item):
            fail(f"связь decision должна быть D-NNN: {item}")
        links.append(item)
    risk, status, level = blank(ns.risk), blank(ns.status), blank(ns.level)
    one_of(risk, RISKS, "risk")
    if status is not None and ns.type != "task":
        fail("status только для type=task")
    if ns.type == "task":
        one_of(status, STATUSES, "status")
    if level is not None and ns.type != "finding":
        fail("level только для type=finding")
    if ns.type == "finding":
        one_of(level, LEVELS, "level")
    ts = blank(ns.ts) or utc_now()
    if not TS_RE.match(ts):
        fail("ts должен быть UTC ISO, секунды, с Z")
    try:
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        fail("ts должен быть UTC ISO, секунды, с Z")
    return record(
        agent=blank(ns.agent), commit=blank(ns.commit), decision=decision,
        decisions=links, evidence=blank(ns.evidence), files=list(ns.file or []),
        level=level if ns.type == "finding" else None, model=blank(ns.model),
        risk=risk, status=status if ns.type == "task" else None,
        summary=summary, task=task, ts=ts, type=ns.type,
    )


def check_since(value):
    if not value:
        return
    if not SINCE_RE.match(value):
        fail("since должен быть YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        fail("since должен быть YYYY-MM-DD")


def norm_rel(path):
    text = path or ""
    if text.startswith("./"):
        text = text[2:]
    return text


def file_hit(query, stored):
    query, stored = norm_rel(query), norm_rel(stored)
    if query in stored:
        return True
    return stored.endswith("/") and query.startswith(stored)


def selected(events, ns):
    check_since(getattr(ns, "since", None))
    found = []
    for event in events:
        if ns.task and event.get("task") != ns.task:
            continue
        if getattr(ns, "type", None) and event.get("type") != ns.type:
            continue
        if ns.decision:
            links = event.get("decisions") or []
            if event.get("decision") != ns.decision and ns.decision not in links:
                continue
        if ns.file and not any(file_hit(ns.file, item) for item in event.get("files") or []):
            continue
        if ns.since and (event.get("ts") or "")[:10] < ns.since:
            continue
        found.append(event)
    return found


def compact(event):
    task, decision = event.get("task"), event.get("decision")
    ident = f"{task}/{decision}" if task and decision else (task or decision or "-")
    tail = f" [{event['commit']}]" if event.get("commit") else ""
    date = (event.get("ts") or "")[:10]
    return f"{date} {event.get('type')} {ident} {event.get('agent') or ''}: {event.get('summary')}{tail}"


def _groups(events, want_task):
    groups = {}
    for index, event in enumerate(events):
        if want_task and not event.get("task"):
            continue
        if not want_task and event.get("type") not in ("task", *BODY):
            continue
        key = event.get("task") or "—"
        groups.setdefault(key, []).append((index, event))
    return groups


def _latest(items, only_task=False):
    pool = [(i, ev) for i, ev in items if ev.get("type") == "task"] if only_task else items
    if not pool:
        return None
    return max(pool, key=lambda pair: (pair[1].get("ts") or "", pair[0]))[1]


def render_changelog(events):
    groups = _groups(events, want_task=False)
    lines = []
    order = sorted(groups, key=lambda name: max((ev.get("ts") or "", i) for i, ev in groups[name]), reverse=True)
    for key in order:
        items = groups[key]
        last = _latest(items, only_task=True)
        lines.append(f"## {key} — {last.get('summary') if last else ''}".rstrip())
        body = [ev for _, ev in sorted(items, key=lambda pair: (pair[1].get("ts") or "", pair[0]), reverse=True)]
        for event in body:
            if event.get("type") not in BODY:
                continue
            bits = [(event.get("ts") or "")[:10], event.get("type") or ""]
            if event.get("commit"):
                bits.append(event["commit"])
            if event.get("decisions"):
                bits.append(" ".join(event["decisions"]))
            lines.append("- " + " ".join(bits) + ": " + (event.get("summary") or ""))
        lines.append("")
    text = "\n".join(lines).rstrip()
    return text + "\n" if text else ""


def render_state(events):
    groups = _groups(events, want_task=True)
    rows = []
    for task, items in groups.items():
        last = _latest(items)
        task_event = _latest(items, only_task=True)
        status = (task_event or {}).get("status") or ""
        ts = (last or {}).get("ts") or ""
        rows.append((ts, task, status, ts[:10], len(items)))
    rows.sort(reverse=True)
    lines = ["| TASK | status | дата | события |", "|---|---|---|---|"]
    lines.extend(f"| {task} | {status} | {date} | {count} |" for _, task, status, date, count in rows)
    return "\n".join(lines) + "\n"


def import_docs(root, path):
    events = load_events(path)
    seen_dec = {ev.get("decision") for ev in events if ev.get("type") == "decision"}
    seen_task = {ev.get("task") for ev in events if ev.get("type") == "task" and ev.get("evidence") == "import"}
    added = skipped = 0
    imported_at = utc_now()
    decisions = root / "docs" / "DECISIONS.md"
    if not decisions.is_file():
        print(f"предупреждение: нет файла {decisions}", file=sys.stderr)
    for number, line in enumerate(decisions.read_text(encoding="utf-8").splitlines(), 1) if decisions.is_file() else []:
        header = DEC_HDR.match(line.strip())
        if not header:
            continue
        dec_id, rest = header.group(1), header.group(2).strip()
        dated = DATE_TAIL.match(rest)
        summary, ts = (dated.group(1).strip(), date_to_ts(dated.group(2))) if dated else (rest, imported_at)
        if not summary or dec_id in seen_dec:
            if not summary:
                print(f"предупреждение: {decisions}:{number}: пустой заголовок", file=sys.stderr)
            skipped += 1
            continue
        append_event(path, record(
            agent="scribe", decision=dec_id, evidence="import", summary=summary, ts=ts, type="decision",
        ))
        seen_dec.add(dec_id)
        added += 1
    plans_dir = root / ".cursor" / "plans"
    for plan in sorted(plans_dir.glob("TASK-*.md")) if plans_dir.is_dir() else []:
        rel = plan.relative_to(root).as_posix()
        first = plan.read_text(encoding="utf-8").splitlines()[:1]
        header = PLAN_HDR.match(first[0].strip()) if first else None
        if not header:
            print(f"предупреждение: {rel}: первая строка не # TASK-NNN", file=sys.stderr)
            skipped += 1
            continue
        task_id, summary = header.group(1), header.group(2).strip()
        if task_id in seen_task:
            skipped += 1
            continue
        mtime = datetime.fromtimestamp(plan.stat().st_mtime, timezone.utc)
        append_event(path, record(
            evidence="import", files=[rel], status="planned", summary=summary, task=task_id,
            ts=mtime.strftime("%Y-%m-%dT%H:%M:%SZ"), type="task",
        ))
        seen_task.add(task_id)
        added += 1
    print(f"добавлено {added}, пропущено {skipped}")


def parser():
    main = argparse.ArgumentParser(description="Журнал действий агентов")
    sub = main.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--type", required=True)
    add.add_argument("--summary", required=True)
    for name in ("task", "decision", "agent", "model", "evidence", "risk", "commit", "status", "level", "ts"):
        add.add_argument("--" + name)
    add.add_argument("--file", action="append")
    add.add_argument("--link-decision", action="append")
    query = sub.add_parser("query")
    for name in ("task", "decision", "file", "type", "since"):
        query.add_argument("--" + name)
    query.add_argument("--json", action="store_true")
    export = sub.add_parser("export")
    export.add_argument("what", choices=("changelog", "state"))
    export.add_argument("--since")
    sub.add_parser("import-docs").add_argument("--root")
    return main


def main(argv=None):
    ns = parser().parse_args(argv)
    if ns.cmd == "add":
        append_event(events_path(), build_event(ns))
        return
    if ns.cmd == "import-docs":
        if ns.root:
            root = Path(ns.root)
        elif os.environ.get("KG_ROOT"):
            root = Path(os.environ["KG_ROOT"])
        else:
            root = repo_root()
        import_docs(root.resolve(), events_path())
        return
    check_since(ns.since)
    events = load_events(events_path())
    if ns.cmd == "query":
        found = selected(events, ns)
        if ns.json:
            print(json.dumps(found, ensure_ascii=False, sort_keys=True, indent=2))
        else:
            for event in found:
                print(compact(event))
        return
    if ns.since:
        events = [ev for ev in events if (ev.get("ts") or "")[:10] >= ns.since]
    print((render_changelog if ns.what == "changelog" else render_state)(events), end="")


if __name__ == "__main__":
    main()
