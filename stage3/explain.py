from typing import List

from .audit import DecisionAudit
from .models import Explanation, RecordRef


def explain_decision(
    decision_id: str,
    audit: DecisionAudit,
) -> Explanation:
    """
    Explain a decision using ONLY the recorded audit trace.

    The explanation is deliberately not reconstructed from the
    current study data.
    """

    decision = audit.get_decision(decision_id)

    if decision is None:
        raise KeyError(
            f"Decision {decision_id} was not found in the audit trace."
        )

    evidence: List[RecordRef] = decision.evidence

    evidence_lines = []

    for ref in evidence:
        parts = [ref.domain]

        if ref.usubjid is not None:
            parts.append(f"USUBJID={ref.usubjid}")

        if ref.seq is not None:
            parts.append(f"SEQ={ref.seq}")

        evidence_lines.append(
            " | ".join(parts)
        )

    if decision.action == "CUT_PROCESSED":
        what = (
            f"Surveillance cut {decision.cut} was processed."
        )

        alternatives = [
            "No action beyond processing the cut.",
            "Continue surveillance at the next cut.",
        ]

    else:
        what = (
            f"The system recorded action "
            f"'{decision.action}'."
        )

        alternatives = [
            "Take no action.",
            "Escalate for additional review.",
        ]

    return Explanation(
        decision_id=decision.decision_id,
        what=what,
        evidence=evidence,
        evidence_lines=evidence_lines,
        alternatives=alternatives,
        why=decision.reason,
        consistent_with_trace=True,
    )