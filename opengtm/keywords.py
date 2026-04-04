"""
keywords.py - AI keyword research pipeline.

Ported from hyperniche/python-backend/services/keywords/ (7-stage pipeline).

Function:
  research_keywords(domain: str, context: dict = None, limit: int = 50) -> list

Stages:
  1. Company analysis: Gemini + Google Search grounding
  2. Deep research: Reddit + Quora/forums via Google Search
  3. AI generation: Diverse keyword intents
  4. Scoring + dedup: 0-100 company-fit score
  5. Clustering: Semantic clusters
  6. (SERP/volume skipped - requires paid Serper/DataForSEO API keys)
  7. Content briefs: angle, questions, gap, pain point, word count

Returns list of keyword dicts sorted by score (highest first).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


# =============================================================================
# Gemini client helper (inline, no hyperniche core dependency)
# =============================================================================

async def _gemini_generate(
    prompt: str,
    response_schema: Optional[dict] = None,
    use_google_search: bool = False,
    temperature: float = 0.3,
    api_key: Optional[str] = None,
) -> dict:
    """Call Gemini and return parsed JSON dict."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No Gemini API key. Set GEMINI_API_KEY environment variable.")

    # Try newer google-genai SDK first
    try:
        from google import genai as new_genai
        from google.genai import types as new_types

        client = new_genai.Client(api_key=key)
        tools = []
        if use_google_search:
            tools.append(new_types.Tool(google_search=new_types.GoogleSearch()))

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=new_types.GenerateContentConfig(
                tools=tools if tools else None,
                temperature=temperature,
            ),
        )
        text = response.text

    except Exception:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
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
        raise ValueError(f"Could not parse JSON: {text[:200]}")


# =============================================================================
# Stage 1: Company Analysis
# =============================================================================

COMPANY_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "description": {"type": "string"},
        "industry": {"type": "string"},
        "target_audience": {"type": "array", "items": {"type": "string"}},
        "products": {"type": "array", "items": {"type": "string"}},
        "services": {"type": "array", "items": {"type": "string"}},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "customer_problems": {"type": "array", "items": {"type": "string"}},
        "use_cases": {"type": "array", "items": {"type": "string"}},
        "value_propositions": {"type": "array", "items": {"type": "string"}},
        "differentiators": {"type": "array", "items": {"type": "string"}},
        "key_features": {"type": "array", "items": {"type": "string"}},
        "solution_keywords": {"type": "array", "items": {"type": "string"}},
        "competitors": {"type": "array", "items": {"type": "string"}},
        "brand_voice": {"type": "string"},
        "product_category": {"type": "string"},
        "primary_region": {"type": "string"},
    },
    "required": ["company_name", "description", "industry", "products"],
}


async def _stage1_company_analysis(
    domain: str,
    context: Optional[dict],
    api_key: Optional[str],
) -> dict:
    """Stage 1: Analyze company via Gemini + Google Search."""
    if context and context.get("company_name"):
        logger.info("[keywords] Stage 1: using provided context")
        return context

    logger.info(f"[keywords] Stage 1: analyzing {domain}")
    current_date = datetime.now().strftime("%B %Y")

    prompt = f"""Today's date: {current_date}

Analyze the company at {domain}

Search Google for comprehensive information about this company:
- Search: "{domain} products services"
- Search: "{domain} customers reviews"
- Search: "{domain} vs competitors"

Extract SPECIFIC information:

1. COMPANY BASICS
   - Company name (official name)
   - Description (2-3 sentences about what they do)
   - Industry (be specific: EdTech, FinTech, B2B SaaS, etc.)

2. PRODUCTS & SERVICES
   - What do they SELL? (use actual product/service names)
   - What services do they offer?

3. CUSTOMER INSIGHTS
   - Who are their customers? (include company sizes: startups, SMEs, enterprise)
   - What pain points do customers have?
   - What problems does their solution solve?
   - Real use cases where the product is used

4. VALUE & DIFFERENTIATION
   - Key value propositions
   - What makes them unique vs competitors?
   - Key features and capabilities
   - Terms describing their approach/solution

5. MARKET
   - Who are their main competitors? (3-5 names)
   - Primary geographic region (US, Europe, Global, etc.)

6. BRAND
   - Brand voice (formal/casual, technical/simple)
   - Product category

Be thorough and specific. Use real information from search results.

Return JSON matching this schema:
{json.dumps(COMPANY_ANALYSIS_SCHEMA, indent=2)}"""

    data = await _gemini_generate(
        prompt=prompt,
        response_schema=COMPANY_ANALYSIS_SCHEMA,
        use_google_search=True,
        temperature=0.2,
        api_key=api_key,
    )
    return data


