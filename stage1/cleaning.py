"""
Owned by: Person B
Two jobs: (1) convert every lab value to the CENTRAL reference unit before
anyone compares it to a range, (2) decide what non-numeric values and bad
dates mean. Document every decision below in plain comments — you need this
verbatim for the README's "Data handling" section.

Confirmed from the real data:
- ALT/AST are reported in U/L (most sites) or ukat/L (site S07 only).
  1 ukat/L = 60 U/L (per documents/lab-manual.md).
- reference_ranges.csv has a LAB column: rows with LAB=CENTRAL are the
  conventional-unit ranges; the LAB=S07 rows are already in ukat/L for
  site S07's own reporting unit.
- Non-numeric LBORRES values seen in the data: "<5", "ND", "" (empty),
  and decimal-comma values like "117,9" or "8,17" (European format).
"""

UKAT_TO_U_PER_L = 60.0

# status codes returned alongside a value — use these consistently
BELOW_DETECTION = "BELOW_DETECTION"   # "<5" style
NOT_DONE = "NOT_DONE"                  # "ND"
MISSING = "MISSING"                    # empty string
OK = "OK"


def normalize_lab_value(raw, unit, testcd, site_id, reference_ranges):
    """
    Converts a raw LBORRES/LBORRESU pair into a (value, unit, status) tuple
    in the CENTRAL reference unit for that test, so it can be compared
    directly against the CENTRAL row in reference_ranges.csv.

    Returns:
        (float_value_or_None, standard_unit, status)

    Decision: "<5", "ND" and "" are NEVER treated as 0. A caller must check
    status == OK before doing arithmetic on the value.
    """
    raw = (raw or "").strip()

    if raw == "":
        return None, unit, MISSING
    if raw.upper() == "ND":
        return None, unit, NOT_DONE
    if raw.startswith("<") or raw.startswith(">"):
        # Below/above detection limit — report as such, don't guess a number.
        return None, unit, BELOW_DETECTION

    # Decimal-comma numbers (e.g. "117,9") -> convert to a real float.
    numeric_str = raw.replace(",", ".") if raw.count(",") == 1 else raw
    try:
        value = float(numeric_str)
    except ValueError:
        return None, unit, MISSING  # unrecognised format — treat as missing, don't crash

    # Unit conversion: ukat/L -> U/L for ALT/AST at the local lab (site S07).
    if unit == "ukat/L" and testcd in ("ALT", "AST"):
        value = value * UKAT_TO_U_PER_L
        unit = "U/L"

    return value, unit, OK


def get_central_range(testcd, reference_ranges):
    """Looks up the CENTRAL (conventional-unit) reference range for a test."""
    for row in reference_ranges:
        if row["LBTESTCD"] == testcd and row["LAB"] == "CENTRAL":
            return float(row["LOW"]), float(row["HIGH"]), row["UNIT"]
    return None


def parse_date(raw):
    """
    Accepts the two date formats seen in the data: ISO (2026-03-21) and
    DD-MON-YYYY (03-FEB-2026). Returns a datetime.date or None if the
    format isn't recognised — callers must handle None, never assume a date.
    """
    from datetime import datetime
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None  # unrecognised format — do not guess


if __name__ == "__main__":
    # Smoke tests
    refs = [{"LBTESTCD": "ALT", "UNIT": "U/L", "LOW": "7", "HIGH": "56", "LAB": "CENTRAL"}]
    print(normalize_lab_value("40.4", "U/L", "ALT", "S01", refs))
    print(normalize_lab_value("1.2", "ukat/L", "ALT", "S07", refs))
    print(normalize_lab_value("<5", "%", "HBA1C", "S01", refs))
    print(normalize_lab_value("117,9", "mg/dL", "GLUC", "S11", refs))
    print(parse_date("2026-03-21"), parse_date("03-FEB-2026"), parse_date("garbage"))
