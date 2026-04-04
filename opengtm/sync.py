"""
sync.py - CRM sync via Google Apps Script webhook.

Posts leads to a Google Sheet via a doPost Apps Script endpoint.
Supports both new row inserts and row-number-targeted updates.

Configuration via environment variables:
  CRM_WEBHOOK_URL   - Apps Script doPost URL
  CRM_WEBHOOK_TOKEN - Auth token (sent as ?token= query param)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Optional


CRM_WEBHOOK_URL = os.environ.get("CRM_WEBHOOK_URL", "")
CRM_WEBHOOK_TOKEN = os.environ.get("CRM_WEBHOOK_TOKEN", "")


def _post_to_webhook(
    data: list[dict],
    webhook_url: str,
    token: str,
    timeout: int = 120,
) -> bool:
    """POST data to Apps Script webhook via curl."""
    if not webhook_url:
        raise ValueError(
            "CRM_WEBHOOK_URL is not set. "
            "Set it in your .env or as an environment variable."
        )

    url = f"{webhook_url}?token={token}" if token else webhook_url
    payload = json.dumps(data)

    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", str(timeout),
         "-H", "Content-Type: application/json",
         "-d", payload, url],
        capture_output=True, text=True, timeout=timeout + 10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"curl exit {result.returncode}: {result.stderr[:200]}")

    try:
        resp = json.loads(result.stdout)
        return resp.get("status") == "ok"
    except json.JSONDecodeError:
        return "ok" in result.stdout.lower()


def sync_leads(
    leads: list[dict],
    webhook_url: Optional[str] = None,
    token: Optional[str] = None,
    batch_size: int = 50,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Sync a list of enriched leads to a Google Sheet CRM via Apps Script webhook.

    Each lead dict is mapped to a CRM row. Expected keys per lead:
      company, domain, industry, contact_name, contact_title,
      linkedin_url, contact_email, status, research_notes,
      linkedin_connection, linkedin_followup

    Args:
        leads:       List of lead dicts
        webhook_url: Apps Script doPost URL (defaults to CRM_WEBHOOK_URL env var)
        token:       Auth token (defaults to CRM_WEBHOOK_TOKEN env var)
        batch_size:  Rows per HTTP call (default 50)
        dry_run:     Print what would be synced, do not actually post
        verbose:     Print progress

    Returns:
        Dict with: synced (int), skipped (int), errors (list)
    """
    url = webhook_url or CRM_WEBHOOK_URL
    tok = token or CRM_WEBHOOK_TOKEN

    if dry_run:
        if verbose:
            print(f"[sync] DRY RUN: would sync {len(leads)} leads", flush=True)
            for lead in leads[:5]:
                print(f"  {lead.get('company', '?')} ({lead.get('domain', '?')})", flush=True)
            if len(leads) > 5:
                print(f"  ... and {len(leads) - 5} more", flush=True)
        return {"synced": 0, "skipped": 0, "errors": [], "dry_run": True}

    synced = 0
    errors = []

    for i in range(0, len(leads), batch_size):
        batch = leads[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(leads) + batch_size - 1) // batch_size

        try:
            ok = _post_to_webhook(batch, url, tok)
            if ok:
                synced += len(batch)
                if verbose:
                    print(
                        f"  Batch [{batch_num}/{total_batches}]: "
                        f"{len(batch)} rows synced",
                        flush=True,
                    )
            else:
                errors.append(f"Batch {batch_num}: webhook returned non-ok status")
                if verbose:
                    print(f"  Batch [{batch_num}/{total_batches}]: FAILED", flush=True)
        except Exception as e:
            errors.append(f"Batch {batch_num}: {e}")
            if verbose:
                print(f"  Batch [{batch_num}/{total_batches}]: ERROR - {e}", flush=True)

        if i + batch_size < len(leads):
            time.sleep(1)

    if verbose:
        print(f"[sync] Done: {synced}/{len(leads)} synced, {len(errors)} errors", flush=True)

    return {"synced": synced, "skipped": len(leads) - synced, "errors": errors}


def build_sync_payload(prospect: dict) -> dict:
    """
    Convert a fully-enriched prospect dict (from pipeline) to CRM row format.

    Args:
        prospect: Dict with keys: company, domain, industry, contact_name,
                  contact_title, linkedin_url, contact_email, audit, messages

    Returns:
        Flat dict ready for webhook POST
    """
    messages = prospect.get("messages", {})
    audit = prospect.get("audit", {})
    findings = audit.get("findings", [])

    # Build research_notes from best finding
    best = messages.get("best_finding", "")
    if best and isinstance(best, dict):
        research_notes = best.get("detail", str(best))
    elif best:
        research_notes = str(best)
    elif messages.get("pattern") == "E":
        research_notes = audit.get("overall_assessment", "")
    else:
        research_notes = messages.get("pattern_reason", "")

    return {
        "company": prospect.get("company", ""),
        "domain": prospect.get("domain", ""),
        "industry": prospect.get("industry", ""),
        "contact_name": prospect.get("contact_name", ""),
        "contact_title": prospect.get("contact_title", ""),
        "linkedin_url": prospect.get("linkedin_url"),
        "contact_email": prospect.get("contact_email"),
        "status": "New",
        "research_notes": research_notes,
        "linkedin_connection": messages.get("connection_note", ""),
        "linkedin_followup": messages.get("first_dm", ""),
    }
