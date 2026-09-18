"""
Owned by: Person A
Loads every domain CSV into a dict of lists-of-dicts, keyed by domain name.
Everyone else imports load_data() and get_cut_view() from here — do not
duplicate CSV reading logic in your own file.
"""
import csv
import os

DOMAINS = ["DM", "AE", "LB", "VS", "EX", "CM", "DS", "MH", "EG"]


def load_data(data_dir):
    """
    Returns: {"DM": [ {col: val, ...}, ... ], "AE": [...], ...}
    Every record keeps its raw string values — cleaning happens in cleaning.py,
    not here. This function's only job is: read CSV -> list of dicts.
    """
    data = {}
    for domain in DOMAINS:
        path = os.path.join(data_dir, "data", f"{domain}.csv")
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            data[domain] = list(reader)
    return data


def load_reference_ranges(data_dir):
    """Returns list of {LBTESTCD, UNIT, LOW, HIGH, LAB}."""
    path = os.path.join(data_dir, "data", "reference_ranges.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_corrections(data_dir):
    path = os.path.join(data_dir, "data", "corrections.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_cuts(data_dir):
    path = os.path.join(data_dir, "data", "cuts.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_cut_view(data, cut):
    """
    Returns the study as it looked at a given cut: only records with
    cut_available <= cut. Use this instead of filtering manually everywhere —
    keeps the "what did we know at cut N" logic in one place.
    """
    cut = int(cut)
    view = {}
    for domain, records in data.items():
        view[domain] = [
            r for r in records if int(r.get("cut_available", 0)) <= cut
        ]
    return view


def apply_corrections(data, corrections, up_to_cut):
    """
    Applies corrections.csv entries with cut <= up_to_cut onto the matching
    (domain, USUBJID, seq) record's field. Returns a NEW data dict — never
    mutates the input, so re-running at a different cut is always correct.
    """
    import copy
    data = copy.deepcopy(data)
    seq_field = {
        "AE": "AESEQ", "LB": "LBSEQ", "VS": "VSSEQ", "EX": "EXSEQ",
        "CM": "CMSEQ", "DS": "DSSEQ", "MH": "MHSEQ", "EG": "EGSEQ",
    }
    index = {}
    for domain, records in data.items():
        if domain == "DM":
            continue
        sf = seq_field.get(domain)
        if not sf:
            continue
        for r in records:
            index[(domain, r["USUBJID"], r[sf])] = r

    for c in corrections:
        if int(c["cut"]) > int(up_to_cut):
            continue
        key = (c["domain"], c["usubjid"], c["seq"])
        rec = index.get(key)
        if rec is not None:
            rec[c["field"]] = c["new_value"]
    return data


if __name__ == "__main__":
    # Quick smoke test — run this after cloning to confirm loading works.
    d = load_data("hackathon-data")
    for domain, records in d.items():
        print(domain, len(records), "records")
