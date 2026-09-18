"""
stage2/nodes/human_gate.py  —  PERSON B

Sends escalations for findings that need human sign-off (critical severity,
or auto-escalated after recurring `threshold` cycles unresolved), then
handles the monitor's response:
  - APPROVED -> mark resolved
  - REJECTED -> mark resolved (rejected, but no further action this cycle)
  - CLARIFY  -> auto-answer using graph data, without a further human round-trip

The CLARIFY auto-answer is the one piece worth pairing with Person A on —
it needs both graph access (this file) and knowing what a clarify question
is actually asking (their domain knowledge). See auto_answer_clarify() below.
"""

from __future__ import annotations

from stage2 import api_client
from stage2.memory import CrossCycleMemory
from stage2.schema import Escalation, Finding
from stage2.trace_logger import TraceLogger

ESCALATION_SEVERITIES = {"critical", "major"}
AUTO_ESCALATE_CYCLE_THRESHOLD = 3


def needs_escalation(finding: Finding, memory: CrossCycleMemory) -> bool:
    if finding.severity in ESCALATION_SEVERITIES:
        return True
    if memory.should_auto_escalate(finding.finding_id, threshold=AUTO_ESCALATE_CYCLE_THRESHOLD):
        return True
    return False


def auto_answer_clarify(finding: Finding, clarify_question: str) -> str:
    """
    TODO (pair with Person A): use stage1's graph to look up whatever the
    clarify_question is asking about (e.g. subject history, prior visit
    data) and construct a factual answer — no further human round-trip.

    Placeholder for now: echoes back what would need graph data to answer.
    """
    return f"[auto-answer placeholder] Needs graph lookup for: {clarify_question}"


def process(findings: list[Finding], memory: CrossCycleMemory, logger: TraceLogger) -> list[Finding]:
    for f in findings:
        if f.status == "queried":
            # Already handled by data_manager this cycle — don't also escalate.
            f.node_trail.append("human_gate")
            continue

        if memory.was_escalated(f.finding_id) and not needs_escalation(f, memory):
            f.node_trail.append("human_gate")
            continue

        if not needs_escalation(f, memory):
            f.node_trail.append("human_gate")
            continue

        escalation = Escalation(
            finding_id=f.finding_id,
            subject_id=f.subject_id,
            reason=f.detail,
            record_refs=f.record_refs,
        )

        try:
            response = api_client.post_escalation(
                escalation.subject_id, escalation.reason, escalation.record_refs
            )
            memory.mark_escalated(f.finding_id)
            decision = response.get("decision")

            if decision == "APPROVED":
                f.status = "resolved"
                memory.mark_resolved(f.finding_id)
                logger.log("human_gate", f.finding_id, "approved", "monitor approved", f.record_refs)

            elif decision == "REJECTED":
                f.status = "resolved"
                memory.mark_resolved(f.finding_id)
                logger.log("human_gate", f.finding_id, "rejected", "monitor rejected", f.record_refs)

            elif decision == "CLARIFY":
                answer = auto_answer_clarify(f, response.get("clarify_question", ""))
                f.status = "escalated"
                logger.log(
                    "human_gate", f.finding_id, "auto_answered_clarify", answer, f.record_refs
                )

            else:
                logger.log(
                    "human_gate", f.finding_id, "unknown_response", str(response), f.record_refs
                )

        except Exception as exc:  # noqa: BLE001
            logger.log("human_gate", f.finding_id, "escalation_failed", str(exc), f.record_refs)

        f.node_trail.append("human_gate")

    return findings
