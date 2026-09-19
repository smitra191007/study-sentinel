"""
ATLAS — Study Knowledge Graph / Patient 360 query layer.

Owned by: Person A

Responsibilities:
- Load the study data through loader.py
- Apply cut and correction logic
- Build the study graph
- Run deterministic safety/protocol checks
- Detect embedded prompt-injection instructions in documents
- Handle site queries / monitor escalations
- Answer COUNT / LOOKUP / FINDING / TRAP questions
"""

import argparse
import json
import os

from .loader import (
    load_data,
    load_reference_ranges,
    load_corrections,
    load_cuts,
    get_cut_view,
    apply_corrections,
)

from .graph import build

from .documents import (
    active_protocol_version,
    prohibited_meds,
    scan_for_embedded_instructions,
    load_protocol_text,
)

from . import checks

from .answer_agent import answer_question


def load_json_file(path):
    """
    Load a JSON file if it exists.

    Returns:
        Parsed JSON object, or None if the file does not exist.
    """
    if not os.path.exists(path):
        return None

    with open(
        path,
        encoding="utf-8",
    ) as f:
        return json.load(f)


def query_site(
    data_dir,
    finding,
):
    """
    Look for a site response corresponding to a finding.

    The response files are optional. Missing files simply produce
    no site response.
    """

    path = os.path.join(
        data_dir,
        "responses",
        "site_replies.json",
    )

    replies = load_json_file(path)

    if not replies:
        return None

    usubjid = finding.get("usubjid")

    finding_code = finding.get(
        "finding"
    )

    if isinstance(replies, list):
        for reply in replies:
            if not isinstance(reply, dict):
                continue

            if (
                reply.get("usubjid") == usubjid
                and (
                    reply.get("finding") == finding_code
                    or reply.get("finding_code") == finding_code
                )
            ):
                return reply

    elif isinstance(replies, dict):
        key = (
            f"{usubjid}:{finding_code}"
        )

        if key in replies:
            return replies[key]

    return None


def escalate_finding(
    data_dir,
    finding,
):
    """
    Look for a monitor decision corresponding to a finding.

    The monitor decision file is optional.
    """

    path = os.path.join(
        data_dir,
        "responses",
        "monitor_decisions.json",
    )

    decisions = load_json_file(path)

    if not decisions:
        return None

    usubjid = finding.get("usubjid")

    finding_code = finding.get(
        "finding"
    )

    if isinstance(decisions, list):
        for decision in decisions:
            if not isinstance(decision, dict):
                continue

            if (
                decision.get("usubjid") == usubjid
                and (
                    decision.get("finding") == finding_code
                    or decision.get("finding_code") == finding_code
                )
            ):
                return decision

    elif isinstance(decisions, dict):
        key = (
            f"{usubjid}:{finding_code}"
        )

        if key in decisions:
            return decisions[key]

    return None


def handle_findings(
    data_dir,
    findings,
):
    """
    Add site-query and monitor-escalation results to findings.

    Findings with evidence triples are eligible for a site query.
    Monitor escalation uses the finding code and subject ID.
    """

    query_results = []
    escalation_results = []

    for category, category_findings in findings.items():

        if not isinstance(
            category_findings,
            list,
        ):
            continue

        for finding in category_findings:

            if not isinstance(
                finding,
                dict,
            ):
                continue

            evidence = finding.get(
                "evidence",
                [],
            )

            # Findings with evidence can be sent to the site.
            if evidence:
                site_response = query_site(
                    data_dir,
                    finding,
                )

                if site_response is not None:
                    query_results.append(
                        {
                            "category": category,
                            "finding": finding,
                            "response": site_response,
                        }
                    )

            # Findings can also be escalated to the monitor.
            monitor_response = escalate_finding(
                data_dir,
                finding,
            )

            if monitor_response is not None:
                escalation_results.append(
                    {
                        "category": category,
                        "finding": finding,
                        "response": monitor_response,
                    }
                )

    return (
        query_results,
        escalation_results,
    )


