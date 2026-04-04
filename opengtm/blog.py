"""
blog.py - AI blog article generation pipeline.

Ported from hyperniche/python-backend/services/blog/ (5-stage pipeline).

Function:
  generate_article(domain: str, keyword: str, context: dict = None) -> dict

Stages:
  1. Context + Sitemap: Extract company context, crawl sitemap for internal links
  2. Write: Generate article with Gemini + Google Search grounding
  3. Similarity: Detect content cannibalization via character shingles
  4. URL Verify: Check all links in article, remove dead ones
  5. Final: Return structured output

Returns:
  {title, meta_title, meta_description, content_html, content_markdown,
   word_count, sources, similarity_score, urls_verified, keyword, domain}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Similarity thresholds (verbatim from source)
CHAR_SIMILARITY_THRESHOLD = 0.65
SHINGLE_SIZE = 5

# Article generation system instruction (fallback)
_SYSTEM_INSTRUCTION = '''You are an expert content writer. Write like a skilled human, not AI.

HARD RULES:
- Use Google Search for all stats/facts - NEVER invent them
- Only use exact URLs from search results - NEVER guess URLs
- NEVER mention competitors by name
- NO em-dashes (—), NO "Here's how", "Key points:", or robotic phrases

FRESH DATA:
- Today is {current_date}
- Use current year data. Say "2025 report" not "recent report"

VOICE:
- Match the company's tone and voice persona exactly

CONTENT QUALITY:
- Be direct - no filler like "In today's rapidly evolving..."
- Vary section lengths (some long 500+ words, some shorter)
- Include 2+ of: decision frameworks, concrete scenarios, common mistakes, strong opinions
- Cite stats naturally inline: "According to [Source]'s report..." not boring lists

FORMATTING:
- HTML: <p>, <ul>, <li>, <ol>, <strong>
- Lists are encouraged - use them for any set of 3+ related points'''

_USER_PROMPT = '''Write a comprehensive, engaging blog article.

TOPIC: {keyword}

COMPANY CONTEXT:
{company_context}

LOCALIZATION:
- Language: {language}
- Country/Region: {country}

PARAMETERS:
- Word count: {word_count}
- Sections: 4-6 content sections
- PAA: 4 People Also Ask questions with answers
- FAQ: 5-6 FAQ questions with answers
- Takeaways: 3 key takeaways

Return valid JSON with these fields:
Headline, Teaser, Direct_Answer, Intro, Meta_Title, Meta_Description,
section_01_title, section_01_content, section_02_title, section_02_content,
section_03_title, section_03_content, section_04_title, section_04_content,
section_05_title, section_05_content (optional), section_06_title, section_06_content (optional),
key_takeaway_01, key_takeaway_02, key_takeaway_03,
paa_01_question, paa_01_answer, paa_02_question, paa_02_answer,
paa_03_question, paa_03_answer, paa_04_question, paa_04_answer,
faq_01_question, faq_01_answer, faq_02_question, faq_02_answer,
faq_03_question, faq_03_answer, faq_04_question, faq_04_answer,
faq_05_question, faq_05_answer,
Sources (list of {"title": "...", "url": "...", "description": "..."} - MANDATORY, 3-5 sources),
Search_Queries.
'''


# =============================================================================
# Company context formatter (verbatim from blog_writer.py)
# =============================================================================

def _format_company_context(context: dict) -> str:
    """Format company context dict into readable string for Gemini prompt."""
    lines = [
        f"Company: {context.get('company_name', 'Unknown')}",
        f"Industry: {context.get('industry', '')}",
        f"Target Audience: {context.get('target_audience', '')}",
        f"Tone: {context.get('tone', 'professional')}",
    ]

    description = context.get("description", "")
    if description:
        lines.append(f"About: {description}")

    products = context.get("products", [])
    if products:
        if isinstance(products, list):
            lines.append(f"Products/Services: {', '.join(str(p) for p in products)}")
        else:
            lines.append(f"Products/Services: {products}")

    pain_points = context.get("pain_points", [])
    if pain_points:
        if isinstance(pain_points, list):
            lines.append(f"Customer Pain Points: {'; '.join(str(p) for p in pain_points)}")
        else:
            lines.append(f"Customer Pain Points: {pain_points}")

    value_props = context.get("value_propositions", [])
    if value_props:
        if isinstance(value_props, list):
            lines.append(f"Value Propositions: {'; '.join(str(v) for v in value_props)}")
        else:
            lines.append(f"Value Propositions: {value_props}")

    competitors = context.get("competitors", [])
    if competitors:
        if isinstance(competitors, list):
            lines.append(f"COMPETITORS (NEVER mention these): {', '.join(str(c) for c in competitors)}")
        else:
            lines.append(f"COMPETITORS (NEVER mention these): {competitors}")

    use_cases = context.get("use_cases", [])
    if use_cases:
        if isinstance(use_cases, list):
            lines.append(f"Common Use Cases: {'; '.join(str(u) for u in use_cases)}")
        else:
            lines.append(f"Common Use Cases: {use_cases}")

    return "\n".join(lines)


# =============================================================================
# Similarity check (verbatim from similarity_check.py)
# =============================================================================

def _generate_shingles(text: str, size: int = SHINGLE_SIZE) -> Set[str]:
    """Generate character shingles from text."""
    shingles = set()
    normalized = " ".join(text.lower().split())
    for i in range(len(normalized) - size + 1):
        shingles.add(normalized[i:i + size])
    return shingles


def _jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if len(set1) == 0 and len(set2) == 0:
        return 1.0
    if len(set1) == 0 or len(set2) == 0:
        return 0.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


# Session-level batch memory for similarity checks
_batch_memory: dict = {}


def _check_similarity(keyword: str, content_text: str) -> float:
    """Check content similarity against batch memory. Returns max similarity score."""
    current_shingles = _generate_shingles(content_text)
    max_sim = 0.0

    for other_kw, other_text in _batch_memory.items():
        if other_kw == keyword:
            continue
        other_shingles = _generate_shingles(other_text)
        sim = _jaccard_similarity(current_shingles, other_shingles)
        max_sim = max(max_sim, sim)

    _batch_memory[keyword] = content_text
    return round(max_sim, 3)


# =============================================================================
# URL verification (Stage 4 logic)
# =============================================================================

async def _verify_urls_in_html(html: str) -> tuple[str, int]:
    """
    Find all URLs in HTML, verify them with HEAD requests.
    Remove dead links (4xx/5xx). Returns (cleaned_html, verified_count).
    """
    try:
        import httpx
    except ImportError:
        return html, 0

    url_pattern = re.compile(r'href=["\']([^"\']+)["\']')
    found_urls = url_pattern.findall(html)

    if not found_urls:
        return html, 0

    # Only check http/https links
    to_check = [u for u in found_urls if u.startswith("http")]
    verified = 0
    dead = set()

    semaphore = asyncio.Semaphore(5)

    async def check(url: str) -> tuple[str, bool]:
        async with semaphore:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0),
                    follow_redirects=True,
                ) as client:
                    r = await client.head(url)
                    return url, r.status_code < 400
            except Exception:
                return url, False

    results = await asyncio.gather(*[check(u) for u in to_check[:30]])

    for url, is_alive in results:
        if is_alive:
            verified += 1
        else:
            dead.add(url)
            logger.debug(f"[blog] Dead link removed: {url}")

    # Remove dead links from HTML (replace href with # and add note)
    cleaned = html
    for url in dead:
        cleaned = cleaned.replace(f'href="{url}"', 'href="#"')
        cleaned = cleaned.replace(f"href='{url}'", "href='#'")

    return cleaned, verified


# =============================================================================
# Gemini article generation (Stage 2 logic)
# =============================================================================

async def _generate_with_gemini(
    keyword: str,
    company_context: dict,
    word_count: int = 2000,
    language: str = "en",
    country: str = "United States",
    api_key: Optional[str] = None,
) -> dict:
    """Call Gemini to generate blog article. Returns raw dict."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No Gemini API key. Set GEMINI_API_KEY environment variable.")

    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system_instruction = _SYSTEM_INSTRUCTION.format(current_date=current_date)

    company_str = _format_company_context(company_context)
    prompt = _USER_PROMPT.format(
        keyword=keyword,
        company_context=company_str,
        word_count=word_count,
        language=language,
        country=country,
    )

    # Try newer google-genai SDK first (supports URL context + Google Search)
    try:
        from google import genai as new_genai
        from google.genai import types as new_types

        client = new_genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=new_types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[new_types.Tool(google_search=new_types.GoogleSearch())],
                temperature=0.3,
                max_output_tokens=16384,
            ),
        )
        text = response.text

    except Exception:
        # Fallback to older SDK
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 16384,
                "response_mime_type": "application/json",
            },
            system_instruction=system_instruction,
        )
        response = model.generate_content(prompt)
        text = response.text

    # Parse JSON
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Could not parse JSON from Gemini response: {text[:200]}")


