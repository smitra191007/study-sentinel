"""
Owned by: Person A

Deterministic protocol and safety checks for ATLAS.

Rules implemented:
- Hy's Law candidates
- Hospitalisation seriousness override
- Prohibited medication use by protocol version
- Dosing errors
- Visit-window / protocol deviations
"""

from datetime import timedelta

from .cleaning import (
    get_reference_range,
    normalize_lab_value,
    parse_date,
)


def hys_law_candidates(graph, reference_ranges):
    """
    Detect potential Hy's law candidates.

    Protocol rule:
        ALT or AST > 3x ULN
        AND
        total bilirubin > 2x ULN
        within 14 days.

    Site-specific laboratory reference ranges are used.
    S07 ALT/AST values are normalized by cleaning.py.
    """

    findings = []

    for subject_id, subject in graph.get("subjects", {}).items():
        site_id = subject.get("SITEID")

        alt_ast = []
        bilirubin = []

        for r in subject.get("records", {}).get("LB", []):
            testcd = r.get("LBTESTCD")
            raw_value = r.get("LBORRES")
            unit = r.get("LBORRESU", "")

            if testcd not in {"ALT", "AST", "BILI"}:
                continue

            value, normalized_unit, status = normalize_lab_value(
                raw_value,
                unit,
                testcd,
                site_id,
                reference_ranges,
            )

            if status != "OK" or value is None:
                continue

            date = parse_date(r.get("LBDTC"))

            # Invalid dates cannot be used for the
            # 14-day window.
            if date is None:
                continue

            low, high, range_unit = get_reference_range(
                testcd,
                site_id,
                reference_ranges,
            )

            if high is None:
                continue

            if testcd in {"ALT", "AST"}:
                if value > 3 * high:
                    alt_ast.append(
                        {
                            "record": r,
                            "date": date,
                            "value": value,
                            "uln": high,
                            "unit": normalized_unit,
                        }
                    )

            elif testcd == "BILI":
                if value > 2 * high:
                    bilirubin.append(
                        {
                            "record": r,
                            "date": date,
                            "value": value,
                            "uln": high,
                            "unit": normalized_unit,
                        }
                    )

        # Pair elevated liver enzyme and bilirubin results
        # occurring within 14 days.
        for enzyme in alt_ast:
            for bili in bilirubin:
                difference = abs(
                    (enzyme["date"] - bili["date"]).days
                )

                if difference <= 14:
                    enzyme_record = enzyme["record"]
                    bili_record = bili["record"]

                    findings.append(
                        {
                            "usubjid": subject_id,
                            "finding": "HYS_LAW_CANDIDATE",
                            "evidence": [
                                (
                                    "LB",
                                    subject_id,
                                    enzyme_record.get("LBSEQ"),
                                ),
                                (
                                    "LB",
                                    subject_id,
                                    bili_record.get("LBSEQ"),
                                ),
                            ],
                            "detail": (
                                f"liver enzyme >3xULN on "
                                f"{enzyme['date'].isoformat()}, "
                                f"bilirubin >2xULN on "
                                f"{bili['date'].isoformat()}"
                            ),
                        }
                    )

    return findings


def hospitalization_overrides(data):
    """
    Protocol seriousness rule:

        AESHOSP = Y

    makes the adverse event serious regardless of AESER.
    """

    findings = []

    for r in data.get("AE", []):
        hospitalization = str(
            r.get("AESHOSP", "")
        ).strip().upper()

        serious = str(
            r.get("AESER", "")
        ).strip().upper()

        if hospitalization == "Y" and serious != "Y":
            findings.append(
                {
                    "usubjid": r.get("USUBJID"),
                    "finding": "SERIOUS_AE_HOSPITALIZATION_OVERRIDE",
                    "evidence": [
                        (
                            "AE",
                            r.get("USUBJID"),
                            r.get("AESEQ"),
                        )
                    ],
                    "detail": (
                        "AESHOSP=Y but AESER=N — "
                        "protocol says this is serious regardless"
                    ),
                }
            )

    return findings


def prohibited_medication_use(
    data,
    prohibited_meds_by_version,
    cuts_rows,
):
    """
    Flag concomitant medications that are prohibited under
    the protocol version active at the record's cut.

    Protocol versions:

        v1/v2:
            SYSTEMIC GLUCOCORTICOID

        v3:
            SYSTEMIC GLUCOCORTICOID
            SULFONYLUREA
    """

    from .documents import active_protocol_version

    findings = []

    for r in data.get("CM", []):
        medication_class = str(
            r.get("CMCLAS", "")
        ).strip().upper()

        cut = int(
            r.get("cut_available", 0)
        )

        version = active_protocol_version(
            cut,
            cuts_rows,
        )

        # If the cut cannot be mapped, use protocol v1
        # only because v1 is the initial protocol.
        if version is None:
            version = 1

        prohibited = prohibited_meds_by_version(
            version
        )

        if medication_class in prohibited:
            findings.append(
                {
                    "usubjid": r.get("USUBJID"),
                    "finding": "PROHIBITED_MEDICATION",
                    "evidence": [
                        (
                            "CM",
                            r.get("USUBJID"),
                            r.get("CMSEQ"),
                        )
                    ],
                    "detail": (
                        f"{medication_class} prohibited "
                        f"under protocol v{version}"
                    ),
                }
            )

    return findings


