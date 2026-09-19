"""
stage3/integrity.py

PERSON 2 — Data integrity / laboratory anomaly detection.

Detects site-wide laboratory distribution shifts that may indicate
unit corruption or other data-integrity problems.

Important safety behavior:
    suspicious lab values
        -> UNTRUSTED
        -> exclude from clinical safety interpretation
        -> raise data-quality query
        -> NEVER create a clinical escalation from the corrupted values

This module does not modify watch.py.
It returns Stage 3 Decision objects that the surveillance framework
can record and consume.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from stage3.models import Decision, RecordRef


# Common unit-conversion factors encountered in laboratory data.
# This is deliberately generic rather than tied to a particular subject/site.
UNIT_FACTORS = {
    18.0: "possible glucose mg/dL ↔ mmol/L conversion",
    10.0: "possible ten-fold unit conversion",
    100.0: "possible hundred-fold unit conversion",
    1000.0: "possible thousand-fold unit conversion",
}


def _number(value: Any) -> float | None:
    """Convert a raw CSV value to float when possible."""
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _field(record: dict, *names: str) -> Any:
    """Return the first populated field from a record."""
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def _lab_test_code(record: dict) -> str:
    return str(
        _field(
            record,
            "LBTESTCD",
            "LBTEST",
            "test_code",
            "test",
        )
        or ""
    ).strip()


def _lab_unit(record: dict) -> str:
    return str(
        _field(
            record,
            "LBORRESU",
            "LBSTRESU",
            "UNIT",
            "unit",
        )
        or ""
    ).strip()


def _lab_value(record: dict) -> float | None:
    """
    Prefer standardized numeric result, then fall back to original result.
    """
    return _number(
        _field(
            record,
            "LBSTRESN",
            "LBORRES",
            "value",
            "result",
        )
    )


def _subject(record: dict) -> str | None:
    return (
        record.get("USUBJID")
        or record.get("usubjid")
        or record.get("subject_id")
    )


def _sequence(record: dict) -> Any:
    return (
        record.get("LBSEQ")
        or record.get("seq")
        or record.get("SEQ")
    )


def _site(record: dict) -> str:
    """
    Resolve site from an explicit field where available.

    Falls back to extracting Sxx from USUBJID, without hardcoding a
    particular study/site identifier.
    """
    explicit = (
        record.get("SITE")
        or record.get("SITEID")
        or record.get("site")
        or record.get("site_id")
    )

    if explicit:
        return str(explicit)

    subject = _subject(record) or ""

    if "-S" in subject:
        tail = subject.split("-S", 1)[1]
        site_number = tail.split("-", 1)[0]
        return f"S{site_number}"

    return ""


def _group_records(
    records: list[dict],
) -> dict[tuple[str, str], list[dict]]:
    """
    Group numeric lab records by (site, test).

    This lets us detect a site-wide shift rather than reacting to one
    clinically interesting patient value.
    """
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for record in records:
        value = _lab_value(record)

        if value is None:
            continue

        site = _site(record)
        test = _lab_test_code(record)

        if not site or not test:
            continue

        groups[(site, test)].append(record)

    return groups


def _possible_conversion(
    before: float,
    current: float,
) -> tuple[float, str] | None:
    """
    Check whether two medians are approximately related by a common
    unit-conversion factor.

    Returns:
        (factor, explanation)
    """

    if before <= 0 or current <= 0:
        return None

    ratio = before / current

    for factor, description in UNIT_FACTORS.items():
        if abs(ratio - factor) / factor <= 0.15:
            return factor, description

        inverse = 1.0 / factor

        if abs(ratio - inverse) / inverse <= 0.15:
            return factor, description

    return None


def detect_lab_integrity(
    cut_data: dict[str, list[dict]],
    cut: int,
    previous_data: dict[str, list[dict]] | None = None,
) -> list[Decision]:
    """
    Detect site-wide laboratory distribution shifts.

    Parameters
    ----------
    cut_data:
        Corrected data view available at the current cut.

    cut:
        Current surveillance cut.

    previous_data:
        Previous cut's corrected data, when available.

    Returns
    -------
    list[Decision]
        Integrity decisions. These decisions identify data as untrusted.
        They do NOT represent clinical safety escalations.
    """

    current_records = cut_data.get("LB", [])

    if not current_records:
        return []

    previous_records = (
        previous_data.get("LB", [])
        if previous_data
        else []
    )

    current_groups = _group_records(current_records)
    previous_groups = _group_records(previous_records)

    decisions: list[Decision] = []

    for (site, test), current_rows in current_groups.items():

        # We need enough observations to call something site-wide.
        if len(current_rows) < 3:
            continue

        current_values = [
            _lab_value(row)
            for row in current_rows
        ]

        current_values = [
            value
            for value in current_values
            if value is not None
        ]

        if len(current_values) < 3:
            continue

        current_median = median(current_values)

        previous_rows = previous_groups.get(
            (site, test),
            [],
        )

        if len(previous_rows) < 3:
            continue

        previous_values = [
            _lab_value(row)
            for row in previous_rows
        ]

        previous_values = [
            value
            for value in previous_values
            if value is not None
        ]

        if len(previous_values) < 3:
            continue

        previous_median = median(previous_values)

        if previous_median <= 0 or current_median <= 0:
            continue

        ratio = current_median / previous_median

        # Ignore small ordinary fluctuations.
        if 0.5 < ratio < 2.0:
            continue

        conversion = _possible_conversion(
            previous_median,
            current_median,
        )

        # A very large site-wide shift without a recognizable
        # conversion factor can still be a data-integrity signal.
        shift_detected = (
            ratio <= 0.5
            or ratio >= 2.0
        )

        if not shift_detected:
            continue

        if conversion:
            factor, explanation = conversion
            reason = (
                f"Site {site} laboratory test {test} shows a "
                f"site-wide distribution shift at cut {cut}: "
                f"median changed from {previous_median:g} to "
                f"{current_median:g} (ratio {ratio:.3f}). "
                f"Possible unit conversion detected "
                f"(factor approximately {factor:g}; {explanation}). "
                f"Values are treated as UNTRUSTED pending laboratory "
                f"confirmation."
            )
        else:
            reason = (
                f"Site {site} laboratory test {test} shows a "
                f"site-wide distribution shift at cut {cut}: "
                f"median changed from {previous_median:g} to "
                f"{current_median:g} (ratio {ratio:.3f}). "
                f"No ordinary clinical explanation is assumed; "
                f"values are treated as UNTRUSTED pending laboratory "
                f"confirmation."
            )

        evidence_rows = current_rows[:5]

        evidence = [
            RecordRef(
                domain="LB",
                usubjid=_subject(row),
                seq=_sequence(row),
            )
            for row in evidence_rows
        ]

        decision_id = (
            f"integrity-LB-{site}-{test}-cut{cut}"
        )

        decisions.append(
            Decision(
                decision_id=decision_id,
                cut=cut,
                node="integrity",
                action="UNTRUSTED",
                reason=reason,
                status="OPEN",
                evidence=evidence,
                metadata={
                    "site": site,
                    "test": test,
                    "previous_median": previous_median,
                    "current_median": current_median,
                    "ratio": ratio,
                    "possible_unit_conversion": bool(conversion),
                    "clinical_escalation": False,
                    "exclude_from_safety_screening": True,
                    "lab_query_required": True,
                },
            )
        )

    return decisions


def mark_untrusted_records(
    cut_data: dict[str, list[dict]],
    decisions: list[Decision],
) -> list[dict]:
    """
    Return references to records covered by integrity decisions.

    The original records are not modified.

    This helper can be used by the surveillance layer to maintain
    WatchState.untrusted_records.
    """

    untrusted: list[dict] = []

    for decision in decisions:
        if decision.action != "UNTRUSTED":
            continue

        for ref in decision.evidence:
            untrusted.append(
                ref.to_dict()
            )

    return untrusted