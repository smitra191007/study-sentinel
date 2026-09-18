# Stage 2 Planning — Study Sentinel

## Start here

1. Run the smoke test first, on both machines, before writing anything:
   ```bash
   pip install -r requirements.txt
   python -m pytest tests/test_crew_smoke.py -v
   ```
   If this passes, the scaffold is sound and you're both building on solid ground.

2. Read `stage2/schema.py` together. This is the only file you should need
   to jointly agree on changes to — everything else is separable.

## Who owns what

### Person A — Medical & Compliance Logic
- `stage2/nodes/medical_review.py` — replace the placeholder with the real
  `AESHOSP=Y forces serious` override (and any other hidden rules from the
  protocol/SAP).
- `stage2/nodes/compliance.py` — wire in `stage1.documents.active_version_for_date`
  to map each subject's data-cut date to the real active protocol version.
- `stage2/nodes/data_manager.py` — own `draft_query_text()` only (the
  wording of what gets queried per finding_type). Leave the rest of that
  file to Person B.

### Person B — Orchestration & Infra
- `stage2/crew.py` — wire the real `detect()` function into `stage1.atlas.Atlas`
  once Person A confirms the finding shape coming out of Stage 1.
- `stage2/memory.py` — already functional; extend `should_auto_escalate`
  threshold logic if the spec needs something smarter than a flat count.
- `stage2/nodes/human_gate.py` — everything except `auto_answer_clarify()`,
  which needs pairing (see below).
- `stage2/trace_logger.py` — already functional; adjust format if judges
  want a specific structure.

### Pair on this one
- `auto_answer_clarify()` in `stage2/nodes/human_gate.py` needs both graph
  access (Person B's territory) and domain knowledge of what a CLARIFY
  question is actually asking (Person A's territory). Do this together once
  both halves of the pipeline are working independently.

## Suggested order

1. **Both, ~30 min:** confirm `schema.py` is right for your actual Stage 1 output.
2. **Parallel:** A builds `medical_review.py` + `compliance.py` against fixture
   data. B wires `detect()` into real `stage1.atlas` output and confirms
   `data_manager.py` / `human_gate.py` call the API correctly (mock the API
   for now if it's not live yet).
3. **Integration:** run `python -m stage2.crew --data-dir hackathon-data`
   end-to-end, fix schema drift between what A produces and what B consumes.
4. **Together, last:** `auto_answer_clarify()`.
5. **Buffer:** check `stage2_trace.jsonl` reads clearly — this is what judges
   will actually look at to audit your reasoning.

## Known gaps in this scaffold (by design — these are your TODOs)

- `detect()` in `crew.py` returns `[]` — needs real Stage 1 wiring.
- `medical_review.py` and `compliance.py` have placeholder logic clearly
  marked `# --- TODO ---`.
- `draft_query_text()` in `data_manager.py` is a generic template — needs
  real per-finding-type wording.
- `auto_answer_clarify()` in `human_gate.py` is a stub — needs graph lookup.
- The API client (`api_client.py`) assumes a `{"decision": ...}` response
  shape for escalations — confirm this against the actual API spec once
  you have it, and adjust.
