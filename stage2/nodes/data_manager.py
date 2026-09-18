"""
stage2/nodes/data_manager.py  —  PERSON B

Formats data-quality findings into precise, record-cited queries and sends
them via POST /queries — but only if this exact finding hasn't already been
queried in a previous cycle (checked against cross-cycle memory).

The QUERY TEXT TEMPLATE (what the query actually says) is intentionally a
placeholder here — Person A owns deciding what a good query reads like for
each finding_type. Swap draft_query_text() for their logic once it exists.
"""

from __future__ import annotations

from stage2 import api_client
from stage2.memory import CrossCycleMemory
from stage2.schema import Finding, QueryDraft
from stage2.trace_logger import TraceLogger


def draft_query_text(finding: Finding) -> str:
    """
    TODO (Person A): replace with real per-finding-type query wording.
    Keep it short, specific, and cite the record.
    """
    return f"Please confirm/correct: {finding.detail} (refs: {', '.join(finding.record_refs)})"


def process(findings: list[Finding], memory: CrossCycleMemory, logger: TraceLogger) -> list[Finding]:
    for f in findings:
        memory.touch(f.finding_id, f.subject_id, f.site_id, f.finding_type)

        if memory.was_queried(f.finding_id):
            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="skip_duplicate_query",
                rationale="already queried in a prior cycle",
                evidence=f.record_refs,
            )
            f.node_trail.append("data_manager")
            continue

        draft = QueryDraft(
            finding_id=f.finding_id,
            subject_id=f.subject_id,
            query_text=draft_query_text(f),
            record_refs=f.record_refs,
        )

        try:
            api_client.post_query(draft.subject_id, draft.query_text, draft.record_refs)
            memory.mark_queried(f.finding_id)
            f.status = "queried"
            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="query_sent",
                rationale=draft.query_text,
                evidence=f.record_refs,
            )
        except Exception as exc:  # noqa: BLE001
            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="query_failed",
                rationale=str(exc),
                evidence=f.record_refs,
            )

        f.node_trail.append("data_manager")

    return findings
