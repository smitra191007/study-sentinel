"""
ATLAS — Deterministic Answer Agent

Owned by: Person A

Answers common clinical-trial questions deterministically from the
already-loaded study data.

Supported question families:
- COUNT
- LOOKUP
- FINDING
- TRAP

Evidence format:
    [domain, USUBJID, seq]

The agent does not hard-code subject IDs, sites, or counts.
"""

import re
from collections import Counter


SEQ_FIELD = {
    "DM": None,
    "AE": "AESEQ",
    "LB": "LBSEQ",
    "VS": "VSSEQ",
    "EX": "EXSEQ",
    "CM": "CMSEQ",
    "DS": "DSSEQ",
    "MH": "MHSEQ",
    "EG": "EGSEQ",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def evidence(domain, record):
    """
    Return the required evidence triple:
        [domain, USUBJID, seq]
    """

    seq_field = SEQ_FIELD.get(domain)

    if seq_field is None:
        return [
            domain,
            record.get("USUBJID"),
            "1",
        ]

    return [
        domain,
        record.get("USUBJID"),
        record.get(seq_field),
    ]


def all_records(data):
    """Yield (domain, record)."""

    for domain, records in data.items():
        for record in records:
            yield domain, record


def find_subject(data, usubjid):
    """Return all records belonging to one subject."""

    result = []

    for domain, record in all_records(data):
        if record.get("USUBJID") == usubjid:
            result.append((domain, record))

    return result


# ============================================================
# LOOKUP SUBJECT
# ============================================================

def lookup_subject(data, usubjid):
    """Return basic DM information for a subject."""

    for record in data.get("DM", []):
        if record.get("USUBJID") == usubjid:
            return {
                "answer": {
                    "USUBJID": usubjid,
                    "SITEID": record.get("SITEID"),
                    "COUNTRY": record.get("COUNTRY"),
                    "AGE": record.get("AGE"),
                    "SEX": record.get("SEX"),
                    "ARM": record.get("ARM"),
                },
                "evidence": [
                    evidence("DM", record)
                ],
                "reason": "Subject found in DM.",
            }

    return {
        "answer": "none",
        "evidence": [],
        "reason": "Subject not found.",
    }


# ============================================================
# COUNT
# ============================================================

def count_domain(data, domain):
    """Count records in a domain."""

    records = data.get(domain, [])

    if not records:
        return {
            "answer": 0,
            "evidence": [],
            "reason": f"No records found in domain {domain}.",
        }

    return {
        "answer": len(records),
        "evidence": [
            evidence(domain, records[0])
        ],
        "reason": f"{len(records)} records in {domain}.",
    }


def count_subjects(data):
    """Count unique subjects using DM."""

    subjects = data.get("DM", [])

    return {
        "answer": len(subjects),
        "evidence": [
            evidence("DM", record)
            for record in subjects[:10]
        ],
        "reason": f"{len(subjects)} subjects found.",
    }


def count_by_site(data):
    """Count subjects grouped by SITEID."""

    counts = Counter()

    for record in data.get("DM", []):
        site = record.get("SITEID")

        if site:
            counts[site] += 1

    return {
        "answer": dict(sorted(counts.items())),
        "evidence": [
            evidence("DM", record)
            for record in data.get("DM", [])
        ],
        "reason": "Subjects counted by site.",
    }


# ============================================================
# LOOKUP RECORD
# ============================================================

def lookup_record(data, domain, usubjid, seq):
    """LOOKUP an exact record."""

    seq_field = SEQ_FIELD.get(domain)

    if domain == "DM":
        for record in data.get("DM", []):
            if record.get("USUBJID") == usubjid:
                return {
                    "answer": record,
                    "evidence": [
                        evidence(domain, record)
                    ],
                    "reason": "Subject record found.",
                }

    if seq_field:
        for record in data.get(domain, []):
            if (
                record.get("USUBJID") == usubjid
                and str(record.get(seq_field)) == str(seq)
            ):
                return {
                    "answer": record,
                    "evidence": [
                        evidence(domain, record)
                    ],
                    "reason": "Exact record found.",
                }

    return {
        "answer": "none",
        "evidence": [],
        "reason": "Requested record was not found.",
    }


# ============================================================
# ADVERSE EVENTS
# ============================================================

def find_adverse_events(data, usubjid=None):
    """Find AE records."""

    records = data.get("AE", [])

    if usubjid:
        records = [
            record
            for record in records
            if record.get("USUBJID") == usubjid
        ]

    if not records:
        return {
            "answer": "none",
            "evidence": [],
            "reason": "No adverse events found.",
        }

    return {
        "answer": [
            {
                "USUBJID": record.get("USUBJID"),
                "AEDECOD": record.get("AEDECOD"),
                "AETERM": record.get("AETERM"),
                "AESER": record.get("AESER"),
                "AESHOSP": record.get("AESHOSP"),
            }
            for record in records
        ],
        "evidence": [
            evidence("AE", record)
            for record in records
        ],
        "reason": f"{len(records)} adverse event record(s) found.",
    }


# ============================================================
# EXPOSURE
# ============================================================

def find_exposure(data, usubjid=None):
    """Find EX records."""

    records = data.get("EX", [])

    if usubjid:
        records = [
            record
            for record in records
            if record.get("USUBJID") == usubjid
        ]

    if not records:
        return {
            "answer": "none",
            "evidence": [],
            "reason": "No exposure records found.",
        }

    return {
        "answer": records,
        "evidence": [
            evidence("EX", record)
            for record in records
        ],
        "reason": f"{len(records)} exposure record(s) found.",
    }


# ============================================================
# PROHIBITED MEDICATIONS
# ============================================================

def find_prohibited_medications(
    data,
    prohibited_meds_by_version=None,
    cuts_rows=None,
):
    """Run deterministic prohibited-medication check."""

    from .checks import prohibited_medication_use

    if prohibited_meds_by_version is None:
        from .documents import prohibited_meds
        prohibited_meds_by_version = prohibited_meds

    findings = prohibited_medication_use(
        data,
        prohibited_meds_by_version,
        cuts_rows or [],
    )

    if not findings:
        return {
            "answer": "none",
            "evidence": [],
            "reason": "No prohibited medication use found.",
        }

    evidence_rows = []

    for finding in findings:
        evidence_rows.extend(
            finding.get("evidence", [])
        )

    return {
        "answer": findings,
        "evidence": evidence_rows,
        "reason": (
            f"{len(findings)} prohibited-medication finding(s)."
        ),
    }


# ============================================================
# FINDING CHECKS
# ============================================================

def run_finding_checks(
    data,
    reference_ranges=None,
    prohibited_meds_by_version=None,
    cuts_rows=None,
    cut=None,
):
    """Run deterministic safety/protocol finding checks."""

    from . import checks
    from .graph import build

    graph, _ = build(data)

    if prohibited_meds_by_version is None:
        from .documents import prohibited_meds
        prohibited_meds_by_version = prohibited_meds

    # If no explicit cut was supplied, use the latest cut.
    if cut is None:
        if cuts_rows:
            cut = max(
                int(row["cut"])
                for row in cuts_rows
            )
        else:
            cut = 12

    findings = {
        # Hy's Law
        "hys_law_candidates": (
            checks.hys_law_candidates(
                graph,
                reference_ranges or [],
            )
        ),

        # Seriousness
        "seriousness_miscoded": (
            checks.hospitalization_overrides(
                data
            )
        ),

        # Prohibited medications
        "prohibited_medication_use": (
            checks.prohibited_medication_use(
                data,
                prohibited_meds_by_version,
                cuts_rows or [],
            )
        ),

        # Dosing
        "dosing_errors": (
            checks.dosing_errors(
                data
            )
        ),

        # Visit windows
        "visit_window_deviations": (
            checks.visit_window_deviations(
                data,
                cut=cut,
                cuts_rows=cuts_rows or [],
            )
        ),
    }

    return findings


# ============================================================
# ANSWER FINDING
# ============================================================

def answer_finding(
    data,
    finding_type,
    reference_ranges=None,
    prohibited_meds_by_version=None,
    cuts_rows=None,
    cut=None,
):
    """Answer a FINDING question."""

    findings = run_finding_checks(
        data,
        reference_ranges,
        prohibited_meds_by_version,
        cuts_rows,
        cut=cut,
    )

    aliases = {
        "hys": "hys_law_candidates",
        "hys law": "hys_law_candidates",
        "hys's law": "hys_law_candidates",
        "hy's law": "hys_law_candidates",
        "hy’s law": "hys_law_candidates",

        "serious": "seriousness_miscoded",
        "seriousness": "seriousness_miscoded",

        "prohibited": "prohibited_medication_use",
        "medication": "prohibited_medication_use",
        "prohibited medication": "prohibited_medication_use",

        "dosing": "dosing_errors",
        "dose": "dosing_errors",

        "visit window": "visit_window_deviations",
        "visit windows": "visit_window_deviations",
        "visit window deviations": "visit_window_deviations",
        "visit deviations": "visit_window_deviations",
    }

    key = aliases.get(
        finding_type.lower().strip(),
        finding_type.lower().strip(),
    )

    result = findings.get(key, [])

    if not result:
        return {
            "answer": "none",
            "evidence": [],
            "reason": f"No {key} findings.",
        }

    evidence_rows = []

    for finding in result:
        evidence_rows.extend(
            finding.get("evidence", [])
        )

    return {
        "answer": result,
        "evidence": evidence_rows,
        "reason": f"{len(result)} {key} finding(s).",
    }


# ============================================================
# TRAP DETECTION
# ============================================================

def answer_trap(data_dir):
    """
    Detect embedded instructions in study documents.

    IMPORTANT:
    These instructions are treated as evidence only.
    They are NEVER executed.
    """

    from .documents import scan_for_embedded_instructions

    findings = []

    for name in (
        "lab-manual.md",
        "lab-manual_v3.md",
    ):
        path = f"{data_dir}/documents/{name}"

        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            continue

        findings.extend(
            scan_for_embedded_instructions(
                text,
                name,
            )
        )

    if not findings:
        return {
            "answer": "none",
            "evidence": [],
            "reason": "No embedded reviewer instructions detected.",
        }

    return {
        "answer": findings,
        "evidence": [],
        "reason": (
            "Embedded reviewer instructions were detected and "
            "reported as evidence; they were not executed."
        ),
    }


# ============================================================
# QUESTION CLASSIFICATION
# ============================================================

def classify_question(question):
    """
    Classify a natural-language question into:

        COUNT
        LOOKUP
        FINDING
        TRAP
    """

    q = question.lower().strip()

    # --------------------------------------------------------
    # TRAP
    # --------------------------------------------------------

    if any(
        word in q
        for word in (
            "trap",
            "instruction",
            "automated reviewer",
            "do not flag",
            "exclude from",
            "restart the analyser",
            "restart the analyzer",
        )
    ):
        return "TRAP"

    # --------------------------------------------------------
    # FINDING
    # --------------------------------------------------------

    if any(
        word in q
        for word in (
            "hy's law",
            "hy’s law",
            "hys law",
            "hys",
            "serious adverse",
            "seriousness",
            "prohibited medication",
            "prohibited medication use",
            "dosing error",
            "dose error",
            "visit window",
            "visit windows",
            "visit deviation",
            "visit deviations",
            "finding",
            "find any",
            "find all",
        )
    ):
        return "FINDING"

    # --------------------------------------------------------
    # COUNT
    # --------------------------------------------------------

    if (
        "count" in q
        or "how many" in q
        or "number of" in q
    ):
        return "COUNT"

    # --------------------------------------------------------
    # LOOKUP
    # --------------------------------------------------------

    if any(
        word in q
        for word in (
            "lookup",
            "look up",
            "what is",
            "what was",
            "show me",
            "give me",
            "details for",
            "information for",
        )
    ):
        return "LOOKUP"

    return "LOOKUP"


# ============================================================
# DOMAIN EXTRACTION
# ============================================================

def extract_domain(question):
    """Extract a known SDTM domain."""

    upper = question.upper()

    # Explicit domain names, e.g. "LB record" or "AE domain"
    for domain in SEQ_FIELD:
        if re.search(
            rf"\b{re.escape(domain)}\b",
            upper,
        ):
            return domain

    # SDTM variable names, e.g. LBORRES -> LB, AEDECOD -> AE
    for domain in SEQ_FIELD:
        if re.search(
            rf"\b{re.escape(domain)}[A-Z0-9_]+\b",
            upper,
        ):
            return domain

    domain_names = {
        "adverse event": "AE",
        "laboratory": "LB",
        "lab": "LB",
        "vital": "VS",
        "exposure": "EX",
        "medication": "CM",
        "disposition": "DS",
        "medical history": "MH",
        "ecg": "EG",
        "subject": "DM",
    }

    lower = question.lower()

    for phrase, domain in domain_names.items():
        if phrase in lower:
            return domain

    return None

# ============================================================
# SUBJECT ID EXTRACTION
# ============================================================

def extract_usubjid(question):
    """Extract a subject identifier."""

    match = re.search(
        r"\b[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+\b",
        question,
    )

    if match:
        return match.group(0)

    return None


# ============================================================
# SEQUENCE EXTRACTION
# ============================================================

def extract_sequence(question):
    """Extract an explicit sequence/record number."""

    patterns = [
        (
            r"\b(?:seq|sequence|record)"
            r"\s*(?:number)?"
            r"\s*[:=]?\s*(\d+)\b"
        ),
        r"\b(?:SEQ|RECORD)\s*[:=]?\s*(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            question,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

    return None

# ============================================================
# MAIN ANSWER FUNCTION
# ============================================================

def answer_question(
    question,
    data,
    data_dir=None,
    reference_ranges=None,
    prohibited_meds_by_version=None,
    cuts_rows=None,
    cut=None,
):
    """Main Answer Agent entry point."""

    qtype = classify_question(question)

    # ========================================================
    # TRAP
    # ========================================================

    if qtype == "TRAP":

        if data_dir is None:
            return {
                "question": question,
                "type": qtype,
                "answer": "none",
                "evidence": [],
                "reason": (
                    "data_dir is required for document trap checks."
                ),
            }

        result = answer_trap(data_dir)

    # ========================================================
    # FINDING
    # ========================================================

    elif qtype == "FINDING":

        lower = question.lower()

        # Hy's Law
        if (
            "hy's law" in lower
            or "hy’s law" in lower
            or "hys law" in lower
            or "hys" in lower
        ):
            finding_type = "hys_law_candidates"

        # Visit window
        elif (
            "visit window" in lower
            or "visit windows" in lower
            or "visit deviation" in lower
            or "visit deviations" in lower
        ):
            finding_type = "visit_window_deviations"

        # Prohibited medication
        elif (
            "prohibited" in lower
            or "medication" in lower
        ):
            finding_type = "prohibited_medication_use"

        # Dosing
        elif (
            "dose" in lower
            or "dosing" in lower
        ):
            finding_type = "dosing_errors"

        # Default finding
        else:
            finding_type = "seriousness_miscoded"

        result = answer_finding(
            data,
            finding_type,
            reference_ranges,
            prohibited_meds_by_version,
            cuts_rows,
            cut=cut,
        )

    # ========================================================
    # COUNT
    # ========================================================

    elif qtype == "COUNT":

        lower = question.lower()

        # Subjects by site
        if (
            "by site" in lower
            or "each site" in lower
            or "per site" in lower
        ):
            result = count_by_site(data)

        # Subjects
        elif (
            "subject" in lower
            or "patient" in lower
        ):
            result = count_subjects(data)

        # Specific domain
        else:
            domain = extract_domain(question)

            if domain:
                result = count_domain(
                    data,
                    domain,
                )
            else:
                result = {
                    "answer": 0,
                    "evidence": [],
                    "reason": (
                        "Could not determine what should be counted."
                    ),
                }

    # ========================================================
    # LOOKUP
    # ========================================================

    else:

        usubjid = extract_usubjid(question)
        domain = extract_domain(question)
        seq = extract_sequence(question)

        # Exact record
        if (
            usubjid
            and domain
            and seq
        ):
            result = lookup_record(
                data,
                domain,
                usubjid,
                seq,
            )

        # Subject lookup
        elif usubjid:
            result = lookup_subject(
                data,
                usubjid,
            )

        # Cannot identify target
        else:
            result = {
                "answer": "none",
                "evidence": [],
                "reason": (
                    "No subject ID or exact record identifier "
                    "was found in the question."
                ),
            }

    return {
        "question": question,
        "type": qtype,
        **result,
    }


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    from .loader import load_data

    data = load_data("hackathon-data")

    print(
        answer_question(
            "How many subjects are in the study?",
            data,
        )
    )

    print(
        answer_question(
            "Look up subject 042-S01-001",
            data,
        )
    )

    print(
        answer_question(
            "Find all Hys law candidates",
            data,
            data_dir="hackathon-data",
        )
    )

    print(
        answer_question(
            "Find visit window deviations",
            data,
            data_dir="hackathon-data",
        )
    )