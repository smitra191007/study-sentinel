from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class HumanDecision:
    decision_id: str
    status: str = "PENDING"
    cut_submitted: int = 0
    last_checked_cut: int = 0
    response: Optional[str] = None
    reason: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "decision_id": self.decision_id,
            "status": self.status,
            "cut_submitted": self.cut_submitted,
            "last_checked_cut": self.last_checked_cut,
            "response": self.response,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class HumanGate:
    """
    Human approval gate for surveillance decisions.

    Rules:
    - New escalation starts as PENDING.
    - Only an explicit human response can change status.
    - No response never becomes APPROVED.
    - After 4 cuts without response, the item remains PENDING
      and approval-gated actions remain blocked.
    """

    def __init__(self, response_delay_cuts: int = 4):
        self.response_delay_cuts = response_delay_cuts
        self.decisions: Dict[str, HumanDecision] = {}

    def submit(self, decision_id: str, cut: int, reason: str = ""):
        """Create a new human approval request."""
        if decision_id in self.decisions:
            return self.decisions[decision_id]

        decision = HumanDecision(
            decision_id=decision_id,
            status="PENDING",
            cut_submitted=cut,
            last_checked_cut=cut,
            reason=reason,
        )

        self.decisions[decision_id] = decision
        return decision

    def respond(
        self,
        decision_id: str,
        status: str,
        reason: str = "",
        response: Optional[str] = None,
    ):
        """
        Record an explicit human response.

        Valid statuses:
        APPROVED
        REJECTED
        CLARIFY
        """

        status = status.upper()

        if status not in {"APPROVED", "REJECTED", "CLARIFY"}:
            raise ValueError(
                "Human response must be APPROVED, REJECTED, or CLARIFY"
            )

        if decision_id not in self.decisions:
            raise KeyError(
                f"Unknown human decision: {decision_id}"
            )

        decision = self.decisions[decision_id]

        decision.status = status
        decision.response = response or status
        decision.reason = reason

        return decision

    def tick(self, cut: int):
        """
        Advance the gate to a new surveillance cut.

        IMPORTANT:
        A pending decision NEVER becomes approved automatically.
        """

        for decision in self.decisions.values():

            if decision.status == "PENDING":
                decision.last_checked_cut = cut

                waiting_cuts = (
                    cut - decision.cut_submitted
                )

                if waiting_cuts >= self.response_delay_cuts:
                    decision.metadata["slow_human"] = True
                    decision.metadata["waiting_cuts"] = waiting_cuts
                    decision.metadata["approval_blocked"] = True

        return self.status_all()

    def status(self, decision_id: str):
        if decision_id not in self.decisions:
            return None

        return self.decisions[decision_id]

    def status_all(self):
        return [
            decision.to_dict()
            for decision in self.decisions.values()
        ]

    def can_execute(self, decision_id: str) -> bool:
        """
        Approval-gated execution is allowed ONLY after
        an explicit APPROVED response.
        """

        decision = self.status(decision_id)

        if decision is None:
            return False

        return decision.status == "APPROVED"

    def needs_clarification(self, decision_id: str) -> bool:
        decision = self.status(decision_id)

        if decision is None:
            return False

        return decision.status == "CLARIFY"

    def is_pending(self, decision_id: str) -> bool:
        decision = self.status(decision_id)

        if decision is None:
            return False

        return decision.status == "PENDING"