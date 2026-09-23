"""
Edge types: typed relations in the organizational knowledge graph.
BPMN-oriented edges enable direct rendering of process diagrams from graph.
"""

from enum import Enum


class EdgeType(Enum):
    """Типы рёбер в организационном графе."""

    # RACI responsibility
    RESPONSIBLE_FOR  = "responsible_for"    # R: кто делает
    ACCOUNTABLE_FOR  = "accountable_for"    # A: кто отвечает
    CONSULTED_IN     = "consulted_in"       # C: с кем консультируются
    INFORMED_OF      = "informed_of"        # I: кого информируют

    # Process flow (BPMN mapping)
    SEQUENCE         = "sequence"           # Step → Step (SequenceFlow)
    DECISION         = "decision"           # Step → DecisionRule → Step (Gateway)
    PARALLEL         = "parallel"           # Parallel split/join

    # Data flow
    INPUTS           = "inputs"             # Input → Step
    OUTPUTS          = "outputs"            # Step → Output
    USES_SYSTEM      = "uses_system"        # Step → System

    # Measurement
    MEASURES         = "measures"           # KPI → Step or Role
    TARGET           = "target"             # KPI → target value

    # Control
    CONTROLS         = "controls"           # Control → Step
    MITIGATES        = "mitigates"          # Control → Risk

    # Document
    REFERENCES       = "references"         # DocumentRef → Document
    DEFINED_IN       = "defined_in"         # Any node → Document (provenance)
    SUPERSEDES       = "supersedes"         # Document → Document (authority)

    # Organization
    PART_OF          = "part_of"            # Role → OrgUnit
    REPORTS_TO       = "reports_to"         # Role → Role