def dosing_errors(data):
    """
    Protocol dosing rule:

        DRUG arm:
            expected dose = 10 mg

        PLACEBO arm:
            expected dose = 0 mg

    Any administered dose different from the expected
    dose is a dosing error.
    """

    expected_by_arm = {
        "DRUG": 10.0,
        "PLACEBO": 0.0,
    }

    # Get treatment assignment from DM.
    arm_by_subject = {}

    for r in data.get("DM", []):
        subject = r.get("USUBJID")
        arm = str(
            r.get("ARM", "")
        ).strip().upper()

        if subject:
            arm_by_subject[subject] = arm

    findings = []

    for r in data.get("EX", []):
        subject = r.get("USUBJID")

        arm = arm_by_subject.get(subject)

        if arm not in expected_by_arm:
            continue

        expected = expected_by_arm[arm]

        raw_dose = r.get("EXDOSE")

        try:
            actual = float(raw_dose)
        except (TypeError, ValueError):
            continue

        if actual != expected:
            findings.append(
                {
                    "usubjid": subject,
                    "finding": "DOSING_ERROR",
                    "evidence": [
                        (
                            "EX",
                            subject,
                            r.get("EXSEQ"),
                        )
                    ],
                    "detail": (
                        f"{arm} arm received {actual} mg; "
                        f"expected {expected:g} mg"
                    ),
                }
            )

    return findings


def visit_window_deviations(
    data,
    cut=12,
    cuts_rows=None,
):
    """
    Detect visits performed outside the protocol-defined
    visit window.

    Protocol:

        v1: +/- 7 days
        v2/v3: +/- 3 days

    Visit schedule is relative to each subject's
    baseline date:

        SCREENING = -14
        BASELINE  = 0
        WEEK2     = 14
        WEEK4     = 28
        WEEK8     = 56
        WEEK12    = 84
        WEEK16    = 112
        WEEK20    = 140
        WEEK24    = 168
        EOS       = 182

    A visit outside the allowed window is a
    protocol deviation.
    """

    from .documents import (
        active_protocol_version,
        visit_window_days,
    )

    schedule = {
        "SCREENING": -14,
        "BASELINE": 0,
        "WEEK2": 14,
        "WEEK4": 28,
        "WEEK8": 56,
        "WEEK12": 84,
        "WEEK16": 112,
        "WEEK20": 140,
        "WEEK24": 168,
        "EOS": 182,
    }

    findings = []

    # Determine protocol version at this cut.
    version = None

    if cuts_rows is not None:
        version = active_protocol_version(
            cut,
            cuts_rows,
        )

    if version is None:
        version = 1

    window = visit_window_days(version)

    # Find each subject's baseline date.
    baseline_dates = {}

    for r in data.get("VS", []):
        visit = str(
            r.get("VISIT", "")
        ).strip().upper()

        if visit != "BASELINE":
            continue

        subject = r.get("USUBJID")

        date = parse_date(
            r.get("VSDTC")
        )

        if subject and date is not None:
            baseline_dates.setdefault(
                subject,
                date,
            )

    # Avoid reporting the same visit repeatedly
    # because VS contains multiple measurements
    # for the same visit.
    seen = set()

    for r in data.get("VS", []):
        subject = r.get("USUBJID")

        visit = str(
            r.get("VISIT", "")
        ).strip().upper()

        actual_date = parse_date(
            r.get("VSDTC")
        )

        if not subject:
            continue

        if visit not in schedule:
            continue

        if actual_date is None:
            continue

        baseline = baseline_dates.get(subject)

        if baseline is None:
            continue

        scheduled_date = (
            baseline
            + timedelta(
                days=schedule[visit]
            )
        )

        difference = (
            actual_date - scheduled_date
        ).days

        key = (
            subject,
            visit,
            actual_date,
        )

        if key in seen:
            continue

        seen.add(key)

        if abs(difference) > window:
            findings.append(
                {
                    "usubjid": subject,
                    "finding": "VISIT_WINDOW_DEVIATION",
                    "evidence": [
                        (
                            "VS",
                            subject,
                            r.get("VSSEQ"),
                        )
                    ],
                    "detail": (
                        f"{visit} occurred "
                        f"{difference:+d} days from "
                        f"scheduled day; allowed "
                        f"window is +/-{window} days "
                        f"under protocol v{version}"
                    ),
                }
            )

    return findings


def answer_or_none(
    findings,
    question_context="",
):
    """
    Convert a list of findings into a simple ATLAS answer.
    """

    if not findings:
        return {
            "answer": "none",
            "evidence": [],
            "reason": (
                f"No findings for {question_context}."
                if question_context
                else "No findings."
            ),
        }

    evidence = []

    for finding in findings:
        for item in finding.get(
            "evidence",
            [],
        ):
            if item not in evidence:
                evidence.append(item)

    return {
        "answer": findings,
        "evidence": evidence,
        "reason": (
            f"{len(findings)} finding(s)."
        ),
    }


if __name__ == "__main__":
    print(
        "checks.py loaded successfully."
    )