# =============================================================================
# Stage 2: Deep Research (Reddit + Quora)
# =============================================================================

RESEARCH_KEYWORD_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "intent": {
                        "type": "string",
                        "enum": ["question", "commercial", "informational", "transactional", "comparison"],
                    },
                    "source": {"type": "string"},
                },
                "required": ["keyword", "intent", "source"],
            },
        }
    },
    "required": ["keywords"],
}


async def _stage2_research(
    company: dict,
    language: str,
    target_count: int,
    api_key: Optional[str],
) -> List[dict]:
    """Stage 2: Discover keywords from Reddit + Quora via Google Search grounding."""
    industry = company.get("industry", "technology")
    services = company.get("services", [])
    services_str = ", ".join(services[:3]) if services else industry
    current_date = datetime.now().strftime("%B %Y")

    lang_code = (language or "en").strip().lower().split("-")[0][:2]
    lang_note = ""
    if lang_code not in ("", "en"):
        lang_note = f"\nTARGET LANGUAGE: {lang_code}. Return each keyword in that language.\n"

    # Reddit research
    reddit_prompt = f"""Today's date: {current_date}

Search Reddit for discussions about: {industry}
Related services: {services_str}
{lang_note}
Find {target_count // 2} unique long-tail keywords and questions.

Search queries to use:
- site:reddit.com "{industry} help"
- site:reddit.com "{industry} recommendation"
- site:reddit.com "{industry} vs"
- site:reddit.com "{services_str} question"

Extract:
1. Real questions people ask
2. Problem descriptions (pain points)
3. Specific terminology used
4. Comparison phrases
5. "How to" queries

Return JSON with array of keywords, each with keyword, intent, source fields."""

    # Quora/forums research
    quora_prompt = f"""Today's date: {current_date}

Search for questions about: {industry}
Related services: {services_str}
{lang_note}
Find {target_count // 2} unique questions and long-tail keywords.

Search queries:
- site:quora.com "{industry}"
- "{industry}" people also ask
- "{services_str}" how to
- "{industry}" forum discussion

Extract:
1. Actual questions people ask
2. "How to" queries
3. "Best way to" phrases
4. Comparison questions
5. Specific pain points

Return JSON with array of keywords, each with keyword, intent, source fields."""

    tasks = [
        _gemini_generate(reddit_prompt, use_google_search=True, temperature=0.2, api_key=api_key),
        _gemini_generate(quora_prompt, use_google_search=True, temperature=0.2, api_key=api_key),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_keywords = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"[keywords] Stage 2 research task failed: {result}")
            continue
        for kw in result.get("keywords", []):
            if kw.get("keyword"):
                all_keywords.append({
                    "keyword": kw["keyword"],
                    "intent": kw.get("intent", "informational"),
                    "source": kw.get("source", "research"),
                    "is_question": "?" in kw["keyword"] or kw.get("intent") == "question",
                    "score": 0,
                })

    return all_keywords


# =============================================================================
# Stage 3: AI Keyword Generation
# =============================================================================

KEYWORD_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "intent": {
                        "type": "string",
                        "enum": ["transactional", "commercial", "informational", "question", "comparison"],
                    },
                    "is_question": {"type": "boolean"},
                },
                "required": ["keyword", "intent"],
            },
        }
    },
    "required": ["keywords"],
}


