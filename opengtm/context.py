"""
context.py - Company context extraction via Gemini + Google Search grounding.

Ported from hyperniche/python-backend/services/context/opencontext/opencontext.py

Function:
  extract_context(url: str) -> dict

Returns company name, industry, products, services, target audience,
competitors, tone, pain points, value propositions, use cases, content themes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# =============================================================================
# Gemini client (minimal inline version - no hyperniche core dependency)
# =============================================================================

def _get_gemini_client(api_key: Optional[str] = None):
    """Build a google.generativeai client with the given key."""
    try:
        import google.generativeai as genai
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("No Gemini API key. Set GEMINI_API_KEY environment variable.")
        genai.configure(api_key=key)
        return genai
    except ImportError:
        raise ImportError(
            "google-generativeai not installed. Run: pip install google-generativeai"
        )


# =============================================================================
# Context extraction prompt (verbatim from source)
# =============================================================================

def _build_prompt(url: str, user_context: Optional[dict] = None) -> str:
    prompt = f"""Analyze the company website at {url} and extract company context.

Search Google for comprehensive information about this company and return a JSON object with these fields:

- company_name: Official company name (string)
- company_url: Company website URL (string)
- industry: Primary industry category (string)
- description: 2-3 sentence company description (string)
- products: Products offered (array of strings)
- services: Services offered (array of strings)
- target_audience: Ideal customer profile (string)
- target_audiences: Target audience segments (array of strings)
- competitors: Main competitors (array of strings)
- competitor_categories: Competing solution categories (array of strings)
- primary_region: Primary geographic market (string)
- primary_country: Primary country ISO code (string)
- primary_language: Primary language ISO code (string)
- tone: Brand voice tone (string)
- pain_points: Customer pain points (array of strings)
- value_propositions: Key value propositions (array of strings)
- use_cases: Common use cases (array of strings)
- content_themes: Content themes and topics (array of strings)
- gtm_playbook: Go-to-market strategy classification (string)
- product_type: Product type such as SaaS, API, Platform, etc. (string)

