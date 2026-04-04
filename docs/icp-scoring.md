# ICP Scoring Methodology

opengtm scores each lead 0-100 on ICP fit using 6 dimensions derived from website audit signals.

## Why Signal-Based Scoring?

Traditional ICP scoring requires manual data entry (headcount, revenue, tech stack). opengtm infers these from publicly available website signals, making it fully automated.

## Dimensions

### 1. Company Size Signals (0-20 pts)

Inferred from website complexity since headcount isn't directly available:

| Signal | Points | Rationale |
|--------|--------|-----------|
| Has blog/news section | 6 | Requires dedicated content capacity |
| Active social media presence | 4 | Ongoing investment, likely team |
| Complex site (4+ audit signals) | 6 | Larger org has more surface area |
| Specific title tag / positioning | 4 | Deliberate positioning = real business |

Target range: 10-200 employees scores highest. Signals proxy for this.

### 2. Industry Fit (0-25 pts)

Tiered by typical LTV, digital spend, and sales cycle predictability:

| Tier | Industries | Points |
|------|-----------|--------|
| 1 | B2B SaaS, IT Services, Cybersecurity | 25 |
| 2 | Recruiting, Marketing & Advertising, Consulting | 20 |
| 3 | E-Commerce, Financial Services, Accounting, Legal | 15 |
| 4 | Real Estate, Medical, Industrial | 8 |
| 5 | Gastronomie, Fitness, Handwerk | 3 |

### 3. Digital Maturity (0-15 pts)

Higher maturity = company understands digital value, easier to sell to:

| Signal | Points |
|--------|--------|
| Has blog/content | 5 |
| Active social media | 4 |
| Uses schema markup | 3 |
| Consistent site language | 3 |

### 4. Pain Signals (0-20 pts)

More pain = better opportunity. Severity-weighted:

| Severity | Points per unique finding type |
|----------|-------------------------------|
| High | 5 |
| Medium | 3 |
| Low | 1 |

Examples: missing meta description (high), no social links (medium), no schema (low).

Pain weight multiplier can be set per ICP profile (e.g., `pain_weight: 1.5` for profiles where pain is more predictive).

### 5. Revenue/Budget Signals (0-10 pts)

Proxy for ability to pay:

| Signal | Points |
|--------|--------|
| Has blog (marketing investment) | 3 |
| Active social (ongoing spend) | 3 |
| 2+ high-severity issues (real site, needs work) | 4 |

### 6. Contact Quality (0-10 pts)

Reachability of decision-maker:

| Signal | Points |
|--------|--------|
| Name found | 3 |
| LinkedIn profile verified | 5 |
| Email found | 2 |

## Tiers

| Score | Tier | Action |
|-------|------|--------|
| 70-100 | Hot | Prioritize: connect this week |
| 45-69 | Warm | Connect: standard sequence |
| 0-44 | Cold | Nurture: low priority, long-term pool |

## ICP Profiles

Named profiles configure industry tiers and pain weight:

- **saas**: B2B SaaS/tech focus, extra pain weight (1.2x)
- **agency**: Marketing/design agencies, requires blog
- **professional_services**: Law/finance/consulting
- **default**: General B2B, equal weighting

Custom profiles supported via `custom_profile` parameter.

## Limitations

- Size scoring is a proxy, not actual headcount
- Pain signals assume audit quality is high (requires real Gemini+Search grounding)
- Industry fit scores are opinionated defaults; adjust INDUSTRY_TIERS for your market
