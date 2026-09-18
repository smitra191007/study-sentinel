"""
stage2/schema.py

THE SHARED CONTRACT. Agree on this together before either of you writes a
node. Every node in crew.py takes a list[Finding] and returns a list[Finding]
(possibly enriched, possibly with new status). Nothing else should need to
change shape as it flows through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FindingStatus = Literal["open", "queried", "escalated", "resolved", "auto_answered"]


@dataclass
class Finding:
    """
    One unit flowing through the pipeline. Starts life as a raw Stage 1
    detection, gets enriched by medical review + compliance, then acted on
    by data manager / human gate.
    """
    finding_id: str          # stable, deterministic ID — see make_finding_id()
    subject_id: str
    site_id: str
    finding_type: str        # e.g. "ae_serious_override", "visit_window", "hys_law"
    detail: str
    record_refs: list[str] = field(default_factory=list)
    status: FindingStatus = "open"
    cycle_count: int = 0       # bumped by memory layer when seen again unresolved
    severity: str | None = None      # set by medical review, e.g. "critical" | "major" | "minor"
    protocol_version: str | None = None  # set by compliance node
    node_trail: list[str] = field(default_factory=list)  # which nodes have touched this


@dataclass
class QueryDraft:
    """What the data manager sends via POST /queries."""
    finding_id: str
    subject_id: str
    query_text: str
    record_refs: list[str]


@dataclass
class Escalation:
    """What the human gate sends via POST /escalations."""
    finding_id: str
    subject_id: str
    reason: str
    record_refs: list[str]


def make_finding_id(subject_id: str, finding_type: str, detail_key: str) -> str:
    """
    Deterministic ID so the same underlying issue always maps to the same
    finding_id across cycles — this is what makes de-duplication possible.
    detail_key should be something stable about the finding (e.g. a visit_id
    or lab_id), NOT the free-text detail string (which might get reworded).
    """
    return f"{subject_id}:{finding_type}:{detail_key}"