# =============================================================================
# HTML assembly from article dict
# =============================================================================

def _assemble_html(article: dict) -> str:
    """Assemble article dict into HTML string."""
    parts = []

    headline = article.get("Headline", "")
    if headline:
        parts.append(f"<h1>{headline}</h1>")

    teaser = article.get("Teaser", "")
    if teaser:
        parts.append(f"<p class='teaser'>{teaser}</p>")

    direct_answer = article.get("Direct_Answer", "")
    if direct_answer:
        parts.append(f"<div class='direct-answer'><p>{direct_answer}</p></div>")

    intro = article.get("Intro", "")
    if intro:
        parts.append(f"<div class='intro'>{intro}</div>")

    # Content sections
    for i in range(1, 10):
        key = str(i).zfill(2)
        title = article.get(f"section_{key}_title", "")
        content = article.get(f"section_{key}_content", "")
        if title or content:
            parts.append(f"<section>")
            if title:
                parts.append(f"<h2>{title}</h2>")
            if content:
                parts.append(content)
            parts.append(f"</section>")

    # Key takeaways
    takeaways = []
    for i in range(1, 4):
        t = article.get(f"key_takeaway_{str(i).zfill(2)}", "")
        if t:
            takeaways.append(f"<li>{t}</li>")
    if takeaways:
        parts.append(f"<section class='takeaways'><h2>Key Takeaways</h2><ul>{''.join(takeaways)}</ul></section>")

    # PAA
    paa_items = []
    for i in range(1, 5):
        q = article.get(f"paa_{str(i).zfill(2)}_question", "")
        a = article.get(f"paa_{str(i).zfill(2)}_answer", "")
        if q and a:
            paa_items.append(f"<div class='paa-item'><strong>{q}</strong><p>{a}</p></div>")
    if paa_items:
        parts.append(f"<section class='paa'><h2>People Also Ask</h2>{''.join(paa_items)}</section>")

    # FAQ
    faq_items = []
    for i in range(1, 7):
        q = article.get(f"faq_{str(i).zfill(2)}_question", "")
        a = article.get(f"faq_{str(i).zfill(2)}_answer", "")
        if q and a:
            faq_items.append(f"<div class='faq-item'><strong>{q}</strong><p>{a}</p></div>")
    if faq_items:
        parts.append(f"<section class='faq'><h2>FAQ</h2>{''.join(faq_items)}</section>")

    return "\n".join(parts)


