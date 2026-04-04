"""
discover.py - Lead discovery via Gemini + Google Search grounding.

Input:  industry, region, limit
Output: list of {company, domain, industry, region}
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from typing import Optional


MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


DISCOVER_PROMPT = """Find {limit} {industry} companies in {region} that have their own website.

Requirements:
- Only real, currently operating companies
- Must have a working website (own domain, not just social media)
- Include small to medium firms (1-200 employees)
- Do NOT include large multinationals or enterprise firms
- Do NOT include directories, portals, or aggregator sites
{exclusion_clause}

Return ONLY a JSON array, no other text:
[{{"company": "Full Company Name", "domain": "example.com"}}]"""


def _gemini_call(prompt: str, timeout: int = 90) -> str:
    """Call Gemini API via curl (bypasses Python SSL edge cases)."""
    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1},
    })
    result = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout),
         "-H", "Content-Type: application/json",
         "-d", payload, api_url],
        capture_output=True, text=True, timeout=timeout + 10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl exit {result.returncode}: {result.stderr[:200]}")
    if not result.stdout.strip():
        raise RuntimeError("Empty response from Gemini API")
    data = json.loads(result.stdout)
    if "error" in data:
        raise RuntimeError(f"API error: {data['error'].get('message', str(data['error']))[:200]}")
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No candidates in Gemini response")
    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [p["text"] for p in parts if "text" in p]
    if not text_parts:
        raise RuntimeError("No text in Gemini response parts")
    return "\n".join(text_parts)


def _validate_url(domain: str, timeout: int = 6) -> bool:
    """HEAD request to verify domain is reachable."""
    url = f"https://{domain}" if not domain.startswith("http") else domain
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; opengtm/0.1)")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status in (200, 301, 302, 403)
    except Exception:
        try:
            url2 = url.replace("https://", "http://")
            req2 = urllib.request.Request(url2, method="HEAD")
            req2.add_header("User-Agent", "Mozilla/5.0 (compatible; opengtm/0.1)")
            resp2 = urllib.request.urlopen(req2, timeout=timeout)
            return resp2.status in (200, 301, 302, 403)
        except Exception:
            return False


def _normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if d.startswith("www."):
        d = d[4:]
    return d


def discover(
    industry: str,
    region: str,
    limit: int = 20,
    existing_domains: Optional[set] = None,
    validate: bool = True,
    verbose: bool = True,
) -> list[dict]:
    """
    Discover companies using Gemini + Google Search grounding.

    Args:
        industry:  Industry vertical (e.g. "B2B SaaS", "IT Services", "Recruiting")
        region:    City or region (e.g. "Berlin", "San Francisco", "London")
        limit:     Max number of validated companies to return
        existing_domains: Set of known domains to skip (dedup)
        validate:  Whether to verify each domain is reachable
        verbose:   Print progress to stdout

    Returns:
        List of dicts: {company, domain, industry, region}
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    known = set(existing_domains or [])
    exclusion = (
        f"- Do NOT include these domains (already known): {', '.join(list(known)[:50])}"
        if known else ""
    )

    prompt = DISCOVER_PROMPT.format(
        limit=limit + 5,
        industry=industry,
        region=region,
        exclusion_clause=exclusion,
    )

    if verbose:
        print(f"[discover] Searching for {industry} companies in {region}...", flush=True)

    companies = None
    for attempt in range(3):
        try:
            text = _gemini_call(prompt, timeout=90)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            companies = json.loads(text)
            break
        except Exception as e:
            if verbose:
                print(f"  Attempt {attempt + 1}/3 failed: {e}", flush=True)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))

    if not companies:
        if verbose:
            print("  ERROR: Discovery failed after 3 attempts", flush=True)
        return []

    validated = []
    for c in companies:
        domain = _normalize_domain(c.get("domain", ""))
        if not domain:
            continue
        c["domain"] = domain

        if domain in known:
            if verbose:
                print(f"  SKIP (duplicate): {domain}", flush=True)
            continue

        if validate:
            if _validate_url(domain):
                validated.append({
                    "company": c["company"],
                    "domain": domain,
                    "industry": industry,
                    "region": region,
                })
                known.add(domain)
                if verbose:
                    print(f"  OK: {c['company']} ({domain})", flush=True)
            else:
                if verbose:
                    print(f"  DROP (unreachable): {domain}", flush=True)
        else:
            validated.append({
                "company": c["company"],
                "domain": domain,
                "industry": industry,
                "region": region,
            })
            known.add(domain)

        if len(validated) >= limit:
            break

    if verbose and len(validated) < limit:
        print(
            f"  Warning: Found {len(validated)}/{limit} valid companies",
            flush=True,
        )

    return validated
