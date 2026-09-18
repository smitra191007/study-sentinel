"""
Owned by: Person D

The core scoring logic.

Every check returns findings shaped like:

    {
        "usubjid": "042-S01-001",
        "finding": "HYS_LAW_CANDIDATE",
        "evidence": [
            ("LB", "042-S01-001", "12"),
            ("LB", "042-S01-001", "13")
        ],
        "detail": "ALT 3.2xULN and BILI 2.1xULN within 14 days"
    }

Evidence is always a list of:

    (domain, USUBJID, seq)

These triples identify the exact source records supporting
the finding.

Never cite a triple that does not support the claim.

If a check finds nothing, return an empty list.
That IS the answer "none".

Do not return a placeholder or guess.
"""

from .cleaning import (
    normalize_lab_value,
    get_reference_range,
    OK,
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

    This function only identifies candidates.

    Final adjudication may require checking for:
        - cholestasis
        - alternative explanations
        - other clinical information

    Site-specific laboratory ranges are used:

        S07 -> S07 range
        other sites -> CENTRAL range

    All measured values and ranges are compared in the same
    normalized unit.
    """

    findings = []

    # ---------------------------------------------------------
    # Process each subject independently.
    # ---------------------------------------------------------

    for usubjid, subj in graph["subjects"].items():

        site = subj["site"]

        lb_records = subj["records"].get("LB", [])

        # -----------------------------------------------------
        # Get the correct reference ranges for this subject's
        # laboratory/site.
        # -----------------------------------------------------

        alt_range = get_reference_range(
            "ALT",
            site,
            reference_ranges,
        )

        ast_range = get_reference_range(
            "AST",
            site,
            reference_ranges,
        )

        bili_range = get_reference_range(
            "BILI",
            site,
            reference_ranges,
        )

        # If any required reference range is unavailable,
        # do not guess.
        if (
            alt_range is None
            or ast_range is None
            or bili_range is None
        ):
            continue

        _, alt_high, _ = alt_range
        _, ast_high, _ = ast_range
        _, bili_high, _ = bili_range

        # -----------------------------------------------------
        # Store liver enzyme and bilirubin threshold hits.
        #
        # Each item:
        #
        #     (date, domain, sequence)
        #
        # -----------------------------------------------------

        liver_hits = []
        bili_hits = []

        # -----------------------------------------------------
        # Inspect laboratory records.
        # -----------------------------------------------------

        for r in lb_records:

            value, unit, status = normalize_lab_value(
                r.get("LBORRES"),
                r.get("LBORRESU"),
                r.get("LBTESTCD"),
                site,
                reference_ranges,
            )

            # Non-numeric / missing / detection-limit values
            # cannot be safely used in arithmetic.
            if status != OK:
                continue

            date = parse_date(
                r.get("LBDTC")
            )

            # Invalid dates cannot be used for the
            # 14-day window.
            if date is None:
                continue

            testcd = r.get("LBTESTCD")

            # -------------------------------------------------
            # ALT > 3x ULN
            # -------------------------------------------------

            if (
                testcd == "ALT"
                and value > 3 * alt_high
            ):
                liver_hits.append(
                    (
                        date,
                        "LB",
                        r["LBSEQ"],
                    )
                )

            # -------------------------------------------------
            # AST > 3x ULN
            # -------------------------------------------------

            elif (
                testcd == "AST"
                and value > 3 * ast_high
            ):
                liver_hits.append(
                    (
                        date,
                        "LB",
                        r["LBSEQ"],
                    )
                )

            # -------------------------------------------------
            # Total bilirubin > 2x ULN
            # -------------------------------------------------

            elif (
                testcd == "BILI"
                and value > 2 * bili_high
            ):
                bili_hits.append(
                    (
                        date,
                        "LB",
                        r["LBSEQ"],
                    )
                )

        # -----------------------------------------------------
        # Pair liver-enzyme and bilirubin abnormalities.
        #
        # Hy's law requires the two abnormalities to occur
        # within 14 days of each other.
        # -----------------------------------------------------

        for (
            liver_date,
            liver_domain,
            liver_seq,
        ) in liver_hits:

            for (
                bili_date,
                bili_domain,
                bili_seq,
            ) in bili_hits:

                difference_days = abs(
                    (liver_date - bili_date).days
                )

                if difference_days <= 14:

                    findings.append(
                        {
                            "usubjid": usubjid,
                            "finding": "HYS_LAW_CANDIDATE",
                            "evidence": [
                                (
                                    liver_domain,
                                    usubjid,
                                    liver_seq,
                                ),
                                (
                                    bili_domain,
                                    usubjid,
                                    bili_seq,
                                ),
                            ],
                            "detail": (
                                f"liver enzyme >3xULN on "
                                f"{liver_date}, "
                                f"bilirubin >2xULN on "
                                f"{bili_date}"
                            ),
                        }
                    )

    return findings


def hospitalization_overrides(data):
    """
    Protocol seriousness rule:

        AESHOSP = Y

    makes the adverse event serious regardless of AESER.

    Therefore, flag:

        AESHOSP = Y
        AESER = N

    as a seriousness miscoding.
    """

    findings = []

    for r in data.get("AE", []):

        if (
            r.get("AESHOSP") == "Y"
            and r.get("AESER") == "N"
        ):
            findings.append(
                {
                    "usubjid": r["USUBJID"],
                    "finding": "SERIOUSNESS_MISCODED",
                    "evidence": [
                        (
                            "AE",
                            r["USUBJID"],
                            r["AESEQ"],
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
            SYSTEMIC_GLUCOCORTICOID

        v3:
            SYSTEMIC_GLUCOCORTICOID
            SULFONYLUREA
    """

    from .documents import active_protocol_version

    findings = []

    for r in data.get("CM", []):

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

        medication_class = (
            r.get("CMCLAS", "")
            .upper()
        )

        if medication_class in prohibited:

            findings.append(
                {
                    "usubjid": r["USUBJID"],
                    "finding": "PROHIBITED_MEDICATION",
                    "evidence": [
                        (
                            "CM",
                            r["USUBJID"],
                            r["CMSEQ"],
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

    Any administered dose different from the expected dose
    is flagged as a dosing error.
    """

    findings = []

    # ---------------------------------------------------------
    # Map each subject to their treatment arm.
    # ---------------------------------------------------------

    dm_arm = {
        r["USUBJID"]: r["ARM"]
        for r in data.get("DM", [])
    }

    # ---------------------------------------------------------
    # Inspect exposure records.
    # ---------------------------------------------------------

    for r in data.get("EX", []):

        usubjid = r["USUBJID"]

        arm = dm_arm.get(usubjid)

        # If there is no known treatment arm, do not guess.
        if arm is None:
            continue

        try:
            dose = float(
                r["EXDOSE"]
            )
        except (
            ValueError,
            TypeError,
        ):
            # Non-numeric dose cannot be compared safely.
            continue

        if arm == "DRUG":
            expected = 10
        elif arm == "PLACEBO":
            expected = 0
        else:
            # Unknown arm — do not guess expected dose.
            continue

        if dose != expected:

            findings.append(
                {
                    "usubjid": usubjid,
                    "finding": "DOSING_ERROR",
                    "evidence": [
                        (
                            "EX",
                            usubjid,
                            r["EXSEQ"],
                        )
                    ],
                    "detail": (
                        f"dose {dose}mg, "
                        f"expected {expected}mg "
                        f"for arm {arm}"
                    ),
                }
            )

    return findings


def answer_or_none(
    findings,
    question_context="",
):
    """
    Convert a findings list into an answer structure.

    If there are no findings:

        answer = "none"

    Never fabricate a finding.
    """

    if not findings:

        return {
            "answer": "none",
            "evidence": [],
            "reason": (
                f"no matching records found "
                f"({question_context})"
            ),
        }

    return {
        "answer": findings,
        "evidence": [
            finding["evidence"]
            for finding in findings
        ],
    }