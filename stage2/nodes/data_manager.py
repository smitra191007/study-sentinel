"""
stage2/nodes/data_manager.py  —  PERSON B

Formats data-quality findings into precise, record-cited queries and sends
them via POST /queries — but never twice on the same record (checked
against cross-cycle memory).

The doc's own example of a GOOD query:
    "AE 'Fatigue' starts 2026-01-08, before first dose 2026-01-13. Please
     verify the AE start date against source and correct or confirm."

And a BAD query (avoid this):
    "please check subject 042-S11-005" — names no record, asks nothing
    specific, "earns nothing."
"""

from __future__ import annotations

from stage2.api_client import ApiClient
from stage2.memory import CrossCycleMemory
from stage2.schema import Finding, QueryDraft
from stage2.trace_logger import TraceLogger


def draft_query_text(finding: Finding) -> str:
    """
    TODO (Person A): extend per finding.code with real, specific wording.
    A good query: names the record, states what looks wrong, asks for ONE
    thing. Never a vague "please check subject X".
    """
    if finding.code == "AE_BEFORE_FIRST_DOSE":
        return (
            f"{finding.rationale} Please verify the AE start date against "
            f"source and correct or confirm."
        )
    return f"{finding.rationale} Please verify against source and correct or confirm."


def process(
    findings: list[Finding],
    memory: CrossCycleMemory,
    client: ApiClient,
    cut: int,
    logger: TraceLogger,
) -> list[Finding]:
    queries_raised = 0
    duplicates_skipped = 0

    for f in findings:
        memory.touch(f.finding_id, f.usubjid, f.site, f.code)

        if memory.was_queried(f.finding_id):
            duplicates_skipped += 1
            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="skip_duplicate_query",
                rationale="record already queried in a prior cycle — never repeat",
                evidence=[e.to_dict() for e in f.evidence],
            )
            f.node_trail.append("data_manager")
            continue

        if not f.evidence:
            f.node_trail.append("data_manager")
            continue

        primary = f.evidence[0]
        draft = QueryDraft(
            usubjid=f.usubjid,
            domain=primary.domain,
            seq=primary.seq,
            cut=cut,
            text=draft_query_text(f),
        )

        try:
            response = client.post_query(draft)
            memory.mark_queried(f.finding_id)
            f.status = "queried"
            queries_raised += 1
            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision=f"query_raised (id={response.id})",
                rationale=draft.text,
                evidence=[e.to_dict() for e in f.evidence],
            )
        except Exception as exc:  # noqa: BLE001
            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="query_failed",
                rationale=str(exc),
                evidence=[e.to_dict() for e in f.evidence],
            )

        f.node_trail.append("data_manager")

    logger.log_summary(
        "data_manager",
        f"{queries_raised} queries raised, {duplicates_skipped} duplicates skipped",
    )
    return findings
