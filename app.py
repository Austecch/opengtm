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

from floom import app

from opengtm.analytics import run_health_check
from opengtm.qualify import qualify as _qualify


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
    lead: dict,
    icp_profile: str = "default",
    custom_profile: dict = None,
) -> dict:
    """
    Score a lead on ICP fit (0-100) and return tier + recommended action.

    `lead` is a dict that contains at minimum:
      - domain (str)
      - company (str)
      - industry (str, optional)
      - research_data (dict, optional) -- output of opengtm research.py
    `icp_profile` selects one of the built-in profiles (default, saas, agency,
    enterprise, ...). Pass `custom_profile` to override the profile entirely.
    """
    if not isinstance(lead, dict):
        return {"error": "lead must be a JSON object"}
    try:
        return _qualify(lead, icp_profile=icp_profile, custom_profile=custom_profile)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"score_lead failed: {exc}"}
