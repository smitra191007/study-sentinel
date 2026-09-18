"""
Owned by: Person D
The core scoring logic. Every check returns findings shaped like:

    {
        "usubjid": "042-S01-001",
        "finding": "HYS_LAW_CANDIDATE",
        "evidence": [("LB", "042-S01-001", "12"), ("LB", "042-S01-001", "13")],
        "detail": "ALT 3.2xULN and BILI 2.1xULN within 14 days"
    }

evidence is always a list of (domain, USUBJID, seq) triples — that is what
gets checked against the real record. Never cite a triple that doesn't
back the claim.

If a check finds nothing, return an empty list — that IS the answer "none".
Do not return a placeholder or a guess.
"""
from datetime import timedelta
from cleaning import normalize_lab_value, get_central_range, OK, parse_date


def hys_law_candidates(graph, reference_ranges):
    """
    Potential Hy's law (protocol §7): ALT or AST > 3x ULN AND total bilirubin
    > 2x ULN within 14 days, without cholestasis/alt explanation (that
    adjudication is a human/monitor step — this check only flags candidates).
    """
    findings = []
    alt_ulih, _, _ = get_central_range("ALT", reference_ranges)
    _, alt_high, _ = get_central_range("ALT", reference_ranges)
    _, ast_high, _ = get_central_range("AST", reference_ranges)
    _, bili_high, _ = get_central_range("BILI", reference_ranges)

    for usubjid, subj in graph["subjects"].items():
        site = subj["site"]
        lb_records = subj["records"].get("LB", [])

        liver_hits = []  # (date, testcd, seq)
        bili_hits = []
        for r in lb_records:
            value, unit, status = normalize_lab_value(
                r["LBORRES"], r["LBORRESU"], r["LBTESTCD"], site, reference_ranges
            )
            if status != OK:
                continue
            date = parse_date(r["LBDTC"])
            if date is None:
                continue
            if r["LBTESTCD"] == "ALT" and value > 3 * alt_high:
                liver_hits.append((date, "LB", r["LBSEQ"]))
            elif r["LBTESTCD"] == "AST" and value > 3 * ast_high:
                liver_hits.append((date, "LB", r["LBSEQ"]))
            elif r["LBTESTCD"] == "BILI" and value > 2 * bili_high:
                bili_hits.append((date, "LB", r["LBSEQ"]))

        for ldate, ldomain, lseq in liver_hits:
            for bdate, bdomain, bseq in bili_hits:
                if abs((ldate - bdate).days) <= 14:
                    findings.append({
                        "usubjid": usubjid,
                        "finding": "HYS_LAW_CANDIDATE",
                        "evidence": [(ldomain, usubjid, lseq), (bdomain, usubjid, bseq)],
                        "detail": f"liver enzyme >3xULN on {ldate}, bilirubin >2xULN on {bdate}",
                    })
    return findings


def hospitalization_overrides(data):
    """
    Protocol §6: AESHOSP = Y makes an event serious regardless of AESER.
    Flags every AE where AESER says N but AESHOSP says Y.
    """
    findings = []
    for r in data.get("AE", []):
        if r.get("AESHOSP") == "Y" and r.get("AESER") == "N":
            findings.append({
                "usubjid": r["USUBJID"],
                "finding": "SERIOUSNESS_MISCODED",
                "evidence": [("AE", r["USUBJID"], r["AESEQ"])],
                "detail": "AESHOSP=Y but AESER=N — protocol says this is serious regardless",
            })
    return findings


def prohibited_medication_use(data, prohibited_meds_by_version, cuts_rows):
    """Flags CM records whose CMCLAS is prohibited under the protocol version active at that record's cut."""
    from documents import active_protocol_version
    findings = []
    for r in data.get("CM", []):
        cut = int(r.get("cut_available", 0))
        version = active_protocol_version(cut, cuts_rows) or 1
        prohibited = prohibited_meds_by_version(version)
        if r.get("CMCLAS", "").upper() in prohibited:
            findings.append({
                "usubjid": r["USUBJID"],
                "finding": "PROHIBITED_MEDICATION",
                "evidence": [("CM", r["USUBJID"], r["CMSEQ"])],
                "detail": f"{r['CMCLAS']} prohibited under protocol v{version}",
            })
    return findings


def dosing_errors(data):
    """Protocol §8: any dose other than 10mg (drug) or 0mg (placebo) is an error."""
    findings = []
    dm_arm = {r["USUBJID"]: r["ARM"] for r in data.get("DM", [])}
    for r in data.get("EX", []):
        arm = dm_arm.get(r["USUBJID"])
        try:
            dose = float(r["EXDOSE"])
        except (ValueError, TypeError):
            continue
        expected = 10 if arm == "DRUG" else 0
        if dose != expected:
            findings.append({
                "usubjid": r["USUBJID"],
                "finding": "DOSING_ERROR",
                "evidence": [("EX", r["USUBJID"], r["EXSEQ"])],
                "detail": f"dose {dose}mg, expected {expected}mg for arm {arm}",
            })
    return findings


def answer_or_none(findings, question_context=""):
    """
    Wraps a findings list into the final answer shape. If findings is empty,
    explicitly returns "none" with a reason — never a guess.
    """
    if not findings:
        return {"answer": "none", "evidence": [], "reason": f"no matching records found ({question_context})"}
    return {"answer": findings, "evidence": [f["evidence"] for f in findings]}
