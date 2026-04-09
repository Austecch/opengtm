"""
Floom app entrypoint for opengtm.

Exposes two GTM actions to the Floom runtime:

  - aeo_health: run the 29-check AEO/SEO health report on any URL.
                No API key required, just httpx fetches + local scoring.
  - score_lead: score a lead dict (research output) on ICP fit and return
                a tier (hot/warm/cold) plus a recommended action.

opengtm ships far more than this (research, outreach, messaging, blog,
mentions) but that surface area depends on Gemini+Google Search grounding,
CRM access, and multi-step pipelines. This wrapper keeps things small:
two pure functions that are useful on their own and play nicely with the
Floom stateless runtime.
"""

import json

from floom import app

from opengtm.analytics import run_health_check
from opengtm.qualify import qualify as _qualify


def _coerce_json(value, default=None):
    """Parse a value that may already be a dict/list or a JSON-encoded string."""
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


@app.action
def aeo_health(url: str, timeout: float = 30.0) -> dict:
    """
    Run a 29-check AEO/SEO health report on a URL.

    Covers technical SEO (16 checks), structured data (6), AI crawler
    access (4) and authority signals (3). Returns a tiered score, letter
    grade (A+ to F), and list of findings.
    """
    if not url or not isinstance(url, str):
        return {"error": "url is required"}
    try:
        return run_health_check(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"health check failed: {exc}", "url": url}


@app.action
def score_lead(
    lead,
    icp_profile: str = "default",
    custom_profile=None,
) -> dict:
    """
    Score a lead on ICP fit (0-100) and return tier + recommended action.

    `lead` is a dict (or JSON-encoded string) with at minimum:
      - domain (str)
      - company (str)
      - industry (str, optional)
      - research_data (dict, optional) -- output of opengtm research.py
    `icp_profile` selects one of the built-in profiles (default, saas, agency,
    enterprise, ...). Pass `custom_profile` (dict or JSON string) to override
    the profile entirely.
    """
    lead_dict = _coerce_json(lead)
    if not isinstance(lead_dict, dict):
        return {"error": "lead must be a JSON object"}

    profile_dict = _coerce_json(custom_profile) if custom_profile else None

    try:
        return _qualify(lead_dict, icp_profile=icp_profile, custom_profile=profile_dict)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"score_lead failed: {exc}"}
