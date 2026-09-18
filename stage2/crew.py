"""
stage2/crew.py

The 6-node orchestration pipeline:
  detect -> medical review -> data manager -> compliance -> human gate -> execute

Note the order per the spec: data_manager runs BEFORE compliance. That's
intentional — data quality issues get queried first, and compliance checks
against protocol version run after, so a corrected value can still be
checked against the right protocol.
"""

from __future__ import annotations

from stage2.memory import CrossCycleMemory
from stage2.nodes import compliance, data_manager, human_gate, medical_review
from stage2.schema import Finding,make_finding_id
from stage1.atlas import run as atlas_run
from stage2.trace_logger import TraceLogger

# TODO: point this at your real Stage 1 detector once package paths are final.
# from stage1.atlas import Atlas


def detect(data_dir: str) -> list[Finding]:
    """
    Run Stage 1 ATLAS and map its deterministic findings into
    Stage 2 Finding objects.
    """
    _, raw_findings = atlas_run(data_dir)

    findings = []

    for finding_type, records in raw_findings.items():
        if not isinstance(records, list):
            continue

        for index, r in enumerate(records):
            if not isinstance(r, dict):
                continue

            subject_id = (
                r.get("usubjid")
                or r.get("subject_id")
                or r.get("USUBJID")
                or ""
            )

            if not subject_id:
                continue

            detail = str(r.get("detail", ""))

            site_id = r.get("site_id", "")

            if not site_id and "-S" in subject_id:
                site_id = subject_id.split("-S", 1)[1].split("-", 1)[0]
                site_id = f"S{site_id}"

            raw_evidence = r.get("evidence", [])

            record_refs = []
            for ref in raw_evidence:
                if isinstance(ref, (list, tuple)):
                    record_refs.append(":".join(str(x) for x in ref))
                else:
                    record_refs.append(str(ref))

            detail_key = (
                record_refs[0]
                if record_refs
                else str(index)
            )

            finding_id = make_finding_id(
                subject_id,
                finding_type,
                detail_key,
            )

            findings.append(
                Finding(
                    finding_id=finding_id,
                    subject_id=subject_id,
                    site_id=site_id,
                    finding_type=finding_type,
                    detail=detail,
                    record_refs=record_refs,
                )
            )

    return findings


def execute(findings: list[Finding], logger: TraceLogger) -> list[Finding]:
    """
    Final node: anything not queried, escalated, or resolved by this point
    is logged as passed-through with no action needed this cycle.
    """
    for f in findings:
        if f.status == "open":
            logger.log(
                node="execute",
                finding_id=f.finding_id,
                decision="no_action",
                rationale="not queried or escalated this cycle",
                evidence=f.record_refs,
            )
        f.node_trail.append("execute")
    return findings


def run_pipeline(
    data_dir: str,
    protocol_versions: list | None = None,
    memory_path: str = "stage2_memory.json",
    trace_path: str = "stage2_trace.jsonl",
) -> list[Finding]:
    memory = CrossCycleMemory(path=memory_path)
    logger = TraceLogger(path=trace_path)
    cycle = memory.start_new_cycle()
    logger.log("crew", "-", "cycle_start", f"cycle {cycle} beginning", [])

    findings = detect(data_dir)
    findings = medical_review.review(findings, logger)
    findings = data_manager.process(findings, memory, logger)
    findings = compliance.check(findings, protocol_versions or [], logger)
    findings = human_gate.process(findings, memory, logger)
    findings = execute(findings, logger)

    logger.log("crew", "-", "cycle_end", f"cycle {cycle} complete, {len(findings)} findings processed", [])
    return findings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Stage 2 review crew pipeline.")
    parser.add_argument("--data-dir", default="hackathon-data")
    parser.add_argument("--memory-path", default="stage2_memory.json")
    parser.add_argument("--trace-path", default="stage2_trace.jsonl")
    args = parser.parse_args()

    results = run_pipeline(
        data_dir=args.data_dir,
        memory_path=args.memory_path,
        trace_path=args.trace_path,
    )
    print(f"Processed {len(results)} findings. See {args.trace_path} for the full trace.")
