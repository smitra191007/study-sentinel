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

from stage1.atlas import run as atlas_run
from stage2.api_client import ApiClient
from stage2.memory import CrossCycleMemory
from stage2.nodes import compliance, data_manager, human_gate, medical_review
from stage2.schema import EvidenceRef, Finding, make_finding_id
from stage2.trace_logger import TraceLogger


@dataclass
class ReviewReport:
    cut: int
    protocol_version: int
    findings_count: int
    escalations_count: int
    queries_count: int
    findings: list[Finding] = field(default_factory=list)


def _build_evidence(usubjid: str, raw_evidence, start_seq: int = 0) -> list[EvidenceRef]:
    """
    Normalize whatever shape Stage 1 emits for `evidence` into EvidenceRef
    objects. Stage 1's real output may already match {"domain","usubjid","seq"}
    dicts (the doc's exact shape), or may be tuples/lists, or bare values —
    handle all three defensively.

    TODO: once you've confirmed Stage 1's real evidence shape, simplify this
    to just the branch that actually applies — this defensive fallback is a
    safety net, not the final answer.
    """
    evidence: list[EvidenceRef] = []
    for i, ref in enumerate(raw_evidence or []):
        if isinstance(ref, dict) and "domain" in ref and "seq" in ref:
            evidence.append(
                EvidenceRef(domain=ref["domain"], usubjid=ref.get("usubjid", usubjid), seq=ref["seq"])
            )
        elif isinstance(ref, (list, tuple)) and len(ref) >= 2:
            parts = [str(x) for x in ref]
            domain = parts[0]
            seq = start_seq + i
            evidence.append(EvidenceRef(domain=domain, usubjid=usubjid, seq=seq))
        else:
            evidence.append(EvidenceRef(domain="UNKNOWN", usubjid=usubjid, seq=start_seq + i))
    return evidence


class ReviewCrew:
    def __init__(self, hub_url: str, gateway_url: str, team_key: str, atlas) -> None:
        self.atlas = atlas
        self.client = ApiClient(hub_url=hub_url, gateway_url=gateway_url, team_key=team_key)
        self.memory = CrossCycleMemory(path="stage2_memory.json")
        self.logger = TraceLogger(path="stage2_trace.jsonl")

    def detect(self, cut: int) -> list[Finding]:
        """
        Runs Stage 1 ATLAS and maps its raw findings into Stage 2 Finding
        objects (code/usubjid/site/severity/rationale/evidence).

        TODO: confirm stage1.atlas.run()'s actual signature — this assumes
        it takes only data_dir and returns (_, raw_findings) where
        raw_findings is a dict keyed by finding code, each value a list of
        record dicts. If Stage 1's `run()` also accepts `cut`, pass it
        through: atlas_run(data_dir, cut=cut).
        """
        data_dir = getattr(self.atlas, "data_dir", "hackathon-data")
        _, raw_findings = atlas_run(data_dir)

        findings: list[Finding] = []

        for finding_code, records in raw_findings.items():
            if not isinstance(records, list):
                continue

            for index, r in enumerate(records):
                if not isinstance(r, dict):
                    continue

                usubjid = (
                    r.get("usubjid")
                    or r.get("subject_id")
                    or r.get("USUBJID")
                    or ""
                )
                if not usubjid:
                    continue

                rationale = str(r.get("rationale", r.get("detail", "")))
                severity = str(r.get("severity", ""))

                site = r.get("site", r.get("site_id", ""))
                if not site and "-S" in usubjid:
                    site = usubjid.split("-S", 1)[1].split("-", 1)[0]
                    site = f"S{site}"

                evidence = _build_evidence(usubjid, r.get("evidence", []), start_seq=index)
                finding_id = make_finding_id(usubjid, finding_code, evidence)

                findings.append(
                    Finding(
                        finding_id=finding_id,
                        code=finding_code,
                        usubjid=usubjid,
                        site=site,
                        severity=severity,
                        rationale=rationale,
                        evidence=evidence,
                    )
                )

        return findings

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
    parser.add_argument("--data-dir", default="hackathon-data")
    args = parser.parse_args()

    class _AtlasHandle:
        def __init__(self, data_dir: str) -> None:
            self.data_dir = data_dir

    crew = ReviewCrew(
        hub_url=args.hub_url,
        gateway_url=args.gateway_url,
        team_key=args.team_key,
        atlas=_AtlasHandle(args.data_dir),
    )
    report = crew.run_cycle(cut=args.cut, protocol_version=args.protocol_version)
    print(
        f"Cycle complete: {report.findings_count} findings, "
        f"{report.escalations_count} escalations, {report.queries_count} queries. "
        f"See stage2_trace.jsonl for the full trace."
    )
