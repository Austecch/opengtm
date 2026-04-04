<!-- keywords: claude code gtm, ai lead generation, open source outreach automation, ai sales tools, prospect research automation, icp scoring python -->

# opengtm - AI-powered GTM automation for Claude Code

> Discover leads, research prospects, score ICP fit, generate personalized outreach, and run multi-touch sequences. All from your terminal, zero manual steps.

Built for founders and GTM engineers who want AI lead generation without the SaaS pricing. opengtm is the Claude Code GTM automation toolkit that runs end-to-end: from "find me 20 IT consultancies in Berlin" to ready-to-send LinkedIn messages with follow-up sequences.

## What it does

opengtm uses Gemini + Google Search grounding to discover real companies, audit their websites for specific technical pain signals, score each lead against your ICP (0-100), and generate personalized outreach messages based on what it actually found. No templates, no hallucinated findings.

**Who it's for:** Founders doing outbound, GTM engineers building AI sales automation, Claude Code users who want open source lead generation they can extend.

**What problem it solves:** Manual GTM research is bottlenecked by time. Existing tools either fake personalization or cost $500/month. opengtm is open source AI outreach automation that generates real signal-based messages.

## Pipeline

```
Discover -> Research -> Qualify -> Message -> Outreach -> Sync
   |            |          |          |          |          |
industry     domain     ICP 0-100  patterns   sequence  CRM sheet
+ region     audit      hot/warm/  A/B/C/D/E  manager   via webhook
+ limit      contact    cold       EN/DE
```

## Quickstart

```bash
pip install opengtm
```

Or from source:

```bash
git clone https://github.com/federicodeponte/opengtm
cd opengtm
pip install -e .
```

Set your API key:

```bash
export GEMINI_API_KEY=your_gemini_api_key_here
```

Run the full pipeline:

```bash
opengtm pipeline --industry "B2B SaaS" --region "Berlin" --limit 10
```

That's it. You get 10 discovered companies, researched, ICP-scored, and with LinkedIn messages ready to send.

## Modules

| Module | What it does | CLI command |
|--------|-------------|-------------|
| `discover.py` | Find companies by industry + region via Gemini + Google Search | `opengtm discover` |
| `research.py` | Extract decision-maker contact + run 7-point website audit | `opengtm research` |
| `qualify.py` | Score ICP fit 0-100 across 6 dimensions | `opengtm qualify` |
| `message.py` | Generate personalized outreach messages from audit findings | `opengtm message` |
| `outreach.py` | Manage multi-touch sequences, daily limits, due-today queue | `opengtm outreach` |
| `sync.py` | Push leads to Google Sheet CRM via Apps Script webhook | `opengtm sync` |

## CLI Reference

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

### Full pipeline (all steps in one)

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
# Load qualified leads into sequence
opengtm outreach load --input /tmp/opengtm-messages.json --state-file seq.json

# See who to reach out to today
opengtm outreach queue --state-file seq.json

# Check stats
opengtm outreach status --state-file seq.json
```

### Sync to CRM

```bash
# Requires CRM_WEBHOOK_URL in .env
opengtm sync --input /tmp/opengtm-messages.json
opengtm sync --input /tmp/opengtm-messages.json --dry-run  # preview first
```

## ICP Scoring

Leads are scored 0-100 across 6 dimensions inferred from website signals:

| Dimension | Max | What it measures |
|-----------|-----|-----------------|
| Company size | 20 | Blog, social, site complexity as headcount proxy |
| Industry fit | 25 | Tiered by typical LTV and digital spend |
| Digital maturity | 15 | Blog, social, schema markup, language consistency |
| Pain signals | 20 | Severity-weighted audit findings |
| Revenue signals | 10 | Content investment, multiple high-severity issues |
| Contact quality | 10 | Name + LinkedIn (5 pts) + email found |

| Score | Tier | Action |
|-------|------|--------|
| 70-100 | Hot | Prioritize: connect this week |
| 45-69 | Warm | Standard outreach sequence |
| 0-44 | Cold | Long-term nurture pool |

See [docs/icp-scoring.md](docs/icp-scoring.md) for full methodology.

## Message Frameworks

opengtm selects from 5 pattern categories based on the best audit finding:

| Pattern | Trigger | Example hook |
|---------|---------|-------------|
| **A** | Specific finding (meta, title, broken elements, social, schema) | "I noticed example.com has no meta description..." |
| **B** | Competitor visible in AI search | "[Competitor] shows up in ChatGPT, you don't yet..." |
| **C** | Blog exists but not indexed | "Your blog isn't being picked up by search engines..." |
| **D** | No strong finding / free tool angle | "Do you know your AI visibility score?" |
| **E** | Clean site / fallback | "I tested whether example.com shows up in ChatGPT..." |

Every output includes:
- `connection_note` (LinkedIn connection request, optimized for 280 char limit)
- `first_dm` (post-connect follow-up, 500 chars)
- `followup` (Day 3, concrete fix preview)
- `followup_2` (Day 10, industry peer comparison)
- `followup_3` (Day 21, clean breakup)
- `alternatives` (other patterns available for the same lead)

Supports English and German (DACH-calibrated: formal address for Finance/Legal/Medical).

See [docs/message-frameworks.md](docs/message-frameworks.md) for full pattern documentation.

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Gemini model override
# GEMINI_MODEL=gemini-3-flash-preview

# Optional: CRM sync
CRM_WEBHOOK_URL=your_google_apps_script_dopost_url
CRM_WEBHOOK_TOKEN=your_token

# Optional: defaults
DEFAULT_LANGUAGE=en
DEFAULT_DAILY_LIMIT=20
```

Get a Gemini API key at [aistudio.google.com](https://aistudio.google.com). The free tier works for development.

## Python API

Use opengtm as a library:

```python
from opengtm.discover import discover
from opengtm.research import research
from opengtm.qualify import qualify_batch
from opengtm.message import generate_messages
from opengtm.outreach import OutreachSequence

# Discover
leads = discover(industry="B2B SaaS", region="Berlin", limit=10)

# Research
for lead in leads:
    audit = research(domain=lead["domain"], company=lead["company"])
    lead["audit"] = audit
    lead["contact_name"] = audit["contact"]["name"]

# Qualify
qualified = qualify_batch(leads, icp_profile="saas")

# Generate messages
for lead in qualified:
    lead["messages"] = generate_messages(
        domain=lead["domain"],
        company=lead["company"],
        contact_name=lead.get("contact_name", ""),
        industry=lead["industry"],
        audit=lead["audit"],
    )

# Load into sequence
seq = OutreachSequence(daily_limit=20)
seq.add_leads(qualified)
due = seq.get_due_today()
seq.export("outreach-state.json")
```

## CRM Webhook Setup

opengtm syncs to Google Sheets via a simple Apps Script webhook. To set up:

1. Create a new Google Sheet with a "Prospects" tab
2. Go to Extensions > Apps Script
3. Deploy a doPost function that accepts JSON arrays and writes rows
4. Copy the web app URL to `CRM_WEBHOOK_URL` in your `.env`

The sync payload per row includes: company, domain, industry, contact_name, contact_title, linkedin_url, contact_email, status, research_notes, linkedin_connection, linkedin_followup.

## Requirements

- Python 3.10+
- `curl` (for Gemini API calls - bypasses Python SSL edge cases on some servers)
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

Open an issue first for significant changes.

## License

MIT License. Copyright 2026 Federico De Ponte.
