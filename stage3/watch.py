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
from .adversarial import AdversarialDetector


@dataclass
class WatchState:
    current_cut: int = 0

    data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    previous_data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    findings_by_cut: Dict[int, List[Any]] = field(default_factory=dict)

    open_items: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Delayed-human tracking.
    pending_humans: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    human_history: List[Dict[str, Any]] = field(default_factory=list)

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
    ):
        self.data_dir = data_dir
        self.crew = crew

        self.audit = DecisionAudit(audit_path)
        self.budget = BudgetManager(total=budget_total)

        self.state = WatchState()
        self.decisions: List[Decision] = []

        self.raw_data = load_data(data_dir)
        self.corrections = load_corrections(data_dir)
        self.cuts = load_cuts(data_dir)

        # Stateful adversarial detector.
        #
        # It must live for the entire WATCH period so that it can compare
        # one cut with the previous cut and detect changes such as the
        # S04 glucose scale shift.
        self.adversarial = AdversarialDetector(
            documents_dir=f"{data_dir}/documents"
        )

    # ------------------------------------------------------------------
    # CUT / DATA PREPARATION
    # ------------------------------------------------------------------

    def _prepare_cut(self, cut: int):
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
        Determine protocol version from the cut metadata when available.
        Falls back to v1 if the metadata does not expose a version.
        """

        if isinstance(self.cuts, list):

            for row in self.cuts:

                if not isinstance(row, dict):
                    continue

                row_cut = row.get("cut")

                try:
                    row_cut = int(row_cut)
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                if row_cut != int(cut):
                    continue

                for key in (
                    "protocol_version",
                    "protocol",
                    "version",
                ):
                    value = row.get(key)

                    if value is not None:
                        try:
                            return int(value)
                        except (
                            TypeError,
                            ValueError,
                        ):
                            pass

        return 1

    # ------------------------------------------------------------------
    # EVIDENCE / DECISION HELPERS
    # ------------------------------------------------------------------

    def _finding_evidence(
        self,
        finding,
    ) -> List[RecordRef]:

        evidence = []

        for ref in getattr(
            finding,
            "evidence",
            [],
        ) or []:

            evidence.append(
                RecordRef(
                    domain=getattr(
                        ref,
                        "domain",
                        "",
                    ),
                    usubjid=getattr(
                        ref,
                        "usubjid",
                        None,
                    ),
                    seq=getattr(
                        ref,
                        "seq",
                        None,
                    ),
                )
            )

        return evidence

    def _record_finding(
        self,
        cut: int,
        finding,
    ) -> Decision:

        evidence = self._finding_evidence(
            finding
        )

        status = str(
            getattr(
                finding,
                "status",
                "open",
            )
        )

        decision = self.audit.record_decision(
            node="watch",
            evidence=evidence,
            reason=str(
                getattr(
                    finding,
                    "rationale",
                    "",
                )
            ),
            action=str(
                getattr(
                    finding,
                    "code",
                    "FINDING",
                )
            ),
            status=status.upper(),
            cut=cut,
            metadata={
                "finding_id": getattr(
                    finding,
                    "finding_id",
                    None,
                ),
                "usubjid": getattr(
                    finding,
                    "usubjid",
                    None,
                ),
                "site": getattr(
                    finding,
                    "site",
                    None,
                ),
                "severity": getattr(
                    finding,
                    "severity",
                    None,
                ),
                "protocol_version": getattr(
                    finding,
                    "protocol_version",
                    None,
                ),
            },
        )

        self.decisions.append(
            decision
        )

        return decision

    # ------------------------------------------------------------------
    # ADVERSARIAL EVENTS
    # ------------------------------------------------------------------

    def _record_adversarial_event(
        self,
        cut: int,
        event,
    ) -> Decision:

        evidence = []

        for ref in (
            getattr(
                event,
                "evidence",
                [],
            )
            or []
        ):

            evidence.append(
                RecordRef(
                    domain=str(
                        ref.get(
                            "domain",
                            "",
                        )
                    ),
                    usubjid=ref.get(
                        "usubjid"
                    ),
                    seq=ref.get(
                        "seq"
                    ),
                )
            )

        metadata = dict(
            getattr(
                event,
                "metadata",
                {},
            )
            or {}
        )

        metadata.update(
            {
                "event_type": getattr(
                    event,
                    "event_type",
                    None,
                ),
                "site": getattr(
                    event,
                    "site",
                    None,
                ),
                "domain": getattr(
                    event,
                    "domain",
                    None,
                ),
                "usubjid": getattr(
                    event,
                    "usubjid",
                    None,
                ),
            }
        )

        decision = self.audit.record_decision(
            node="adversarial",
            evidence=evidence,
            reason=str(
                getattr(
                    event,
                    "reason",
                    "",
                )
            ),
            action=str(
                getattr(
                    event,
                    "action",
                    "ADVERSARIAL_EVENT",
                )
            ),
            status="OPEN",
            cut=cut,
            metadata=metadata,
        )

        self.decisions.append(
            decision
        )

        return decision

    def _process_adversarial_events(
        self,
        cut: int,
        protocol_version: int,
    ):
        """
        Run all adversarial/integrity detectors against the current
        corrected cut.

        The detector is stateful across the whole WATCH period.
        """

        events = self.adversarial.on_cut(
            cut=cut,
            data=self.state.data,
            protocol_version=protocol_version,
        )

        report_events = []

        for event in events:

            decision = self._record_adversarial_event(
                cut,
                event,
            )

            event_dict = event.to_dict()

            event_dict["decision_id"] = (
                decision.decision_id
            )

            report_events.append(
                event_dict
            )

            # Track site-level integrity flags.
            site = getattr(
                event,
                "site",
                None,
            )

            if site:

                self.state.site_flags.setdefault(
                    site,
                    {},
                )

                self.state.site_flags[
                    site
                ][
                    event.event_type
                ] = {
                    "cut": cut,
                    "action": event.action,
                    "reason": event.reason,
                }

            # Keep affected records marked as untrusted.
            for ref in (
                getattr(
                    event,
                    "evidence",
                    [],
                )
                or []
            ):

                self.state.untrusted_records.append(
                    {
                        "cut": cut,
                        "event_type": event.event_type,
                        "domain": ref.get(
                            "domain"
                        ),
                        "usubjid": ref.get(
                            "usubjid"
                        ),
                        "seq": ref.get(
                            "seq"
                        ),
                    }
                )

            # Integrity events become open items unless the event is
            # informational entity discovery.
            if event.event_type not in {
                "NEW_SITE",
                "NEW_DOMAIN",
            }:

                self.state.open_items[
                    decision.decision_id
                ] = {
                    "decision_id": decision.decision_id,
                    "cut": cut,
                    "type": event.event_type,
                    "action": event.action,
                    "reason": event.reason,
                    "site": site,
                    "approval_required": False,
                    "clinical_escalation": (
                        event.metadata.get(
                            "clinical_escalation",
                            False,
                        )
                    ),
                }

        return report_events

    # ------------------------------------------------------------------
    # INCREMENTAL CORRECTIONS
    # ------------------------------------------------------------------

    def _correction_key(
        self,
        correction,
    ):

        return (
            str(
                correction["domain"]
            ),
            str(
                correction["usubjid"]
            ),
            str(
                correction["seq"]
            ),
            str(
                correction["field"]
            ),
        )

    def _corrections_for_cut(
        self,
        cut,
    ):

        corrections = []

        for correction in self.corrections:

            correction_cut = int(
                correction["cut"]
            )

            if correction_cut != int(cut):
                continue

            key = self._correction_key(
                correction
            )

            if key in self.state.correction_keys_seen:
                continue

            corrections.append(
                correction
            )

            self.state.correction_keys_seen.add(
                key
            )

        return corrections

    def _record_correction(
        self,
        cut,
        correction,
    ):

        evidence = [
            RecordRef(
                domain=str(
                    correction["domain"]
                ),
                usubjid=str(
                    correction["usubjid"]
                ),
                seq=str(
                    correction["seq"]
                ),
            )
        ]

        reason = (
            f"Data correction applied to "
            f"{correction['domain']} record "
            f"{correction['usubjid']}:"
            f"{correction['seq']} "
            f"field {correction['field']}: "
            f"{correction.get('old_value')} -> "
            f"{correction.get('new_value')} "
            f"({correction.get('reason', '')})"
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
                "old_value": correction.get(
                    "old_value"
                ),
                "new_value": correction.get(
                    "new_value"
                ),
                "correction_reason": correction.get(
                    "reason"
                ),
            },
        )

        self.decisions.append(
            decision
        )

        return decision

    def _affected_previous_decisions(
        self,
        cut,
        correction,
    ):

        affected = []

        target_domain = str(
            correction["domain"]
        )

        target_usubjid = str(
            correction["usubjid"]
        )

        target_seq = str(
            correction["seq"]
        )

        for decision in self.decisions:

            if decision.cut >= int(cut):
                continue

            for evidence in decision.evidence:

                if (
                    str(
                        evidence.domain
                    )
                    == target_domain
                    and str(
                        evidence.usubjid
                    )
                    == target_usubjid
                    and str(
                        evidence.seq
                    )
                    == target_seq
                ):

                    affected.append(
                        decision
                    )

                    break

        return affected

    def _record_correction_impact(
        self,
        cut,
        correction,
        previous_decision,
    ):

        reason = (
            f"Previous decision "
            f"{previous_decision.decision_id} "
            f"references a record changed by a "
            f"cut {cut} correction. The affected "
            f"decision must be re-evaluated against "
            f"the corrected data."
        )

        decision = self.audit.record_decision(
            node="correction",
            evidence=[
                RecordRef(
                    domain=str(
                        correction["domain"]
                    ),
                    usubjid=str(
                        correction["usubjid"]
                    ),
                    seq=str(
                        correction["seq"]
                    ),
                )
            ],
            reason=reason,
            action="UPDATE_REQUIRED",
            status="OPEN",
            cut=cut,
            metadata={
                "previous_decision_id": (
                    previous_decision.decision_id
                ),
                "previous_cut": (
                    previous_decision.cut
                ),
                "correction_cut": cut,
                "domain": correction["domain"],
                "usubjid": correction["usubjid"],
                "seq": correction["seq"],
                "field": correction["field"],
                "old_value": correction.get(
                    "old_value"
                ),
                "new_value": correction.get(
                    "new_value"
                ),
            },
        )

        self.decisions.append(
            decision
        )

        return decision

    def _process_corrections(
        self,
        cut,
    ):

        events = []

        corrections = self._corrections_for_cut(
            cut
        )

        for correction in corrections:

            correction_decision = (
                self._record_correction(
                    cut,
                    correction,
                )
            )

            affected = (
                self._affected_previous_decisions(
                    cut,
                    correction,
                )
            )

            impact_decisions = []

            for previous_decision in affected:

                impact_decision = (
                    self._record_correction_impact(
                        cut,
                        correction,
                        previous_decision,
                    )
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
                    "old_value": correction.get(
                        "old_value"
                    ),
                    "new_value": correction.get(
                        "new_value"
                    ),
                    "reason": correction.get(
                        "reason"
                    ),
                    "decision_id": (
                        correction_decision.decision_id
                    ),
                    "affected_decisions": [
                        d.decision_id
                        for d in affected
                    ],
                    "impact_decisions": (
                        impact_decisions
                    ),
                }
            )

        self.state.applied_corrections.extend(
            events
        )

        return events

    # ------------------------------------------------------------------
    # DELAYED HUMAN TRACKING
    # ------------------------------------------------------------------

    def _finding_requires_human(
        self,
        finding,
    ) -> bool:

        severity = str(
            getattr(
                finding,
                "severity",
                "",
            )
        ).upper()

        status = str(
            getattr(
                finding,
                "status",
                "open",
            )
        ).lower()

        return (
            severity in {
                "CRITICAL",
                "MAJOR",
            }
            and status in {
                "open",
                "escalated",
            }
        )

    def _track_human_state(
        self,
        cut: int,
        finding,
    ):

        finding_id = str(
            getattr(
                finding,
                "finding_id",
                "",
            )
        )

        if not finding_id:
            return None

        status = str(
            getattr(
                finding,
                "status",
                "open",
            )
        ).lower()

        severity = str(
            getattr(
                finding,
                "severity",
                "",
            )
        ).upper()

        if not self._finding_requires_human(
            finding
        ):

            if finding_id in self.state.pending_humans:

                pending = self.state.pending_humans[
                    finding_id
                ]

                if status == "resolved":

                    pending["status"] = "resolved"
                    pending["resolved_cut"] = cut
                    pending["human_decision"] = (
                        "resolved"
                    )

                    self.state.human_history.append(
                        {
                            "finding_id": finding_id,
                            "event": "HUMAN_RESOLVED",
                            "cut": cut,
                            "first_pending_cut": (
                                pending[
                                    "first_pending_cut"
                                ]
                            ),
                            "cuts_waiting": (
                                cut
                                - pending[
                                    "first_pending_cut"
                                ]
                            ),
                        }
                    )

                    del self.state.pending_humans[
                        finding_id
                    ]

            return None

        if finding_id not in self.state.pending_humans:

            self.state.pending_humans[
                finding_id
            ] = {
                "finding_id": finding_id,
                "first_pending_cut": cut,
                "last_seen_cut": cut,
                "cuts_waiting": 0,
                "severity": severity,
                "site": getattr(
                    finding,
                    "site",
                    None,
                ),
                "usubjid": getattr(
                    finding,
                    "usubjid",
                    None,
                ),
                "status": "PENDING_HUMAN",
                "standing_limit": False,
                "approval_required": True,
            }

            event = {
                "finding_id": finding_id,
                "event": "HUMAN_PENDING",
                "cut": cut,
                "first_pending_cut": cut,
                "cuts_waiting": 0,
                "approval_required": True,
            }

            self.state.human_history.append(
                event
            )

            return event

        pending = self.state.pending_humans[
            finding_id
        ]

        pending["last_seen_cut"] = cut

        pending["cuts_waiting"] = (
            cut
            - pending[
                "first_pending_cut"
            ]
        )

        if pending["cuts_waiting"] >= 4:

            pending["standing_limit"] = True
            pending["status"] = "STANDING_LIMIT"

            event = {
                "finding_id": finding_id,
                "event": (
                    "HUMAN_UNANSWERED_STANDING_LIMIT"
                ),
                "cut": cut,
                "first_pending_cut": (
                    pending[
                        "first_pending_cut"
                    ]
                ),
                "cuts_waiting": (
                    pending[
                        "cuts_waiting"
                    ]
                ),
                "approval_required": True,
                "approval_received": False,
                "action": (
                    "NO_APPROVAL_GATED_ACTION"
                ),
            }

            self.state.human_history.append(
                event
            )

            return event

        pending["status"] = "PENDING_HUMAN"

        event = {
            "finding_id": finding_id,
            "event": "HUMAN_STILL_PENDING",
            "cut": cut,
            "first_pending_cut": (
                pending[
                    "first_pending_cut"
                ]
            ),
            "cuts_waiting": (
                pending[
                    "cuts_waiting"
                ]
            ),
            "approval_required": True,
            "approval_received": False,
        }

        self.state.human_history.append(
            event
        )

        return event

    def _process_human_tracking(
        self,
        cut,
        findings,
    ):

        events = []

        for finding in findings:

            event = self._track_human_state(
                cut,
                finding,
            )

            if event is not None:
                events.append(
                    event
                )

        return events

    # ------------------------------------------------------------------
    # BUDGET
    # ------------------------------------------------------------------

    def _consume_cut_budget(
        self,
        cut,
        finding_count,
        correction_count=0,
        human_event_count=0,
        adversarial_event_count=0,
    ):

        base_cost = 1.0

        finding_cost = (
            0.1
            * finding_count
        )

        correction_cost = (
            0.02
            * correction_count
        )

        human_cost = (
            0.05
            * human_event_count
        )

        adversarial_cost = (
            0.05
            * adversarial_event_count
        )

        self.budget.consume(
            base_cost
            + finding_cost
            + correction_cost
            + human_cost
            + adversarial_cost
        )

    # ------------------------------------------------------------------
    # MAIN WATCH LOOP
    # ------------------------------------------------------------------

    def run_period(
        self,
        cuts=range(1, 13),
    ) -> SurveillanceReport:

        report = SurveillanceReport(
            cuts_processed=[],
            signals=[],
            site_risk=[],
            deviations=[],
            adversarial_events=[],
            open_items=[],
            budget_total=self.budget.total,
            budget_used=self.budget.used,
            narrative_enabled=(
                self.budget.narrative_enabled
            ),
            decisions=[],
        )

        for cut in cuts:

            previous_data = self.state.data

            self.state.previous_data = (
                previous_data
            )

            self.state.data = (
                self._prepare_cut(cut)
            )

            self.state.current_cut = cut

            protocol_version = (
                self._protocol_version_for_cut(
                    cut
                )
            )

            # ----------------------------------------------------------
            # 1. Process corrections first.
            # ----------------------------------------------------------

            correction_events = (
                self._process_corrections(
                    cut
                )
            )

            # ----------------------------------------------------------
            # 2. Run adversarial/integrity detection.
            #
            # This happens on the corrected current cut.
            # ----------------------------------------------------------

            adversarial_events = (
                self._process_adversarial_events(
                    cut,
                    protocol_version,
                )
            )

            # ----------------------------------------------------------
            # 3. Run the existing Stage 2 review crew.
            # ----------------------------------------------------------

            cycle_report = (
                self.crew.run_cycle(
                    cut=cut,
                    protocol_version=(
                        protocol_version
                    ),
                )
            )

            findings = getattr(
                cycle_report,
                "findings",
                [],
            )

            self.state.findings_by_cut[
                cut
            ] = findings

            # ----------------------------------------------------------
            # 4. Track delayed human decisions.
            # ----------------------------------------------------------

            human_events = (
                self._process_human_tracking(
                    cut,
                    findings,
                )
            )

            # ----------------------------------------------------------
            # 5. Consume budget.
            # ----------------------------------------------------------

            self._consume_cut_budget(
                cut,
                len(findings),
                len(correction_events),
                len(human_events),
                len(adversarial_events),
            )

            # ----------------------------------------------------------
            # 6. Record Stage 2 findings in trace.
            # ----------------------------------------------------------

            for finding in findings:

                decision = (
                    self._record_finding(
                        cut,
                        finding,
                    )
                )

                report.decisions.append(
                    decision
                )

            # ----------------------------------------------------------
            # 7. Update public report.
            # ----------------------------------------------------------

            report.cuts_processed.append(
                cut
            )

            report.signals.extend(
                findings
            )

            # Corrections are also represented as adversarial/integrity
            # events in the public report.
            report.adversarial_events.extend(
                correction_events
            )

            # Add actual adversarial detector events.
            report.adversarial_events.extend(
                adversarial_events
            )

            # Human events remain open items because unresolved human
            # approval must never silently become approval.
            report.open_items.extend(
                human_events
            )

            # Integrity events requiring follow-up also become open items.
            for event in adversarial_events:

                if event.get(
                    "event_type"
                ) in {
                    "SITE_SCALE_SHIFT",
                    "LAB_UNIT_ANOMALY",
                    "UNRELIABLE_LAB_SITE",
                    "TAMPERED_DOCUMENT_INSTRUCTION",
                    "PROTOCOL_AMENDMENT",
                }:

                    report.open_items.append(
                        {
                            "decision_id": event.get(
                                "decision_id"
                            ),
                            "cut": cut,
                            "event": event.get(
                                "event_type"
                            ),
                            "action": event.get(
                                "action"
                            ),
                            "reason": event.get(
                                "reason"
                            ),
                            "site": event.get(
                                "site"
                            ),
                            "approval_required": False,
                            "clinical_escalation": (
                                event.get(
                                    "metadata",
                                    {},
                                ).get(
                                    "clinical_escalation",
                                    False,
                                )
                            ),
                        }
                    )

            report.budget_used = (
                self.budget.used
            )

            report.narrative_enabled = (
                self.budget.narrative_enabled
            )

        report.budget_used = (
            self.budget.used
        )

        report.narrative_enabled = (
            self.budget.narrative_enabled
        )

        report.decisions = list(
            self.decisions
        )

        return report

    # ------------------------------------------------------------------
    # TRACE-BASED EXPLANATION
    # ------------------------------------------------------------------

    def explain(
        self,
        decision_id: str,
    ):

        from .explain import explain_decision

        return explain_decision(
            decision_id=decision_id,
            audit=self.audit,
        )