"""
stage2/trace_logger.py  —  PERSON B

Strict, real-time logging: every node decision, its rationale, and the
evidence behind it, written as it happens (not batched at the end) so a
judge can open the trace file mid-run and see exactly what the system is
doing and why.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceLogger:
    def __init__(self, path: str = "stage2_trace.jsonl", also_print: bool = True) -> None:
        self.path = Path(path)
        self.also_print = also_print
        # Truncate at the start of each run — this is a per-run trace, not an
        # accumulating log. Cross-cycle history lives in memory.py instead.
        self.path.write_text("", encoding="utf-8")

    def log(
        self,
        node: str,
        finding_id: str,
        decision: str,
        rationale: str,
        evidence: list[str] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "finding_id": finding_id,
            "decision": decision,
            "rationale": rationale,
            "evidence": evidence or [],
        }
        line = json.dumps(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.also_print:
            print(f"[{node}] {finding_id} -> {decision} :: {rationale}", file=sys.stderr)
