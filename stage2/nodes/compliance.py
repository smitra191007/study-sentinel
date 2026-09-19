"""
stage2/nodes/compliance.py  —  PERSON A

Cross-references each subject against the protocol version active for
THIS cycle's data cut — and critically, per the doc's "what happens
partway through" scenario: if the protocol changes mid-event, subjects
compliant under the old version may be in violation under the new one,
on the SAME data. This node must always apply the CURRENT cycle's
protocol_version, never a cached/previous one.

Failure mode this guards against (from the doc):
  "Applying the previous protocol version's rules after the amendment"
"""

from __future__ import annotations

from stage2.schema import Finding
from stage2.trace_logger import TraceLogger

# TODO: import your real Stage 1 protocol-version logic here, e.g.:
# from stage1.documents import active_version_for_date


def check(findings: list[Finding], protocol_version: int, logger: TraceLogger) -> list[Finding]:
    """
    `protocol_version` is passed in explicitly by ReviewCrew.run_cycle(cut,
    protocol_version) for THIS cycle — always use this value, never one
    stored from a previous cycle, so a mid-event amendment takes effect
    immediately.
    """
    for f in findings:
        f.protocol_version = protocol_version

        # TODO: replace with real rule lookups against this protocol_version,
        # e.g. visit window days, prohibited medication list, eligibility
        # criteria — via stage1.documents or a fetched GET /documents/protocol.

        f.node_trail.append("compliance")
        logger.log(
            node="compliance",
            finding_id=f.finding_id,
            decision=f"checked_under_protocol_v{protocol_version}",
            rationale=f"{f.code} evaluated against protocol version {protocol_version}",
            evidence=[e.to_dict() for e in f.evidence],
        )

    return findings
