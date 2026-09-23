"""
Storage protocols: GraphStore (SSOT) + VectorStore (text index).
Implementations: NetworkX + SQLite (MVP), ChromaDB.
"""

from __future__ import annotations
from typing import Protocol, Optional

from core.knowledge_types import KnowledgeArtifact, KnowledgeType


class GraphStore(Protocol):
    """Organizational Knowledge Graph — SSOT.
    NetworkX + SQLite сейчас, graph DB потом."""

    # --- Write (extraction pipeline) ---
    def add_artifact(self, artifact: KnowledgeArtifact) -> str: ...
    def add_relation(self, source: str, target: str,
                     rel_type: str, props: dict | None = None) -> None: ...
    def delete_by_document(self, doc_code: str) -> None: ...

    # --- Read: general ---
    def query_neighbors(self, node_id: str, hops: int = 1,
                        edge_types: list[str] | None = None) -> list: ...
    def query_by_type(self, artifact_type: KnowledgeType) -> list: ...
    def query_by_document(self, doc_code: str) -> list: ...

    # --- Read: BPMN view ---
    def query_process(self, doc_code: str) -> dict:
        """Roles, steps, decisions, flows for BPMN rendering.""" ...

    # --- Read: RACI view ---
    def query_raci(self, doc_code: str) -> list[dict]:
        """Role × Step × RACI type matrix.""" ...

    # --- Read: KPI view ---
    def query_kpi(self, org_unit: str | None = None) -> list[dict]:
        """KPI nodes + measures edges + targets.""" ...

    # --- Read: Control coverage ---
    def query_controls(self, scope: str | None = None) -> list[dict]:
        """Controls + controlled steps + gaps.""" ...

    # --- Read: RAG traversal ---
    def query_for_rag(self, entities: list[str],
                      edge_types: list[str] | None = None,
                      max_hops: int = 2) -> list[dict]:
        """Structured context for RAG response builder.""" ...

    # --- Persistence ---
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...


class VectorStore(Protocol):
    """Text index for free-form search. ChromaDB сейчас, Qdrant потом."""
    def index(self, chunks: list) -> None: ...
    def search_dense(self, query: str, top_k: int = 20) -> list: ...
    def search_sparse(self, query: str, top_k: int = 20) -> list: ...
    def delete_by_document(self, doc_code: str) -> None: ...
