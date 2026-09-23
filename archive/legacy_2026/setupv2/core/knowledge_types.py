"""
Knowledge types: 13 типов артефактов, извлекаемых из СМК документов.
Provenance: откуда извлечён каждый артефакт.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class KnowledgeType(Enum):
    """13 типов артефактов."""
    DEFINITION      = "definition"
    ABBREVIATION    = "abbreviation"
    DOCUMENT_REF    = "document_ref"
    FORMULA         = "formula"
    FORM_TEMPLATE   = "form_template"
    ROLE            = "role"
    PROCESS_STEP    = "process_step"
    DECISION_RULE   = "decision_rule"
    KPI             = "kpi"
    CONTROL         = "control"
    INPUT_OUTPUT    = "input_output"
    ORG_UNIT        = "org_unit"
    SYSTEM          = "system"


@dataclass
class Provenance:
    """Откуда извлечён артефакт."""
    document_code: str
    document_version: str
    section: str
    page: int
    paragraph: Optional[str] = None
    document_authority: str = "canonical"  # canonical / superseded / draft
    extraction_method: str = ""            # rule_based / llm_based
    confidence: float = 1.0                # 0.0-1.0


@dataclass
class KnowledgeArtifact:
    """Единица знания, извлечённая из документа."""
    id: str
    type: KnowledgeType
    content: dict                          # Специфично для типа
    provenance: Provenance
    relations: list[dict] = field(default_factory=list)
