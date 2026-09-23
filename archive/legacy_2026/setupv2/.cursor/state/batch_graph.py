"""
Batch Pipeline Graph — обработка документов (Фаза 4).

Локальный LangGraph с SqliteSaver:
- Checkpoint: упало на документе #247 → продолжить с #247.
- HITL: пауза после extraction → human проверяет ProcessSpec.
- Routing: canonical → full pipeline, superseded → только RAG index.

Использование:

    from pipeline.batch_graph import BatchPipeline
    
    pipeline = BatchPipeline()
    
    # Обработать один документ (с паузой на human review)
    pipeline.run("input/РД-Б7.004-06.pdf")
    
    # После human review — продолжить
    pipeline.resume(approved=True)
    
    # Batch: обработать все документы из папки
    pipeline.run_batch("input/", max_concurrent=4)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class DocState(TypedDict, total=False):
    """Состояние обработки одного документа."""

    # Input
    document_path: str
    document_code: str                # РД-Б7.004-06
    document_family: str              # РД-Б7.004

    # Authority
    authority: str                    # canonical | superseded | draft

    # Pipeline results (заполняются поэтапно)
    page_classes: dict                # {page_num: "content" | "approval" | ...}
    docling_result: dict              # DoclingDocument JSON
    artifacts: list[dict]             # KnowledgeArtifacts
    processspec: dict                 # ProcessSpec YAML as dict
    bpmn_path: str                    # path to generated BPMN
    rag_indexed: bool                 # chunks indexed in ChromaDB

    # Status
    status: str                       # pending | ingested | extracted | reviewed |
                                      # compiled | indexed | done | failed | skipped
    error: str
    started_at: str
    finished_at: str

    # HITL
    human_approved: bool              # True after human reviews ProcessSpec


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def ingest(state: DocState) -> dict:
    """Docling + OCR + page classifier + authority resolver."""
    logger.info("📄 Ingesting %s", state["document_path"])
    # TODO: Реализация в Фазе 1
    # 1. page_classifier → page_classes
    # 2. docling_adapter → docling_result
    # 3. authority_resolver → authority
    return {
        "status": "ingested",
        "started_at": datetime.now().isoformat(timespec="minutes"),
        # "page_classes": {...},
        # "docling_result": {...},
        # "authority": "canonical",
    }


def extract(state: DocState) -> dict:
    """Typed extraction: 13 типов артефактов (Claude API)."""
    logger.info("🔍 Extracting artifacts from %s", state["document_code"])
    # TODO: Реализация в Фазе 2
    # 1. rule_based extractors → definitions, abbreviations, refs, formulas
    # 2. llm_based extractors (Claude API) → roles, steps, decisions, kpi
    # 3. artifact_assembler → list[KnowledgeArtifact]
    return {
        "status": "extracted",
        # "artifacts": [...],
    }


def assemble_processspec(state: DocState) -> dict:
    """Артефакты → ProcessSpec.yaml."""
    logger.info("📋 Assembling ProcessSpec for %s", state["document_code"])
    # TODO: Реализация в Фазе 2
    # processspec_assembler: artifacts → ProcessSpec
    # schema validation
    return {
        "status": "assembled",
        # "processspec": {...},
    }


def human_review(state: DocState) -> dict:
    """HITL checkpoint: human проверяет ProcessSpec перед BPMN.
    
    LangGraph interrupt_before останавливает здесь.
    Human проверяет processspec, утверждает или корректирует.
    Resume с human_approved=True продолжает pipeline.
    """
    logger.info("⏸️  Waiting for human review of ProcessSpec: %s", state["document_code"])
    return {"status": "reviewed"}


def compile_bpmn(state: DocState) -> dict:
    """ProcessSpec → BPMN XML (код, не AI)."""
    logger.info("🏗️  Compiling BPMN for %s", state["document_code"])
    # TODO: Реализация в Фазе 3B
    # bpmn_compiler: processspec → BPMN XML
    # layout_engine: координаты
    # camunda_validator: schema check
    return {
        "status": "compiled",
        # "bpmn_path": "output/РД-Б7.004-06/РД-Б7.004-06.bpmn",
    }


def inject_guids(state: DocState) -> dict:
    """Подставить BS GUID из реестра."""
    logger.info("🔗 Injecting BS GUIDs for %s", state["document_code"])
    # TODO: Реализация в Фазе 4
    # bpmn_guid_injector: BPMN + bs_guid_registry → BPMN with GUIDs
    # bs_coordinate_adapter: координаты под холст BS
    return {"status": "guid_injected"}


def index_rag(state: DocState) -> dict:
    """Индексация chunks в ChromaDB для RAG."""
    logger.info("📇 Indexing RAG chunks for %s", state["document_code"])
    # TODO: Реализация в Фазе 3A
    # chunker → chunks with metadata (doc_code, section, authority)
    # indexer → ChromaDB
    return {
        "status": "indexed",
        "rag_indexed": True,
    }


def finalize(state: DocState) -> dict:
    """Финализация: статус done."""
    logger.info("✅ Done: %s", state["document_code"])
    return {
        "status": "done",
        "finished_at": datetime.now().isoformat(timespec="minutes"),
    }


def skip(state: DocState) -> dict:
    """Superseded/draft документ — только RAG index, без BPMN."""
    logger.info("⏭️  Skipping BPMN for %s (authority=%s)", 
                state["document_code"], state["authority"])
    return {"status": "skipped_bpmn"}


def handle_error(state: DocState) -> dict:
    """Обработка ошибки."""
    logger.error("❌ Failed: %s — %s", state["document_code"], state.get("error", "?"))
    return {"status": "failed"}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_by_authority(state: DocState) -> str:
    """Canonical → full pipeline, superseded/draft → только RAG."""
    if state.get("authority") == "canonical":
        return "extract"
    return "skip"


def route_after_review(state: DocState) -> str:
    """Human approved → compile, rejected → stop."""
    if state.get("human_approved", False):
        return "compile_bpmn"
    return "handle_error"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_batch_graph() -> StateGraph:
    g = StateGraph(DocState)

    # Nodes
    g.add_node("ingest", ingest)
    g.add_node("extract", extract)
    g.add_node("assemble", assemble_processspec)
    g.add_node("human_review", human_review)
    g.add_node("compile_bpmn", compile_bpmn)
    g.add_node("inject_guids", inject_guids)
    g.add_node("index_rag", index_rag)
    g.add_node("finalize", finalize)
    g.add_node("skip", skip)
    g.add_node("handle_error", handle_error)

    # Edges
    g.set_entry_point("ingest")

    # After ingest: canonical → extract, other → skip to RAG
    g.add_conditional_edges("ingest", route_by_authority, {
        "extract": "extract",
        "skip": "skip",
    })

    # Canonical path: extract → assemble → human review → compile → guids → RAG → done
    g.add_edge("extract", "assemble")
    g.add_edge("assemble", "human_review")

    g.add_conditional_edges("human_review", route_after_review, {
        "compile_bpmn": "compile_bpmn",
        "handle_error": "handle_error",
    })

    g.add_edge("compile_bpmn", "inject_guids")
    g.add_edge("inject_guids", "index_rag")
    g.add_edge("index_rag", "finalize")
    g.add_edge("finalize", END)

    # Superseded path: skip → RAG only → done
    g.add_edge("skip", "index_rag")

    # Error → END
    g.add_edge("handle_error", END)

    return g


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

BATCH_DB = Path(".cursor/state/batch_pipeline.sqlite")


class BatchPipeline:
    """Обёртка для batch processing."""

    def __init__(self, db_path: Path = BATCH_DB):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer = SqliteSaver.from_conn_string(str(db_path))
        self._graph = build_batch_graph().compile(
            checkpointer=self._checkpointer,
            interrupt_before=["human_review"],   # HITL: пауза перед review
        )

    def run(self, document_path: str, document_code: str = "",
            authority: str = "canonical") -> DocState:
        """Запустить pipeline для одного документа."""
        config = {"configurable": {"thread_id": document_code or document_path}}
        result = self._graph.invoke(
            {
                "document_path": document_path,
                "document_code": document_code,
                "authority": authority,
                "status": "pending",
            },
            config=config,
        )
        return result

    def resume(self, document_code: str, human_approved: bool = True) -> DocState:
        """Продолжить после human review."""
        config = {"configurable": {"thread_id": document_code}}
        result = self._graph.invoke(
            {"human_approved": human_approved},
            config=config,
        )
        return result

    def get_status(self, document_code: str) -> DocState | None:
        """Получить статус документа."""
        config = {"configurable": {"thread_id": document_code}}
        snapshot = self._graph.get_state(config)
        return snapshot.values if snapshot else None

    def run_batch(self, input_dir: str, max_docs: int | None = None):
        """Batch: обработать все PDF/DOCX из папки."""
        input_path = Path(input_dir)
        docs = sorted(input_path.glob("*.pdf")) + sorted(input_path.glob("*.docx"))
        if max_docs:
            docs = docs[:max_docs]

        logger.info("📦 Batch: %d documents from %s", len(docs), input_dir)

        for i, doc in enumerate(docs, 1):
            code = doc.stem
            existing = self.get_status(code)

            # Skip already done
            if existing and existing.get("status") == "done":
                logger.info("⏭️  [%d/%d] %s already done", i, len(docs), code)
                continue

            logger.info("📄 [%d/%d] Processing %s", i, len(docs), code)
            try:
                self.run(str(doc), document_code=code)
            except Exception as e:
                logger.error("❌ [%d/%d] %s failed: %s", i, len(docs), code, e)

    def visualize(self) -> str:
        """Mermaid-диаграмма графа."""
        return self._graph.get_graph().draw_mermaid()
