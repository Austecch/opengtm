<!-- keywords: open source gtm automation, ai lead generation python, aeo health check tool, ai seo keyword research, blog generation ai python, company context extraction gemini -->

# opengtm - Open source AI GTM toolkit for Python

> Discover leads, research prospects, score ICP fit, generate outreach, audit AEO health, research keywords, and generate blog content. All from your terminal, no SaaS subscription required.

opengtm is an open source Python toolkit for AI-powered go-to-market automation. It uses Gemini + Google Search grounding throughout: real data, no hallucinations.

**Who it's for:** Founders doing outbound, GTM engineers building AI sales automation, SEO teams running content pipelines, developers who want open source tools they can extend.

## Modules

| Module | What it does | CLI command |
|--------|-------------|-------------|
| `discover.py` | Find companies by industry + region via Gemini + Google Search | `opengtm discover` |
| `research.py` | Extract decision-maker contact + run 7-point website audit | `opengtm research` |
| `qualify.py` | Score ICP fit 0-100 across 6 dimensions | `opengtm qualify` |
| `message.py` | Generate personalized outreach messages from audit findings | `opengtm message` |
| `outreach.py` | Manage multi-touch sequences, daily limits, due-today queue | `opengtm outreach` |
| `sync.py` | Push leads to Google Sheet CRM via Apps Script webhook | `opengtm sync` |
| `context.py` | Extract company context: industry, products, pain points, tone | `opengtm context` |
| `analytics.py` | AEO health check (29 checks, tiered scoring) + AI visibility | `opengtm analytics` |
| `blog.py` | Generate SEO blog articles (5-stage pipeline) | `opengtm blog` |
| `keywords.py` | AI keyword research pipeline (7 stages) | `opengtm keywords` |
| `sitemap.py` | Crawl and classify sitemap URLs by type | `opengtm sitemap` |

## Quickstart

```bash
pip install opengtm
```

Or from source:

```bash
git clone https://github.com/buildingopen/opengtm
cd opengtm
pip install -e .
```

Set your API key:

```bash
export GEMINI_API_KEY=your_gemini_api_key_here
```

## GTM Pipeline (Outbound)

```
Discover -> Research -> Qualify -> Message -> Outreach -> Sync
   |            |          |          |          |          |
industry     domain     ICP 0-100  patterns   sequence  CRM sheet
+ region     audit      hot/warm/  A/B/C/D/E  manager   via webhook
+ limit      contact    cold       EN/DE
```

### Discover companies

```bash
opengtm discover --industry "IT Services" --region "Hamburg" --limit 20
# -> /tmp/opengtm-discovered.json
```

### Research a domain

```bash
opengtm research --domain example.com --company "Acme GmbH" --industry "B2B SaaS"
# -> /tmp/opengtm-researched.json
```

Research a batch from discover output:

```bash
opengtm research --input /tmp/opengtm-discovered.json
```

### Score ICP fit

```bash
opengtm qualify --input /tmp/opengtm-researched.json --icp-profile saas
# -> /tmp/opengtm-qualified.json (sorted by score, hot leads first)
```

Available ICP profiles: `default`, `saas`, `agency`, `professional_services`

### Generate outreach messages

```bash
opengtm message --input /tmp/opengtm-qualified.json --language en
# -> /tmp/opengtm-messages.json (Pattern A/B/C/D/E per lead)
```

### Full GTM pipeline

```bash
opengtm pipeline \
  --industry "Recruiting" \
  --region "Munich" \
  --limit 15 \
  --icp-profile saas \
  --language en
```

### Manage outreach sequences

```bash
opengtm outreach load --input /tmp/opengtm-messages.json --state-file seq.json
opengtm outreach queue --state-file seq.json
opengtm outreach status --state-file seq.json
```

### Sync to CRM

```bash
opengtm sync --input /tmp/opengtm-messages.json
opengtm sync --input /tmp/opengtm-messages.json --dry-run
```

## Content Pipeline (SEO)

### Extract company context

```bash
opengtm context --url https://example.com
# -> /tmp/opengtm-context.json

opengtm context --url https://example.com --country DE --language de
```

