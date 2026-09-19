from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import statistics
from typing import Any, Dict, List, Optional, Set


@dataclass
class AdversarialEvent:
    event_type: str
    cut: int
    action: str
    reason: str
    site: Optional[str] = None
    domain: Optional[str] = None
    usubjid: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "cut": self.cut,
            "action": self.action,
            "reason": self.reason,
            "site": self.site,
            "domain": self.domain,
            "usubjid": self.usubjid,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class AdversarialDetector:
    """
    Stateful Stage 3 adversarial and data-integrity detector.

    The detector runs once per cut and remembers previous cut distributions.
    """

    UNRELIABLE_SITES = {"S03", "S07"}

    EXPECTED_UNITS = {
        "ALT": "U/L",
        "AST": "U/L",
        "BILI": "mg/dL",
        "GLUC": "mg/dL",
        "CREAT": "mg/dL",
        "HBA1C": "%",
    }

    S07_ALT_AST_UNITS = {
        "ukat/L",
        "µkat/L",
        "μkat/L",
    }

    def __init__(
        self,
        documents_dir: str = "hackathon-data/documents",
    ):
        self.documents_dir = Path(documents_dir)

        self.known_sites: Set[str] = set()
        self.known_domains: Set[str] = set()

        # Distribution of records that FIRST became available at each cut.
        #
        # Example:
        #   self.cut_distributions[7]["S04"]["GLUC"] = median of
        #   S04 glucose records whose cut_available == 7
        self.cut_distributions: Dict[
            int,
            Dict[str, Dict[str, float]],
        ] = {}

        self.cut_evidence: Dict[
            int,
            Dict[tuple, List[Dict[str, Any]]],
        ] = {}

        self.protocol_versions_seen: Set[int] = set()

        self.reported_scale_shifts: Set[tuple] = set()
        self.reported_document_events: Set[int] = set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _site_from_usubjid(
        usubjid: Any,
    ) -> Optional[str]:

        if not usubjid:
            return None

        match = re.search(
            r"-([A-Za-z0-9]+)-",
            str(usubjid),
        )

        if match:
            return match.group(1).upper()

        return None

    @staticmethod
    def _normalise_test(
        value: Any,
    ) -> str:

        return str(
            value or ""
        ).strip().upper()

    @staticmethod
    def _normalise_unit(
        value: Any,
    ) -> str:

        return str(
            value or ""
        ).strip()

    @staticmethod
    def _record(
        record: Dict[str, Any],
        domain: str = "LB",
    ) -> Dict[str, Any]:

        sequence_field = (
            "LBSEQ"
            if domain == "LB"
            else f"{domain}SEQ"
        )

        return {
            "domain": domain,
            "usubjid": record.get("USUBJID"),
            "seq": record.get(sequence_field),
        }

    @staticmethod
    def _numeric_value(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        # Support decimal-comma values such as 177,7.
        text = text.replace(",", ".")

        # <5, >100, ND, etc. are not numeric measurements.
        if text.startswith("<") or text.startswith(">"):
            return None

        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Entity discovery
    # ------------------------------------------------------------------

    def discover_entities(
        self,
        data: Dict[str, List[Dict[str, Any]]],
        cut: int,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        for domain, records in data.items():

            if domain not in self.known_domains:

                events.append(
                    AdversarialEvent(
                        event_type="NEW_DOMAIN",
                        cut=cut,
                        action="ONBOARD_DOMAIN",
                        reason=(
                            f"New data domain discovered: {domain}"
                        ),
                        domain=domain,
                        metadata={
                            "discovered_dynamically": True,
                        },
                    )
                )

                self.known_domains.add(domain)

            for record in records:

                site = self._site_from_usubjid(
                    record.get("USUBJID")
                )

                if site and site not in self.known_sites:

                    events.append(
                        AdversarialEvent(
                            event_type="NEW_SITE",
                            cut=cut,
                            action="ONBOARD_SITE",
                            reason=(
                                f"New study site discovered: {site}"
                            ),
                            site=site,
                            domain=domain,
                            usubjid=record.get("USUBJID"),
                            evidence=[
                                self._record(
                                    record,
                                    domain,
                                )
                            ],
                            metadata={
                                "discovered_dynamically": True,
                            },
                        )
                    )

                    self.known_sites.add(site)

        return events

    # ------------------------------------------------------------------
    # Known unreliable sites
    # ------------------------------------------------------------------

    def detect_unreliable_sites(
        self,
        data: Dict[str, List[Dict[str, Any]]],
        cut: int,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        lb_records = data.get(
            "LB",
            [],
        )

        for site in sorted(
            self.UNRELIABLE_SITES
        ):

            site_records = [
                record
                for record in lb_records
                if self._site_from_usubjid(
                    record.get("USUBJID")
                ) == site
            ]

            if not site_records:
                continue

            evidence = [
                self._record(record)
                for record in site_records[:5]
            ]

            events.append(
                AdversarialEvent(
                    event_type="UNRELIABLE_LAB_SITE",
                    cut=cut,
                    action="EXCLUDE_FROM_SAFETY",
                    reason=(
                        f"Site {site} is documented as unreliable "
                        "for laboratory safety assessment."
                    ),
                    site=site,
                    domain="LB",
                    evidence=evidence,
                    metadata={
                        "data_integrity": True,
                        "clinical_escalation": False,
                        "affected_records": len(
                            site_records
                        ),
                    },
                )
            )

        return events

    # ------------------------------------------------------------------
    # Unit anomalies
    # ------------------------------------------------------------------

    def detect_unit_anomalies(
        self,
        data: Dict[str, List[Dict[str, Any]]],
        cut: int,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        grouped: Dict[
            tuple,
            List[Dict[str, Any]],
        ] = {}

        for record in data.get("LB", []):

            test = self._normalise_test(
                record.get("LBTESTCD")
            )

            unit = self._normalise_unit(
                record.get("LBORRESU")
            )

            site = self._site_from_usubjid(
                record.get("USUBJID")
            )

            expected = self.EXPECTED_UNITS.get(
                test
            )

            if not expected:
                continue

            # S07 ALT/AST in ukat/L is valid.
            if (
                site == "S07"
                and test in {"ALT", "AST"}
                and unit in self.S07_ALT_AST_UNITS
            ):
                continue

            if unit != expected:

                key = (
                    site,
                    test,
                    unit,
                    expected,
                )

                grouped.setdefault(
                    key,
                    [],
                ).append(record)

        for (
            site,
            test,
            unit,
            expected,
        ), records in grouped.items():

            events.append(
                AdversarialEvent(
                    event_type="LAB_UNIT_ANOMALY",
                    cut=cut,
                    action="MARK_DATA_UNTRUSTED",
                    reason=(
                        f"Unexpected unit '{unit}' for {test}; "
                        f"expected '{expected}'."
                    ),
                    site=site,
                    domain="LB",
                    evidence=[
                        self._record(record)
                        for record in records[:5]
                    ],
                    metadata={
                        "expected_unit": expected,
                        "observed_unit": unit,
                        "affected_records": len(records),
                        "data_integrity": True,
                        "clinical_escalation": False,
                    },
                )
            )

        return events

    # ------------------------------------------------------------------
    # Site-wide scale-shift detection
    # ------------------------------------------------------------------

    def _build_cut_distributions(
        self,
        data: Dict[str, List[Dict[str, Any]]],
        cut: int,
    ) -> None:

        """
        Build medians from records that became available EXACTLY at this cut.

        This avoids the cumulative-data problem where all earlier records are
        repeatedly included in the median.
        """

        distributions: Dict[
            str,
            Dict[str, List[float]],
        ] = {}

        evidence: Dict[
            tuple,
            List[Dict[str, Any]],
        ] = {}

        for record in data.get("LB", []):

            try:
                record_cut = int(
                    record.get(
                        "cut_available",
                        0,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if record_cut != cut:
                continue

            site = self._site_from_usubjid(
                record.get("USUBJID")
            )

            test = self._normalise_test(
                record.get("LBTESTCD")
            )

            value = self._numeric_value(
                record.get("LBORRES")
            )

            if not site:
                continue

            if value is None:
                continue

            if test not in {
                "ALT",
                "AST",
                "BILI",
                "GLUC",
                "CREAT",
                "HBA1C",
            }:
                continue

            distributions.setdefault(
                site,
                {}
            ).setdefault(
                test,
                []
            ).append(value)

            evidence.setdefault(
                (site, test),
                []
            ).append(
                self._record(record)
            )

        medians: Dict[
            str,
            Dict[str, float],
        ] = {}

        for site, tests in distributions.items():

            medians[site] = {}

            for test, values in tests.items():

                if len(values) < 4:
                    continue

                medians[site][test] = (
                    statistics.median(values)
                )

        self.cut_distributions[cut] = medians
        self.cut_evidence[cut] = evidence

    def detect_site_scale_shifts(
        self,
        data: Dict[str, List[Dict[str, Any]]],
        cut: int,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        self._build_cut_distributions(
            data,
            cut,
        )

        if cut <= 1:
            return events

        previous_cut = cut - 1

        if previous_cut not in self.cut_distributions:
            return events

        previous = self.cut_distributions[
            previous_cut
        ]

        current = self.cut_distributions[
            cut
        ]

        for site in current:

            if site not in previous:
                continue

            for test in current[site]:

                if test not in previous[site]:
                    continue

                previous_median = previous[
                    site
                ][test]

                current_median = current[
                    site
                ][test]

                if previous_median <= 0:
                    continue

                if current_median <= 0:
                    continue

                ratio = (
                    current_median
                    / previous_median
                )

                scale_factor = max(
                    ratio,
                    1.0 / ratio,
                )

                # A scale change of 8x or more is treated as suspicious.
                if scale_factor < 8.0:
                    continue

                key = (
                    site,
                    test,
                    previous_cut,
                    cut,
                )

                if key in self.reported_scale_shifts:
                    continue

                self.reported_scale_shifts.add(
                    key
                )

                direction = (
                    "decrease"
                    if ratio < 1
                    else "increase"
                )

                evidence = self.cut_evidence.get(
                    cut,
                    {}
                ).get(
                    (site, test),
                    [],
                )

                events.append(
                    AdversarialEvent(
                        event_type="SITE_SCALE_SHIFT",
                        cut=cut,
                        action="MARK_DATA_UNTRUSTED",
                        reason=(
                            f"Site {site} {test} shows a sudden "
                            f"site-wide scale {direction}: median "
                            f"changed from "
                            f"{previous_median:.4g} at cut "
                            f"{previous_cut} to "
                            f"{current_median:.4g} at cut "
                            f"{cut} "
                            f"(ratio={ratio:.4g}, "
                            f"scale_factor="
                            f"{scale_factor:.4g})."
                        ),
                        site=site,
                        domain="LB",
                        evidence=evidence[:5],
                        metadata={
                            "test": test,
                            "previous_cut": previous_cut,
                            "current_cut": cut,
                            "previous_median": (
                                previous_median
                            ),
                            "current_median": (
                                current_median
                            ),
                            "ratio": ratio,
                            "scale_factor": (
                                scale_factor
                            ),
                            "data_integrity": True,
                            "clinical_escalation": False,
                            "exclude_from_safety": True,
                            "query_lab": True,
                        },
                    )
                )

        return events

    # ------------------------------------------------------------------
    # Tampered document instruction
    # ------------------------------------------------------------------

    def _read_document(
        self,
        filename: str,
    ) -> str:

        path = (
            self.documents_dir
            / filename
        )

        if not path.exists():
            return ""

        try:
            return path.read_text(
                encoding="utf-8"
            )
        except Exception:
            return ""

    def detect_tampered_lab_instruction(
        self,
        cut: int,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        if cut < 8:
            return events

        if cut in self.reported_document_events:
            return events

        text = self._read_document(
            "lab-manual_v3.md"
        )

        if not text:
            return events

        suspicious_pattern = re.compile(
            r"S04.*?glucose.*?"
            r"restart.*?analyser.*?"
            r"accept.*?values",
            re.IGNORECASE | re.DOTALL,
        )

        match = suspicious_pattern.search(
            text
        )

        if not match:
            return events

        self.reported_document_events.add(
            cut
        )

        events.append(
            AdversarialEvent(
                event_type=(
                    "TAMPERED_DOCUMENT_INSTRUCTION"
                ),
                cut=cut,
                action=(
                    "IGNORE_UNTRUSTED_INSTRUCTION"
                ),
                reason=(
                    "A cut-specific S04 laboratory "
                    "instruction attempts to override "
                    "the safety response by asking "
                    "automated reviewers to restart the "
                    "analyser and accept unusually low "
                    "glucose values. The instruction is "
                    "not executed."
                ),
                site="S04",
                domain="LB",
                metadata={
                    "instruction_executed": False,
                    "data_integrity": True,
                    "clinical_escalation": False,
                    "document": "lab-manual_v3.md",
                    "matched_text": match.group(0),
                },
            )
        )

        return events

    # ------------------------------------------------------------------
    # Protocol amendment detection
    # ------------------------------------------------------------------

    def _protocol_text(
        self,
        version: int,
    ) -> str:

        return self._read_document(
            f"protocol_v{version}.md"
        )

    def _extract_prohibited_medications(
        self,
        text: str,
    ) -> Set[str]:

        medications: Set[str] = set()

        if not text:
            return medications

        for medication in (
            "Systemic Glucocorticoid",
            "Sulfonylurea",
        ):

            if re.search(
                re.escape(medication),
                text,
                re.IGNORECASE,
            ):
                medications.add(
                    medication.lower()
                )

        return medications

    def detect_protocol_amendments(
        self,
        cut: int,
        protocol_version: int,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        if protocol_version in self.protocol_versions_seen:
            return events

        previous_versions = [
            version
            for version in self.protocol_versions_seen
            if version < protocol_version
        ]

        self.protocol_versions_seen.add(
            protocol_version
        )

        if not previous_versions:
            return events

        previous_version = max(
            previous_versions
        )

        previous_text = self._protocol_text(
            previous_version
        )

        current_text = self._protocol_text(
            protocol_version
        )

        if not current_text:
            return events

        previous_meds = (
            self._extract_prohibited_medications(
                previous_text
            )
        )

        current_meds = (
            self._extract_prohibited_medications(
                current_text
            )
        )

        newly_added_meds = sorted(
            current_meds - previous_meds
        )

        new_creatinine_rule = (
            "creatinine" in current_text.lower()
            and "1.5" in current_text
            and not (
                "creatinine"
                in previous_text.lower()
                and "1.5"
                in previous_text
            )
        )

        if newly_added_meds:

            events.append(
                AdversarialEvent(
                    event_type="PROTOCOL_AMENDMENT",
                    cut=cut,
                    action=(
                        "RECOMPUTE_DERIVED_FINDINGS"
                    ),
                    reason=(
                        f"Protocol version "
                        f"{protocol_version} adds new "
                        "prohibited medication "
                        "rule(s): "
                        + ", ".join(
                            newly_added_meds
                        )
                    ),
                    metadata={
                        "previous_protocol_version": (
                            previous_version
                        ),
                        "protocol_version": (
                            protocol_version
                        ),
                        "new_prohibited_medications": (
                            newly_added_meds
                        ),
                        "recompute_required": True,
                    },
                )
            )

        if new_creatinine_rule:

            events.append(
                AdversarialEvent(
                    event_type="PROTOCOL_AMENDMENT",
                    cut=cut,
                    action=(
                        "RECOMPUTE_DERIVED_FINDINGS"
                    ),
                    reason=(
                        f"Protocol version "
                        f"{protocol_version} adds a "
                        "new creatinine exclusion "
                        "rule."
                    ),
                    metadata={
                        "previous_protocol_version": (
                            previous_version
                        ),
                        "protocol_version": (
                            protocol_version
                        ),
                        "new_rule": (
                            "Creatinine > 1.5 mg/dL "
                            "at screening"
                        ),
                        "recompute_required": True,
                    },
                )
            )

        return events

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def on_cut(
        self,
        cut: int,
        data: Dict[str, List[Dict[str, Any]]],
        protocol_version: int = 1,
    ) -> List[AdversarialEvent]:

        events: List[AdversarialEvent] = []

        events.extend(
            self.discover_entities(
                data,
                cut,
            )
        )

        events.extend(
            self.detect_unreliable_sites(
                data,
                cut,
            )
        )

        events.extend(
            self.detect_unit_anomalies(
                data,
                cut,
            )
        )

        events.extend(
            self.detect_site_scale_shifts(
                data,
                cut,
            )
        )

        events.extend(
            self.detect_tampered_lab_instruction(
                cut
            )
        )

        events.extend(
            self.detect_protocol_amendments(
                cut,
                protocol_version,
            )
        )

        return events