async def _stage3_ai_keywords(
    company: dict,
    existing_count: int,
    target_count: int,
    language: str,
    api_key: Optional[str],
) -> List[dict]:
    """Stage 3: Generate keywords with Gemini AI."""
    ai_target = max(target_count - existing_count, target_count // 3)
    if ai_target <= 0:
        return []

    lang_code = (language or "en").strip().lower().split("-")[0][:2]
    lang_instruction = (
        "CRITICAL: Generate EVERY keyword in the target language. "
        "All keyword text MUST be written in the language specified below. "
        "Do not mix English with the target language. "
    )
    if lang_code == "hi":
        lang_instruction += "TARGET LANGUAGE: Hindi. Write every keyword in Hindi using Devanagari script. "
    elif lang_code == "bn":
        lang_instruction += "TARGET LANGUAGE: Bengali. Write every keyword in Bengali/Bangla script. "
    elif lang_code != "en":
        lang_instruction += f"TARGET LANGUAGE: {lang_code}. Write every keyword in that language only. "

    products_str = ", ".join(company.get("products", [])[:5]) or "N/A"
    services_str = ", ".join(company.get("services", [])[:5]) or "N/A"
    pain_points_str = ", ".join(company.get("pain_points", [])[:5]) or "N/A"
    differentiators_str = ", ".join(company.get("differentiators", [])[:3]) or "N/A"

    prompt = f"""Generate {ai_target} SEO keywords for this company:

COMPANY: {company.get('company_name', 'Unknown')}
INDUSTRY: {company.get('industry', 'N/A')}
PRODUCTS: {products_str}
SERVICES: {services_str}
PAIN POINTS: {pain_points_str}
DIFFERENTIATORS: {differentiators_str}
LANGUAGE: {language}

{lang_instruction}

REQUIREMENTS:
1. Generate DIVERSE keywords across these intents:
   - transactional (buy, pricing, demo)
   - commercial (comparison, alternatives, vs)
   - informational (how to, what is, guide)
   - question (actual questions users ask)

2. Include:
   - Long-tail keywords (3-5 words)
   - Question keywords ("how to...", "what is...")
   - Comparison keywords ("X vs Y", "alternatives to")
   - Product-specific keywords
   - Problem-solving keywords

3. AVOID:
   - Generic industry terms
   - Single-word keywords
   - Duplicate variations
   - Writing keyword text in English when LANGUAGE is not en

Return JSON with array of keywords, each with keyword, intent, is_question fields."""

    try:
        data = await _gemini_generate(
            prompt=prompt,
            response_schema=KEYWORD_SCHEMA,
            use_google_search=False,
            temperature=0.7,
            api_key=api_key,
        )
        return [
            {
                "keyword": kw.get("keyword", ""),
                "intent": kw.get("intent", "informational"),
                "source": "ai_generated",
                "is_question": kw.get("is_question", False),
                "score": 0,
            }
            for kw in data.get("keywords", [])
            if kw.get("keyword")
        ]
    except Exception as e:
        logger.warning(f"[keywords] Stage 3 AI generation failed: {e}")
        return []


# =============================================================================
# Stage 4: Scoring + Deduplication
# =============================================================================

SCORING_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["keyword", "score"],
            },
        }
    },
    "required": ["keywords"],
}


def _deduplicate(keywords: List[dict]) -> Tuple[List[dict], int]:
    """Fast deduplication using exact match + token signature."""
    seen_exact: set = set()
    seen_tokens: set = set()
    unique = []
    dup_count = 0

    for kw in keywords:
        text = kw.get("keyword", "").lower().strip()
        if not text:
            continue
        if text in seen_exact:
            dup_count += 1
            continue
        tokens = tuple(sorted(text.split()))
        if tokens in seen_tokens:
            dup_count += 1
            continue
        seen_exact.add(text)
        seen_tokens.add(tokens)
        unique.append(kw)

    return unique, dup_count


