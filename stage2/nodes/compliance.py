"""
stage2/nodes/compliance.py  —  PERSON A

Cross-references each subject against the protocol version that was active
at THAT SUBJECT'S specific data cut — not today's protocol. Reuses the
version-mapping logic already built in stage1/documents.py.

TODO: wire in your real Stage 1 imports once package paths are finalized,
e.g.:
    from stage1.documents import active_version_for_date, parse_protocol_versions
"""

from __future__ import annotations

from stage2.schema import Finding
from stage2.trace_logger import TraceLogger

# TODO: import your real Stage 1 protocol-version logic here
# from stage1.documents import active_version_for_date


def check(findings: list[Finding], protocol_versions: list, logger: TraceLogger) -> list[Finding]:
    """
    Sets `finding.protocol_version` based on the subject's data-cut date.
    `protocol_versions` should be the list already parsed by Stage 1
    (stage1.documents.parse_protocol_versions).
    """
    for f in findings:
        # --- TODO: replace with real active_version_for_date(...) lookup ---
        # cut_date = get_subject_data_cut_date(f.subject_id)
        # version = active_version_for_date(protocol_versions, cut_date)
        # f.protocol_version = version.version_id if version else None
        f.protocol_version = f.protocol_version or "unresolved"  # placeholder

        f.node_trail.append("compliance")
        logger.log(
            node="compliance",
            finding_id=f.finding_id,
            decision=f"protocol_version={f.protocol_version}",
            rationale="placeholder — replace with real data-cut -> version mapping",
            evidence=f.record_refs,
        )

    return findings