def _article_to_text(article: dict) -> str:
    """Extract all text content from article dict for similarity checking."""
    fields = ["Headline", "Teaser", "Direct_Answer", "Intro"]
    parts = [str(article.get(f, "")) for f in fields if article.get(f)]

    for i in range(1, 10):
        key = str(i).zfill(2)
        if t := article.get(f"section_{key}_title"):
            parts.append(str(t))
        if c := article.get(f"section_{key}_content"):
            parts.append(str(c))

    return " ".join(parts)


# =============================================================================
# Public API
# =============================================================================

async def _run_pipeline(
    domain: str,
    keyword: str,
    context: Optional[dict],
    word_count: int,
    language: str,
    country: str,
    api_key: Optional[str],
    verify_urls: bool,
) -> dict:
    """Full async article generation pipeline."""

    # Stage 1: Get context if not provided
    if not context:
        logger.info(f"[blog] Stage 1: extracting context for {domain}")
        from opengtm.context import extract_context
        context = extract_context(domain, api_key=api_key)
    else:
        logger.info("[blog] Stage 1: using provided context")

    # Stage 1b: Crawl sitemap for blog URL reference
    logger.info(f"[blog] Stage 1b: crawling sitemap")
    try:
        from opengtm.sitemap import crawl_sitemap
        sitemap = crawl_sitemap(domain)
        blog_urls = sitemap.get("blog_urls", [])
        logger.info(f"[blog] Found {len(blog_urls)} blog URLs for internal link reference")
    except Exception as e:
        logger.warning(f"[blog] Sitemap crawl failed: {e}")
        blog_urls = []

    # Stage 2: Generate article with Gemini
    logger.info(f"[blog] Stage 2: generating article for keyword '{keyword}'")
    article = await _generate_with_gemini(
        keyword=keyword,
        company_context=context,
        word_count=word_count,
        language=language,
        country=country,
        api_key=api_key,
    )

    # Stage 3: Similarity check
    logger.info("[blog] Stage 3: similarity check")
    article_text = _article_to_text(article)
    similarity_score = _check_similarity(keyword, article_text)
    if similarity_score >= CHAR_SIMILARITY_THRESHOLD:
        logger.warning(f"[blog] High similarity detected: {similarity_score:.1%} (threshold: {CHAR_SIMILARITY_THRESHOLD:.1%})")

    # Stage 4: Assemble HTML and verify URLs
    logger.info("[blog] Stage 4: assembling HTML")
    content_html = _assemble_html(article)
    urls_verified = 0

    if verify_urls:
        logger.info("[blog] Stage 4b: verifying URLs")
        content_html, urls_verified = await _verify_urls_in_html(content_html)

    # Stage 5: Build final output
    sources = article.get("Sources", [])
    if not isinstance(sources, list):
        sources = []

    word_count_actual = len(re.sub(r"<[^>]+>", " ", content_html).split())

    result = {
        "keyword": keyword,
        "domain": domain,
        "title": article.get("Headline", ""),
        "meta_title": article.get("Meta_Title", article.get("Headline", "")),
        "meta_description": article.get("Meta_Description", article.get("Teaser", "")),
        "teaser": article.get("Teaser", ""),
        "intro": article.get("Intro", ""),
        "content_html": content_html,
        "word_count": word_count_actual,
        "sources": sources,
        "similarity_score": similarity_score,
        "is_too_similar": similarity_score >= CHAR_SIMILARITY_THRESHOLD,
        "urls_verified": urls_verified,
        "blog_urls_available": len(blog_urls),
        "language": language,
        "country": country,
    }

    logger.info(
        f"[blog] Done: '{result['title'][:60]}' | "
        f"{result['word_count']} words | "
        f"similarity: {similarity_score:.1%}"
    )

    return result