async def _stage4_score(
    keywords: List[dict],
    company: dict,
    min_score: int = 20,
    api_key: Optional[str] = None,
) -> List[dict]:
    """Stage 4: Score keywords for company-fit and deduplicate."""
    keywords, dup_count = _deduplicate(keywords)
    logger.info(f"[keywords] Stage 4: {len(keywords)} after dedup ({dup_count} removed)")

    if not keywords:
        return []

    products = ", ".join(company.get("products", [])[:5]) or "N/A"
    services = ", ".join(company.get("services", [])[:5]) or "N/A"
    pain_points = ", ".join(company.get("pain_points", [])[:3]) or "N/A"

    batch_size = 50
    scored = []

    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        keyword_list = [kw.get("keyword", "") for kw in batch]

        prompt = f"""Score these keywords for company-fit (0-100):

COMPANY: {company.get('company_name', 'Unknown')}
INDUSTRY: {company.get('industry', 'N/A')}
PRODUCTS: {products}
SERVICES: {services}
PAIN POINTS: {pain_points}

SCORING CRITERIA:
- 80-100: Directly mentions company products/services/solutions
- 60-79: Highly relevant to company's pain points and value props
- 40-59: Generally relevant to industry/niche
- 20-39: Loosely related, might attract some relevant traffic
- 0-19: Not relevant, too generic, or wrong audience

KEYWORDS TO SCORE:
{json.dumps(keyword_list, indent=2)}

Return JSON with array of {{keyword, score}} for each."""

        try:
            data = await _gemini_generate(
                prompt=prompt,
                response_schema=SCORING_SCHEMA,
                use_google_search=False,
                temperature=0.2,
                api_key=api_key,
            )
            scores = {s["keyword"]: s["score"] for s in data.get("keywords", [])}
            for kw in batch:
                kw["score"] = scores.get(kw.get("keyword", ""), 50)
                scored.append(kw)
        except Exception as e:
            logger.warning(f"[keywords] Scoring batch failed: {e}")
            for kw in batch:
                kw["score"] = 50
                scored.append(kw)

    # Filter by min score
    filtered = [kw for kw in scored if kw.get("score", 0) >= min_score]
    logger.info(f"[keywords] Stage 4: {len(filtered)} after score filter (>= {min_score})")
    return filtered


# =============================================================================
# Stage 5: Clustering
# =============================================================================

CLUSTERING_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "keywords"],
            },
        }
    },
    "required": ["clusters"],
}


async def _stage5_cluster(
    keywords: List[dict],
    company: dict,
    cluster_count: int = 5,
    api_key: Optional[str] = None,
) -> List[dict]:
    """Stage 5: Semantic clustering with Gemini."""
    if not keywords:
        return keywords

    keyword_list = [kw["keyword"] for kw in keywords]

    prompt = f"""Group these keywords into {cluster_count} semantic clusters for {company.get('company_name', 'the company')}:

INDUSTRY: {company.get('industry', 'N/A')}

KEYWORDS:
{json.dumps(keyword_list, indent=2)}

CLUSTERING RULES:
1. Create exactly {cluster_count} clusters
2. Each cluster should have a short, descriptive name (2-4 words)
3. Group by semantic similarity and topic
4. Every keyword must belong to exactly one cluster
5. Balance cluster sizes (avoid putting everything in one cluster)

Example cluster names:
- "Pricing & Plans"
- "How-To Guides"
- "Competitor Comparisons"
- "Product Features"
- "Industry Solutions"

Return JSON with clusters array, each containing name and keywords array."""

    try:
        data = await _gemini_generate(
            prompt=prompt,
            response_schema=CLUSTERING_SCHEMA,
            use_google_search=False,
            temperature=0.2,
            api_key=api_key,
        )

        # Build keyword-to-cluster mapping
        kw_to_cluster: Dict[str, str] = {}
        for cluster in data.get("clusters", []):
            cluster_name = cluster.get("name", "Uncategorized")
            for kw in cluster.get("keywords", []):
                kw_to_cluster[kw.lower()] = cluster_name

        # Apply clusters
        for kw in keywords:
            kw["cluster"] = kw_to_cluster.get(kw.get("keyword", "").lower(), "Uncategorized")

        logger.info(f"[keywords] Stage 5: clustered into {len(data.get('clusters', []))} groups")

    except Exception as e:
        logger.warning(f"[keywords] Stage 5 clustering failed: {e}")
        for kw in keywords:
            kw["cluster"] = "Uncategorized"

    return keywords


