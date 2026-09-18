"""
stage2/nodes/medical_review.py  —  PERSON A

Applies hidden clinical rules that a simple field-value check would miss.

TODO (this is your node — replace the TODO logic below):
- AESHOSP = "Y" forces an adverse event to be treated as serious, REGARDLESS
  of what AESER says. Pull the raw AE record via record_refs / your Stage 1
  graph access, check AESHOSP, and override severity accordingly.
- Add any other hidden-rule overrides your protocol/SAP specifies here.
"""

from __future__ import annotations

from stage2.schema import Finding
from stage2.trace_logger import TraceLogger


def review(findings: list[Finding], logger: TraceLogger) -> list[Finding]:
    """
    Enrich each finding with a clinical severity assessment. Must not drop
    findings — only add/adjust `severity` and append to `node_trail`.
    """
    for f in findings:
        # --- TODO: replace this placeholder with real AE lookup + override ---
        if f.finding_type == "adverse_event":
            # Example shape of what you're building toward:
            # ae_record = get_ae_record(f.record_refs)
            # if ae_record.get("AESHOSP") == "Y":
            #     f.severity = "critical"
            #     logger.log(
            #         node="medical_review",
            #         finding_id=f.finding_id,
            #         decision="override_to_serious",
            #         rationale="AESHOSP=Y forces serious regardless of AESER",
            #         evidence=f.record_refs,
            #     )
            #     f.node_trail.append("medical_review")
            #     continue
            f.severity = f.severity or "unclassified"  # placeholder

        f.node_trail.append("medical_review")
        logger.log(
            node="medical_review",
            finding_id=f.finding_id,
            decision=f"severity={f.severity}",
            rationale="placeholder logic — replace with real hidden-rule checks",
            evidence=f.record_refs,
        )

    return findings
