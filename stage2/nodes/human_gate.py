"""
stage2/nodes/human_gate.py  —  PERSON B

Sends escalations via POST /escalations, then handles the monitor's reply.
CRITICAL correction from the problem doc: the response is always
{"id", "decision", "reason"} — for CLARIFY, `reason` IS the question
itself, not a separate field. "Teams that treat CLARIFY as a rejection
lose points."

Also critical: an escalation already made (any decision) is NEVER
repeated — including one that was REJECTED. Re-escalating a rejected
finding is an explicit failure mode in the doc.

The CLARIFY auto-answer is the one piece worth pairing with Person A on —
see auto_answer_clarify() below.
"""

from __future__ import annotations

from stage2.api_client import ApiClient
from stage2.memory import CrossCycleMemory
from stage2.schema import EscalationDraft, Finding
from stage2.trace_logger import TraceLogger

ESCALATION_SEVERITIES = {"CRITICAL", "MAJOR"}


def needs_escalation(finding: Finding, memory: CrossCycleMemory) -> bool:
    if memory.was_escalated(finding.finding_id):
        return False  # never repeat an escalation, regardless of prior decision
    if finding.severity in ESCALATION_SEVERITIES:
        return True
    if memory.should_auto_escalate(finding.finding_id):
        return True
    return False


def auto_answer_clarify(finding: Finding, clarify_question: str) -> str:
    """
    TODO (pair with Person A): "You already hold the answer — screening ALT
    is a lab record you have, concomitant medications are in CM. Look it
    up, resubmit, and the escalation completes." Use stage1's graph/data
    access to answer factually — no further human round-trip.

    Placeholder for now.
    """
    return f"[auto-answer placeholder — needs graph lookup for]: {clarify_question}"


def process(
    findings: list[Finding],
    memory: CrossCycleMemory,
    client: ApiClient,
    logger: TraceLogger,
) -> list[Finding]:
    escalations_raised = 0

    for f in findings:
        if f.status == "queried":
            f.node_trail.append("human_gate")
            continue

        if not needs_escalation(f, memory):
            f.node_trail.append("human_gate")
            continue

        draft = EscalationDraft(
            code=f.code,
            usubjid=f.usubjid,
            severity=f.severity,
            summary=f.rationale,
            evidence=f.evidence,
            alternatives=f.alternatives,
        )

        try:
            response = client.post_escalation(draft)
            memory.mark_escalated(f.finding_id, decision=response.decision)
            escalations_raised += 1

            if response.decision == "APPROVED":
                f.status = "resolved"
                memory.mark_resolved(f.finding_id)
                logger.log(
                    "human_gate", f.finding_id,
                    f"{f.code} {f.usubjid} -> APPROVED",
                    response.reason,
                    [e.to_dict() for e in f.evidence],
                )

            elif response.decision == "REJECTED":
                f.status = "resolved"
                memory.mark_resolved(f.finding_id)
                logger.log(
                    "human_gate", f.finding_id,
                    f"{f.code} {f.usubjid} -> REJECTED",
                    response.reason,
                    [e.to_dict() for e in f.evidence],
                )

            elif response.decision == "CLARIFY":
                # response.reason IS the clarify question here.
                answer = auto_answer_clarify(f, response.reason)
                logger.log(
                    "human_gate", f.finding_id,
                    "CLARIFY received — auto-answering, not rejecting",
                    f"question={response.reason!r} answer={answer!r}",
                    [e.to_dict() for e in f.evidence],
                )
                resolved_response = client.resubmit_escalation_with_clarification(draft, answer)
                if resolved_response.decision == "APPROVED":
                    f.status = "resolved"
                    memory.mark_resolved(f.finding_id)
                elif resolved_response.decision == "REJECTED":
                    f.status = "resolved"
                    memory.mark_resolved(f.finding_id)
                # If it comes back CLARIFY again, leave status as "escalated"
                # rather than looping indefinitely within one cycle.
                else:
                    f.status = "escalated"
                logger.log(
                    "human_gate", f.finding_id,
                    f"resubmitted -> {resolved_response.decision}",
                    resolved_response.reason,
                    [e.to_dict() for e in f.evidence],
                )

        except Exception as exc:  # noqa: BLE001
            logger.log(
                "human_gate", f.finding_id, "escalation_failed", str(exc),
                [e.to_dict() for e in f.evidence],
            )

        f.node_trail.append("human_gate")

    logger.log_summary("human_gate", f"{escalations_raised} escalations raised this cycle")
    return findings