# =============================================================================
# Stage 7: Content Briefs
# =============================================================================

CONTENT_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "content_angle": {"type": "string"},
        "target_questions": {"type": "array", "items": {"type": "string"}},
        "content_gap": {"type": "string"},
        "audience_pain_point": {"type": "string"},
        "recommended_word_count": {"type": "integer"},
    },
    "required": ["content_angle", "target_questions", "content_gap", "audience_pain_point", "recommended_word_count"],
}


async def _generate_brief(
    keyword: dict,
    company_name: str,
    industry: str,
    language: str,
    api_key: Optional[str],
) -> Optional[dict]:
    """Generate content brief for a single keyword."""
    prompt = f"""Generate a content brief for the keyword: "{keyword['keyword']}"

Company: {company_name}
Industry: {industry or "General"}
Search Intent: {keyword.get('intent', 'informational')}
Is Question: {"Yes" if keyword.get('is_question') else "No"}

Generate a content brief with these fields:
1. content_angle: A unique angle or perspective to differentiate from competitors (1-2 sentences)
2. target_questions: 3-5 key questions the content should answer
3. content_gap: What's missing from existing content that we can fill (1 sentence)
4. audience_pain_point: The main pain point to address (1 sentence)
5. recommended_word_count: Recommended word count based on topic complexity (number between 800-3000)"""

    try:
        data = await _gemini_generate(
            prompt=prompt,
            response_schema=CONTENT_BRIEF_SCHEMA,
            use_google_search=False,
            temperature=0.7,
            api_key=api_key,
        )
        return {
            "content_angle": str(data.get("content_angle", ""))[:500],
            "target_questions": [str(q)[:200] for q in data.get("target_questions", [])[:5]],
            "content_gap": str(data.get("content_gap", ""))[:300],
            "audience_pain_point": str(data.get("audience_pain_point", ""))[:300],
            "recommended_word_count": min(max(int(data.get("recommended_word_count", 1500)), 500), 5000),
        }
    except Exception as e:
        logger.warning(f"[keywords] Brief generation failed for '{keyword['keyword']}': {e}")
        return None


