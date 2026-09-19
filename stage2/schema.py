"""
stage2/schema.py

THE SHARED CONTRACT — matches the exact JSON shapes from the problem
statement (Study_Sentinel_Problem_2_Monitor.docx). Field names here are
NOT arbitrary — they mirror what Stage 1 actually emits and what the
gateway API actually expects, so no translation layer is needed at the
API boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FindingStatus = Literal["open", "queried", "escalated", "resolved", "auto_answered"]


@dataclass
class EvidenceRef:
    """One entry in a finding's `evidence` list — a pointer to a source record."""
    domain: str      # e.g. "AE", "LB", "CM"
    usubjid: str
    seq: int

    def to_dict(self) -> dict:
        return {"domain": self.domain, "usubjid": self.usubjid, "seq": self.seq}

    @staticmethod
    def from_dict(d: dict) -> "EvidenceRef":
        return EvidenceRef(domain=d["domain"], usubjid=d["usubjid"], seq=d["seq"])


@dataclass
class Finding:
    """
    One unit flowing through the pipeline. Field names match Stage 1's raw
    output exactly:
        {"code": "SAE_MISCODED", "usubjid": "042-S02-004", "site": "S02",
         "severity": "CRITICAL", "rationale": "...",
         "evidence": [{"domain": "AE", "usubjid": "042-S02-004", "seq": 1}]}
    """
    finding_id: str          # our own stable ID — see make_finding_id()
    code: str                 # e.g. "SAE_MISCODED", "VISIT_WINDOW", "PROHIBITED_MED"
    usubjid: str
    site: str
    severity: str              # "CRITICAL" | "MAJOR" | "MINOR" | ... (Stage 1's own scale)
    rationale: str
    evidence: list[EvidenceRef] = field(default_factory=list)

    status: FindingStatus = "open"
    cycle_count: int = 0        # bumped by memory layer when seen again unresolved
    protocol_version: int | None = None   # set by compliance node
    alternatives: list[str] = field(default_factory=list)  # set by medical review
    node_trail: list[str] = field(default_factory=list)

    @staticmethod
    def from_raw(raw: dict) -> "Finding":
        """Build a Finding from Stage 1's raw dict output."""
        evidence = [EvidenceRef.from_dict(e) for e in raw.get("evidence", [])]
        return Finding(
            finding_id=make_finding_id(raw["usubjid"], raw["code"], evidence),
            code=raw["code"],
            usubjid=raw["usubjid"],
            site=raw.get("site", ""),
            severity=raw.get("severity", ""),
            rationale=raw.get("rationale", ""),
            evidence=evidence,
        )


@dataclass
class QueryDraft:
    """Body for POST /queries — matches the doc's exact shape."""
    usubjid: str
    domain: str
    seq: int
    cut: int
    text: str

    def to_dict(self) -> dict:
        return {
            "usubjid": self.usubjid,
            "domain": self.domain,
            "seq": self.seq,
            "cut": self.cut,
            "text": self.text,
        }


@dataclass
class EscalationDraft:
    """Body for POST /escalations — matches the doc's exact shape."""
    code: str
    usubjid: str
    severity: str
    summary: str
    evidence: list[EvidenceRef]
    alternatives: list[str]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "usubjid": self.usubjid,
            "severity": self.severity,
            "summary": self.summary,
            "evidence": [e.to_dict() for e in self.evidence],
            "alternatives": self.alternatives,
        }


@dataclass
class EscalationResponse:
    """
    Response from POST /escalations. All three decisions carry `reason` —
    for CLARIFY, `reason` IS the clarify question itself (not a separate
    field). This is the #1 thing the problem doc warns teams get wrong.
    """
    id: str
    decision: Literal["APPROVED", "REJECTED", "CLARIFY"]
    reason: str

    @staticmethod
    def from_dict(d: dict) -> "EscalationResponse":
        return EscalationResponse(id=d["id"], decision=d["decision"], reason=d["reason"])


@dataclass
class QueryResponse:
    """Response from POST /queries once the site replies."""
    id: str
    status: Literal["OPEN", "CLOSED"]
    response: str | None = None

    @staticmethod
    def from_dict(d: dict) -> "QueryResponse":
        return QueryResponse(id=d["id"], status=d["status"], response=d.get("response"))


def make_finding_id(usubjid: str, code: str, evidence: list[EvidenceRef]) -> str:
    """
    Deterministic ID so the same underlying record-level issue always maps
    to the same finding_id across cycles — this is what makes the "raise a
    query on a record only once, ever" rule enforceable.

    Keyed off the FIRST evidence record (domain + seq), not the free-text
    rationale, since rationale wording could change between cycles for the
    same underlying issue.
    """
    if evidence:
        e = evidence[0]
        return f"{usubjid}:{code}:{e.domain}:{e.seq}"
    return f"{usubjid}:{code}"
