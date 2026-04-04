"""
outreach.py - Multi-touch outreach sequence manager.

Manages a pipeline of leads through a 3-touch sequence:
  Touch 1 (Day 0):  LinkedIn connection request (280 chars)
  Touch 2 (Day 3):  Follow-up DM with specific finding
  Touch 3 (Day 10): Industry peer comparison angle
  Touch 4 (Day 21): Clean breakup message

Features:
  - Per-lead touch state tracking (in-memory, exportable to JSON)
  - Daily limit enforcement (configurable, default 20 connections/day)
  - Due-today filtering (ready for next touch)
  - Sequence export for manual sending or CRM upload
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


DEFAULT_DAILY_LIMIT = int(os.environ.get("DEFAULT_DAILY_LIMIT", "20"))


class OutreachSequence:
    """
    Manages multi-touch outreach sequences for a set of leads.

    Usage:
        seq = OutreachSequence(daily_limit=20)
        seq.add_leads(qualified_leads)
        due = seq.get_due_today()
        seq.mark_sent(domain, touch=1)
        seq.export("outreach-state.json")
    """

    TOUCH_GAPS = {
        1: 0,   # Day 0: connection request
        2: 3,   # Day 3 after touch 1
        3: 7,   # Day 7 after touch 2 (10 days total)
        4: 11,  # Day 11 after touch 3 (21 days total)
    }

    def __init__(
        self,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        state: Optional[dict] = None,
    ):
        """
        Args:
            daily_limit: Max connection requests per day (touch 1 only)
            state:       Pre-loaded state dict (from export/load)
        """
        self.daily_limit = daily_limit
        # State: {domain: {touch, last_sent, scheduled_next, status, messages, ...}}
        self._state: dict[str, dict] = {}
        self._sends_today: dict[str, int] = {}  # date_str -> count

        if state:
            self._state = state.get("leads", {})
            self._sends_today = state.get("sends_today", {})

    def add_leads(self, leads: list[dict], force: bool = False) -> int:
        """
        Add leads to the sequence.

        Args:
            leads: List of dicts, each with domain + messages (from message.py)
            force: Re-add already-tracked leads (resets their state)

        Returns:
            Number of new leads added
        """
        added = 0
        for lead in leads:
            domain = lead.get("domain", "")
            if not domain:
                continue
            if domain in self._state and not force:
                continue
            messages = lead.get("messages", {})
            self._state[domain] = {
                "domain": domain,
                "company": lead.get("company", domain),
                "contact_name": lead.get("contact_name", ""),
                "linkedin_url": lead.get("linkedin_url"),
                "touch": 0,          # 0 = not started
                "last_sent": None,
                "scheduled_next": datetime.now().strftime("%Y-%m-%d"),
                "status": "pending",  # pending / in_sequence / completed / skipped
                "connection_note": messages.get("connection_note", ""),
                "first_dm": messages.get("first_dm", ""),
                "followup_1": messages.get("followup", ""),
                "followup_2": messages.get("followup_2", ""),
                "followup_3": messages.get("followup_3", ""),
                "score": lead.get("qualification", {}).get("score") if "qualification" in lead else None,
                "tier": lead.get("qualification", {}).get("tier") if "qualification" in lead else None,
            }
            added += 1
        return added

    def get_due_today(
        self,
        touch: Optional[int] = None,
        include_overdue: bool = True,
    ) -> list[dict]:
        """
        Return leads that are due for outreach today (or overdue).

        Args:
            touch:           Filter to a specific touch number (1-4), or None for all
            include_overdue: Include leads past their scheduled date

        Returns:
            List of lead state dicts, sorted by score descending (hot leads first)
        """
        today = datetime.now().date()
        due = []

        for domain, s in self._state.items():
            if s["status"] in ("completed", "skipped"):
                continue

            current_touch = s["touch"]
            next_touch = current_touch + 1

            if next_touch > 4:
                # Sequence complete
                if s["status"] != "completed":
                    s["status"] = "completed"
                continue

            if touch is not None and next_touch != touch:
                continue

            scheduled = s.get("scheduled_next")
            if not scheduled:
                continue

            try:
                scheduled_date = datetime.strptime(scheduled, "%Y-%m-%d").date()
            except ValueError:
                continue

            if scheduled_date <= today or (include_overdue and scheduled_date < today):
                due.append({**s, "next_touch": next_touch})

        # Sort: hot leads first, then by score
        def _sort_key(x):
            tier_order = {"hot": 0, "warm": 1, "cold": 2, None: 3}
            return (tier_order.get(x.get("tier"), 3), -(x.get("score") or 0))

        return sorted(due, key=_sort_key)

    def get_touch_message(self, domain: str, touch_number: int) -> str:
        """Return the message text for a specific touch."""
        s = self._state.get(domain, {})
        mapping = {
            1: "connection_note",
            2: "first_dm",
            3: "followup_1",
            4: "followup_2",
        }
        key = mapping.get(touch_number, "")
        return s.get(key, "")

    def mark_sent(self, domain: str, touch: int) -> bool:
        """
        Record that a touch was sent for a lead.

        Args:
            domain: Lead's domain
            touch:  Touch number that was sent (1-4)

        Returns:
            True if updated, False if domain not found
        """
        if domain not in self._state:
            return False

        s = self._state[domain]
        now_str = datetime.now().strftime("%Y-%m-%d")
        s["touch"] = touch
        s["last_sent"] = now_str
        s["status"] = "in_sequence"

        # Track daily sends for touch 1 (connection requests)
        if touch == 1:
            self._sends_today[now_str] = self._sends_today.get(now_str, 0) + 1

        # Schedule next touch
        next_touch = touch + 1
        if next_touch > 4:
            s["status"] = "completed"
            s["scheduled_next"] = None
        else:
            gap = self.TOUCH_GAPS.get(next_touch, 7)
            next_date = datetime.now() + timedelta(days=gap)
            s["scheduled_next"] = next_date.strftime("%Y-%m-%d")

        return True

    def skip(self, domain: str, reason: str = "") -> bool:
        """Mark a lead as skipped (remove from sequence)."""
        if domain not in self._state:
            return False
        self._state[domain]["status"] = "skipped"
        if reason:
            self._state[domain]["skip_reason"] = reason
        return True

    def daily_capacity_remaining(self) -> int:
        """Return how many connection requests (touch 1) can be sent today."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        sent_today = self._sends_today.get(today_str, 0)
        return max(0, self.daily_limit - sent_today)

    def get_stats(self) -> dict:
        """Return summary statistics for the sequence."""
        counts = {"pending": 0, "in_sequence": 0, "completed": 0, "skipped": 0}
        touch_counts: dict[int, int] = {}
        tiers: dict[str, int] = {}

        for s in self._state.values():
            status = s.get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
            touch = s.get("touch", 0)
            touch_counts[touch] = touch_counts.get(touch, 0) + 1
            tier = s.get("tier")
            if tier:
                tiers[tier] = tiers.get(tier, 0) + 1

        return {
            "total_leads": len(self._state),
            "status_breakdown": counts,
            "touch_breakdown": touch_counts,
            "tier_breakdown": tiers,
            "due_today": len(self.get_due_today()),
            "daily_capacity_remaining": self.daily_capacity_remaining(),
        }

    def export(self, path: Optional[str] = None) -> dict:
        """
        Export state to a JSON-serializable dict (and optionally write to file).

        Args:
            path: File path to write to (optional)

        Returns:
            State dict
        """
        data = {
            "exported_at": datetime.now().isoformat(),
            "daily_limit": self.daily_limit,
            "sends_today": self._sends_today,
            "leads": self._state,
        }
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return data

    @classmethod
    def load(cls, path: str, daily_limit: Optional[int] = None) -> "OutreachSequence":
        """Load a previously exported state file."""
        with open(path) as f:
            data = json.load(f)
        limit = daily_limit or data.get("daily_limit", DEFAULT_DAILY_LIMIT)
        return cls(daily_limit=limit, state=data)

    def print_queue(self, touch: Optional[int] = None) -> None:
        """Print the due-today queue to stdout."""
        due = self.get_due_today(touch=touch)
        if not due:
            print("[outreach] No leads due today.", flush=True)
            return
        remaining = self.daily_capacity_remaining()
        print(
            f"[outreach] {len(due)} leads due today "
            f"({remaining} connection slots remaining)",
            flush=True,
        )
        for item in due:
            touch_num = item.get("next_touch", "?")
            tier = item.get("tier", "-")
            score = item.get("score", "-")
            msg_preview = self.get_touch_message(item["domain"], touch_num)[:60] if touch_num else ""
            print(
                f"  [{tier.upper() if tier else '-'}:{score}] "
                f"{item['company']} ({item['domain']}) "
                f"-> touch {touch_num}: {msg_preview}...",
                flush=True,
            )
