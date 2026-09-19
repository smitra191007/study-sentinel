from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

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
    current_cut: int = 0
    data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    previous_data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    findings_by_cut: Dict[int, List[Any]] = field(default_factory=dict)
    open_items: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    site_flags: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    untrusted_records: List[Dict[str, Any]] = field(default_factory=list)
    applied_corrections: List[Dict[str, Any]] = field(default_factory=list)
    correction_keys_seen: set = field(default_factory=set)


class StudyWatch:
    def __init__(
        self,
        data_dir: str,
        crew,
        audit_path: str = "stage3_decisions.jsonl",
        budget_total: float = 100.0,
    ) -> None:
        self.data_dir = data_dir
        self.crew = crew

        self.raw_data = load_data(data_dir)
        self.corrections = load_corrections(data_dir)
        self.cuts = load_cuts(data_dir)

        self.audit = DecisionAudit(audit_path)
        self.budget = BudgetManager(total=budget_total)

        self.state = WatchState()
        self.decisions: List[Decision] = []

    def _prepare_cut(self, cut: int) -> Dict[str, List[Dict[str, Any]]]:
        cut_view = get_cut_view(self.raw_data, cut)
        corrected = apply_corrections(
            cut_view,
            self.corrections,
            cut,
        )
        return corrected

    def _protocol_version_for_cut(self, cut: int) -> int:
        applicable_versions = [
            int(row["protocol_version"])
            for row in self.cuts
            if int(row["cut"]) <= cut
        ]

        if not applicable_versions:
            raise ValueError(f"No protocol version found for cut {cut}")

        return max(applicable_versions)

    def _finding_evidence(self, finding) -> List[RecordRef]:
        evidence = []

        for ref in getattr(finding, "evidence", []):
            evidence.append(
                RecordRef(
                    domain=ref.domain,
                    usubjid=ref.usubjid,
                    seq=ref.seq,
                )
            )

        return evidence

    def _record_finding(self, cut: int, finding) -> Decision:
        evidence = self._finding_evidence(finding)

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
                "protocol_version": finding.protocol_version,
                "node_trail": list(finding.node_trail),
            },
        )

        self.decisions.append(decision)

        return decision

    def _correction_key(self, correction: Dict[str, Any]) -> Tuple[str, str, str, str]:
        return (
            str(correction["domain"]),
            str(correction["usubjid"]),
            str(correction["seq"]),
            str(correction["field"]),
        )

    def _corrections_for_cut(self, cut: int) -> List[Dict[str, Any]]:
        corrections = []

        for correction in self.corrections:
            correction_cut = int(correction["cut"])

            if correction_cut != cut:
                continue

            key = self._correction_key(correction)

            if key in self.state.correction_keys_seen:
                continue

            corrections.append(correction)
            self.state.correction_keys_seen.add(key)

        return corrections

    def _record_correction(
        self,
        cut: int,
        correction: Dict[str, Any],
    ) -> Decision:
        evidence = [
            RecordRef(
                domain=str(correction["domain"]),
                usubjid=str(correction["usubjid"]),
                seq=str(correction["seq"]),
            )
        ]

        reason = (
            f"Data correction applied to "
            f"{correction['domain']} record "
            f"{correction['usubjid']}:{correction['seq']} "
            f"field {correction['field']}: "
            f"{correction['old_value']} -> {correction['new_value']} "
            f"({correction.get('reason', 'unspecified reason')})"
        )

        decision = self.audit.record_decision(
            node="correction",
            evidence=evidence,
            reason=reason,
            action="DATA_CORRECTION",
            status="RECORDED",
            cut=cut,
            metadata={
                "correction_cut": cut,
                "domain": correction["domain"],
                "usubjid": correction["usubjid"],
                "seq": correction["seq"],
                "field": correction["field"],
                "old_value": correction["old_value"],
                "new_value": correction["new_value"],
                "correction_reason": correction.get("reason", ""),
            },
        )

        self.decisions.append(decision)

        return decision

    def _affected_previous_decisions(
        self,
        cut: int,
        correction: Dict[str, Any],
    ) -> List[Decision]:
        affected = []

        target_domain = str(correction["domain"])
        target_usubjid = str(correction["usubjid"])
        target_seq = str(correction["seq"])

        for decision in self.decisions:
            if decision.cut >= cut:
                continue

            for evidence in decision.evidence:
                if (
                    str(evidence.domain) == target_domain
                    and str(evidence.usubjid) == target_usubjid
                    and str(evidence.seq) == target_seq
                ):
                    affected.append(decision)
                    break

        return affected

    def _record_correction_impact(
        self,
        cut: int,
        correction: Dict[str, Any],
        previous_decision: Decision,
    ) -> Decision:
        evidence = [
            RecordRef(
                domain=str(correction["domain"]),
                usubjid=str(correction["usubjid"]),
                seq=str(correction["seq"]),
            )
        ]

        reason = (
            f"Previous decision {previous_decision.decision_id} "
            f"references a record changed by a cut {cut} correction. "
            f"The affected decision must be re-evaluated against "
            f"the corrected data."
        )

        decision = self.audit.record_decision(
            node="correction",
            evidence=evidence,
            reason=reason,
            action="UPDATE_REQUIRED",
            status="OPEN",
            cut=cut,
            metadata={
                "previous_decision_id": previous_decision.decision_id,
                "previous_cut": previous_decision.cut,
                "correction_cut": cut,
                "domain": correction["domain"],
                "usubjid": correction["usubjid"],
                "seq": correction["seq"],
                "field": correction["field"],
                "old_value": correction["old_value"],
                "new_value": correction["new_value"],
            },
        )

        self.decisions.append(decision)

        return decision

    def _process_corrections(self, cut: int) -> List[Dict[str, Any]]:
        events = []

        corrections = self._corrections_for_cut(cut)

        for correction in corrections:
            correction_decision = self._record_correction(
                cut,
                correction,
            )

            affected = self._affected_previous_decisions(
                cut,
                correction,
            )

            impact_decisions = []

            for previous_decision in affected:
                impact_decision = self._record_correction_impact(
                    cut,
                    correction,
                    previous_decision,
                )
                impact_decisions.append(
                    impact_decision.decision_id
                )

            events.append(
                {
                    "type": "DATA_CORRECTION",
                    "cut": cut,
                    "domain": correction["domain"],
                    "usubjid": correction["usubjid"],
                    "seq": correction["seq"],
                    "field": correction["field"],
                    "old_value": correction["old_value"],
                    "new_value": correction["new_value"],
                    "reason": correction.get("reason", ""),
                    "decision_id": correction_decision.decision_id,
                    "affected_decisions": [
                        decision.decision_id
                        for decision in affected
                    ],
                    "impact_decisions": impact_decisions,
                }
            )

        self.state.applied_corrections.extend(events)

        return events

    def _consume_cut_budget(
        self,
        cut: int,
        finding_count: int,
        correction_count: int = 0,
    ) -> None:
        base_cost = 1.0
        finding_cost = float(finding_count) * 0.10
        correction_cost = float(correction_count) * 0.02

        total_cost = (
            base_cost
            + finding_cost
            + correction_cost
        )

        self.budget.consume(total_cost)

    def run_period(self, cuts=range(1, 13)) -> SurveillanceReport:
        report = SurveillanceReport(
            cuts_processed=[],
            budget_total=self.budget.total,
        )

        for cut in cuts:
            cut = int(cut)

            previous_data = self.state.data

            self.state.previous_data = previous_data
            self.state.data = self._prepare_cut(cut)
            self.state.current_cut = cut

            protocol_version = self._protocol_version_for_cut(cut)

            correction_events = self._process_corrections(cut)

            cycle_report = self.crew.run_cycle(
                cut=cut,
                protocol_version=protocol_version,
            )

            findings = getattr(
                cycle_report,
                "findings",
                [],
            )

            self.state.findings_by_cut[cut] = findings

            self._consume_cut_budget(
                cut=cut,
                finding_count=len(findings),
                correction_count=len(correction_events),
            )

            for finding in findings:
                decision = self._record_finding(
                    cut,
                    finding,
                )

                report.decisions.append(decision)

            report.cuts_processed.append(cut)

            report.signals.extend(findings)

            report.adversarial_events.extend(
                correction_events
            )

            report.budget_used = self.budget.used
            report.narrative_enabled = (
                self.budget.narrative_enabled
            )

        report.budget_used = self.budget.used
        report.narrative_enabled = (
            self.budget.narrative_enabled
        )

        return report

    def explain(self, decision_id: str):
        from .explain import explain_decision

        return explain_decision(
            decision_id=decision_id,
            audit=self.audit,
        )