The context module extracts company name, industry, products, services, target audience, competitors, tone, pain points, value propositions, use cases, and content themes using Gemini + Google Search grounding.

### AEO health check

```bash
# Health check (29 checks, tiered scoring, grade A+ to F)
opengtm analytics --url https://example.com --health-only

# AI visibility check
opengtm analytics --company "Example Corp" --industry "SaaS" --mentions-only

# Full analysis
opengtm analytics --url https://example.com --company "Example Corp"
```

The AEO (Answer Engine Optimization) health check runs 29 checks across 4 categories:

| Category | Checks | Purpose |
|----------|--------|---------|
| AI Crawler Access | 4 | GPTBot, Claude, PerplexityBot, CCBot |
| Structured Data | 6 | Organization schema, FAQ, sameAs links |
| Technical SEO | 16 | Title, meta, canonical, H1/H2, HTTPS, sitemap |
| Authority Signals | 3 | About page, contact info, social proof |

Tiered scoring: if AI crawlers are blocked, max score is 10. Missing Organization schema caps at 45. See [AEO scoring methodology](#aeo-scoring).

### Keyword research

```bash
opengtm keywords --domain example.com --limit 50
opengtm keywords --domain example.com --language de --region DE --clusters 8
opengtm keywords --domain example.com --no-briefs  # skip content briefs
```

The keyword pipeline runs 7 stages:
1. Company analysis with Gemini + Google Search
2. Reddit + Quora research
3. AI keyword generation (transactional, commercial, informational, question)
4. Scoring + deduplication
5. Semantic clustering
6. Volume estimation (SERP - requires paid Serper key)
7. Content briefs

### Generate blog articles

```bash
opengtm blog --domain example.com --keyword "best practices for SaaS onboarding"
opengtm blog --domain example.com --keyword "was ist AEO" --language de --country Germany
opengtm blog --domain example.com --keyword "keyword" --context /tmp/opengtm-context.json
```

The blog pipeline runs 5 stages:
1. Extract company context + crawl sitemap
2. Generate article with Gemini + Google Search grounding
3. Content similarity check (character shingles, Jaccard)
4. URL verification + dead link removal
5. Return structured output with HTML, sources, word count

### Crawl sitemap

```bash
opengtm sitemap --url https://example.com
opengtm sitemap --url https://example.com --validate  # verify each URL
```

Classifies URLs into: blog, product, service, docs, resource, company, legal, contact, landing, other.

## AEO Scoring

The AEO funnel:

1. **CAN AI ACCESS?** If blocked, nothing else matters (Tier 0)
2. **CAN AI UNDERSTAND?** Schema.org is essential (Tier 1)
3. **IS CONTENT STRUCTURED?** Technical SEO (Tier 2)
4. **IS IT TRUSTWORTHY?** Authority signals (Tier 3)

| Tier | Condition | Score Cap |
|------|-----------|-----------|
| 0 | Blocks all AI crawlers | 10 |
| 0 | Blocks 3 AI crawlers | 25 |
| 0 | noindex on page | 5 |
| 1 | Missing Organization schema | 45 |
| 1 | Missing title or HTTPS | 55 |
| 2 | Incomplete schema | 75-95 |
| 3 | Full optimization | 100 |

| Grade | Score | Description |
|-------|-------|-------------|
| A+ | 90+ | Exceptional |
| A | 80-89 | Excellent |
| B | 65-79 | Good |
| C | 45-64 | Fair |
| D | 25-44 | Poor |
| F | <25 | Critical |

## ICP Scoring

Leads are scored 0-100 across 6 dimensions inferred from website signals:

| Dimension | Max | What it measures |
|-----------|-----|--------------------|
| Company size | 20 | Blog, social, site complexity as headcount proxy |
| Industry fit | 25 | Tiered by typical LTV and digital spend |
| Digital maturity | 15 | Blog, social, schema markup, language consistency |
| Pain signals | 20 | Severity-weighted audit findings |
| Revenue signals | 10 | Content investment, multiple high-severity issues |
| Contact quality | 10 | Name + LinkedIn + email found |

| Score | Tier | Action |
|-------|------|--------|
| 70-100 | Hot | Prioritize: connect this week |
| 45-69 | Warm | Standard outreach sequence |
| 0-44 | Cold | Long-term nurture pool |

## Message Frameworks

5 pattern categories based on best audit finding:

| Pattern | Trigger | Example hook |
|---------|---------|--------------|
| **A** | Specific finding (meta, title, broken elements) | "I noticed example.com has no meta description..." |
| **B** | Competitor visible in AI search | "[Competitor] shows up in ChatGPT, you don't yet..." |
| **C** | Blog exists but not indexed | "Your blog isn't being picked up by search engines..." |
| **D** | No strong finding / free tool angle | "Do you know your AI visibility score?" |
| **E** | Clean site / fallback | "I tested whether example.com shows up in ChatGPT..." |

Every output includes: `connection_note`, `first_dm`, `followup`, `followup_2`, `followup_3`, `alternatives`.

Supports English and German (DACH-calibrated formal address for Finance/Legal/Medical).

## Python API

```python
from opengtm.discover import discover
from opengtm.research import research
from opengtm.qualify import qualify_batch
from opengtm.message import generate_messages
from opengtm.context import extract_context
from opengtm.analytics import run_health_check, run_mentions
from opengtm.blog import generate_article
from opengtm.keywords import research_keywords
from opengtm.sitemap import crawl_sitemap

# Extract company context
context = extract_context("https://example.com")

# AEO health check
health = run_health_check("https://example.com")
print(f"Score: {health['score']} | Grade: {health['grade']}")

# AI visibility
visibility = run_mentions(
    domain="example.com",
    company_name="Example Corp",
    industry="SaaS",
)
print(f"Visibility: {visibility['visibility_score']:.1f}%")

# Keyword research
keywords = research_keywords("example.com", limit=30)
for kw in keywords[:5]:
    print(f"[{kw['score']}] {kw['keyword']} ({kw['cluster']})")

# Blog article
article = generate_article(
    domain="example.com",
    keyword="best practices for SaaS onboarding",
    context=context,
)
print(f"Title: {article['title']} ({article['word_count']} words)")

# Crawl sitemap
sitemap = crawl_sitemap("https://example.com")
print(f"Blog URLs: {len(sitemap['blog_urls'])}")

# GTM outbound
leads = discover(industry="B2B SaaS", region="Berlin", limit=10)
for lead in leads:
    audit = research(domain=lead["domain"], company=lead["company"])
    lead["audit"] = audit

qualified = qualify_batch(leads, icp_profile="saas")
for lead in qualified:
    lead["messages"] = generate_messages(
        domain=lead["domain"],
        company=lead["company"],
        contact_name=lead.get("contact_name", ""),
        industry=lead["industry"],
        audit=lead["audit"],
    )
```

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Gemini model override
# GEMINI_MODEL=gemini-2.0-flash

# Optional: CRM sync
CRM_WEBHOOK_URL=your_google_apps_script_dopost_url
CRM_WEBHOOK_TOKEN=your_token

# Optional: defaults
DEFAULT_LANGUAGE=en
DEFAULT_DAILY_LIMIT=20
```

Get a Gemini API key at [aistudio.google.com](https://aistudio.google.com). The free tier works for development.

## Requirements

- Python 3.10+
- Gemini API key (free tier at aistudio.google.com)

## Related Projects

- [session-recall](https://github.com/federicodeponte/session-recall) - Claude Code session recovery tool
- [buildingopen](https://github.com/buildingopen) - Open source tools for builders

## Contributing

Pull requests welcome. The most useful contributions:

1. New ICP profiles in `qualify.py`
2. New message frameworks in `message.py`
3. CRM integrations in `sync.py` (HubSpot, Pipedrive, Airtable)
4. Additional language support in `message.py`
5. SERP volume integration in `keywords.py` (Serper, DataForSEO)

Open an issue first for significant changes.

## License

MIT License. Copyright 2026 Federico De Ponte.
