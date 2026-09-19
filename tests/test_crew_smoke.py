"""
Smoke test built directly from the problem doc's worked example:
  - the SAE_MISCODED / AESHOSP=Y finding
  - APPROVED, REJECTED, and CLARIFY escalation responses
  - the "re-run the same cut -> zero new queries/escalations" memory rule

Run with:  pytest tests/test_crew_smoke.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stage2.crew import ReviewCrew
from stage2.schema import EscalationResponse, Finding, QueryResponse


# --- The exact raw finding from the problem doc's worked example ---------
SAE_MISCODED_RAW = {
    "code": "SAE_MISCODED",
    "usubjid": "042-S02-004",
    "site": "S02",
    "severity": "CRITICAL",
    "rationale": "'Cellulitis' has AESHOSP=Y but AESER=N",
    "evidence": [{"domain": "AE", "usubjid": "042-S02-004", "seq": 1}],
}

AE_BEFORE_DOSE_RAW = {
    "code": "AE_BEFORE_FIRST_DOSE",
    "usubjid": "042-S11-005",
    "site": "S11",
    "severity": "MINOR",
    "rationale": "AE 'Fatigue' starts 2026-01-08, before first dose 2026-01-13.",
    "evidence": [{"domain": "AE", "usubjid": "042-S11-005", "seq": 1}],
}


def _make_crew(tmp_path) -> ReviewCrew:
    crew = ReviewCrew(
        hub_url="http://fake-hub",
        gateway_url="http://fake-gateway",
        team_key="fake-key",
        atlas=None,
    )
    crew.memory.path = tmp_path / "memory.json"
    crew.logger.path = tmp_path / "trace.jsonl"
    crew.logger.path.write_text("", encoding="utf-8")
    return crew


def test_sae_miscoded_escalates_and_gets_approved(tmp_path):
    crew = _make_crew(tmp_path)
    fake_finding = Finding.from_raw(SAE_MISCODED_RAW)

    with patch.object(crew, "detect", return_value=[fake_finding]), \
         patch(
             "stage2.nodes.human_gate.ApiClient.post_escalation",
             return_value=EscalationResponse(
                 id="E-0007", decision="APPROVED",
                 reason="Serious adverse event confirmed; expedited report within 24 h.",
             ),
         ):
        report = crew.run_cycle(cut=6, protocol_version=2)

    assert report.escalations_count == 1
    resolved = [f for f in report.findings if f.status == "resolved"]
    assert len(resolved) == 1
    assert resolved[0].code == "SAE_MISCODED"


def test_clarify_is_auto_answered_not_treated_as_rejection(tmp_path):
    crew = _make_crew(tmp_path)
    fake_finding = Finding.from_raw(SAE_MISCODED_RAW)

    responses = [
        EscalationResponse(
            id="E-0007", decision="CLARIFY",
            reason="What was the ALT at screening, and is there a concomitant hepatotoxic medication?",
        ),
        EscalationResponse(id="E-0007", decision="APPROVED", reason="Clarification accepted."),
    ]

    with patch.object(crew, "detect", return_value=[fake_finding]), \
         patch("stage2.nodes.human_gate.ApiClient.post_escalation", side_effect=[responses[0]]), \
         patch(
             "stage2.nodes.human_gate.ApiClient.resubmit_escalation_with_clarification",
             return_value=responses[1],
         ):
        report = crew.run_cycle(cut=6, protocol_version=2)

    resolved = [f for f in report.findings if f.status == "resolved"]
    assert len(resolved) == 1  # CLARIFY -> auto-answered -> resolved, not rejected


def test_rejected_escalation_is_never_repeated(tmp_path):
    crew = _make_crew(tmp_path)
    fake_finding = Finding.from_raw(SAE_MISCODED_RAW)

    with patch.object(crew, "detect", return_value=[fake_finding]), \
         patch(
             "stage2.nodes.human_gate.ApiClient.post_escalation",
             return_value=EscalationResponse(id="E-0007", decision="REJECTED", reason="Not significant."),
         ) as mock_escalate:
        crew.run_cycle(cut=6, protocol_version=2)
        # Second cycle, same finding, same cut — must NOT escalate again.
        crew.run_cycle(cut=6, protocol_version=2)

    assert mock_escalate.call_count == 1


def test_query_is_never_raised_twice_on_same_record(tmp_path):
    crew = _make_crew(tmp_path)
    fake_finding = Finding.from_raw(AE_BEFORE_DOSE_RAW)

    with patch.object(crew, "detect", return_value=[fake_finding]), \
         patch(
             "stage2.nodes.data_manager.ApiClient.post_query",
             return_value=QueryResponse(id="Q-0031", status="OPEN"),
         ) as mock_query:
        crew.run_cycle(cut=6, protocol_version=2)
        crew.run_cycle(cut=6, protocol_version=2)

    # Judges re-run the same cut and expect ZERO new queries the second time.
    assert mock_query.call_count == 1
