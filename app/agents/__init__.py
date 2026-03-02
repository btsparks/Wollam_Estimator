"""WEIS Bid Intelligence Agents.

Agent registry for Phase 3 document review agents.
"""

from app.agents.document_control import DocumentControlAgent
from app.agents.legal import LegalAgent
from app.agents.quality import QualityAgent
from app.agents.safety import SafetyAgent
from app.agents.subcontract import SubcontractAgent

# Ordered: Document Control first, then parallel reviewers
AGENT_REGISTRY: dict[str, type] = {
    "document_control": DocumentControlAgent,
    "legal": LegalAgent,
    "quality": QualityAgent,
    "safety": SafetyAgent,
    "subcontract": SubcontractAgent,
}

__all__ = [
    "AGENT_REGISTRY",
    "DocumentControlAgent",
    "LegalAgent",
    "QualityAgent",
    "SafetyAgent",
    "SubcontractAgent",
]
