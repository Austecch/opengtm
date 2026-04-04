"""
research.py - Lead research and website enrichment.

Combines:
- Decision-maker contact extraction (name, title, email, LinkedIn)
- 7-point technical website audit
- Structured output for downstream qualify/message steps

Input:  domain (+ optional company name, industry)
Output: structured dict with contact info and audit findings
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


RESEARCH_PROMPT = """Analyze the company "{company}" at website {domain} (industry: {industry}).

Task 1 - Find the decision-maker / main contact:
- Check the Impressum/About/Team page for the managing director, owner, or founder
- Find their full name, title/position
- Find the company email address
- Find their LinkedIn profile URL (must be linkedin.com/in/ format, NOT linkedin.com/company/)
- CRITICAL: Only include a LinkedIn URL if you found it on the website or can verify it exists.
  Do NOT guess or construct LinkedIn URLs from the person's name.

Task 2 - Technical website audit (7 dimensions):
1. Title tag: generic ("Home", "Welcome")? Too long (>60 chars)? Too short? Missing?
2. Meta description: missing entirely? Too short (<120 chars)? Too long (>160 chars)?
3. Content indexing: blog/news pages accessible? Any noindex issues? Content behind login?
4. Broken elements: dead links (href="#"), placeholder text, broken plugin outputs?
5. Social media links: present (LinkedIn, Twitter/X, Instagram) or completely missing?
6. Language consistency: mixed languages across meta tags vs content?
7. Schema markup: any structured data (JSON-LD, microdata)?

IMPORTANT: Only report findings you can VERIFY from the actual website. Be specific.

Return ONLY valid JSON:
{{
  "contact": {{
    "name": "Full Name or empty string if not found",
    "title": "Their title/position or empty string",
    "email": "company email or null",
    "linkedin_url": "linkedin.com/in/name URL or null"
  }},
  "findings": [
    {{
      "type": "title_tag|meta_description|content_indexing|broken_element|social_links|language_mismatch|schema|other",
      "severity": "high|medium|low",
      "detail": "Exact specific finding",
      "evidence": "The exact text/element from the website"
    }}
  ],
  "title_tag_text": "exact title tag text",
  "meta_description_text": "exact meta description or MISSING",
  "site_language": "en|de|mixed|other",
  "has_blog_or_news": true,
  "has_social_links": true,
  "overall_assessment": "One sentence summary of the most important finding"
}}"""


def _gemini_call(prompt: str, timeout: int = 90) -> str:
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
        raise RuntimeError(f"curl exit {result.returncode}")
    if not result.stdout.strip():
        raise RuntimeError("Empty response")
    data = json.loads(result.stdout)
    if "error" in data:
        raise RuntimeError(f"API error: {data['error'].get('message', '')[:200]}")
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No candidates in response")
    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [p["text"] for p in parts if "text" in p]
    return "\n".join(text_parts)


def _verify_linkedin(url: str) -> bool:
    """Verify a LinkedIn profile URL actually exists (not hallucinated)."""
    if not url:
        return False
    if "linkedin.com/in/" not in url:
        return False
    if "linkedin.com/company/" in url:
        return False
    full_url = url if url.startswith("http") else f"https://{url}"
    try:
        req = urllib.request.Request(full_url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; opengtm/0.1)")
        resp = urllib.request.urlopen(req, timeout=8)
        return resp.status in (200, 301, 302)
    except Exception:
        return False


def research(
    domain: str,
    company: str = "",
    industry: str = "",
    verify_linkedin: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Research a company: extract decision-maker contact + run website audit.

    Args:
        domain:          Company website domain (e.g. "example.com")
        company:         Company name (improves Gemini accuracy)
        industry:        Industry vertical (improves audit relevance)
        verify_linkedin: Whether to verify extracted LinkedIn URLs are real
        verbose:         Print progress to stdout

    Returns:
        Dict with keys: contact, findings, title_tag_text, meta_description_text,
        site_language, has_blog_or_news, has_social_links, overall_assessment
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    # Normalize domain
    if domain.startswith("www."):
        domain = domain[4:]

    comp = company or domain
    prompt = RESEARCH_PROMPT.format(
        domain=domain,
        company=comp,
        industry=industry or "general",
    )

    if verbose:
        print(f"[research] Analyzing {domain}...", flush=True)

    for attempt in range(3):
        try:
            text = _gemini_call(prompt, timeout=90)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data = json.loads(text)

            # Validate and optionally verify LinkedIn URL
            contact = data.get("contact", {})
            linkedin = contact.get("linkedin_url")
            if linkedin:
                if verify_linkedin:
                    if not _verify_linkedin(linkedin):
                        if verbose:
                            print(f"  LinkedIn URL unverified, dropping: {linkedin}", flush=True)
                        contact["linkedin_url"] = None
                else:
                    # At minimum, validate format
                    if "linkedin.com/in/" not in linkedin or "linkedin.com/company/" in linkedin:
                        contact["linkedin_url"] = None

            if verbose:
                n = len(data.get("findings", []))
                name = contact.get("name", "not found")
                print(f"  Contact: {name} | {n} findings | {data.get('overall_assessment', '')[:60]}", flush=True)

            return data

        except json.JSONDecodeError as e:
            if verbose:
                print(f"  Attempt {attempt + 1}/3 JSON parse error: {e}", flush=True)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
        except Exception as e:
            if verbose:
                print(f"  Attempt {attempt + 1}/3 error: {e}", flush=True)
            if attempt < 2:
                time.sleep(4 * (attempt + 1))

    # Return empty-but-valid structure on total failure
    return {
        "contact": {"name": "", "title": "", "email": None, "linkedin_url": None},
        "findings": [],
        "title_tag_text": "",
        "meta_description_text": "MISSING",
        "site_language": "unknown",
        "has_blog_or_news": False,
        "has_social_links": False,
        "overall_assessment": "Research failed after 3 attempts",
    }
