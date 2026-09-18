"""
Owned by: Person A (integrator). Wires loader + cleaning + graph + checks +
documents together. Run: python -m stage1.atlas --data hackathon-data
"""
import argparse
import json
import sys

from .loader import load_data, load_reference_ranges, load_corrections, load_cuts, get_cut_view, apply_corrections
from .graph import build, write_stats
from .documents import active_protocol_version, prohibited_meds, scan_for_embedded_instructions
from . import checks


def run(data_dir, cut=None):
    data = load_data(data_dir)
    reference_ranges = load_reference_ranges(data_dir)
    corrections = load_corrections(data_dir)
    cuts_rows = load_cuts(data_dir)

    if cut is not None:
        data = get_cut_view(data, cut)
        data = apply_corrections(data, corrections, cut)

    graph, stats = build(data)
    write_stats(stats, "graph_stats.json")

    findings = {
        "hys_law_candidates": checks.hys_law_candidates(graph, reference_ranges),
        "seriousness_miscoded": checks.hospitalization_overrides(data),
        "prohibited_medication_use": checks.prohibited_medication_use(
            data, prohibited_meds, cuts_rows
        ),
        "dosing_errors": checks.dosing_errors(data),
    }

    # Documents: scan for planted instructions, report but never obey.
    doc_flags = []
    for name in ("lab-manual.md", "lab-manual_v3.md"):
        try:
            with open(f"{data_dir}/documents/{name}", encoding="utf-8") as f:
                text = f.read()
            doc_flags.extend(scan_for_embedded_instructions(text, name))
        except FileNotFoundError:
            pass
    findings["embedded_instructions_detected_not_followed"] = doc_flags

    return stats, findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--cut", type=int, default=None)
    parser.add_argument("--out", default="stage1_public.json")
    args = parser.parse_args()

    stats, findings = run(args.data, cut=args.cut)
    with open(args.out, "w") as f:
        json.dump(findings, f, indent=2, default=str)

    print(json.dumps(stats, indent=2))
    print(f"Findings written to {args.out}")
