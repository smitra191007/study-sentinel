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
    refs = ", ".join(finding.record_refs)

    if finding.finding_type == "visit_window_deviations":
        return (
            f"Visit for subject {finding.subject_id} occurred outside "
            f"the protocol window. {finding.detail} "
            f"Please confirm the actual visit date and protocol deviation. "
            f"(refs: {refs})"
        )

    elif finding.finding_type == "prohibited_medication_use":
        return (
            f"Subject {finding.subject_id} has a concomitant medication "
            f"flagged as prohibited under the applicable protocol. "
            f"{finding.detail} Please confirm or correct the medication "
            f"information. (refs: {refs})"
        )

    elif finding.finding_type == "seriousness_miscoded":
        return (
            f"AE record for subject {finding.subject_id} may be miscoded "
            f"as non-serious. {finding.detail} "
            f"Please review and confirm the correct seriousness classification. "
            f"(refs: {refs})"
        )

    elif finding.finding_type == "dosing_errors":
        return (
            f"Exposure record for subject {finding.subject_id} contains "
            f"a possible dosing discrepancy. {finding.detail} "
            f"Please confirm the administered dose and treatment arm. "
            f"(refs: {refs})"
        )

    elif finding.finding_type == "hys_law_candidates":
        return (
            f"Subject {finding.subject_id} has laboratory findings that "
            f"meet a potential Hy's Law signal. {finding.detail} "
            f"Please review the relevant laboratory results and confirm "
            f"the clinical interpretation. (refs: {refs})"
        )

    else:
        return (
            f"Please review finding for subject {finding.subject_id}: "
            f"{finding.detail} (refs: {refs})"
        )


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