def run(
    data_dir,
    cut=None,
):
    """
    Run the complete deterministic ATLAS pipeline.

    Steps:
        1. Load raw data
        2. Apply requested cut
        3. Apply corrections available at that cut
        4. Build the study graph
        5. Run deterministic checks
        6. Scan documents for embedded instructions
        7. Handle site queries / monitor escalations

    Returns:
        stats, findings
    """

    # ---------------------------------------------------------
    # Load data
    # ---------------------------------------------------------

    raw_data = load_data(
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

    # ---------------------------------------------------------
    # Determine cut
    # ---------------------------------------------------------

    if cut is None:
        effective_cut = max(
            int(row["cut"])
            for row in cuts_rows
        )
    else:
        effective_cut = int(cut)

    # ---------------------------------------------------------
    # Apply cut
    # ---------------------------------------------------------

    data = get_cut_view(
        raw_data,
        effective_cut,
    )

    # ---------------------------------------------------------
    # Apply corrections available at this cut
    # ---------------------------------------------------------

    data = apply_corrections(
        data,
        corrections,
        effective_cut,
    )

    # ---------------------------------------------------------
    # Build graph
    # ---------------------------------------------------------

    graph, stats = build(
        data
    )

    # ---------------------------------------------------------
    # Deterministic findings
    # ---------------------------------------------------------

    findings = {

        # Hy's Law
        "hys_law_candidates": (
            checks.hys_law_candidates(
                graph,
                reference_ranges,
            )
        ),

        # Hospitalisation override
        "seriousness_miscoded": (
            checks.hospitalization_overrides(
                data
            )
        ),

        # Prohibited medications
        "prohibited_medication_use": (
            checks.prohibited_medication_use(
                data,
                prohibited_meds,
                cuts_rows,
            )
        ),

        # Dosing errors
        "dosing_errors": (
            checks.dosing_errors(
                data
            )
        ),

        # Visit-window deviations
        "visit_window_deviations": (
            checks.visit_window_deviations(
                data,
                cut=effective_cut,
                cuts_rows=cuts_rows,
            )
        ),
    }

    # ---------------------------------------------------------
    # Scan protocol/lab-manual documents
    # ---------------------------------------------------------

    doc_flags = []

    versions_to_scan = sorted(
        set(
            int(row["protocol_version"])
            for row in cuts_rows
        )
    )

    for version in versions_to_scan:

        try:
            protocol_text = load_protocol_text(
                data_dir,
                version,
            )

            doc_flags.extend(
                scan_for_embedded_instructions(
                    protocol_text,
                    f"protocol_v{version}.md",
                )
            )

        except FileNotFoundError:
            pass

    # Lab manual
    lab_manual_path = os.path.join(
        data_dir,
        "documents",
        "lab-manual.md",
    )

    if os.path.exists(
        lab_manual_path
    ):
        with open(
            lab_manual_path,
            encoding="utf-8",
        ) as f:
            lab_manual_text = f.read()

        doc_flags.extend(
            scan_for_embedded_instructions(
                lab_manual_text,
                "lab-manual.md",
            )
        )

    # Lab manual v3
    lab_manual_v3_path = os.path.join(
        data_dir,
        "documents",
        "lab-manual_v3.md",
    )

    if os.path.exists(
        lab_manual_v3_path
    ):
        with open(
            lab_manual_v3_path,
            encoding="utf-8",
        ) as f:
            lab_manual_v3_text = f.read()

        doc_flags.extend(
            scan_for_embedded_instructions(
                lab_manual_v3_text,
                "lab-manual_v3.md",
            )
        )

    findings[
        "embedded_instructions_detected_not_followed"
    ] = doc_flags

    # ---------------------------------------------------------
    # Handle site queries / monitor escalations
    # ---------------------------------------------------------

    (
        query_results,
        escalation_results,
    ) = handle_findings(
        data_dir,
        findings,
    )

    findings[
        "site_query_responses"
    ] = query_results

    findings[
        "monitor_escalations"
    ] = escalation_results

    return (
        stats,
        findings,
    )


def answer(
    data_dir,
    question,
    cut=None,
):
    """
    Answer a natural-language ATLAS question.

    The answer agent handles:
        COUNT
        LOOKUP
        FINDING
        TRAP

    The same cut/correction logic used by run() is applied first.
    """

    # ---------------------------------------------------------
    # Load data
    # ---------------------------------------------------------

    raw_data = load_data(
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

    # ---------------------------------------------------------
    # Determine effective cut
    # ---------------------------------------------------------

    if cut is None:
        effective_cut = max(
            int(row["cut"])
            for row in cuts_rows
        )
    else:
        effective_cut = int(cut)

    # ---------------------------------------------------------
    # Apply cut
    # ---------------------------------------------------------

    data = get_cut_view(
        raw_data,
        effective_cut,
    )

    # ---------------------------------------------------------
    # Apply corrections
    # ---------------------------------------------------------

    data = apply_corrections(
        data,
        corrections,
        effective_cut,
    )

    # ---------------------------------------------------------
    # Answer question
    # ---------------------------------------------------------

    return answer_question(
        question=question,
        data=data,
        data_dir=data_dir,
        reference_ranges=reference_ranges,
        prohibited_meds_by_version=prohibited_meds,
        cuts_rows=cuts_rows,
    )


def main():
    parser = argparse.ArgumentParser(
        description="ATLAS Study Knowledge Graph"
    )

    parser.add_argument(
        "--data",
        default="hackathon-data",
        help="Path to hackathon data directory",
    )

    parser.add_argument(
        "--cut",
        type=int,
        default=None,
        help="Historical data cut to use",
    )

    parser.add_argument(
        "--out",
        default="stage1_public.json",
        help="Output findings JSON file",
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # Run ATLAS
    # ---------------------------------------------------------

    stats, findings = run(
        args.data,
        cut=args.cut,
    )

    # ---------------------------------------------------------
    # Print statistics
    # ---------------------------------------------------------

    print(
        json.dumps(
            stats,
            indent=2,
            default=str,
        )
    )

    # ---------------------------------------------------------
    # Write findings
    # ---------------------------------------------------------

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

    print(
        f"Findings written to {args.out}"
    )


if __name__ == "__main__":
    main()
class Atlas:
    """
    Wrapper class to satisfy Stage 2 imports while utilizing Stage 1 engine functions.
    """
    def __init__(self, data_dir: str = "hackathon-data"):
        self.data_dir = data_dir

    def run(self, cut: int | None = None):
        return run(self.data_dir, cut=cut)

    def answer(self, question: str, cut: int | None = None):
        return answer(self.data_dir, question, cut=cut)