Analyze: {url}"""

    # Append target market context if provided
    if user_context and (user_context.get("country") or user_context.get("language")):
        target_country = user_context.get("country", "")
        target_language = user_context.get("language", "")
        market_parts = []
        if target_country:
            market_parts.append(f"country: {target_country}")
        if target_language:
            market_parts.append(f"language: {target_language}")
        prompt += (
            f"\n\n## TARGET MARKET CONTEXT\n"
            f"The user is targeting the following market: {', '.join(market_parts)}.\n"
            f"IMPORTANT: Tailor your analysis for this specific market:\n"
            f"- Identify competitors relevant to this market/region\n"
            f"- Describe pain points and value propositions from the perspective of customers in this market\n"
            f"- Use the target language ({target_language}) context for tone and voice analysis\n"
            f"- Set primary_country to '{target_country}' and primary_language to '{target_language}' in the response\n"
            f"- Identify target audience segments relevant to this geographic market\n"
            f"- Content themes should be relevant to this market's needs and trends"
        )

    MAX_TOTAL_CONTEXT_LENGTH = 10000
    if user_context:
        additional_context = []
        total_length = 0

        if user_context.get("system_instructions"):
            text = user_context["system_instructions"]
            if total_length + len(text) < MAX_TOTAL_CONTEXT_LENGTH:
                additional_context.append(f"\n\n## User Instructions:\n{text}")
                total_length += len(text)

        if user_context.get("client_knowledge_base"):
            text = user_context["client_knowledge_base"]
            if total_length + len(text) < MAX_TOTAL_CONTEXT_LENGTH:
                additional_context.append(f"\n\n## Known Facts About This Company:\n{text}")
                total_length += len(text)

        if user_context.get("content_instructions"):
            text = user_context["content_instructions"]
            if total_length + len(text) < MAX_TOTAL_CONTEXT_LENGTH:
                additional_context.append(f"\n\n## Content Guidelines:\n{text}")
                total_length += len(text)

        if additional_context:
            prompt += "\n\nUse this additional context provided by the user to enhance your analysis:"
            prompt += "".join(additional_context)

    return prompt


# =============================================================================
# Basic fallback (no AI)
# =============================================================================

def _basic_detection(url: str) -> dict:
    """Extract minimal context from URL when AI is unavailable."""
    if not url.startswith("http"):
        url = f"https://{url}"
    domain = urlparse(url).netloc.replace("www.", "")
    company_name = domain.split(".")[0].replace("-", " ").title()
    return {
        "company_name": company_name,
        "company_url": url,
        "industry": "",
        "description": "",
        "products": [],
        "services": [],
        "target_audience": "",
        "target_audiences": [],
        "competitors": [],
        "competitor_categories": [],
        "primary_region": "",
        "primary_country": "",
        "primary_language": "en",
        "tone": "professional",
        "pain_points": [],
        "value_propositions": [],
        "use_cases": [],
        "content_themes": [],
        "gtm_playbook": "",
        "product_type": "",
    }


# =============================================================================
# Core async extraction
# =============================================================================

async def _run_extraction(url: str, api_key: Optional[str] = None,
                          user_context: Optional[dict] = None) -> dict:
    """Call Gemini with Google Search grounding and return parsed context."""
    try:
        import google.generativeai as genai
        from google.generativeai import types as genai_types
    except ImportError:
        raise ImportError("google-generativeai not installed")

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No Gemini API key. Set GEMINI_API_KEY environment variable.")

    genai.configure(api_key=key)

    prompt = _build_prompt(url, user_context)

    # Try google-genai SDK first (newer), fall back to google-generativeai
    try:
        from google import genai as new_genai
        client = new_genai.Client(api_key=key)
        from google.genai import types as new_types

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=new_types.GenerateContentConfig(
                tools=[new_types.Tool(google_search=new_types.GoogleSearch())],
                temperature=0.3,
            ),
        )
        text = response.text
    except Exception:
        # Fallback to older SDK
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={"temperature": 0.3, "response_mime_type": "application/json"},
        )
        response = model.generate_content(prompt)
        text = response.text

    # Parse JSON from response
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object from text
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"Could not parse JSON from Gemini response: {text[:200]}")

    return data


# =============================================================================
# Public API
# =============================================================================

def extract_context(
    url: str,
    api_key: Optional[str] = None,
    user_context: Optional[dict] = None,
    fallback_on_error: bool = True,
) -> dict:
    """
    Extract company context from a URL using Gemini + Google Search grounding.

    Args:
        url: Company website URL (e.g. "https://example.com" or "example.com")
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        user_context: Optional dict with system_instructions, client_knowledge_base,
                      content_instructions, country, language fields.
        fallback_on_error: If True, returns basic domain-derived context on error.

    Returns:
        dict with keys: company_name, company_url, industry, description,
        products, services, target_audience, competitors, tone, pain_points,
        value_propositions, use_cases, content_themes, and more.

    Raises:
        ValueError: If no API key and fallback_on_error=False
        Exception: If Gemini call fails and fallback_on_error=False
    """
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.info(f"[context] Extracting context for {url}")

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not resolved_key:
        if fallback_on_error:
            logger.warning("[context] No API key, using basic detection")
            return _basic_detection(url)
        raise ValueError("No Gemini API key. Set GEMINI_API_KEY environment variable.")

    try:
        result = asyncio.run(_run_extraction(url, resolved_key, user_context))
        # Ensure required fields exist
        result.setdefault("company_url", url)
        result.setdefault("products", [])
        result.setdefault("services", [])
        result.setdefault("target_audiences", [])
        result.setdefault("competitors", [])
        result.setdefault("competitor_categories", [])
        result.setdefault("pain_points", [])
        result.setdefault("value_propositions", [])
        result.setdefault("use_cases", [])
        result.setdefault("content_themes", [])
        result.setdefault("tone", "professional")
        logger.info(f"[context] Done: {result.get('company_name', 'Unknown')}")
        return result
    except RuntimeError:
        # Already in an event loop (e.g. Jupyter) - use nest_asyncio or thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _run_extraction(url, resolved_key, user_context))
            try:
                result = future.result(timeout=120)
                result.setdefault("company_url", url)
                result.setdefault("products", [])
                result.setdefault("services", [])
                result.setdefault("pain_points", [])
                result.setdefault("value_propositions", [])
                result.setdefault("use_cases", [])
                result.setdefault("content_themes", [])
                return result
            except Exception as e:
                if fallback_on_error:
                    logger.warning(f"[context] Failed in thread: {e}, using basic detection")
                    return _basic_detection(url)
                raise
    except Exception as e:
        logger.warning(f"[context] Extraction failed: {e}")
        if fallback_on_error:
            return _basic_detection(url)
        raise
