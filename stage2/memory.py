"""
stage2/memory.py  —  PERSON B

Cross-cycle memory: remembers what's already been queried or escalated so
the pipeline never repeats itself, and tracks how many cycles a finding has
recurred (for auto-escalation) and which sites keep coming up (site-level
patterns).

Backed by a single JSON file for simplicity — swap for SQLite later if you
need concurrent access, but for a hackathon this is enough and it's easy to
eyeball in a text editor while debugging.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MemoryRecord:
    finding_id: str
    subject_id: str
    site_id: str
    finding_type: str
    first_seen_cycle: int
    last_seen_cycle: int
    times_seen: int = 1
    queried: bool = False
    escalated: bool = False
    resolved: bool = False


class CrossCycleMemory:
    def __init__(self, path: str = "stage2_memory.json") -> None:
        self.path = Path(path)
        self._records: dict[str, MemoryRecord] = {}
        self._current_cycle = 0
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._current_cycle = raw.get("current_cycle", 0)
            self._records = {
                fid: MemoryRecord(**rec) for fid, rec in raw.get("records", {}).items()
            }

    def _save(self) -> None:
        payload = {
            "current_cycle": self._current_cycle,
            "records": {fid: asdict(rec) for fid, rec in self._records.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def start_new_cycle(self) -> int:
        """Call once at the start of each pipeline run."""
        self._current_cycle += 1
        self._save()
        return self._current_cycle

    @property
    def current_cycle(self) -> int:
        return self._current_cycle

    def has_seen(self, finding_id: str) -> bool:
        return finding_id in self._records

    def get_cycle_count(self, finding_id: str) -> int:
        rec = self._records.get(finding_id)
        return rec.times_seen if rec else 0

    def was_queried(self, finding_id: str) -> bool:
        rec = self._records.get(finding_id)
        return bool(rec and rec.queried)

    def was_escalated(self, finding_id: str) -> bool:
        rec = self._records.get(finding_id)
        return bool(rec and rec.escalated)

    def touch(self, finding_id: str, subject_id: str, site_id: str, finding_type: str) -> MemoryRecord:
        """Register that this finding was seen in the current cycle."""
        rec = self._records.get(finding_id)
        if rec is None:
            rec = MemoryRecord(
                finding_id=finding_id,
                subject_id=subject_id,
                site_id=site_id,
                finding_type=finding_type,
                first_seen_cycle=self._current_cycle,
                last_seen_cycle=self._current_cycle,
                times_seen=1,
            )
            self._records[finding_id] = rec
        else:
            if rec.last_seen_cycle != self._current_cycle:
                rec.times_seen += 1
                rec.last_seen_cycle = self._current_cycle
        self._save()
        return rec

    def mark_queried(self, finding_id: str) -> None:
        if finding_id in self._records:
            self._records[finding_id].queried = True
            self._save()

    def mark_escalated(self, finding_id: str) -> None:
        if finding_id in self._records:
            self._records[finding_id].escalated = True
            self._save()

    def mark_resolved(self, finding_id: str) -> None:
        if finding_id in self._records:
            self._records[finding_id].resolved = True
            self._save()

    def site_recurrence_count(self, site_id: str) -> int:
        """How many distinct findings at this site have recurred (times_seen > 1)."""
        return sum(
            1 for rec in self._records.values()
            if rec.site_id == site_id and rec.times_seen > 1
        )

    def should_auto_escalate(self, finding_id: str, threshold: int = 3) -> bool:
        """A finding that's recurred `threshold` cycles unresolved should escalate automatically."""
        rec = self._records.get(finding_id)
        return bool(rec and rec.times_seen >= threshold and not rec.resolved)
