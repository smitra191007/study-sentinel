"""
stage2/nodes/data_manager.py — PERSON B (infra) + PERSON A (query wording)

Formats data-quality findings into precise, record-cited queries and sends
them via POST /queries — but never twice on the same record (checked
against cross-cycle memory).
"""

from __future__ import annotations

from stage2.api_client import ApiClient
from stage2.memory import CrossCycleMemory
from stage2.schema import Finding, QueryDraft
from stage2.trace_logger import TraceLogger


def draft_query_text(finding: Finding) -> str:
    """
    Per-code query wording. A good query names the record, states what
    looks wrong, and asks for ONE thing — never a vague "please check
    subject X".
    """

    refs = ", ".join(f"{e.domain}:{e.seq}" for e in finding.evidence)

    if finding.code == "AE_BEFORE_FIRST_DOSE":
        return (
            f"{finding.rationale} Please verify the AE start date against "
            f"source and correct or confirm."
        )

    elif finding.code == "visit_window_deviations":
        return (
            f"Visit for subject {finding.usubjid} occurred outside "
            f"the protocol window. {finding.rationale} "
            f"Please confirm the actual visit date and protocol deviation. "
            f"(refs: {refs})"
        )

    elif finding.code == "prohibited_medication_use":
        return (
            f"Subject {finding.usubjid} has a concomitant medication "
            f"flagged as prohibited under the applicable protocol. "
            f"{finding.rationale} Please confirm or correct the medication "
            f"information. (refs: {refs})"
        )

    elif finding.code == "seriousness_miscoded":
        return (
            f"AE record for subject {finding.usubjid} may be miscoded "
            f"as non-serious. {finding.rationale} "
            f"Please review and confirm the correct seriousness classification. "
            f"(refs: {refs})"
        )

    elif finding.code == "dosing_errors":
        return (
            f"Exposure record for subject {finding.usubjid} contains "
            f"a possible dosing discrepancy. {finding.rationale} "
            f"Please confirm the administered dose and treatment arm. "
            f"(refs: {refs})"
        )

    elif finding.code == "hys_law_candidates":
        return (
            f"Subject {finding.usubjid} has laboratory findings that "
            f"meet a potential Hy's Law signal. {finding.rationale} "
            f"Please review the relevant laboratory results and confirm "
            f"the clinical interpretation. (refs: {refs})"
        )

    else:
        return (
            f"Please review finding for subject {finding.usubjid}: "
            f"{finding.rationale} (refs: {refs})"
        )


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

        memory.touch(
            f.finding_id,
            f.usubjid,
            f.site,
            f.code,
        )

        # Never send the same query twice.
        if memory.was_queried(f.finding_id):
            duplicates_skipped += 1

            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="skip_duplicate_query",
                rationale=(
                    "record already queried in a prior cycle — never repeat"
                ),
                evidence=[
                    e.to_dict()
                    for e in f.evidence
                ],
            )

            f.node_trail.append("data_manager")
            continue

        # Nothing to cite → nothing to query.
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
            # FIX:
            # ApiClient.post_query() expects:
            #   subject_id
            #   query_text
            #   record_refs
            response = client.post_query(
                subject_id=draft.usubjid,
                query_text=draft.text,
                record_refs=[
                    {
                        "domain": draft.domain,
                        "seq": draft.seq,
                    }
                ],
            )

            memory.mark_queried(f.finding_id)

            f.status = "queried"
            queries_raised += 1

            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision=f"query_raised (id={response['id']})",
                rationale=draft.text,
                evidence=[
                    e.to_dict()
                    for e in f.evidence
                ],
            )

        except Exception as exc:  # noqa: BLE001

            logger.log(
                node="data_manager",
                finding_id=f.finding_id,
                decision="query_failed",
                rationale=str(exc),
                evidence=[
                    e.to_dict()
                    for e in f.evidence
                ],
            )

        f.node_trail.append("data_manager")

    logger.log_summary(
        "data_manager",
        f"{queries_raised} queries raised, "
        f"{duplicates_skipped} duplicates skipped",
    )

    return findings