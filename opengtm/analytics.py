"""
analytics.py - AEO (Answer Engine Optimization) health scoring and AI visibility.

Ported from hyperniche/openanalytics-main/

Two main functions:
  run_health_check(url: str) -> dict
    Runs 29 checks across 4 categories:
      - Technical SEO (16 checks)
      - Structured Data (6 checks)
      - AI Crawler Access (4 checks)
      - Authority Signals (3 checks)
    Returns tiered score, grade (A+/A/B/C/D/F), and findings list.

  run_mentions(domain: str, queries: int = 20) -> dict
    Generates unbranded/competitive/branded queries, tests with Gemini,
    returns visibility score and mention examples.

Tiered scoring caps (verbatim from source):
  Tier 0 (AI crawler access): caps overall score if crawlers are blocked
  Tier 1 (org schema): caps if missing
  Tier 2 (schema quality): adjusts further
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from . import DEFAULT_MODEL

logger = logging.getLogger(__name__)


# =============================================================================
# HTTP Fetcher
# =============================================================================

async def _fetch_page(url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Fetch a URL and return html, robots_txt, sitemap_found, response_time_ms, final_url, error."""
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx not installed. Run: pip install httpx")

    if not url.startswith("http"):
        url = f"https://{url}"

    result = {
        "html": "",
        "robots_txt": None,
        "sitemap_found": False,
        "html_response_time_ms": 0,
        "final_url": url,
        "js_rendered": False,
        "error": None,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; opengtm/1.0; +https://github.com/buildingopen/opengtm)"
        )
    }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            headers=headers,
        ) as client:
            t0 = time.time()
            resp = await client.get(url)
            result["html_response_time_ms"] = int((time.time() - t0) * 1000)
            result["html"] = resp.text
            result["final_url"] = str(resp.url)

            # Fetch robots.txt
            try:
                parsed = urlparse(result["final_url"])
                base = f"{parsed.scheme}://{parsed.netloc}"
                robots_resp = await client.get(f"{base}/robots.txt", timeout=10.0)
                if robots_resp.status_code == 200:
                    result["robots_txt"] = robots_resp.text
            except Exception:
                pass

            # Check sitemap
            try:
                parsed = urlparse(result["final_url"])
                base = f"{parsed.scheme}://{parsed.netloc}"
                sitemap_resp = await client.get(f"{base}/sitemap.xml", timeout=10.0)
                result["sitemap_found"] = sitemap_resp.status_code == 200
            except Exception:
                pass

    except Exception as e:
        result["error"] = str(e)

    return result


# =============================================================================
# AI Crawler Checks (4 checks) - ported from checks/aeo_crawler.py
# =============================================================================

def _parse_robots_txt(robots_txt: Optional[str]) -> Dict[str, Dict[str, bool]]:
    """Parse robots.txt and extract rules per user-agent."""
    if not robots_txt:
        return {}
    rules = {}
    current_agents = []
    for line in robots_txt.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.lower().startswith('user-agent:'):
            agent = line.split(':', 1)[1].strip().lower()
            current_agents = [agent]
            if agent not in rules:
                rules[agent] = {'disallow_all': False, 'allow_all': True}
        elif line.lower().startswith('disallow:') and current_agents:
            path = line.split(':', 1)[1].strip()
            for agent in current_agents:
                if agent not in rules:
                    rules[agent] = {'disallow_all': False, 'allow_all': True}
                if path == '/' or path == '/*':
                    rules[agent]['disallow_all'] = True
                    rules[agent]['allow_all'] = False
                elif path:
                    rules[agent]['allow_all'] = False
        elif line.lower().startswith('allow:') and current_agents:
            path = line.split(':', 1)[1].strip()
            for agent in current_agents:
                if agent not in rules:
                    rules[agent] = {'disallow_all': False, 'allow_all': True}
                if path == '/' or path == '/*':
                    rules[agent]['disallow_all'] = False
                    rules[agent]['allow_all'] = True
    return rules


def _is_crawler_allowed(rules: Dict[str, Dict[str, bool]], crawler_name: str) -> bool:
    if crawler_name in rules:
        return not rules[crawler_name]['disallow_all']
    if '*' in rules:
        return not rules['*']['disallow_all']
    return True


def _run_aeo_crawler_checks(robots_txt: Optional[str]) -> List[Dict[str, Any]]:
    """Run all 4 AI crawler access checks."""
    issues = []
    rules = _parse_robots_txt(robots_txt)

    # 1. GPTBot (OpenAI)
    gptbot_allowed = _is_crawler_allowed(rules, 'gptbot')
    issues.append({
        'check': 'gptbot_access', 'category': 'aeo_crawler',
        'passed': gptbot_allowed,
        'severity': 'pass' if gptbot_allowed else 'error',
        'message': 'GPTBot (OpenAI) is allowed' if gptbot_allowed else 'GPTBot is blocked in robots.txt',
        'recommendation': '' if gptbot_allowed else "Remove 'Disallow: /' for GPTBot to ensure visibility in ChatGPT",
        'score_impact': 8,
    })

    # 2. Claude-Web (Anthropic)
    claude_allowed = (
        _is_crawler_allowed(rules, 'claudebot') and
        _is_crawler_allowed(rules, 'claude-web') and
        _is_crawler_allowed(rules, 'anthropic-ai')
    )
    issues.append({
        'check': 'claude_access', 'category': 'aeo_crawler',
        'passed': claude_allowed,
        'severity': 'pass' if claude_allowed else 'warning',
        'message': 'Claude-Web (Anthropic) is allowed' if claude_allowed else 'Claude-Web/Anthropic crawler is blocked',
        'recommendation': '' if claude_allowed else "Remove blocks for ClaudeBot, Claude-Web, and Anthropic-AI",
        'score_impact': 5,
    })

    # 3. PerplexityBot
    perplexity_allowed = _is_crawler_allowed(rules, 'perplexitybot')
    issues.append({
        'check': 'perplexitybot_access', 'category': 'aeo_crawler',
        'passed': perplexity_allowed,
        'severity': 'pass' if perplexity_allowed else 'warning',
        'message': 'PerplexityBot is allowed' if perplexity_allowed else 'PerplexityBot is blocked in robots.txt',
        'recommendation': '' if perplexity_allowed else "Remove 'Disallow: /' for PerplexityBot",
        'score_impact': 5,
    })

    # 4. CCBot (Common Crawl)
    ccbot_allowed = _is_crawler_allowed(rules, 'ccbot')
    issues.append({
        'check': 'ccbot_access', 'category': 'aeo_crawler',
        'passed': ccbot_allowed,
        'severity': 'pass' if ccbot_allowed else 'notice',
        'message': 'CCBot (Common Crawl) is allowed' if ccbot_allowed else 'CCBot (Common Crawl) is blocked',
        'recommendation': '' if ccbot_allowed else "Consider allowing CCBot - Common Crawl data trains many LLMs",
        'score_impact': 4,
    })

    return issues


