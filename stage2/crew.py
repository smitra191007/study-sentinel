"""
stage2/crew.py

Matches the exact class shape the problem doc specifies:

    class ReviewCrew:
        def __init__(self, hub_url, gateway_url, team_key, atlas: Atlas): ...
        def run_cycle(self, cut: int, protocol_version: int) -> ReviewReport: ...

Six nodes, in order: detect -> medical_review -> data_manager -> compliance
-> human_gate -> execute. (data_manager runs before compliance, per the
original scaffold design — data issues get queried first, compliance runs
after so a corrected value is still checked against the right protocol.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stage2.api_client import ApiClient
from stage2.memory import CrossCycleMemory
from stage2.nodes import compliance, data_manager, human_gate, medical_review
from stage2.schema import Finding
from stage2.trace_logger import TraceLogger

# TODO: point this at your real Stage 1 detector once package paths are final.
# from stage1.atlas import Atlas


@dataclass
class ReviewReport:
    cut: int
    protocol_version: int
    findings_count: int
    escalations_count: int
    queries_count: int
    findings: list[Finding] = field(default_factory=list)


class ReviewCrew:
    def __init__(self, hub_url: str, gateway_url: str, team_key: str, atlas) -> None:
        self.atlas = atlas
        self.client = ApiClient(hub_url=hub_url, gateway_url=gateway_url, team_key=team_key)
        self.memory = CrossCycleMemory(path="stage2_memory.json")
        self.logger = TraceLogger(path="stage2_trace.jsonl")

    def detect(self, cut: int) -> list[Finding]:
        """
        Stage 1 hookup. TODO: replace with your real call, e.g.:

            raw_findings = self.atlas.detect(cut=cut)  # or whatever Stage 1's
                                                         # real method is called
            return [Finding.from_raw(r) for r in raw_findings]

        Must return Finding objects built via Finding.from_raw(raw_dict) so
        the code/usubjid/evidence field names match Stage 1's actual output.
        """
        return []

    def execute(self, findings: list[Finding]) -> list[Finding]:
        """Final node: anything untouched this cycle is logged as no-action."""
        for f in findings:
            if f.status == "open":
                self.logger.log(
                    node="execute",
                    finding_id=f.finding_id,
                    decision="no_action",
                    rationale="not queried or escalated this cycle",
                    evidence=[e.to_dict() for e in f.evidence],
                )
            f.node_trail.append("execute")
        return findings

    def run_cycle(self, cut: int, protocol_version: int) -> ReviewReport:
        cycle = self.memory.start_new_cycle()
        self.logger.log("crew", "-", "cycle_start", f"cut={cut} cycle={cycle} protocol_version={protocol_version}")

        findings = self.detect(cut)
        self.logger.log_summary("detect", f"{len(findings)} findings under protocol v{protocol_version}")

        findings = medical_review.review(findings, self.logger)
        findings = data_manager.process(findings, self.memory, self.client, cut, self.logger)
        findings = compliance.check(findings, protocol_version, self.logger)
        findings = human_gate.process(findings, self.memory, self.client, self.logger)
        findings = self.execute(findings)

        escalations_count = sum(1 for f in findings if f.status in ("resolved", "escalated"))
        queries_count = sum(1 for f in findings if f.status == "queried")

        report = ReviewReport(
            cut=cut,
            protocol_version=protocol_version,
            findings_count=len(findings),
            escalations_count=escalations_count,
            queries_count=queries_count,
            findings=findings,
        )

        self.logger.log_summary(
            "execute",
            f"cycle complete: {report.findings_count} findings, "
            f"{report.escalations_count} escalations, {report.queries_count} queries",
        )
        return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run one Stage 2 review cycle.")
    parser.add_argument("--hub-url", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--team-key", required=True)
    parser.add_argument("--cut", type=int, required=True)
    parser.add_argument("--protocol-version", type=int, required=True)
    args = parser.parse_args()

    # TODO: replace with real Atlas construction once Stage 1 is wired in.
    # from stage1.atlas import Atlas
    # atlas = Atlas(data_dir="hackathon-data").build()
    atlas = None

    crew = ReviewCrew(
        hub_url=args.hub_url,
        gateway_url=args.gateway_url,
        team_key=args.team_key,
        atlas=atlas,
    )
    report = crew.run_cycle(cut=args.cut, protocol_version=args.protocol_version)
    print(
        f"Cycle complete: {report.findings_count} findings, "
        f"{report.escalations_count} escalations, {report.queries_count} queries. "
        f"See stage2_trace.jsonl for the full trace."
    )
