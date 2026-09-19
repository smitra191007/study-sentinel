from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RecordRef:
    domain: str
    usubjid: Optional[str] = None
    seq: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "usubjid": self.usubjid,
            "seq": self.seq,
        }


@dataclass
class Decision:
    decision_id: str
    cut: int
    node: str
    action: str
    reason: str
    status: str = "OPEN"
    evidence: List[RecordRef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "cut": self.cut,
            "node": self.node,
            "action": self.action,
            "reason": self.reason,
            "status": self.status,
            "evidence": [ref.to_dict() for ref in self.evidence],
            "metadata": self.metadata,
        }


@dataclass
class Explanation:
    decision_id: str
    what: str
    evidence: List[RecordRef] = field(default_factory=list)
    evidence_lines: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    why: str = ""
    consistent_with_trace: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "what": self.what,
            "evidence": [ref.to_dict() for ref in self.evidence],
            "evidence_lines": self.evidence_lines,
            "alternatives": self.alternatives,
            "why": self.why,
            "consistent_with_trace": self.consistent_with_trace,
        }


@dataclass
class SurveillanceReport:
    cuts_processed: List[int] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    site_risk: List[Dict[str, Any]] = field(default_factory=list)
    deviations: List[Dict[str, Any]] = field(default_factory=list)
    adversarial_events: List[Dict[str, Any]] = field(default_factory=list)
    open_items: List[Dict[str, Any]] = field(default_factory=list)

    budget_total: float = 0.0
    budget_used: float = 0.0
    narrative_enabled: bool = True

    decisions: List[Decision] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cuts_processed": self.cuts_processed,
            "signals": self.signals,
            "site_risk": self.site_risk,
            "deviations": self.deviations,
            "adversarial_events": self.adversarial_events,
            "open_items": self.open_items,
            "budget": {
                "total": self.budget_total,
                "used": self.budget_used,
                "narrative_enabled": self.narrative_enabled,
            },
            "decisions": [
                decision.to_dict()
                for decision in self.decisions
            ],
        }