"""
Owned by: Person A (integrator).

Wires loader + cleaning + graph + checks + documents +
site-query / monitor-escalation handling + Answer Agent.

Run:
    python -m stage1.atlas --data hackathon-data

For a natural-language question:
    from stage1.atlas import answer
    result = answer("hackathon-data", "How many subjects are in the study?")
"""

import argparse
import json
from pathlib import Path

from .loader import (
    load_data,
    load_reference_ranges,
    load_corrections,
    load_cuts,
    get_cut_view,
    apply_corrections,
)

from .graph import build, write_stats

from .documents import (
    active_protocol_version,
    prohibited_meds,
    scan_for_embedded_instructions,
)

from . import checks

from .answer_agent import answer_question


def load_json_file(path):
    """Load a JSON file and return its contents."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def query_site(data_dir, domain, usubjid, seq):
    """
    Look up a site response using:

        DOMAIN|USUBJID|SEQ

    If no matching response exists, use the _default response.
    """
    path = Path(data_dir) / "responses" / "site_replies.json"
    replies = load_json_file(path)

    key = f"{domain}|{usubjid}|{seq}"

    response = replies.get(
        key,
        replies.get("_default"),
    )

    if response is None:
        return None

    return {
        "status": response[0],
        "response": response[1],
    }


def escalate_finding(data_dir, code, usubjid):
    """
    Look up the monitor decision using:

        CODE|USUBJID

    Handles APPROVED, REJECTED and CLARIFY responses.
    """
    path = (
        Path(data_dir)
        / "responses"
        / "monitor_decisions.json"
    )

    decisions = load_json_file(path)

    key = f"{code}|{usubjid}"

    response = decisions.get(key)

    if response is None:
        return None

    return {
        "status": response[0],
        "response": response[1],
    }


def handle_findings(data_dir, findings):
    """
    Add site-query and monitor-escalation results to findings.

    Findings with evidence triples are eligible for a site query.
    Monitor escalation uses the finding code and subject ID.
    """
    query_results = []
    escalation_results = []

    for category, category_findings in findings.items():

        if not isinstance(category_findings, list):
            continue

        for finding in category_findings:

            if not isinstance(finding, dict):
                continue

            evidence = finding.get("evidence", [])

            # ---------------------------------------------------------
            # Site queries
            # ---------------------------------------------------------

            for item in evidence:

                if len(item) != 3:
                    continue

                domain, usubjid, seq = item

                response = query_site(
                    data_dir,
                    domain,
                    usubjid,
                    seq,
                )

                if response is not None:

                    query_results.append(
                        {
                            "finding": finding.get(
                                "finding",
                                category,
                            ),
                            "usubjid": usubjid,
                            "evidence": [
                                domain,
                                usubjid,
                                seq,
                            ],
                            "site_response": response,
                        }
                    )

            # ---------------------------------------------------------
            # Monitor escalation
            # ---------------------------------------------------------

            code = finding.get("finding")

            if code and finding.get("usubjid"):

                response = escalate_finding(
                    data_dir,
                    code,
                    finding["usubjid"],
                )

                if response is not None:

                    escalation_results.append(
                        {
                            "finding": code,
                            "usubjid": finding["usubjid"],
                            "monitor_decision": response,
                        }
                    )

    return query_results, escalation_results


def run(data_dir, cut=None):
    """
    Run the complete ATLAS Stage 1 pipeline.

    Data is loaded once here.

    If a cut is supplied:
        1. records available by that cut are selected
        2. corrections available by that cut are applied

    Then:
        CSV data
            ↓
        graph
            ↓
        deterministic checks
            ↓
        document trap detection
            ↓
        site queries
            ↓
        monitor escalations
    """

    # -------------------------------------------------------------
    # Load all structured data
    # -------------------------------------------------------------

    data = load_data(data_dir)

    reference_ranges = load_reference_ranges(
        data_dir
    )

    corrections = load_corrections(
        data_dir
    )

    cuts_rows = load_cuts(
        data_dir
    )

    # -------------------------------------------------------------
    # Apply historical cut if requested
    # -------------------------------------------------------------

    if cut is not None:

        data = get_cut_view(
            data,
            cut,
        )

        data = apply_corrections(
            data,
            corrections,
            cut,
        )

    # -------------------------------------------------------------
    # Build study graph
    # -------------------------------------------------------------

    graph, stats = build(data)

    write_stats(
        stats,
        "graph_stats.json",
    )

    # -------------------------------------------------------------
    # Run deterministic clinical checks
    # -------------------------------------------------------------

    findings = {
        "hys_law_candidates": checks.hys_law_candidates(
            graph,
            reference_ranges,
        ),

        "seriousness_miscoded": checks.hospitalization_overrides(
            data
        ),

        "prohibited_medication_use": (
            checks.prohibited_medication_use(
                data,
                prohibited_meds,
                cuts_rows,
            )
        ),

        "dosing_errors": checks.dosing_errors(
            data
        ),
    }

    # -------------------------------------------------------------
    # Documents: detect planted instructions
    #
    # IMPORTANT:
    # These instructions are evidence and are NEVER executed.
    # -------------------------------------------------------------

    doc_flags = []

    for name in (
        "lab-manual.md",
        "lab-manual_v3.md",
    ):

        try:

            with open(
                f"{data_dir}/documents/{name}",
                encoding="utf-8",
            ) as f:

                text = f.read()

            doc_flags.extend(
                scan_for_embedded_instructions(
                    text,
                    name,
                )
            )

        except FileNotFoundError:
            pass

    findings[
        "embedded_instructions_detected_not_followed"
    ] = doc_flags

    # -------------------------------------------------------------
    # Handle site queries and monitor escalations
    # -------------------------------------------------------------

    query_results, escalation_results = handle_findings(
        data_dir,
        findings,
    )

    findings[
        "site_query_responses"
    ] = query_results

    findings[
        "monitor_escalations"
    ] = escalation_results

    return stats, findings


def answer(
    data_dir,
    question,
    cut=None,
):
    """
    Answer a natural-language ATLAS question.

    The same loader/cut/correction layer is used here as in run().

    Examples:

        answer(
            "hackathon-data",
            "How many subjects are in the study?"
        )

        answer(
            "hackathon-data",
            "Look up subject 042-S01-001"
        )

        answer(
            "hackathon-data",
            "Find Hy's law candidates"
        )
    """

    # -------------------------------------------------------------
    # Load structured data
    # -------------------------------------------------------------

    data = load_data(
        data_dir
    )

    reference_ranges = load_reference_ranges(
        data_dir
    )

    corrections = load_corrections(
        data_dir
    )

    cuts_rows = load_cuts(
        data_dir
    )

    # -------------------------------------------------------------
    # Apply cut + corrections
    # -------------------------------------------------------------

    if cut is not None:

        data = get_cut_view(
            data,
            cut,
        )

        data = apply_corrections(
            data,
            corrections,
            cut,
        )

    # -------------------------------------------------------------
    # Send already-loaded data to Answer Agent
    # -------------------------------------------------------------

    return answer_question(
        question=question,
        data=data,
        data_dir=data_dir,
        reference_ranges=reference_ranges,
        prohibited_meds_by_version=prohibited_meds,
        cuts_rows=cuts_rows,
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data",
        required=True,
    )

    parser.add_argument(
        "--cut",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--out",
        default="stage1_public.json",
    )

    args = parser.parse_args()

    # -------------------------------------------------------------
    # Run complete ATLAS pipeline
    # -------------------------------------------------------------

    stats, findings = run(
        args.data,
        cut=args.cut,
    )

    # -------------------------------------------------------------
    # Write public findings
    # -------------------------------------------------------------

    with open(
        args.out,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            findings,
            f,
            indent=2,
            default=str,
        )

    # -------------------------------------------------------------
    # Console output
    # -------------------------------------------------------------

    print(
        json.dumps(
            stats,
            indent=2,
        )
    )

    print(
        f"Findings written to {args.out}"
    )