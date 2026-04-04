"""
sitemap.py - Crawl and classify company sitemap URLs.

Ported from hyperniche/python-backend/services/blog/stage1/sitemap_crawler.py

Function:
  crawl_sitemap(url: str, validate: bool = False) -> dict

Returns categorized URLs: blog, product, service, docs, resource, company, legal, contact, landing, other.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_SITEMAP_URLS = 500


# =============================================================================
# URL Entry with Metadata
# =============================================================================

@dataclass
class URLEntry:
    """URL entry with sitemap metadata."""
    url: str
    priority: Optional[float] = None
    changefreq: Optional[str] = None
    lastmod: Optional[str] = None


# =============================================================================
# URL Pattern Classification
# =============================================================================

URL_PATTERNS: Dict[str, List[str]] = {
    "blog": [
        r"\/blog\/?",
        r"\/magazine\/?",
        r"\/magazin\/?",
        r"\/news\/?",
        r"\/articles?\/?",
        r"\/posts?\/?",
        r"\/insights?\/?",
        r"\/stories\/?",
        r"\/updates?\/?",
        r"\/press\/?",
    ],
    "product": [
        r"\/products?\/?",
        r"\/solutions?\/?",
        r"\/pricing\/?",
        r"\/features?\/?",
        r"\/plans?\/?",
        r"\/offerings?\/?",
        r"\/store\/?",
        r"\/shop\/?",
        r"\/catalog\/?",
    ],
    "service": [
        r"\/services?\/?",
        r"\/consulting\/?",
        r"\/agency\/?",
        r"\/professional-services\/?",
    ],
    "docs": [
        r"\/docs?\/?",
        r"\/documentation\/?",
        r"\/guides?\/?",
        r"\/tutorials?\/?",
        r"\/help\/?",
        r"\/kb\/?",
        r"\/knowledge-base\/?",
        r"\/faq\/?",
    ],
    "resource": [
        r"\/whitepapers?\/?",
        r"\/case-studies?\/?",
        r"\/case_studies?\/?",
        r"\/templates?\/?",
        r"\/tools?\/?",
        r"\/calculators?\/?",
        r"\/webinars?\/?",
        r"\/videos?\/?",
        r"\/ebooks?\/?",
        r"\/reports?\/?",
        r"\/resources?\/?",
    ],
    "company": [
        r"\/about\/?",
        r"\/about-us\/?",
        r"\/team\/?",
        r"\/careers?\/?",
        r"\/jobs?\/?",
        r"\/culture\/?",
        r"\/company\/?",
        r"\/who-we-are\/?",
    ],
    "legal": [
        r"\/imprint\/?",
        r"\/impressum\/?",
        r"\/privacy\/?",
        r"\/privacy-policy\/?",
        r"\/datenschutz\/?",
        r"\/terms\/?",
        r"\/agb\/?",
        r"\/legal\/?",
        r"\/disclaimer\/?",
        r"\/cookies?\/?",
        r"\/gdpr\/?",
        r"\/dsgvo\/?",
    ],
    "contact": [
        r"\/contact\/?",
        r"\/contact-us\/?",
        r"\/get-in-touch\/?",
        r"\/support\/?",
    ],
    "landing": [
        r"\/campaigns?\/?",
        r"\/lp\/?",
        r"\/landing\/?",
        r"\/offers?\/?",
        r"\/promotions?\/?",
    ],
}

DANGEROUS_PROTOCOLS = [
    "javascript:", "file:", "data:", "vbscript:",
    "about:", "chrome:", "chrome-extension:",
]


def classify_url(url: str) -> str:
    """Classify a URL based on path patterns."""
    path = urlparse(url).path.lower()
    for label, patterns in URL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, path):
                return label
    return "other"


def _is_valid_url(url: str) -> bool:
    """Validate URL - reject dangerous protocols."""
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower().strip()
    if any(url_lower.startswith(proto) for proto in DANGEROUS_PROTOCOLS):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
    except Exception:
        return False


# =============================================================================
# XML parsing (no defusedxml dependency required)
# =============================================================================

def _parse_xml(content: bytes):
    """Parse XML content, return root element."""
    try:
        import xml.etree.ElementTree as ET
        return ET.fromstring(content)
    except Exception as e:
        logger.warning(f"XML parse failed: {e}")
        return None


def _extract_urls_with_metadata(content: bytes) -> List[URLEntry]:
    """Extract URLs with full metadata from sitemap XML content."""
    entries = []
    root = _parse_xml(content)
    if root is None:
        return entries

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    for url_elem in root.findall(".//sm:url", ns):
        loc_elem = url_elem.find("sm:loc", ns)
        if loc_elem is None or not loc_elem.text or not loc_elem.text.strip():
            continue

        url = loc_elem.text.strip()
        if not _is_valid_url(url):
            continue

        priority = None
        priority_elem = url_elem.find("sm:priority", ns)
        if priority_elem is not None and priority_elem.text:
            try:
                priority = float(priority_elem.text.strip())
            except ValueError:
                pass

        changefreq = None
        changefreq_elem = url_elem.find("sm:changefreq", ns)
        if changefreq_elem is not None and changefreq_elem.text:
            changefreq = changefreq_elem.text.strip().lower()

        lastmod = None
        lastmod_elem = url_elem.find("sm:lastmod", ns)
        if lastmod_elem is not None and lastmod_elem.text:
            lastmod = lastmod_elem.text.strip()

        entries.append(URLEntry(
            url=url,
            priority=priority,
            changefreq=changefreq,
            lastmod=lastmod,
        ))

    return entries


# =============================================================================
# Async crawler
# =============================================================================

async def _fetch_sub_sitemap(client, url: str) -> List[URLEntry]:
    """Fetch URLs from a sub-sitemap."""
    try:
        await asyncio.sleep(0.2)
        response = await client.get(url)
        if response.status_code == 200:
            return _extract_urls_with_metadata(response.content)
    except Exception as e:
        logger.debug(f"Sub-sitemap fetch failed {url}: {e}")
    return []


async def _fetch_all_urls(company_url: str, timeout: float = 10.0) -> List[URLEntry]:
    """Fetch all URLs from company sitemap(s)."""
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx not installed. Run: pip install httpx")

    all_entries: List[URLEntry] = []

    company_url = company_url.rstrip("/")
    parsed = urlparse(company_url)

    sitemap_locations = [
        f"{company_url}/sitemap.xml",
        f"{company_url}/sitemap_index.xml",
        f"{company_url}/sitemap/sitemap.xml",
    ]

    # Also try www version if not present
    if not parsed.netloc.startswith("www."):
        www_base = f"{parsed.scheme}://www.{parsed.netloc}"
        sitemap_locations.extend([
            f"{www_base}/sitemap.xml",
            f"{www_base}/sitemap_index.xml",
        ])

    from httpx import Timeout, Limits

    async with httpx.AsyncClient(
        timeout=Timeout(connect=5.0, read=timeout, write=5.0, pool=5.0),
        follow_redirects=True,
        limits=Limits(max_connections=5, max_keepalive_connections=2),
    ) as client:
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        for sitemap_url in sitemap_locations:
            try:
                await asyncio.sleep(0.3)
                response = await client.get(sitemap_url)

                if response.status_code != 200:
                    continue

                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)

                # Check if this is a sitemap_index
                sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
                if sitemaps:
                    logger.info(f"Found sitemap_index with {len(sitemaps)} sitemaps")
                    tasks = [
                        _fetch_sub_sitemap(client, elem.text.strip())
                        for elem in sitemaps if elem.text and elem.text.strip()
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, list):
                            all_entries.extend(result)
                    break
                else:
                    entries = _extract_urls_with_metadata(response.content)
                    all_entries.extend(entries)
                    logger.info(f"Found {len(entries)} URLs in {sitemap_url}")
                    break

            except Exception as e:
                logger.debug(f"Failed to fetch {sitemap_url}: {e}")
                continue

    # Deduplicate
    seen = set()
    unique: List[URLEntry] = []
    for entry in all_entries:
        if entry.url not in seen:
            seen.add(entry.url)
            unique.append(entry)

    return unique


async def _validate_urls(urls: List[str], sample_size: int = 50) -> List[str]:
    """Validate URLs with HEAD requests, filter broken ones."""
    try:
        import httpx
        from httpx import Timeout, Limits
    except ImportError:
        return urls

    if len(urls) > sample_size:
        urls_to_check = urls[:sample_size]
        urls_to_keep = urls[sample_size:]
    else:
        urls_to_check = urls
        urls_to_keep = []

    semaphore = asyncio.Semaphore(10)

    async def check(url: str) -> Optional[str]:
        async with semaphore:
            try:
                async with httpx.AsyncClient(
                    timeout=Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0),
                    follow_redirects=True,
                    limits=Limits(max_connections=20),
                ) as c:
                    response = await c.head(url)
                    if response.status_code < 400:
                        return url
            except Exception:
                pass
            return None

    results = await asyncio.gather(*[check(u) for u in urls_to_check])
    valid = [u for u in results if u is not None]
    valid.extend(urls_to_keep)
    return valid


def _classify_urls(urls: List[str]) -> dict:
    """Classify URLs by type and return dict."""
    categorized: Dict[str, List[str]] = {
        "blog": [], "product": [], "service": [], "docs": [],
        "resource": [], "company": [], "legal": [], "contact": [],
        "landing": [], "other": [],
    }

    for url in urls:
        label = classify_url(url)
        if label in categorized:
            categorized[label].append(url)
        else:
            categorized["other"].append(url)

    return {
        "total_pages": len(urls),
        "blog_urls": categorized["blog"],
        "product_urls": categorized["product"],
        "service_urls": categorized["service"],
        "docs_urls": categorized["docs"],
        "resource_urls": categorized["resource"],
        "company_urls": categorized["company"],
        "legal_urls": categorized["legal"],
        "contact_urls": categorized["contact"],
        "landing_urls": categorized["landing"],
        "other_urls": categorized["other"],
    }


# =============================================================================
# Public API
# =============================================================================

async def _crawl_async(
    url: str,
    validate: bool = False,
    max_urls: int = MAX_SITEMAP_URLS,
    timeout: float = 10.0,
) -> dict:
    """Async implementation of sitemap crawl."""
    if not url.startswith("http"):
        url = f"https://{url}"

    entries = await _fetch_all_urls(url, timeout=timeout)

    if not entries:
        logger.warning(f"No URLs found in sitemap for {url}")
        return _classify_urls([])

    urls = [e.url for e in entries]

    if len(urls) > max_urls:
        logger.info(f"Limiting {len(urls)} URLs to {max_urls}")
        urls = urls[:max_urls]

    if validate:
        urls = await _validate_urls(urls)
        logger.info(f"After validation: {len(urls)} valid URLs")

    return _classify_urls(urls)


def crawl_sitemap(
    url: str,
    validate: bool = False,
    max_urls: int = MAX_SITEMAP_URLS,
    timeout: float = 10.0,
) -> dict:
    """
    Crawl company sitemap and return classified URLs.

    Args:
        url: Company website URL (e.g. "https://example.com")
        validate: If True, validates each URL with a HEAD request (slower)
        max_urls: Maximum number of URLs to return (default 500)
        timeout: HTTP timeout in seconds (default 10)

    Returns:
        dict with keys: total_pages, blog_urls, product_urls, service_urls,
        docs_urls, resource_urls, company_urls, legal_urls, contact_urls,
        landing_urls, other_urls
    """
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.info(f"[sitemap] Crawling {url}")

    try:
        return asyncio.run(_crawl_async(url, validate=validate, max_urls=max_urls, timeout=timeout))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                _crawl_async(url, validate=validate, max_urls=max_urls, timeout=timeout),
            )
            try:
                return future.result(timeout=60)
            except Exception as e:
                logger.warning(f"[sitemap] Crawl failed: {e}")
                return _classify_urls([])
    except Exception as e:
        logger.warning(f"[sitemap] Crawl failed: {e}")
        return _classify_urls([])