# =============================================================================
# Technical SEO Checks (16 checks) - ported from checks/technical.py
# =============================================================================

def _run_technical_checks(
    soup, final_url: str, sitemap_found: bool = False, response_time_ms: int = 0
) -> List[Dict[str, Any]]:
    """Run all 16 technical SEO checks."""
    issues = []

    # 1. Title tag
    title = soup.find('title')
    title_text = title.text.strip() if title else ""
    title_length = len(title_text)
    if not title_text:
        issues.append({'check': 'title_tag', 'category': 'technical', 'passed': False,
                       'severity': 'error', 'message': 'Missing title tag',
                       'recommendation': 'Add a descriptive title tag (30-65 characters)', 'score_impact': 10})
    elif title_length < 30:
        issues.append({'check': 'title_tag', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': f'Title too short ({title_length} chars)',
                       'recommendation': 'Expand title to 30-65 characters for better visibility', 'score_impact': 10})
    elif title_length > 65:
        issues.append({'check': 'title_tag', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': f'Title too long ({title_length} chars)',
                       'recommendation': 'Shorten title to 30-65 characters to avoid truncation', 'score_impact': 10})
    else:
        issues.append({'check': 'title_tag', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'Good title length ({title_length} chars)',
                       'recommendation': '', 'score_impact': 10})

    # 2. Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    meta_text = str(meta_desc.get('content', '')).strip() if meta_desc else ""
    meta_length = len(meta_text)
    if not meta_text:
        issues.append({'check': 'meta_description', 'category': 'technical', 'passed': False,
                       'severity': 'error', 'message': 'Missing meta description',
                       'recommendation': 'Add a meta description (120-160 characters)', 'score_impact': 10})
    elif meta_length < 120:
        issues.append({'check': 'meta_description', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': f'Meta description too short ({meta_length} chars)',
                       'recommendation': 'Expand to 120-160 characters for better SERP display', 'score_impact': 10})
    elif meta_length > 160:
        issues.append({'check': 'meta_description', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': f'Meta description too long ({meta_length} chars)',
                       'recommendation': 'Shorten to 120-160 characters to avoid truncation', 'score_impact': 10})
    else:
        issues.append({'check': 'meta_description', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'Good meta description ({meta_length} chars)',
                       'recommendation': '', 'score_impact': 10})

    # 3. H1 tag
    h1_tags = soup.find_all('h1')
    h1_count = len(h1_tags)
    if h1_count == 0:
        issues.append({'check': 'h1_tag', 'category': 'technical', 'passed': False,
                       'severity': 'error', 'message': 'No H1 tag found',
                       'recommendation': 'Add exactly one H1 tag to clearly define page topic', 'score_impact': 10})
    elif h1_count > 1:
        issues.append({'check': 'h1_tag', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': f'Multiple H1 tags ({h1_count})',
                       'recommendation': 'Use only one H1 tag per page for clarity', 'score_impact': 10})
    else:
        h1_text = h1_tags[0].get_text(strip=True)[:50]
        issues.append({'check': 'h1_tag', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'Single H1 tag: "{h1_text}..."',
                       'recommendation': '', 'score_impact': 10})

    # 4. Heading structure
    h2_count = len(soup.find_all('h2'))
    h3_count = len(soup.find_all('h3'))
    h4_count = len(soup.find_all('h4'))
    if h2_count == 0:
        issues.append({'check': 'heading_structure', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': 'No H2 tags found',
                       'recommendation': 'Add H2 tags to structure your content', 'score_impact': 5})
    else:
        issues.append({'check': 'heading_structure', 'category': 'technical', 'passed': True,
                       'severity': 'pass',
                       'message': f'Good structure: {h1_count} H1, {h2_count} H2, {h3_count} H3, {h4_count} H4',
                       'recommendation': '', 'score_impact': 5})

    # 5. Image alt text
    images = soup.find_all('img')
    total_images = len(images)
    images_with_alt_attr = len([img for img in images if img.get('alt') is not None])
    images_with_descriptive_alt = len([img for img in images if img.get('alt')])
    images_without_alt = total_images - images_with_alt_attr
    if total_images == 0:
        issues.append({'check': 'image_alt_text', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': 'No images on page', 'recommendation': '', 'score_impact': 10})
    elif images_without_alt > 0:
        alt_pct = (images_with_alt_attr / total_images) * 100
        issues.append({'check': 'image_alt_text', 'category': 'technical', 'passed': False,
                       'severity': 'error',
                       'message': f'{images_without_alt}/{total_images} images missing alt attribute ({alt_pct:.0f}% have alt)',
                       'recommendation': f'Add alt attribute to all {images_without_alt} images', 'score_impact': 10})
    elif images_with_descriptive_alt == 0:
        issues.append({'check': 'image_alt_text', 'category': 'technical', 'passed': False,
                       'severity': 'warning',
                       'message': f'All {total_images} images have empty alt="" (no descriptive text)',
                       'recommendation': 'Add descriptive alt text to content images', 'score_impact': 10})
    elif images_with_descriptive_alt < total_images * 0.5:
        desc_pct = (images_with_descriptive_alt / total_images) * 100
        issues.append({'check': 'image_alt_text', 'category': 'technical', 'passed': False,
                       'severity': 'notice',
                       'message': f'Only {images_with_descriptive_alt}/{total_images} images have descriptive alt text ({desc_pct:.0f}%)',
                       'recommendation': 'Add descriptive alt text to more images', 'score_impact': 10})
    else:
        desc_pct = (images_with_descriptive_alt / total_images) * 100
        issues.append({'check': 'image_alt_text', 'category': 'technical', 'passed': True,
                       'severity': 'pass',
                       'message': f'{images_with_descriptive_alt}/{total_images} images have descriptive alt text ({desc_pct:.0f}%)',
                       'recommendation': '', 'score_impact': 10})

    # 6. Mobile viewport
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if not viewport:
        issues.append({'check': 'mobile_viewport', 'category': 'technical', 'passed': False,
                       'severity': 'error', 'message': 'No viewport meta tag',
                       'recommendation': 'Add <meta name="viewport" content="width=device-width, initial-scale=1">',
                       'score_impact': 10})
    else:
        viewport_content = viewport.get('content', '')
        if 'width=device-width' in viewport_content:
            issues.append({'check': 'mobile_viewport', 'category': 'technical', 'passed': True,
                           'severity': 'pass', 'message': 'Viewport configured correctly',
                           'recommendation': '', 'score_impact': 10})
        else:
            issues.append({'check': 'mobile_viewport', 'category': 'technical', 'passed': False,
                           'severity': 'warning', 'message': 'Viewport tag present but not optimal',
                           'recommendation': 'Update viewport to include width=device-width', 'score_impact': 10})

    # 7. Structured data presence
    schema_scripts = soup.find_all('script', attrs={'type': 'application/ld+json'})
    schema_count = len(schema_scripts)
    if schema_count == 0:
        issues.append({'check': 'structured_data_presence', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': 'No structured data (schema.org) found',
                       'recommendation': 'Add JSON-LD structured data to help AI understand your content',
                       'score_impact': 10})
    else:
        issues.append({'check': 'structured_data_presence', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'{schema_count} structured data blocks found',
                       'recommendation': '', 'score_impact': 10})

    # 8. HTTPS
    is_https = final_url.startswith('https://')
    issues.append({'check': 'https', 'category': 'technical', 'passed': is_https,
                   'severity': 'pass' if is_https else 'error',
                   'message': 'Site using HTTPS' if is_https else 'Site not using HTTPS',
                   'recommendation': '' if is_https else 'Enable HTTPS for security and SEO benefits',
                   'score_impact': 10})

    # 9. Canonical tag
    canonical = soup.find('link', attrs={'rel': 'canonical'})
    if not canonical:
        issues.append({'check': 'canonical_tag', 'category': 'technical', 'passed': False,
                       'severity': 'notice', 'message': 'No canonical tag',
                       'recommendation': 'Add canonical tag to prevent duplicate content issues', 'score_impact': 5})
    else:
        canonical_href = canonical.get('href', '').strip()
        def norm(u): return u.rstrip('/').lower().replace('http://', 'https://')
        if not canonical_href:
            issues.append({'check': 'canonical_tag', 'category': 'technical', 'passed': False,
                           'severity': 'warning', 'message': 'Canonical tag has empty href',
                           'recommendation': 'Set canonical href to the preferred URL', 'score_impact': 5})
        elif norm(canonical_href) == norm(final_url):
            issues.append({'check': 'canonical_tag', 'category': 'technical', 'passed': True,
                           'severity': 'pass', 'message': 'Canonical tag is self-referencing (correct)',
                           'recommendation': '', 'score_impact': 5})
        else:
            short = canonical_href[:60] + ('...' if len(canonical_href) > 60 else '')
            issues.append({'check': 'canonical_tag', 'category': 'technical', 'passed': False,
                           'severity': 'notice', 'message': f'Canonical points to different URL: {short}',
                           'recommendation': 'Verify canonical URL is correct', 'score_impact': 5})

    # 10. Robots meta
    robots_meta = soup.find('meta', attrs={'name': 'robots'})
    googlebot_meta = soup.find('meta', attrs={'name': 'googlebot'})
    noindex_found = False
    nofollow_found = False
    for meta in [robots_meta, googlebot_meta]:
        if meta:
            content = (meta.get('content') or '').lower()
            if 'noindex' in content:
                noindex_found = True
            if 'nofollow' in content:
                nofollow_found = True
    if noindex_found:
        issues.append({'check': 'robots_meta', 'category': 'technical', 'passed': False,
                       'severity': 'error', 'message': 'Page has noindex directive - blocked from search engines',
                       'recommendation': 'Remove noindex directive if this page should be indexed', 'score_impact': 15})
    elif nofollow_found:
        issues.append({'check': 'robots_meta', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': 'Page has nofollow directive - links not followed by crawlers',
                       'recommendation': 'Consider removing nofollow if you want crawlers to follow links', 'score_impact': 5})
    else:
        issues.append({'check': 'robots_meta', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': 'No indexing restrictions found',
                       'recommendation': '', 'score_impact': 15})

    # 11. Content word count
    body_text = soup.get_text(separator=' ', strip=True)
    word_count = len(body_text.split())
    if word_count < 300:
        issues.append({'check': 'content_word_count', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': f'Low word count ({word_count} words)',
                       'recommendation': 'Add more comprehensive content (aim for 500+ words)', 'score_impact': 10})
    elif word_count < 500:
        issues.append({'check': 'content_word_count', 'category': 'technical', 'passed': False,
                       'severity': 'notice', 'message': f'Moderate word count ({word_count} words)',
                       'recommendation': 'Consider expanding to 500+ words for better ranking', 'score_impact': 10})
    else:
        issues.append({'check': 'content_word_count', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'Good content length ({word_count} words)',
                       'recommendation': '', 'score_impact': 10})

    # 12. Internal linking
    all_links = soup.find_all('a', href=True)
    domain = urlparse(final_url).netloc

    def is_internal(href: str) -> bool:
        if not href:
            return False
        if href.startswith(('javascript:', 'mailto:', 'tel:', 'data:')):
            return False
        if href.startswith('#'):
            return True
        if href.startswith('/') and not href.startswith('//'):
            return True
        try:
            p = urlparse(href)
            if not p.netloc:
                return True
            return domain in p.netloc or p.netloc in domain
        except Exception:
            return False

    internal_count = sum(1 for link in all_links if is_internal(link.get('href', '')))
    external_count = len(all_links) - internal_count
    if internal_count < 3:
        issues.append({'check': 'internal_linking', 'category': 'technical', 'passed': False,
                       'severity': 'notice', 'message': f'Only {internal_count} internal links',
                       'recommendation': 'Add more internal links (5-10) to improve site structure', 'score_impact': 5})
    else:
        issues.append({'check': 'internal_linking', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'{internal_count} internal links, {external_count} external',
                       'recommendation': '', 'score_impact': 5})

    # 13. Language tag
    html_tag = soup.find('html')
    lang_attr = html_tag.get('lang') if html_tag else None
    if not lang_attr:
        issues.append({'check': 'language_tag', 'category': 'technical', 'passed': False,
                       'severity': 'notice', 'message': 'No lang attribute on <html> tag',
                       'recommendation': "Add lang='en' (or appropriate language) to <html> tag", 'score_impact': 5})
    else:
        issues.append({'check': 'language_tag', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': f'Language set to: {lang_attr}',
                       'recommendation': '', 'score_impact': 5})

    # 14. Sitemap.xml
    if sitemap_found:
        issues.append({'check': 'sitemap_xml', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': 'Sitemap.xml found', 'recommendation': '', 'score_impact': 5})
    else:
        issues.append({'check': 'sitemap_xml', 'category': 'technical', 'passed': False,
                       'severity': 'warning', 'message': 'No sitemap.xml found',
                       'recommendation': 'Add sitemap.xml to help search engines and AI crawlers discover content',
                       'score_impact': 5})

    # 15. Response time
    if response_time_ms > 0:
        if response_time_ms < 500:
            issues.append({'check': 'response_time', 'category': 'technical', 'passed': True,
                           'severity': 'pass', 'message': f'Fast response time ({response_time_ms}ms)',
                           'recommendation': '', 'score_impact': 5})
        elif response_time_ms < 1000:
            issues.append({'check': 'response_time', 'category': 'technical', 'passed': False,
                           'severity': 'notice', 'message': f'Moderate response time ({response_time_ms}ms)',
                           'recommendation': 'Consider optimizing for sub-500ms response time', 'score_impact': 5})
        elif response_time_ms < 2000:
            issues.append({'check': 'response_time', 'category': 'technical', 'passed': False,
                           'severity': 'warning', 'message': f'Slow response time ({response_time_ms}ms)',
                           'recommendation': 'Optimize server response time to under 1 second', 'score_impact': 5})
        else:
            issues.append({'check': 'response_time', 'category': 'technical', 'passed': False,
                           'severity': 'error', 'message': f'Very slow response time ({response_time_ms}ms)',
                           'recommendation': 'Critical: response time over 2 seconds significantly impacts SEO',
                           'score_impact': 5})

    # 16. Hreflang tags
    hreflang_tags = soup.find_all('link', attrs={'rel': 'alternate', 'hreflang': True})
    if len(hreflang_tags) > 0:
        langs = [tag.get('hreflang', '') for tag in hreflang_tags]
        has_x_default = 'x-default' in langs
        display_langs = langs[:5]
        more_text = f" (+{len(langs) - 5} more)" if len(langs) > 5 else ""
        if has_x_default:
            issues.append({'check': 'hreflang_tags', 'category': 'technical', 'passed': True,
                           'severity': 'pass',
                           'message': f'Hreflang configured for {len(langs)} versions including x-default: {", ".join(display_langs)}{more_text}',
                           'recommendation': '', 'score_impact': 5})
        else:
            issues.append({'check': 'hreflang_tags', 'category': 'technical', 'passed': False,
                           'severity': 'notice',
                           'message': f'Hreflang present ({len(langs)} versions) but missing x-default: {", ".join(display_langs)}{more_text}',
                           'recommendation': 'Add x-default hreflang to specify the default/fallback page',
                           'score_impact': 5})
    else:
        issues.append({'check': 'hreflang_tags', 'category': 'technical', 'passed': True,
                       'severity': 'pass', 'message': 'No hreflang tags (single-language site)',
                       'recommendation': '', 'score_impact': 5})

    return issues


# =============================================================================
# Structured Data Checks (6 checks) - ported from checks/structured_data.py
# =============================================================================

def _extract_schema_data(soup) -> Tuple[List[str], List[Dict], Optional[Dict]]:
    """Extract all JSON-LD structured data from page."""
    schema_scripts = soup.find_all('script', attrs={'type': 'application/ld+json'})
    schema_types = []
    all_schemas = []
    org_schema = None

    for script in schema_scripts:
        try:
            data = json.loads(script.string.strip())
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]
            elif isinstance(data, list):
                items = data
            else:
                items = [data]

            for item in items:
                if isinstance(item, dict):
                    all_schemas.append(item)
                    schema_type = item.get("@type")
                    if schema_type:
                        if isinstance(schema_type, list):
                            schema_types.extend(schema_type)
                        else:
                            schema_types.append(schema_type)
                    if schema_type in ["Organization", "LocalBusiness", "Corporation", "Company"]:
                        if org_schema is None:
                            org_schema = item
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    schema_types = list(dict.fromkeys(schema_types))
    return (schema_types, all_schemas, org_schema)


def _calc_org_completeness(org_schema: Optional[Dict]) -> float:
    if not org_schema:
        return 0.0
    score = 0.0
    if org_schema.get("name"):
        score += 0.2
    if org_schema.get("url"):
        score += 0.2
    if org_schema.get("logo"):
        score += 0.15
    if org_schema.get("description"):
        score += 0.15
    if org_schema.get("sameAs") and len(org_schema.get("sameAs", [])) > 0:
        score += 0.1
    if org_schema.get("address"):
        score += 0.1
    if org_schema.get("contactPoint"):
        score += 0.05
    if org_schema.get("foundingDate"):
        score += 0.025
    if org_schema.get("founder") or org_schema.get("founders"):
        score += 0.025
    return min(1.0, score)


def _count_same_as(org_schema: Optional[Dict]) -> int:
    if not org_schema:
        return 0
    same_as = org_schema.get("sameAs", [])
    if isinstance(same_as, str):
        return 1
    elif isinstance(same_as, list):
        return len(same_as)
    return 0


def _check_freshness(soup, all_schemas: List[Dict]) -> Dict[str, Any]:
    has_date_published = False
    has_date_modified = False
    dates_found = []
    for schema in all_schemas:
        schema_type = schema.get("@type", "")
        if schema_type in ["Article", "BlogPosting", "NewsArticle", "TechArticle", "HowTo", "WebPage"]:
            if schema.get("datePublished"):
                has_date_published = True
                dates_found.append("schema:datePublished")
            if schema.get("dateModified"):
                has_date_modified = True
                dates_found.append("schema:dateModified")
    time_elements = soup.find_all('time', attrs={'datetime': True})
    if time_elements and not has_date_published:
        has_date_published = True
        dates_found.append("html:time")
    return {'has_date_published': has_date_published, 'has_date_modified': has_date_modified, 'dates_found': dates_found}


SCHEMA_REQUIRED_FIELDS = {
    'Organization': ['name', 'url'], 'LocalBusiness': ['name', 'address'],
    'Article': ['headline', 'author', 'datePublished'],
    'BlogPosting': ['headline', 'author', 'datePublished'],
    'NewsArticle': ['headline', 'author', 'datePublished'],
    'Product': ['name'], 'FAQPage': ['mainEntity'], 'HowTo': ['name', 'step'],
    'Recipe': ['name', 'recipeIngredient', 'recipeInstructions'],
    'Event': ['name', 'startDate', 'location'], 'Person': ['name'],
    'WebPage': ['name'], 'WebSite': ['name', 'url'],
}


def _run_structured_data_checks(soup) -> List[Dict[str, Any]]:
    """Run all 6 structured data depth checks."""
    issues = []
    schema_types, all_schemas, org_schema = _extract_schema_data(soup)

    # 1. Organization schema completeness
    completeness = _calc_org_completeness(org_schema)
    if org_schema is None:
        issues.append({'check': 'org_schema_completeness', 'category': 'structured_data', 'passed': False,
                       'severity': 'warning', 'message': 'No Organization schema found',
                       'recommendation': 'Add Organization schema with name, url, logo, description, and sameAs links',
                       'score_impact': 10})
    elif completeness < 0.5:
        issues.append({'check': 'org_schema_completeness', 'category': 'structured_data', 'passed': False,
                       'severity': 'warning', 'message': f'Organization schema incomplete ({completeness*100:.0f}%)',
                       'recommendation': 'Add missing fields: logo, description, sameAs links to Wikipedia/LinkedIn',
                       'score_impact': 10})
    else:
        issues.append({'check': 'org_schema_completeness', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass', 'message': f'Organization schema complete ({completeness*100:.0f}%)',
                       'recommendation': '', 'score_impact': 10})

    # 2. FAQ schema
    has_faq = any(t in ["FAQPage", "Question"] for t in schema_types)
    if not has_faq:
        issues.append({'check': 'faq_schema', 'category': 'structured_data', 'passed': False,
                       'severity': 'notice', 'message': 'No FAQ schema found',
                       'recommendation': 'Add FAQPage schema to help AI extract Q&A content', 'score_impact': 5})
    else:
        issues.append({'check': 'faq_schema', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass', 'message': 'FAQ schema present', 'recommendation': '', 'score_impact': 5})

    # 3. Content schema (HowTo/Article)
    content_schemas = ["HowTo", "Article", "BlogPosting", "NewsArticle", "TechArticle"]
    has_content_schema = any(t in content_schemas for t in schema_types)
    if not has_content_schema:
        issues.append({'check': 'content_schema', 'category': 'structured_data', 'passed': False,
                       'severity': 'notice', 'message': 'No content schema (HowTo/Article) found',
                       'recommendation': 'Add Article or HowTo schema for content-rich pages', 'score_impact': 5})
    else:
        found_types = [t for t in schema_types if t in content_schemas]
        issues.append({'check': 'content_schema', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass', 'message': f'Content schema present: {", ".join(found_types)}',
                       'recommendation': '', 'score_impact': 5})

    # 4. sameAs links
    same_as_count = _count_same_as(org_schema)
    if same_as_count == 0:
        issues.append({'check': 'sameas_links', 'category': 'structured_data', 'passed': False,
                       'severity': 'warning', 'message': 'No sameAs links in Organization schema',
                       'recommendation': 'Add sameAs links to LinkedIn, Wikipedia, Twitter, Crunchbase',
                       'score_impact': 5})
    elif same_as_count < 3:
        issues.append({'check': 'sameas_links', 'category': 'structured_data', 'passed': False,
                       'severity': 'notice', 'message': f'Only {same_as_count} sameAs link(s)',
                       'recommendation': 'Add more sameAs links (aim for 3-5) to strengthen entity recognition',
                       'score_impact': 5})
    else:
        issues.append({'check': 'sameas_links', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass', 'message': f'{same_as_count} sameAs links found',
                       'recommendation': '', 'score_impact': 5})

    # 5. Content freshness
    freshness = _check_freshness(soup, all_schemas)
    if not freshness['has_date_published'] and not freshness['has_date_modified']:
        issues.append({'check': 'content_freshness', 'category': 'structured_data', 'passed': False,
                       'severity': 'notice', 'message': 'No content dates found (datePublished/dateModified)',
                       'recommendation': 'Add datePublished and dateModified to Article schema', 'score_impact': 5})
    elif not freshness['has_date_modified']:
        issues.append({'check': 'content_freshness', 'category': 'structured_data', 'passed': False,
                       'severity': 'notice',
                       'message': f'Has datePublished but no dateModified ({", ".join(freshness["dates_found"])})',
                       'recommendation': 'Add dateModified to show content is maintained and up-to-date',
                       'score_impact': 5})
    else:
        issues.append({'check': 'content_freshness', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass',
                       'message': f'Content dates present ({", ".join(freshness["dates_found"])})',
                       'recommendation': '', 'score_impact': 5})

    # 6. JSON-LD validation
    validation_errors = []
    schemas_checked = 0
    for schema in all_schemas:
        schema_type = schema.get('@type', 'Unknown')
        if isinstance(schema_type, list):
            schema_type = schema_type[0] if schema_type else 'Unknown'
        if schema_type in SCHEMA_REQUIRED_FIELDS:
            schemas_checked += 1
            required = SCHEMA_REQUIRED_FIELDS[schema_type]
            missing = [f for f in required if f not in schema or not schema[f]]
            if missing:
                validation_errors.append({'type': schema_type, 'missing_fields': missing})

    if schemas_checked == 0:
        issues.append({'check': 'jsonld_validation', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass', 'message': 'No validatable schemas found',
                       'recommendation': '', 'score_impact': 5})
    elif validation_errors:
        error_msgs = [f"{e['type']} missing: {', '.join(e['missing_fields'])}" for e in validation_errors[:3]]
        issues.append({'check': 'jsonld_validation', 'category': 'structured_data', 'passed': False,
                       'severity': 'warning',
                       'message': f"Schema validation errors ({len(validation_errors)}): {'; '.join(error_msgs)}",
                       'recommendation': 'Add missing required fields to fix Rich Results eligibility',
                       'score_impact': 5})
    else:
        issues.append({'check': 'jsonld_validation', 'category': 'structured_data', 'passed': True,
                       'severity': 'pass', 'message': f"All {schemas_checked} schemas have required fields",
                       'recommendation': '', 'score_impact': 5})

    return issues


# =============================================================================
# Authority Checks (3 checks) - ported from checks/authority.py
# =============================================================================

def _find_link_patterns(soup, patterns: List[str]) -> bool:
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '').lower()
        for pattern in patterns:
            if re.search(pattern, href):
                return True
    return False


def _extract_social_links(soup, same_as_urls: List[str] = None) -> Set[str]:
    social_patterns = {
        'linkedin': r'linkedin\.com', 'twitter': r'(twitter\.com|x\.com)',
        'facebook': r'facebook\.com', 'instagram': r'instagram\.com',
        'youtube': r'youtube\.com', 'github': r'github\.com', 'tiktok': r'tiktok\.com',
    }
    found = set()
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').lower()
        for platform, pattern in social_patterns.items():
            if re.search(pattern, href):
                found.add(platform)
    if same_as_urls:
        for url in same_as_urls:
            url_lower = url.lower()
            for platform, pattern in social_patterns.items():
                if re.search(pattern, url_lower):
                    found.add(platform)
    return found


def _has_contact_info(soup) -> Dict[str, bool]:
    text = soup.get_text(separator=' ', strip=True)
    has_email = bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text))
    phone_patterns = [
        r'(?:tel|phone|call|fax|mobile)[\s:]+[\+\d\s\-\(\)\.]{10,}',
        r'\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
        r'(?:1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    ]
    has_phone = any(re.search(p, text, re.IGNORECASE) for p in phone_patterns)
    address_patterns = [
        r'\d+\s+[\w\s]+(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|way|drive|dr)\b',
        r'(?:floor|suite|ste|unit)\s*#?\s*\d+',
        r'\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b',
        r'\b\d{5}\s+[A-Za-z]+\b',
    ]
    has_address = any(re.search(p, text, re.IGNORECASE) for p in address_patterns)
    return {'has_email': has_email, 'has_phone': has_phone, 'has_address': has_address}


def _run_authority_checks(soup, same_as_urls: List[str] = None) -> List[Dict[str, Any]]:
    """Run all 3 authority/E-E-A-T signal checks."""
    issues = []

    # 1. About page
    about_patterns = [r'/about($|/|-us|_us)', r'/company($|/)', r'/who-we-are', r'/our-story',
                      r'/ueber-uns', r'/wir-sind']
    has_about = _find_link_patterns(soup, about_patterns)
    issues.append({'check': 'about_page', 'category': 'authority',
                   'passed': has_about,
                   'severity': 'pass' if has_about else 'notice',
                   'message': 'About page link found' if has_about else 'No About page link found',
                   'recommendation': '' if has_about else 'Add a visible link to your About/Company page for trust signals',
                   'score_impact': 5})

    # 2. Contact information
    contact_info = _has_contact_info(soup)
    has_any_contact = contact_info['has_email'] or contact_info['has_phone'] or contact_info['has_address']
    contact_patterns = [r'/contact($|/|-us)', r'/kontakt', r'/get-in-touch']
    has_contact_page = _find_link_patterns(soup, contact_patterns)
    if not has_any_contact and not has_contact_page:
        issues.append({'check': 'contact_info', 'category': 'authority', 'passed': False,
                       'severity': 'warning', 'message': 'No contact information found',
                       'recommendation': 'Add visible email, phone, or address for trust and local SEO', 'score_impact': 5})
    else:
        contact_types = []
        if contact_info['has_email']: contact_types.append('email')
        if contact_info['has_phone']: contact_types.append('phone')
        if contact_info['has_address']: contact_types.append('address')
        if has_contact_page: contact_types.append('contact page')
        issues.append({'check': 'contact_info', 'category': 'authority', 'passed': True,
                       'severity': 'pass', 'message': f'Contact info found: {", ".join(contact_types)}',
                       'recommendation': '', 'score_impact': 5})

    # 3. Social proof links
    social_links = _extract_social_links(soup, same_as_urls=same_as_urls)
    key_socials = {'linkedin', 'twitter'}
    has_key_socials = len(social_links.intersection(key_socials)) > 0
    if len(social_links) == 0:
        issues.append({'check': 'social_proof_links', 'category': 'authority', 'passed': False,
                       'severity': 'warning', 'message': 'No social media links found',
                       'recommendation': 'Add links to LinkedIn, Twitter/X for social proof and entity recognition',
                       'score_impact': 4})
    elif not has_key_socials:
        issues.append({'check': 'social_proof_links', 'category': 'authority', 'passed': False,
                       'severity': 'notice',
                       'message': f'Found social links ({", ".join(social_links)}) but missing LinkedIn/Twitter',
                       'recommendation': 'Add LinkedIn and Twitter for stronger business authority signals',
                       'score_impact': 4})
    else:
        issues.append({'check': 'social_proof_links', 'category': 'authority', 'passed': True,
                       'severity': 'pass',
                       'message': f'Social proof links found: {", ".join(sorted(social_links))}',
                       'recommendation': '', 'score_impact': 4})

    return issues


# =============================================================================
# Tiered Scoring - ported from scoring.py (verbatim logic)
# =============================================================================

def _evaluate_tier0_critical(issues: List[Dict[str, Any]]) -> Tuple[bool, int, str]:
    ai_crawler_checks = ['gptbot_access', 'claude_access', 'perplexitybot_access', 'ccbot_access']
    blocked_crawlers = [i.get('check') for i in issues
                        if i.get('check') in ai_crawler_checks and not i.get('passed', False)]
    if len(blocked_crawlers) >= 4:
        return (False, 10, "Blocks all AI crawlers - invisible to AI")
    if len(blocked_crawlers) >= 3:
        return (False, 25, f"Blocks most AI crawlers ({len(blocked_crawlers)}/4)")
    for issue in issues:
        if issue.get('check') == 'robots_meta':
            message = issue.get('message', '').lower()
            if 'noindex' in message and not issue.get('passed', False):
                return (False, 5, "Has noindex - won't be indexed by AI")
    return (True, 100, "AI can access site")


def _evaluate_tier1_essential(issues: List[Dict[str, Any]]) -> Tuple[bool, int, str]:
    has_org_schema = False
    has_title = False
    has_https = False
    for issue in issues:
        check = issue.get('check', '')
        passed = issue.get('passed', False)
        message = issue.get('message', '').lower()
        if check == 'org_schema_completeness':
            if 'no organization schema' not in message:
                has_org_schema = True
        elif check == 'title_tag':
            if 'missing title' not in message:
                has_title = True
        elif check == 'https' and passed:
            has_https = True
    missing = []
    if not has_org_schema: missing.append("Organization schema")
    if not has_title: missing.append("title tag")
    if not has_https: missing.append("HTTPS")
    if not has_org_schema:
        return (False, 45, "Missing Organization schema - AI can't identify entity")
    if missing:
        return (False, 55, f"Missing essentials: {', '.join(missing)}")
    return (True, 100, "Has essential elements")


def _evaluate_tier2_important(issues: List[Dict[str, Any]]) -> Tuple[bool, int, str]:
    org_complete = False
    org_partial = False
    has_meta_desc = False
    good_content = False
    has_sameas = False
    for issue in issues:
        check = issue.get('check', '')
        passed = issue.get('passed', False)
        message = issue.get('message', '')
        if check == 'org_schema_completeness':
            if 'no organization schema' not in message.lower():
                org_partial = True
                match = re.search(r'(\d+)%', message or '0%')
                if match and int(match.group(1)) >= 70:
                    org_complete = True
        elif check == 'meta_description':
            if 'missing' not in message.lower():
                has_meta_desc = True
        elif check == 'content_word_count' and passed:
            good_content = True
        elif check == 'sameas_links' and passed:
            has_sameas = True
    important_issues = []
    minor_issues = []
    if org_partial and not org_complete:
        important_issues.append("incomplete Organization schema")
    if not has_sameas:
        important_issues.append("no sameAs links")
    if not has_meta_desc:
        minor_issues.append("no meta description")
    if not good_content:
        minor_issues.append("thin content")
    if len(important_issues) >= 2:
        return (False, 75, f"Issues: {', '.join(important_issues)}")
    elif len(important_issues) == 1:
        return (False, 85, f"Issue: {important_issues[0]}")
    elif len(minor_issues) >= 2:
        return (False, 90, f"Minor issues: {', '.join(minor_issues)}")
    elif len(minor_issues) == 1:
        return (False, 95, f"Minor: {minor_issues[0]}")
    return (True, 100, "Excellent AEO optimization")


def _calculate_base_score(issues: List[Dict[str, Any]]) -> float:
    total_impact = 0
    earned_impact = 0
    for issue in issues:
        impact = issue.get('score_impact', 5)
        total_impact += impact
        if issue.get('passed', False):
            earned_impact += impact
        elif issue.get('severity') == 'notice':
            earned_impact += impact * 0.7
        elif issue.get('severity') == 'warning':
            earned_impact += impact * 0.3
    if total_impact > 0:
        return (earned_impact / total_impact) * 100
    return 0.0


def _calculate_tiered_score(issues: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    tier0_passed, tier0_cap, tier0_reason = _evaluate_tier0_critical(issues)
    tier1_passed, tier1_cap, tier1_reason = _evaluate_tier1_essential(issues)
    tier2_passed, tier2_cap, tier2_reason = _evaluate_tier2_important(issues)
    base_score = _calculate_base_score(issues)
    final_score = min(tier0_cap, tier1_cap, tier2_cap, base_score)
    limiting_tier = "base"
    limiting_reason = "Check performance"
    if tier0_cap <= final_score + 1:
        limiting_tier, limiting_reason = "tier0", tier0_reason
    elif tier1_cap <= final_score + 1:
        limiting_tier, limiting_reason = "tier1", tier1_reason
    elif tier2_cap <= final_score + 1:
        limiting_tier, limiting_reason = "tier2", tier2_reason
    tier_details = {
        'tier0': {'passed': tier0_passed, 'cap': tier0_cap, 'reason': tier0_reason},
        'tier1': {'passed': tier1_passed, 'cap': tier1_cap, 'reason': tier1_reason},
        'tier2': {'passed': tier2_passed, 'cap': tier2_cap, 'reason': tier2_reason},
        'base_score': round(base_score, 1),
        'limiting_tier': limiting_tier,
        'limiting_reason': limiting_reason,
    }
    return (round(final_score, 1), tier_details)


def _calculate_grade(score: float) -> str:
    if score >= 90: return 'A+'
    elif score >= 80: return 'A'
    elif score >= 65: return 'B'
    elif score >= 45: return 'C'
    elif score >= 25: return 'D'
    else: return 'F'


def _calculate_visibility_band(score: float) -> Tuple[str, str]:
    if score >= 80: return ('Excellent', '#22c55e')
    elif score >= 65: return ('Strong', '#84cc16')
    elif score >= 45: return ('Moderate', '#eab308')
    elif score >= 25: return ('Weak', '#f97316')
    else: return ('Critical', '#ef4444')


# =============================================================================
# Public API: run_health_check
# =============================================================================

async def _async_health_check(url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Internal async implementation of health check."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("beautifulsoup4 not installed. Run: pip install beautifulsoup4")

    start_time = time.time()

    fetch = await _fetch_page(url, timeout)

    if fetch.get("error"):
        execution_time = time.time() - start_time
        return {
            "url": fetch["final_url"],
            "score": 0.0,
            "max_score": 100.0,
            "grade": "F",
            "band": "Critical",
            "band_color": "#ef4444",
            "checks_passed": 0,
            "checks_failed": 29,
            "issues": [{"check": "fetch", "category": "critical", "passed": False,
                        "severity": "error", "message": fetch["error"],
                        "recommendation": "Ensure the URL is accessible"}],
            "tier_details": {
                "tier0": {"passed": False, "cap": 0, "reason": fetch["error"]},
                "tier1": {"passed": False, "cap": 0, "reason": "Could not fetch"},
                "tier2": {"passed": False, "cap": 0, "reason": "Could not fetch"},
                "base_score": 0, "limiting_tier": "tier0", "limiting_reason": fetch["error"],
            },
            "execution_time": execution_time,
            "fetch_time_ms": fetch["html_response_time_ms"],
            "js_rendered": False,
        }

    soup = BeautifulSoup(fetch["html"], 'html.parser')

    technical = _run_technical_checks(
        soup, fetch["final_url"], fetch["sitemap_found"], fetch["html_response_time_ms"]
    )
    structured = _run_structured_data_checks(soup)
    crawlers = _run_aeo_crawler_checks(fetch.get("robots_txt") or "")

    # Extract sameAs URLs for authority checks
    _, _, org_schema = _extract_schema_data(soup)
    same_as_urls = []
    if org_schema:
        same_as = org_schema.get("sameAs", [])
        same_as_urls = [same_as] if isinstance(same_as, str) else same_as

    authority = _run_authority_checks(soup, same_as_urls)

    all_results = technical + structured + crawlers + authority

    final_score, tier_details = _calculate_tiered_score(all_results)
    grade = _calculate_grade(final_score)
    band, band_color = _calculate_visibility_band(final_score)

    passed = sum(1 for r in all_results if r.get("passed") is True)
    failed = len(all_results) - passed
    execution_time = time.time() - start_time

    return {
        "url": fetch["final_url"],
        "score": final_score,
        "max_score": 100.0,
        "grade": grade,
        "band": band,
        "band_color": band_color,
        "checks_passed": passed,
        "checks_failed": failed,
        "issues": [r for r in all_results if not r.get("passed")],
        "tier_details": tier_details,
        "execution_time": execution_time,
        "fetch_time_ms": fetch["html_response_time_ms"],
        "js_rendered": fetch["js_rendered"],
    }


def run_health_check(url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """
    Run comprehensive AEO health check: 29 checks across 4 categories.

    Technical SEO (16): title, meta description, H1, heading structure, image alt,
      viewport, structured data presence, HTTPS, canonical, robots meta, word count,
      internal linking, language tag, sitemap, response time, hreflang.

    Structured Data (6): organization schema completeness, FAQ schema, content schema,
      sameAs links, content freshness, JSON-LD validation.

    AI Crawler Access (4): GPTBot, Claude-Web, PerplexityBot, CCBot.

    Authority Signals (3): about page, contact info, social proof links.

    Tiered scoring caps are preserved exactly from the source:
      Tier 0: blocks all AI crawlers -> max score 10
      Tier 1: missing Organization schema -> max score 45
      Tier 2: incomplete schema/thin content -> max score 70-95

    Args:
        url: URL to analyze (e.g. "https://example.com")
        timeout: HTTP request timeout in seconds

    Returns:
        dict with keys: url, score, grade (A+/A/B/C/D/F), band, band_color,
        checks_passed, checks_failed, issues (list of failed checks),
        tier_details, execution_time, fetch_time_ms
    """
    if not url.startswith("http"):
        url = f"https://{url}"
    try:
        return asyncio.run(_async_health_check(url, timeout))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _async_health_check(url, timeout))
            return future.result(timeout=timeout + 30)


# =============================================================================
# Public API: run_mentions
# =============================================================================

async def _async_mentions(
    domain: str,
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    products: Optional[List[str]] = None,
    target_audience: Optional[str] = None,
    queries: int = 20,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal async implementation of mentions check."""
    import json as _json

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No Gemini API key. Set GEMINI_API_KEY environment variable.")

    if not company_name:
        company_name = domain.split(".")[0].replace("-", " ").title()

    products_str = ", ".join(products) if products else "N/A"

    # Generate hyperniche queries (verbatim prompt from stage_mentions.py)
    gen_prompt = f"""Generate {queries} hyperniche AEO visibility queries for {company_name}.

Company Data:
- Industry: {industry or 'N/A'}
- Products: {products_str}
- Target Audience: {target_audience or 'N/A'}

Query Distribution:
- 70% UNBRANDED (no mention of {company_name})
- 20% COMPETITIVE (alternatives, comparisons)
- 10% BRANDED ({company_name} + product)

Requirements:
- Layer 2-3 targeting dimensions (Industry + Role + Geo)
- Use actual ICP data
- Make queries hyper-specific

Examples:
- "best [product] for [target audience] United States"
- "enterprise [industry] [product] solutions"
- "[product] for [role] in [industry]"
- "{company_name} [product]" (only 1 branded)

Return as JSON array:
[{{"query": "actual query", "dimension": "UNBRANDED_HYPERNICHE"}}]"""

    start_time = time.time()
    ai_calls = 0

    # Try google-genai SDK
    try:
        from google import genai as new_genai
        from google.genai import types as new_types
        client = new_genai.Client(api_key=key)

        # Generate queries
        resp = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=gen_prompt,
            config=new_types.GenerateContentConfig(temperature=0.3),
        )
        ai_calls += 1
        text = resp.text.strip()
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()
        try:
            generated_queries = _json.loads(text)
        except _json.JSONDecodeError:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            generated_queries = _json.loads(match.group(0)) if match else []

        generated_queries = generated_queries[:queries]

        # Test each query
        query_results = []
        for q_data in generated_queries:
            query = q_data.get("query", "")
            if not query:
                continue
            try:
                qresp = client.models.generate_content(
                    model=DEFAULT_MODEL,
                    contents=f"Answer this query concisely: {query}",
                    config=new_types.GenerateContentConfig(temperature=0.3),
                )
                ai_calls += 1
                response_text = qresp.text or ""
                company_mentioned = company_name.lower() in response_text.lower()
                query_results.append({
                    "query": query,
                    "dimension": q_data.get("dimension", ""),
                    "has_response": bool(response_text),
                    "company_mentioned": company_mentioned,
                    "response_length": len(response_text),
                    "response_preview": response_text[:200],
                })
            except Exception as e:
                query_results.append({
                    "query": query, "has_response": False, "company_mentioned": False, "error": str(e)
                })

    except ImportError:
        # Fallback to google-generativeai
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(DEFAULT_MODEL)

        resp = model.generate_content(gen_prompt)
        ai_calls += 1
        text = resp.text.strip()
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        try:
            generated_queries = _json.loads(text.strip())[:queries]
        except Exception:
            generated_queries = []

        query_results = []
        for q_data in generated_queries:
            query = q_data.get("query", "")
            if not query:
                continue
            try:
                qresp = model.generate_content(f"Answer this query concisely: {query}")
                ai_calls += 1
                response_text = qresp.text or ""
                company_mentioned = company_name.lower() in response_text.lower()
                query_results.append({
                    "query": query,
                    "dimension": q_data.get("dimension", ""),
                    "has_response": bool(response_text),
                    "company_mentioned": company_mentioned,
                    "response_length": len(response_text),
                    "response_preview": response_text[:200],
                })
            except Exception as e:
                query_results.append({"query": query, "has_response": False, "company_mentioned": False, "error": str(e)})

    # Calculate metrics (verbatim from stage_mentions.py)
    total_responses = sum(1 for r in query_results if r.get("has_response"))
    total_mentions = sum(1 for r in query_results if r.get("company_mentioned"))
    presence_rate = (total_responses / len(query_results) * 100) if query_results else 0
    mention_rate = (total_mentions / len(query_results) * 100) if query_results else 0
    visibility = mention_rate
    quality_score = min(10.0, mention_rate / 10)
    execution_time = time.time() - start_time

    return {
        "company_name": company_name,
        "domain": domain,
        "queries_generated": generated_queries,
        "query_results": query_results,
        "visibility": round(visibility, 1),
        "mentions": total_mentions,
        "presence_rate": round(presence_rate, 1),
        "quality_score": round(quality_score, 2),
        "execution_time": round(execution_time, 2),
        "ai_calls": ai_calls,
    }


def run_mentions(
    domain: str,
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    products: Optional[List[str]] = None,
    target_audience: Optional[str] = None,
    queries: int = 20,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run AI visibility check: generate queries and test with Gemini.

    Query distribution (verbatim from source):
      70% UNBRANDED - tests real organic discovery
      20% COMPETITIVE - comparison/alternative queries
      10% BRANDED - brand awareness queries

    Args:
        domain: Company domain (e.g. "example.com")
        company_name: Company name (inferred from domain if not provided)
        industry: Industry description
        products: List of products/services
        target_audience: Target audience description
        queries: Number of queries to generate and test (default 20)
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        dict with keys: company_name, domain, queries_generated, query_results,
        visibility (0-100), mentions (count), presence_rate, quality_score,
        execution_time, ai_calls
    """
    try:
        return asyncio.run(_async_mentions(
            domain, company_name, industry, products, target_audience, queries, api_key
        ))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _async_mentions(
                domain, company_name, industry, products, target_audience, queries, api_key
            ))
            return future.result(timeout=300)
