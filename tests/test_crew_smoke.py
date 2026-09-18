"""
Smoke test: proves the pipeline structure works end-to-end BEFORE any real
node logic exists. Run this first, on both machines, to confirm the
scaffold itself is sound. Mocks the API client so it needs no network.

Run with:  pytest tests/test_crew_smoke.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stage2 import crew
from stage2.schema import Finding


def _fake_findings() -> list[Finding]:
    return [
        Finding(
            finding_id="SUBJ-001:adverse_event:AE-0002",
            subject_id="SUBJ-001",
            site_id="S01",
            finding_type="adverse_event",
            detail="AE reported without hospitalization flag reviewed",
            record_refs=["adverse_events:AE-0002"],
        ),
        Finding(
            finding_id="SUBJ-004:visit_window:V-0006",
            subject_id="SUBJ-004",
            site_id="S03",
            finding_type="visit_window",
            detail="Visit occurred outside protocol window",
            record_refs=["visits:V-0006"],
        ),
    ]


def test_pipeline_runs_end_to_end(tmp_path):
    memory_path = str(tmp_path / "memory.json")
    trace_path = str(tmp_path / "trace.jsonl")

    with patch.object(crew, "detect", return_value=_fake_findings()), \
         patch("stage2.nodes.data_manager.api_client.post_query", return_value={"ok": True}), \
         patch("stage2.nodes.human_gate.api_client.post_escalation", return_value={"decision": "APPROVED"}):

        results = crew.run_pipeline(
            data_dir="unused",
            memory_path=memory_path,
            trace_path=trace_path,
        )

    assert len(results) == 2
    for f in results:
        assert "medical_review" in f.node_trail
        assert "compliance" in f.node_trail
        assert "data_manager" in f.node_trail
        assert "human_gate" in f.node_trail
        assert "execute" in f.node_trail

    assert Path(trace_path).exists()
    assert Path(trace_path).read_text().strip() != ""


def test_duplicate_query_is_skipped_on_second_cycle(tmp_path):
    memory_path = str(tmp_path / "memory.json")
    trace_path = str(tmp_path / "trace.jsonl")

    with patch.object(crew, "detect", return_value=_fake_findings()), \
         patch("stage2.nodes.data_manager.api_client.post_query", return_value={"ok": True}) as mock_post, \
         patch("stage2.nodes.human_gate.api_client.post_escalation", return_value={"decision": "APPROVED"}):

        crew.run_pipeline(data_dir="unused", memory_path=memory_path, trace_path=trace_path)
        crew.run_pipeline(data_dir="unused", memory_path=memory_path, trace_path=trace_path)

    # Two findings, queried once each across two cycles -> exactly 2 calls, not 4.
    assert mock_post.call_count == 2
