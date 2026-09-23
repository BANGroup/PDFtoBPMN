"""
Dev State Graph — память проекта между сессиями.

Scribe пишет по командам orchestrator'а.
Orchestrator читает перед планированием.
Persistence: SQLite (локально, без сервера).

Использование:

    from state.dev_graph import DevGraph
    
    graph = DevGraph()
    
    # Scribe записывает решение
    graph.log_decision(
        title="OCR: RapidOCR",
        context="POC показал 94% vs 91% на кириллице",
        decision="RapidOCR через Docling RapidOcrOptions",
        rejected=["EasyOCR — 91%", "Tesseract — забракован"]
    )
    
    # Scribe обновляет компонент
    graph.update_component("ingestion", status="done", tests_pass=True)
    
    # Scribe записывает валидацию
    graph.log_validation(scope="test_ingestion.py", result="pass", details="12/12")
    
    # Orchestrator читает состояние
    state = graph.get_state()
    print(state["phase"])                # "1_ingestion"
    print(state["components"])           # {"ingestion": {"status": "done", ...}}
    print(len(state["decisions"]))       # 12
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

def _append(left: list, right: list) -> list:
    """Reducer: append-only list."""
    return left + right


class DevState(TypedDict, total=False):
    """Персистентное состояние разработки."""

    # Текущая фаза
    phase: str                    # "0_poc" | "1_ingestion" | "2_extraction" | ...
    current_task: str             # "TASK-005: page_classifier"
    task_status: str              # planned | in_progress | review | done | blocked

    # Append-only
    decisions: Annotated[list[dict], _append]
    validations: Annotated[list[dict], _append]
    action_log: Annotated[list[dict], _append]
    handoffs: Annotated[list[dict], _append]   # H1-H9 protocol log

    # Mutable
    components: dict[str, dict]   # {"ingestion": {"status": "done", ...}}
    blockers: list[dict]
    current_gates: dict           # {"pre": "pass", "post": "pending", "retries": 0}

    # Internal
    _command: str                 # "log_decision" | "update_component" | ...
    _payload: dict


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def router(state: DevState) -> str:
    """Маршрутизация по команде."""
    return state.get("_command", "noop")


def log_decision(state: DevState) -> dict:
    p = state["_payload"]
    entry = {
        "id": f"D-{len(state.get('decisions', [])) + 1:03d}",
        "date": datetime.now().isoformat(timespec="minutes"),
        "title": p["title"],
        "context": p.get("context", ""),
        "decision": p["decision"],
        "alternatives_rejected": p.get("rejected", []),
        "revisit_if": p.get("revisit_if", ""),
    }
    return {"decisions": [entry], "_command": "", "_payload": {}}


def update_component(state: DevState) -> dict:
    p = state["_payload"]
    components = dict(state.get("components", {}))
    components[p["name"]] = {
        "status": p["status"],
        "tests_pass": p.get("tests_pass", False),
        "last_updated": datetime.now().isoformat(timespec="minutes"),
    }
    return {"components": components, "_command": "", "_payload": {}}


def log_validation(state: DevState) -> dict:
    p = state["_payload"]
    entry = {
        "date": datetime.now().isoformat(timespec="minutes"),
        "scope": p["scope"],
        "result": p["result"],      # "pass" | "fail"
        "details": p.get("details", ""),
    }
    return {"validations": [entry], "_command": "", "_payload": {}}


def update_phase(state: DevState) -> dict:
    p = state["_payload"]
    return {
        "phase": p["phase"],
        "current_task": p.get("task", ""),
        "task_status": p.get("status", "planned"),
        "_command": "",
        "_payload": {},
    }


def log_action(state: DevState) -> dict:
    p = state["_payload"]
    entry = {
        "date": datetime.now().isoformat(timespec="minutes"),
        "action": p["action"],
        "agent": p.get("agent", ""),
    }
    return {"action_log": [entry], "_command": "", "_payload": {}}


def log_handoff(state: DevState) -> dict:
    """Записать handoff между агентами (H1-H9 protocol)."""
    p = state["_payload"]
    entry = {
        "date": datetime.now().isoformat(timespec="minutes"),
        "handoff_id": p["handoff_id"],     # "H1" | "H2" | ... | "H9"
        "from_agent": p["from_agent"],     # "human" | "orchestrator" | ...
        "to_agent": p["to_agent"],
        "task": p.get("task", state.get("current_task", "")),
        "payload_summary": p.get("summary", ""),
        "result": p.get("result", ""),     # "PASS" | "FAIL" | "" for dispatches
    }
    return {"handoffs": [entry], "_command": "", "_payload": {}}


def noop(state: DevState) -> dict:
    return {"_command": "", "_payload": {}}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    g = StateGraph(DevState)

    g.add_node("log_decision", log_decision)
    g.add_node("update_component", update_component)
    g.add_node("log_validation", log_validation)
    g.add_node("update_phase", update_phase)
    g.add_node("log_action", log_action)
    g.add_node("log_handoff", log_handoff)
    g.add_node("noop", noop)

    g.set_conditional_entry_point(router, {
        "log_decision": "log_decision",
        "update_component": "update_component",
        "log_validation": "log_validation",
        "update_phase": "update_phase",
        "log_action": "log_action",
        "log_handoff": "log_handoff",
        "noop": "noop",
    })

    for node in ["log_decision", "update_component", "log_validation",
                 "update_phase", "log_action", "log_handoff", "noop"]:
        g.add_edge(node, END)

    return g


# ---------------------------------------------------------------------------
# DevGraph interface (local, no server)
# ---------------------------------------------------------------------------

DB_PATH = Path(".cursor/state/dev_state.sqlite")
THREAD_ID = "pdftobpmn-dev"


class DevGraph:
    """Обёртка над LangGraph для удобного вызова из scribe."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer = SqliteSaver.from_conn_string(str(db_path))
        self._graph = _build_graph().compile(checkpointer=self._checkpointer)
        self._config = {"configurable": {"thread_id": THREAD_ID}}

    # --- Read ---

    def get_state(self) -> DevState:
        """Текущее состояние (orchestrator читает это)."""
        snapshot = self._graph.get_state(self._config)
        if snapshot and snapshot.values:
            return snapshot.values
        return {
            "phase": "0_poc",
            "current_task": "",
            "task_status": "planned",
            "decisions": [],
            "validations": [],
            "action_log": [],
            "handoffs": [],
            "components": {},
            "blockers": [],
            "current_gates": {"pre": "", "post": "", "retries": 0},
        }

    def get_decisions(self) -> list[dict]:
        return self.get_state().get("decisions", [])

    def get_components(self) -> dict:
        return self.get_state().get("components", {})

    # --- Write (scribe only) ---

    def _invoke(self, command: str, payload: dict):
        self._graph.invoke(
            {"_command": command, "_payload": payload},
            config=self._config,
        )

    def log_decision(self, title: str, decision: str,
                     context: str = "", rejected: list[str] | None = None,
                     revisit_if: str = ""):
        self._invoke("log_decision", {
            "title": title,
            "decision": decision,
            "context": context,
            "rejected": rejected or [],
            "revisit_if": revisit_if,
        })

    def update_component(self, name: str, status: str, tests_pass: bool = False):
        self._invoke("update_component", {
            "name": name,
            "status": status,
            "tests_pass": tests_pass,
        })

    def log_validation(self, scope: str, result: str, details: str = ""):
        self._invoke("log_validation", {
            "scope": scope,
            "result": result,
            "details": details,
        })

    def update_phase(self, phase: str, task: str = "", status: str = "planned"):
        self._invoke("update_phase", {
            "phase": phase,
            "task": task,
            "status": status,
        })

    def log_action(self, action: str, agent: str = ""):
        self._invoke("log_action", {
            "action": action,
            "agent": agent,
        })

    def log_handoff(self, handoff_id: str, from_agent: str, to_agent: str,
                    task: str = "", summary: str = "", result: str = ""):
        """Записать handoff H1-H9."""
        self._invoke("log_handoff", {
            "handoff_id": handoff_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task": task,
            "summary": summary,
            "result": result,
        })

    def get_handoffs(self, task: str | None = None) -> list[dict]:
        """Получить handoff'ы, опционально фильтр по задаче."""
        handoffs = self.get_state().get("handoffs", [])
        if task:
            return [h for h in handoffs if task in h.get("task", "")]
        return handoffs

    # --- Export (scribe → DECISIONS.md, CURRENT_STATE.md) ---

    def export_decisions_md(self) -> str:
        """Генерирует DECISIONS.md из state."""
        lines = ["# Решения проекта PDFtoBPMN v2.1\n"]
        for d in self.get_decisions():
            lines.append(f"## {d['id']}: {d['title']} ({d['date']})")
            lines.append(f"**Контекст:** {d['context']}")
            lines.append(f"**Решение:** {d['decision']}")
            if d.get("alternatives_rejected"):
                lines.append(f"**Отклонено:** {', '.join(d['alternatives_rejected'])}")
            if d.get("revisit_if"):
                lines.append(f"**Вернуться если:** {d['revisit_if']}")
            lines.append("")
        return "\n".join(lines)

    def export_current_state_md(self) -> str:
        """Генерирует CURRENT_STATE.md из state."""
        s = self.get_state()
        lines = [
            "# Текущее состояние\n",
            f"## Фаза: {s.get('phase', '?')}",
            f"## Задача: {s.get('current_task', '—')}",
            f"## Статус: {s.get('task_status', '?')}\n",
            "### Компоненты",
        ]
        for name, info in s.get("components", {}).items():
            check = "✅" if info.get("tests_pass") else "⬜"
            lines.append(f"- {check} **{name}**: {info.get('status', '?')}")

        blockers = s.get("blockers", [])
        if blockers:
            lines.append("\n### Блокеры")
            for b in blockers:
                lines.append(f"- {b.get('description', '?')}")

        last_vals = s.get("validations", [])[-5:]
        if last_vals:
            lines.append("\n### Последние валидации")
            for v in last_vals:
                icon = "✅" if v["result"] == "pass" else "❌"
                lines.append(f"- {icon} {v['scope']} ({v['date']})")

        last_handoffs = s.get("handoffs", [])[-10:]
        if last_handoffs:
            lines.append("\n### Последние handoff'ы")
            for h in last_handoffs:
                result = f" → {h['result']}" if h.get("result") else ""
                lines.append(
                    f"- {h['handoff_id']}: {h['from_agent']} → {h['to_agent']}"
                    f"{result} ({h['date']})"
                )

        return "\n".join(lines)
