"""
Тест: dev_graph persistence, append-only decisions, export.
Запустить: pytest tests/test_dev_graph.py -v
"""

import tempfile
from pathlib import Path

from state.dev_graph import DevGraph


def test_decision_append_only():
    """Decisions append-only: два решения → оба сохраняются."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        g = DevGraph(db_path=db)

        g.log_decision(
            title="OCR: RapidOCR",
            decision="RapidOCR через Docling",
            context="POC: 94% vs 91%",
            rejected=["EasyOCR", "Tesseract"],
        )
        g.log_decision(
            title="Граф знаний: убран из MVP",
            decision="Metadata-rich chunks в ChromaDB",
            context="Из 6 типов запросов 1 требует multi-hop",
            revisit_if="multi-hop проседает после запуска RAG",
        )

        decisions = g.get_decisions()
        assert len(decisions) == 2
        assert decisions[0]["id"] == "D-001"
        assert decisions[1]["id"] == "D-002"
        assert "RapidOCR" in decisions[0]["title"]
        assert "Граф" in decisions[1]["title"]


def test_component_status():
    """Компоненты обновляются, не дублируются."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        g = DevGraph(db_path=db)

        g.update_component("ingestion", status="in_progress", tests_pass=False)
        g.update_component("ingestion", status="done", tests_pass=True)

        components = g.get_components()
        assert components["ingestion"]["status"] == "done"
        assert components["ingestion"]["tests_pass"] is True


def test_validation_log():
    """Валидации записываются."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        g = DevGraph(db_path=db)

        g.log_validation(scope="test_ingestion.py", result="pass", details="12/12 tests")
        g.log_validation(scope="test_extraction.py", result="fail", details="3/10 tests")

        state = g.get_state()
        assert len(state["validations"]) == 2
        assert state["validations"][0]["result"] == "pass"
        assert state["validations"][1]["result"] == "fail"


def test_phase_update():
    """Фаза и задача обновляются."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        g = DevGraph(db_path=db)

        g.update_phase("2_extraction", task="TASK-005: role_extractor", status="in_progress")

        state = g.get_state()
        assert state["phase"] == "2_extraction"
        assert "TASK-005" in state["current_task"]


def test_export_decisions_md():
    """Export → DECISIONS.md формат."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        g = DevGraph(db_path=db)

        g.log_decision(title="Test", decision="Yes", context="Because")
        md = g.export_decisions_md()

        assert "# Решения проекта" in md
        assert "D-001" in md
        assert "**Решение:** Yes" in md


def test_persistence_between_instances():
    """State сохраняется между инстансами (имитация перезапуска сессии)."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"

        # Сессия 1: записать
        g1 = DevGraph(db_path=db)
        g1.log_decision(title="Alpha", decision="Go")
        g1.update_component("ingestion", status="done", tests_pass=True)

        # Сессия 2: прочитать (новый инстанс, тот же файл)
        g2 = DevGraph(db_path=db)
        assert len(g2.get_decisions()) == 1
        assert g2.get_components()["ingestion"]["status"] == "done"
