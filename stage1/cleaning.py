"""
Owned by: Person B

Two jobs:
1. Convert every lab value to the CENTRAL reference unit before anyone
   compares it to a reference range.
2. Decide what non-numeric values and bad dates mean.

Confirmed from the real data:
- ALT/AST are reported in U/L at most sites and ukat/L at site S07.
- 1 ukat/L = 60 U/L.
- reference_ranges.csv contains a LAB column:
    - LAB=CENTRAL -> central laboratory ranges
    - LAB=S07 -> S07's local laboratory ranges
- Non-numeric LBORRES values seen in the data:
    - "<5"
    - "ND"
    - ""
    - decimal-comma values such as "117,9" and "8,17"

Important:
The measured value and the reference range must use the SAME unit
before a safety comparison is made.
Therefore, S07 ALT/AST reference ranges are converted from ukat/L
to U/L before being returned by get_reference_range().
"""

UKAT_TO_U_PER_L = 60.0

# Status codes returned alongside a value.
BELOW_DETECTION = "BELOW_DETECTION"
NOT_DONE = "NOT_DONE"
MISSING = "MISSING"
OK = "OK"


def normalize_lab_value(raw, unit, testcd, site_id, reference_ranges):
    """
    Convert a raw LBORRES/LBORRESU pair into:

        (value, normalized_unit, status)

    The normalized unit is the central/reference comparison unit.

    For S07 ALT/AST:
        raw value: ukat/L
        normalized value: U/L

        conversion:
            1 ukat/L = 60 U/L

    Examples:

        "40.4", "U/L"
            -> (40.4, "U/L", "OK")

        "1.2", "ukat/L", S07 ALT
            -> (72.0, "U/L", "OK")

        "<5"
            -> (None, unit, "BELOW_DETECTION")

        "ND"
            -> (None, unit, "NOT_DONE")

        ""
            -> (None, unit, "MISSING")

    "<5", "ND", and "" are NEVER treated as zero.
    """

    raw = (raw or "").strip()

    # Missing value.
    if raw == "":
        return None, unit, MISSING

    # Not done.
    if raw.upper() == "ND":
        return None, unit, NOT_DONE

    # Below/above detection limit.
    # We do not guess an exact numeric value.
    if raw.startswith("<") or raw.startswith(">"):
        return None, unit, BELOW_DETECTION

    # Handle European decimal-comma notation.
    #
    # Example:
    #     "117,9" -> "117.9"
    #     "8,17"  -> "8.17"
    #
    # Only replace when there is exactly one comma.
    numeric_str = raw.replace(",", ".") if raw.count(",") == 1 else raw

    try:
        value = float(numeric_str)
    except ValueError:
        # Unknown/unrecognised numeric format.
        # Do not crash and do not invent a value.
        return None, unit, MISSING

    # ---------------------------------------------------------
    # S07 ALT/AST unit conversion
    # ---------------------------------------------------------
    #
    # S07 reports ALT and AST in ukat/L.
    # All normalized safety comparisons use U/L.
    #
    # 1 ukat/L = 60 U/L
    #
    if (
        site_id == "S07"
        and unit == "ukat/L"
        and testcd in ("ALT", "AST")
    ):
        value = value * UKAT_TO_U_PER_L
        unit = "U/L"

    return value, unit, OK


def get_reference_range(testcd, site_id, reference_ranges):
    """
    Look up the correct reference range for a test and site.

    Laboratory selection:
        S07 -> LAB=S07
        all other sites -> LAB=CENTRAL

    The returned range is ALWAYS expressed in the same normalized unit
    used by normalize_lab_value().

    Therefore:

        S01 ALT:
            CENTRAL 7-56 U/L
            returns (7.0, 56.0, "U/L")

        S07 ALT:
            S07 local range 0.12-0.93 ukat/L
            converted using x60
            returns approximately (7.2, 55.8, "U/L")

    This prevents an incorrect comparison such as:

        72 U/L > 3 * 0.93 ukat/L

    because those values use different units.
    """

    # Select the appropriate laboratory.
    lab = "S07" if site_id == "S07" else "CENTRAL"

    for row in reference_ranges:

        if (
            row["LBTESTCD"] == testcd
            and row["LAB"] == lab
        ):
            low = float(row["LOW"])
            high = float(row["HIGH"])
            unit = row["UNIT"]

            # -------------------------------------------------
            # Convert S07 ALT/AST reference ranges
            # from ukat/L -> U/L
            # -------------------------------------------------
            if (
                site_id == "S07"
                and testcd in ("ALT", "AST")
                and unit == "ukat/L"
            ):
                low *= UKAT_TO_U_PER_L
                high *= UKAT_TO_U_PER_L
                unit = "U/L"

            return low, high, unit

    # No matching reference range.
    # Never guess a range.
    return None


def get_central_range(testcd, reference_ranges):
    """
    Look up the CENTRAL laboratory reference range for a test.

    This function is retained for callers that specifically need
    the central laboratory range rather than the site-specific range.

    Returns:
        (low, high, unit)

    or:

        None
    """

    for row in reference_ranges:

        if (
            row["LBTESTCD"] == testcd
            and row["LAB"] == "CENTRAL"
        ):
            return (
                float(row["LOW"]),
                float(row["HIGH"]),
                row["UNIT"],
            )

    return None


def parse_date(raw):
    """
    Parse dates found in the study data.

    Supported formats:

        YYYY-MM-DD
        DD-MON-YYYY

    Examples:

        2026-03-21
        03-FEB-2026

    Returns:
        datetime.date

    or:

        None

    Invalid/missing dates are never guessed.
    """

    from datetime import datetime

    raw = (raw or "").strip()

    if not raw:
        return None

    formats = (
        "%Y-%m-%d",
        "%d-%b-%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


if __name__ == "__main__":
    # ---------------------------------------------------------
    # Smoke tests
    # ---------------------------------------------------------

    refs = [
        {
            "LBTESTCD": "ALT",
            "UNIT": "U/L",
            "LOW": "7",
            "HIGH": "56",
            "LAB": "CENTRAL",
        },
        {
            "LBTESTCD": "ALT",
            "UNIT": "ukat/L",
            "LOW": "0.12",
            "HIGH": "0.93",
            "LAB": "S07",
        },
        {
            "LBTESTCD": "AST",
            "UNIT": "U/L",
            "LOW": "10",
            "HIGH": "40",
            "LAB": "CENTRAL",
        },
        {
            "LBTESTCD": "AST",
            "UNIT": "ukat/L",
            "LOW": "0.17",
            "HIGH": "0.67",
            "LAB": "S07",
        },
    ]

    print(
        normalize_lab_value(
            "40.4",
            "U/L",
            "ALT",
            "S01",
            refs,
        )
    )

    print(
        normalize_lab_value(
            "1.2",
            "ukat/L",
            "ALT",
            "S07",
            refs,
        )
    )

    print(
        normalize_lab_value(
            "<5",
            "%",
            "HBA1C",
            "S01",
            refs,
        )
    )

    print(
        normalize_lab_value(
            "117,9",
            "mg/dL",
            "GLUC",
            "S11",
            refs,
        )
    )

    print(
        "S01 ALT:",
        get_reference_range(
            "ALT",
            "S01",
            refs,
        ),
    )

    print(
        "S07 ALT:",
        get_reference_range(
            "ALT",
            "S07",
            refs,
        ),
    )

    print(
        "S07 AST:",
        get_reference_range(
            "AST",
            "S07",
            refs,
        ),
    )

    print(
        parse_date("2026-03-21"),
        parse_date("03-FEB-2026"),
        parse_date("garbage"),
    )