async def _stage7_briefs(
    keywords: List[dict],
    company: dict,
    language: str,
    brief_sample_size: int,
    api_key: Optional[str],
) -> List[dict]:
    """Stage 7: Generate content briefs for top keywords."""
    sorted_kws = sorted(keywords, key=lambda k: k.get("score", 0), reverse=True)
    sample = sorted_kws[:brief_sample_size]

    company_name = company.get("company_name", "Unknown")
    industry = company.get("industry", "")

    # Process in batches of 5 (verbatim from source)
    batch_size = 5
    briefs_generated = 0

    for i in range(0, len(sample), batch_size):
        batch = sample[i:i + batch_size]
        tasks = [
            _generate_brief(kw, company_name, industry, language, api_key)
            for kw in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for kw, result in zip(batch, results):
            if isinstance(result, dict):
                kw["content_brief"] = result
                briefs_generated += 1
            else:
                kw["content_brief"] = None

        if i + batch_size < len(sample):
            await asyncio.sleep(0.3)

    logger.info(f"[keywords] Stage 7: generated {briefs_generated} content briefs")
    return keywords


# =============================================================================
# Public API
# =============================================================================

async def _run_pipeline(
    domain: str,
    context: Optional[dict],
    limit: int,
    language: str,
    region: str,
    min_score: int,
    cluster_count: int,
    brief_sample_size: int,
    generate_briefs: bool,
    api_key: Optional[str],
) -> List[dict]:
    """Full async keyword research pipeline."""

    # Stage 1: Company analysis
    company = await _stage1_company_analysis(domain, context, api_key)
    logger.info(f"[keywords] Company: {company.get('company_name', 'Unknown')}")

    # Stage 2: Deep research (Reddit + Quora)
    logger.info("[keywords] Stage 2: deep research")
    research_keywords = await _stage2_research(company, language, limit, api_key)
    logger.info(f"[keywords] Stage 2: {len(research_keywords)} research keywords")

    # Stage 3: AI keyword generation
    logger.info("[keywords] Stage 3: AI generation")
    ai_keywords = await _stage3_ai_keywords(
        company, len(research_keywords), limit, language, api_key
    )
    logger.info(f"[keywords] Stage 3: {len(ai_keywords)} AI keywords")

    # Combine
    all_keywords = research_keywords + ai_keywords

    # Stage 4: Score + dedup
    logger.info("[keywords] Stage 4: scoring + deduplication")
    scored = await _stage4_score(all_keywords, company, min_score=min_score, api_key=api_key)

    # Sort by score, take top N
    scored.sort(key=lambda k: k.get("score", 0), reverse=True)
    scored = scored[:limit]

    # Stage 5: Clustering
    logger.info("[keywords] Stage 5: clustering")
    clustered = await _stage5_cluster(scored, company, cluster_count=cluster_count, api_key=api_key)

    # Stage 6: SERP/volume skipped (requires paid Serper/DataForSEO API keys)
    # Stage 7: Content briefs (top N only)
    if generate_briefs and clustered:
        logger.info("[keywords] Stage 7: content briefs")
        clustered = await _stage7_briefs(clustered, company, language, brief_sample_size, api_key)

    logger.info(f"[keywords] Pipeline complete: {len(clustered)} keywords")
    return clustered


def research_keywords(
    domain: str,
    context: Optional[dict] = None,
    limit: int = 50,
    language: str = "en",
    region: str = "US",
    min_score: int = 20,
    cluster_count: int = 5,
    brief_sample_size: int = 10,
    generate_briefs: bool = True,
    api_key: Optional[str] = None,
) -> List[dict]:
    """
    Research SEO keywords for a company using AI.

    7-stage pipeline: analyze -> research -> generate -> score -> cluster -> briefs

    Args:
        domain: Company website domain or URL (e.g. "example.com")
        context: Optional company context dict (from extract_context). If not
                 provided, context is automatically extracted via Gemini.
        limit: Maximum number of keywords to return (default 50)
        language: Language code (default "en")
        region: Target region code (default "US")
        min_score: Minimum company-fit score 0-100 to include (default 20)
        cluster_count: Number of semantic clusters to create (default 5)
        brief_sample_size: Number of top keywords to generate content briefs for
                           (default 10)
        generate_briefs: If True, generate content briefs for top keywords
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        List of keyword dicts sorted by score (highest first). Each dict has:
        keyword, intent, source, is_question, score, cluster, content_brief (optional)
    """
    if not domain.startswith("http"):
        domain = f"https://{domain}"

    logger.info(f"[keywords] research_keywords: domain={domain} limit={limit}")

    try:
        return asyncio.run(_run_pipeline(
            domain=domain,
            context=context,
            limit=limit,
            language=language,
            region=region,
            min_score=min_score,
            cluster_count=cluster_count,
            brief_sample_size=brief_sample_size,
            generate_briefs=generate_briefs,
            api_key=api_key,
        ))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                _run_pipeline(
                    domain=domain,
                    context=context,
                    limit=limit,
                    language=language,
                    region=region,
                    min_score=min_score,
                    cluster_count=cluster_count,
                    brief_sample_size=brief_sample_size,
                    generate_briefs=generate_briefs,
                    api_key=api_key,
                ),
            )
            return future.result(timeout=600)
    except Exception as e:
        logger.error(f"[keywords] Pipeline failed: {e}")
        raise
