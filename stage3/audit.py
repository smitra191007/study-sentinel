import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Decision, RecordRef


class DecisionAudit:
    """
    Append-only decision trace for Study Watch.

    Every decision is recorded when it happens so that explanations
    can later be reconstructed directly from the trace.
    """

    def __init__(self, path: str = "stage3_decisions.jsonl") -> None:
        self.path = Path(path)
        self._next_id = self._discover_next_id()

    def _discover_next_id(self) -> int:
        if not self.path.exists():
            return 1

        highest = 0

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                decision_id = str(record.get("decision_id", ""))

                if decision_id.startswith("D-"):
                    try:
                        number = int(decision_id[2:])
                        highest = max(highest, number)
                    except ValueError:
                        pass

        return highest + 1

    def record_decision(
        self,
        node: str,
        evidence: Optional[List[RecordRef]] = None,
        reason: str = "",
        action: str = "NO_ACTION",
        status: str = "OPEN",
        cut: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """
        Record one decision immediately.

        Returns the Decision object so other Stage 3 components can
        use the same deterministic decision ID.
        """

        decision_id = f"D-{self._next_id:03d}"
        self._next_id += 1

        decision = Decision(
            decision_id=decision_id,
            cut=cut,
            node=node,
            action=action,
            reason=reason,
            status=status,
            evidence=evidence or [],
            metadata=metadata or {},
        )

        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    decision.to_dict(),
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

        return decision

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        """
        Retrieve a decision directly from the trace.
        """

        if not self.path.exists():
            return None

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if record.get("decision_id") != decision_id:
                    continue

                evidence = [
                    RecordRef(
                        domain=item.get("domain", ""),
                        usubjid=item.get("usubjid"),
                        seq=item.get("seq"),
                    )
                    for item in record.get("evidence", [])
                ]

                return Decision(
                    decision_id=record["decision_id"],
                    cut=int(record.get("cut", 0)),
                    node=record.get("node", ""),
                    action=record.get("action", ""),
                    reason=record.get("reason", ""),
                    status=record.get("status", "OPEN"),
                    evidence=evidence,
                    metadata=record.get("metadata", {}),
                )

        return None

    def all_decisions(self) -> List[Decision]:
        """
        Return all decisions currently present in the trace.
        """

        decisions = []

        if not self.path.exists():
            return decisions

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                evidence = [
                    RecordRef(
                        domain=item.get("domain", ""),
                        usubjid=item.get("usubjid"),
                        seq=item.get("seq"),
                    )
                    for item in record.get("evidence", [])
                ]

                decisions.append(
                    Decision(
                        decision_id=record["decision_id"],
                        cut=int(record.get("cut", 0)),
                        node=record.get("node", ""),
                        action=record.get("action", ""),
                        reason=record.get("reason", ""),
                        status=record.get("status", "OPEN"),
                        evidence=evidence,
                        metadata=record.get("metadata", {}),
                    )
                )

        return decisions