"""
stage2/trace_logger.py

Strict, real-time logging. Per the problem doc: "A node that ran but wrote
no entry is treated as not having run" — every node MUST call log() for
every decision it makes, as it happens, not batched at the end.
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
        self.path.write_text("", encoding="utf-8")

    def log(
        self,
        node: str,
        finding_id: str,
        decision: str,
        rationale: str,
        evidence: list[Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "finding_id": finding_id,
            "decision": decision,
            "rationale": rationale,
            "evidence": evidence or [],
        }
        line = json.dumps(entry, default=str)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.also_print:
            print(f"[{node}] {finding_id} -> {decision} :: {rationale}", file=sys.stderr)

    def log_summary(self, node: str, summary: str) -> None:
        """
        For the node-level aggregate lines the doc's example trace shows, e.g.:
            detect  202 findings under protocol v2 - safety 6, data 16, compliance 179, site 1
        Call this once per node per cycle IN ADDITION TO per-decision log()
        calls, not instead of them.
        """
        self.log(node=node, finding_id="-", decision="cycle_summary", rationale=summary)
