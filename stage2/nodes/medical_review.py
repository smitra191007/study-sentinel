"""
stage2/nodes/medical_review.py  —  PERSON A

Applies hidden clinical rules a simple field-value check would miss.

The worked example from the problem doc (implement this exact logic):
  Stage 1 emits a finding like:
    {"code": "SAE_MISCODED", "usubjid": "042-S02-004", "severity": "CRITICAL",
     "rationale": "'Cellulitis' has AESHOSP=Y but AESER=N",
     "evidence": [{"domain": "AE", "usubjid": "042-S02-004", "seq": 1}]}

  This node must draft an escalation carrying evidence AND alternatives
  considered:
    {"code": "SAE_MISCODED", "usubjid": "042-S02-004", "severity": "CRITICAL",
     "summary": "Cellulitis recorded with AESHOSP=Y and AESER=N. Hospitalisation
                  makes this serious under protocol section 6; the 24-hour
                  reporting clock applies.",
     "evidence": [...],
     "alternatives": ["Re-code as serious and expedite",
                       "Accept AESER=N as entered - rejected: contradicts protocol section 6"]}
"""

from __future__ import annotations

from stage2.schema import Finding
from stage2.trace_logger import TraceLogger

# Protocol section 6, per the doc: AESHOSP=Y forces serious regardless of AESER.
HOSPITALIZATION_OVERRIDE_RULE = (
    "Hospitalisation makes this serious under protocol section 6; "
    "the 24-hour reporting clock applies."
)


def review(findings: list[Finding], logger: TraceLogger) -> list[Finding]:
    """
    For each finding, decide whether it needs an escalation draft (summary +
    alternatives) or can be handled as a plain data query instead. Sets
    `finding.alternatives` for anything going to escalation.
    """
    for f in findings:
        if f.code == "SAE_MISCODED":
            f.alternatives = [
                "Re-code as serious and expedite",
                "Accept AESER=N as entered - rejected: contradicts protocol section 6",
            ]
            # Rewrite rationale into the escalation summary the doc expects.
            f.rationale = (
                f"{f.rationale.rstrip('.')}. {HOSPITALIZATION_OVERRIDE_RULE}"
            )
            f.severity = "CRITICAL"

            logger.log(
                node="medical_review",
                finding_id=f.finding_id,
                decision="escalation_drafted",
                rationale=f.rationale,
                evidence=[e.to_dict() for e in f.evidence],
            )
        else:
            logger.log(
                node="medical_review",
                finding_id=f.finding_id,
                decision="no_override_needed",
                rationale=f"code={f.code} does not require a hidden-rule override",
                evidence=[e.to_dict() for e in f.evidence],
            )

        f.node_trail.append("medical_review")

    return findings