def generate_article(
    domain: str,
    keyword: str,
    context: Optional[dict] = None,
    word_count: int = 2000,
    language: str = "en",
    country: str = "United States",
    api_key: Optional[str] = None,
    verify_urls: bool = False,
) -> dict:
    """
    Generate a blog article using Gemini + Google Search grounding.

    5-stage pipeline: context -> sitemap -> write -> similarity -> verify

    Args:
        domain: Company website domain or URL (e.g. "example.com")
        keyword: Primary SEO keyword to write about
        context: Optional company context dict (from extract_context). If not
                 provided, context is automatically extracted from domain.
        word_count: Target word count (default 2000)
        language: Language code (default "en")
        country: Target country/region (default "United States")
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        verify_urls: If True, verifies all links in article (slower)

    Returns:
        dict with keys: keyword, domain, title, meta_title, meta_description,
        teaser, intro, content_html, word_count, sources, similarity_score,
        is_too_similar, urls_verified, blog_urls_available, language, country
    """
    if not domain.startswith("http"):
        domain = f"https://{domain}"

    logger.info(f"[blog] generate_article: keyword='{keyword}' domain={domain}")

    try:
        return asyncio.run(_run_pipeline(
            domain=domain,
            keyword=keyword,
            context=context,
            word_count=word_count,
            language=language,
            country=country,
            api_key=api_key,
            verify_urls=verify_urls,
        ))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                _run_pipeline(
                    domain=domain,
                    keyword=keyword,
                    context=context,
                    word_count=word_count,
                    language=language,
                    country=country,
                    api_key=api_key,
                    verify_urls=verify_urls,
                ),
            )
            return future.result(timeout=300)
