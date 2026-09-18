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
from stage2.schema import Finding
from stage2.trace_logger import TraceLogger

# TODO: point this at your real Stage 1 detector once package paths are final.
# from stage1.atlas import Atlas


def detect(data_dir: str) -> list[Finding]:
    """
    Stage 1 hookup. Replace this placeholder with a real call into
    stage1.atlas.Atlas(...).build() + query({"type": "Finding", ...}), then
    map each raw Stage 1 finding into a stage2.schema.Finding.

    TODO (either of you — whoever gets to it first):
        atlas = Atlas(data_dir=data_dir).build()
        raw = atlas.query({"type": "Finding", "filters": {}})["result"]
        return [
            Finding(
                finding_id=make_finding_id(r["subject_id"], r["finding_type"], ...),
                subject_id=r["subject_id"],
                site_id=...,
                finding_type=r["finding_type"],
                detail=r["detail"],
                record_refs=[...],
            )
            for r in raw
        ]
    """
    return []


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
