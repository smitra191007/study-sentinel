"""
stage2/memory.py

Cross-cycle memory. Corrected against the problem doc's exact rules:
  - "a query already raised on a record is never raised again"
  - "an escalation already made is not repeated"          (even if REJECTED —
     see failure mode: "Re-escalating something the monitor already rejected")
  - "a subject flagged in two cycles escalates on its own"   (threshold = 2,
     not 3)
  - "a site with recurring problems accumulates a site-level flag"

Tested directly by the judges: re-running the same cut must raise ZERO new
queries and ZERO new escalations.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

AUTO_ESCALATE_CYCLE_THRESHOLD = 2   # per the doc: "flagged in two cycles"
SITE_FLAG_RECURRENCE_THRESHOLD = 2  # findings recurring at a site before it's flagged


@dataclass
class MemoryRecord:
    finding_id: str
    usubjid: str
    site: str
    code: str
    first_seen_cycle: int
    last_seen_cycle: int
    times_seen: int = 1
    queried: bool = False
    escalated: bool = False
    escalation_decision: str | None = None   # "APPROVED" | "REJECTED" | "CLARIFY" | None
    resolved: bool = False


@dataclass
class SiteFlag:
    site: str
    flagged: bool = False
    distinct_recurring_findings: int = 0
    first_flagged_cycle: int | None = None


class CrossCycleMemory:
    def __init__(self, path: str = "stage2_memory.json") -> None:
        self.path = Path(path)
        self._records: dict[str, MemoryRecord] = {}
        self._site_flags: dict[str, SiteFlag] = {}
        self._current_cycle = 0
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._current_cycle = raw.get("current_cycle", 0)
            self._records = {
                fid: MemoryRecord(**rec) for fid, rec in raw.get("records", {}).items()
            }
            self._site_flags = {
                site: SiteFlag(**flag) for site, flag in raw.get("site_flags", {}).items()
            }

    def _save(self) -> None:
        payload = {
            "current_cycle": self._current_cycle,
            "records": {fid: asdict(rec) for fid, rec in self._records.items()},
            "site_flags": {site: asdict(flag) for site, flag in self._site_flags.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def start_new_cycle(self) -> int:
        self._current_cycle += 1
        self._save()
        return self._current_cycle

    @property
    def current_cycle(self) -> int:
        return self._current_cycle

    # --- Query dedup: never raise the same record's query twice, ever -----

    def was_queried(self, finding_id: str) -> bool:
        rec = self._records.get(finding_id)
        return bool(rec and rec.queried)

    def mark_queried(self, finding_id: str) -> None:
        if finding_id in self._records:
            self._records[finding_id].queried = True
            self._save()

    # --- Escalation dedup: never repeat, even if REJECTED ------------------

    def was_escalated(self, finding_id: str) -> bool:
        """
        True if this finding has EVER been escalated, regardless of the
        decision. A REJECTED escalation must not be re-escalated — that's
        an explicit failure mode in the problem doc.
        """
        rec = self._records.get(finding_id)
        return bool(rec and rec.escalated)

    def mark_escalated(self, finding_id: str, decision: str | None = None) -> None:
        if finding_id in self._records:
            self._records[finding_id].escalated = True
            if decision:
                self._records[finding_id].escalation_decision = decision
            self._save()

    def get_escalation_decision(self, finding_id: str) -> str | None:
        rec = self._records.get(finding_id)
        return rec.escalation_decision if rec else None

    def mark_resolved(self, finding_id: str) -> None:
        if finding_id in self._records:
            self._records[finding_id].resolved = True
            self._save()

    # --- Cycle tracking / auto-escalation ------------------------------------

    def has_seen(self, finding_id: str) -> bool:
        return finding_id in self._records

    def get_cycle_count(self, finding_id: str) -> int:
        rec = self._records.get(finding_id)
        return rec.times_seen if rec else 0

    def touch(self, finding_id: str, usubjid: str, site: str, code: str) -> MemoryRecord:
        """Register that this finding was seen in the current cycle."""
        rec = self._records.get(finding_id)
        if rec is None:
            rec = MemoryRecord(
                finding_id=finding_id,
                usubjid=usubjid,
                site=site,
                code=code,
                first_seen_cycle=self._current_cycle,
                last_seen_cycle=self._current_cycle,
                times_seen=1,
            )
            self._records[finding_id] = rec
        else:
            if rec.last_seen_cycle != self._current_cycle:
                rec.times_seen += 1
                rec.last_seen_cycle = self._current_cycle
                self._update_site_flag(site)
        self._save()
        return rec

    def should_auto_escalate(self, finding_id: str) -> bool:
        """
        Per the doc: "a subject flagged in two cycles escalates on its own."
        Threshold is 2 cycles, unresolved, not already escalated.
        """
        rec = self._records.get(finding_id)
        return bool(
            rec
            and rec.times_seen >= AUTO_ESCALATE_CYCLE_THRESHOLD
            and not rec.resolved
            and not rec.escalated
        )

    # --- Site-level recurrence flag --------------------------------------

    def _update_site_flag(self, site: str) -> None:
        """
        Recompute whether this site should carry a recurring-problem flag.
        A site is flagged once SITE_FLAG_RECURRENCE_THRESHOLD distinct
        findings at that site have recurred across cycles.
        """
        recurring_count = sum(
            1 for rec in self._records.values()
            if rec.site == site and rec.times_seen > 1
        )
        flag = self._site_flags.get(site)
        if flag is None:
            flag = SiteFlag(site=site)
            self._site_flags[site] = flag

        flag.distinct_recurring_findings = recurring_count
        if recurring_count >= SITE_FLAG_RECURRENCE_THRESHOLD and not flag.flagged:
            flag.flagged = True
            flag.first_flagged_cycle = self._current_cycle

    def is_site_flagged(self, site: str) -> bool:
        flag = self._site_flags.get(site)
        return bool(flag and flag.flagged)

    def get_site_flag(self, site: str) -> SiteFlag | None:
        return self._site_flags.get(site)

    def all_flagged_sites(self) -> list[SiteFlag]:
        return [f for f in self._site_flags.values() if f.flagged]
