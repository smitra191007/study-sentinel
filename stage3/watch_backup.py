from dataclasses import dataclass, field
from typing import Any, Dict, List

from stage1.loader import (
    load_data,
    load_corrections,
    load_cuts,
    get_cut_view,
    apply_corrections,
)

from .audit import DecisionAudit
from .budget import BudgetManager
from .models import Decision, RecordRef, SurveillanceReport


@dataclass
class WatchState:
    """
    Persistent state carried from one surveillance cut to the next.
    """

    current_cut: int = 0

    data: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )

    findings_by_cut: Dict[int, List[Any]] = field(
        default_factory=dict
    )

    open_items: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )

    site_flags: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )

    untrusted_records: List[Dict[str, Any]] = field(
        default_factory=list
    )


class StudyWatch:
    """
    Stage 3 twelve-cut surveillance engine.

    Responsibilities:
    - prepare corrected data for each cut
    - run the existing Stage 2 crew
    - maintain state across cuts
    - record decisions in the audit trace
    - maintain one shared budget across the whole period
    """

    def __init__(
        self,
        data_dir: str,
        crew,
        audit_path: str = "stage3_decisions.jsonl",
        budget_total: float = 100.0,
    ) -> None:

        self.data_dir = data_dir
        self.crew = crew

        # ---------------------------------------------------------
        # Load study resources once.
        # ---------------------------------------------------------

        self.raw_data = load_data(
            data_dir
        )

        self.corrections = load_corrections(
            data_dir
        )

        self.cuts = load_cuts(
            data_dir
        )

        # ---------------------------------------------------------
        # Stage 3 audit trace.
        # ---------------------------------------------------------

        self.audit = DecisionAudit(
            audit_path
        )

        # ---------------------------------------------------------
        # ONE budget for the complete surveillance period.
        # It is deliberately created only once here.
        # ---------------------------------------------------------

        self.budget = BudgetManager(
            total=budget_total
        )

        # ---------------------------------------------------------
        # Persistent surveillance state.
        # ---------------------------------------------------------

        self.state = WatchState()

        self.decisions: List[Decision] = []

    def _prepare_cut(
        self,
        cut: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build the corrected data view available at this cut.

        Corrections available up to the current cut are applied.
        """

        cut_view = get_cut_view(
            self.raw_data,
            cut,
        )

        corrected = apply_corrections(
            cut_view,
            self.corrections,
            cut,
        )

        return corrected

    def _protocol_version_for_cut(
        self,
        cut: int,
    ) -> int:
        """
        Return the protocol version applicable at the given cut.
        """

        applicable_versions = [
            int(row["protocol_version"])
            for row in self.cuts
            if int(row["cut"]) <= cut
        ]

        if not applicable_versions:
            raise ValueError(
                f"No protocol version found for cut {cut}"
            )

        return max(
            applicable_versions
        )

    def _finding_evidence(
        self,
        finding,
    ) -> List[RecordRef]:
        """
        Convert Stage 2 EvidenceRef objects into
        Stage 3 RecordRef objects.
        """

        evidence = []

        for ref in getattr(
            finding,
            "evidence",
            [],
        ):

            evidence.append(
                RecordRef(
                    domain=ref.domain,
                    usubjid=ref.usubjid,
                    seq=ref.seq,
                )
            )

        return evidence

    def _record_finding(
        self,
        cut: int,
        finding,
    ) -> Decision:
        """
        Record one real Stage 2 finding as a Stage 3 decision.
        """

        evidence = self._finding_evidence(
            finding
        )

        action = "REVIEW"

        if finding.status == "resolved":
            action = "RESOLVED"

        elif finding.status == "escalated":
            action = "ESCALATED"

        elif finding.status == "queried":
            action = "QUERIED"

        elif finding.status == "open":
            action = "OPEN"

        decision = self.audit.record_decision(
            node="stage2",
            evidence=evidence,
            reason=finding.rationale,
            action=action,
            status=finding.status.upper(),
            cut=cut,
            metadata={
                "finding_id": finding.finding_id,
                "code": finding.code,
                "site": finding.site,
                "severity": finding.severity,
                "protocol_version": (
                    finding.protocol_version
                ),
                "node_trail": list(
                    finding.node_trail
                ),
            },
        )

        self.decisions.append(
            decision
        )

        return decision

    def _consume_cut_budget(
        self,
        cut: int,
        finding_count: int,
    ) -> None:
        """
        Consume deterministic budget for the current cut.

        The budget is intentionally simple at this stage:
        - one base unit for processing the cut
        - one small deterministic cost per finding

        Once 80% is reached, BudgetManager disables narrative work.
        Deterministic safety processing remains enabled.
        """

        base_cost = 1.0

        finding_cost = (
            float(finding_count) * 0.10
        )

        self.budget.consume(
            base_cost
            + finding_cost
        )

    def run_period(
        self,
        cuts=range(1, 13),
    ) -> SurveillanceReport:
        """
        Process the requested surveillance cuts in order.

        One BudgetManager instance is shared across the entire period.
        """

        report = SurveillanceReport(
            cuts_processed=[],
            budget_total=self.budget.total,
        )

        for cut in cuts:

            cut = int(cut)

            # -----------------------------------------------------
            # Prepare corrected data for this cut.
            # -----------------------------------------------------

            self.state.data = self._prepare_cut(
                cut
            )

            self.state.current_cut = cut

            # -----------------------------------------------------
            # Determine protocol version for this cut.
            # -----------------------------------------------------

            protocol_version = (
                self._protocol_version_for_cut(
                    cut
                )
            )

            # -----------------------------------------------------
            # Run existing Stage 2 crew for this cut.
            # -----------------------------------------------------

            cycle_report = self.crew.run_cycle(
                cut=cut,
                protocol_version=protocol_version,
            )

            findings = getattr(
                cycle_report,
                "findings",
                [],
            )

            self.state.findings_by_cut[
                cut
            ] = findings

            # -----------------------------------------------------
            # Consume from the ONE period-wide budget.
            # -----------------------------------------------------

            self._consume_cut_budget(
                cut=cut,
                finding_count=len(findings),
            )

            # -----------------------------------------------------
            # Record every actual Stage 2 finding.
            # -----------------------------------------------------

            for finding in findings:

                decision = self._record_finding(
                    cut,
                    finding,
                )

                report.decisions.append(
                    decision
                )

            # -----------------------------------------------------
            # Public signal report.
            # -----------------------------------------------------

            report.cuts_processed.append(
                cut
            )

            report.signals.extend(
                findings
            )

            # -----------------------------------------------------
            # Keep the report's budget state synchronized.
            # -----------------------------------------------------

            report.budget_used = (
                self.budget.used
            )

            report.narrative_enabled = (
                self.budget.narrative_enabled
            )

        # ---------------------------------------------------------
        # Final budget state.
        # ---------------------------------------------------------

        report.budget_used = (
            self.budget.used
        )

        report.narrative_enabled = (
            self.budget.narrative_enabled
        )

        return report

    def explain(
        self,
        decision_id: str,
    ):
        """
        Delegate explanation generation to stage3.explain.

        The explanation reads the recorded audit trace.
        """

        from .explain import explain_decision

        return explain_decision(
            decision_id=decision_id,
            audit=self.audit,
        )