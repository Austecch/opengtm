# Pipeline Architecture

opengtm is a 5-stage pipeline. Each stage is independent and can be run standalone.

```
Discover -> Research -> Qualify -> Message -> Outreach -> Sync
```

## Stages

### 1. Discover (`opengtm/discover.py`)

**Input:** industry, region, limit
**Output:** `[{company, domain, industry, region}]`

Uses Gemini with Google Search grounding to find real companies matching the industry/region criteria. Validates each domain is reachable before returning.

Key behavior:
- Asks Gemini for `limit + 5` companies (buffer for drops)
- Skips domains already in `existing_domains` set
- HEAD request validation: drops unreachable domains
- 3 retries with backoff on API failures

### 2. Research (`opengtm/research.py`)

**Input:** domain, company, industry
**Output:** `{contact, findings, title_tag_text, meta_description_text, ...}`

Runs a combined Gemini call with Google Search grounding to:
1. Find the decision-maker from Impressum/About/Team pages
2. Run a 7-point technical website audit

LinkedIn URLs are validated (format check + optional HEAD request) to prevent hallucinated URLs from entering the pipeline.

### 3. Qualify (`opengtm/qualify.py`)

**Input:** lead dict with audit data
**Output:** `{score, tier, reasons, recommended_action, breakdown}`

Scores 0-100 across 6 dimensions:
- Company size signals (0-20)
- Industry fit (0-25)
- Digital maturity (0-15)
- Pain signals (0-20)
- Revenue/budget signals (0-10)
- Contact quality (0-10)

Tiers: hot (70+), warm (45-69), cold (<45)

### 4. Message (`opengtm/message.py`)

**Input:** lead + audit data
**Output:** `{pattern, connection_note, first_dm, followup, followup_2, followup_3}`

Pattern selection (A-E) based on best audit finding:
- **A** - Specific technical finding (meta, title, broken, social, schema)
- **B** - Competitor gap (requires manual competitor name)
- **C** - Blog/content not indexed
- **D** - Free tool/resource offer
- **E** - AI visibility angle (peer comparison, fallback)

Both EN and DE output supported.

### 5. Outreach (`opengtm/outreach.py`)

**Input:** qualified leads with messages
**Output:** Sequence state (JSON), due-today queue

Manages 4-touch sequences:
- Touch 1 (Day 0): LinkedIn connection request (280 chars)
- Touch 2 (Day 3): Follow-up DM with finding detail
- Touch 3 (Day 10): Industry peer comparison angle
- Touch 4 (Day 21): Clean breakup

Daily limit enforcement prevents LinkedIn rate limit issues (default: 20 connections/day).

### 6. Sync (`opengtm/sync.py`)

**Input:** leads with messages
**Output:** Posted to Google Sheet via Apps Script doPost webhook

Batches rows (default 50/call) and posts via curl. Requires `CRM_WEBHOOK_URL` env var.

## State Management

Pipeline state is saved as JSON files at each step. This enables resume after failure:

```
/tmp/opengtm-pipeline-*.json   - Full pipeline state
/tmp/opengtm-discovered.json   - Step 1 output
/tmp/opengtm-researched.json   - Step 2 output
/tmp/opengtm-qualified.json    - Step 3 output
/tmp/opengtm-messages.json     - Step 4 output
/tmp/opengtm-outreach-state.json - Sequence state
```

## Error Handling

- Gemini API calls: 3 retries with exponential backoff (4s, 8s, 12s)
- JSON parse errors: retry with same prompt
- Domain validation failures: lead dropped silently
- LinkedIn validation failures: URL set to null, lead continues
- CRM sync failures: logged, non-fatal
