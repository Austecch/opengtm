# Message Frameworks

opengtm generates outreach using 5 pattern categories (A-E), each mapped to specific audit findings.

## Pattern Selection Logic

```
Audit findings present?
  No  -> Pattern E (AI visibility angle, safe fallback)
  Yes -> All positive?
    Yes -> Pattern E (clean site angle)
    No  -> Select by best finding type:
      Blog not indexed     -> Pattern C
      Meta description     -> Pattern A (meta variant)
      Title tag issue      -> Pattern A (title variant)
      Broken elements      -> Pattern A (broken variant)
      Language mismatch    -> Pattern A (language variant)
      Missing social links -> Pattern A (social variant)
      Missing schema       -> Pattern A (schema variant)
      Other                -> Pattern A (generic)
```

Always-available alternatives (B, D, E) are included in every output as `alternatives`.

## Patterns

### Pattern A: Specific Technical Finding

The strongest pattern. Uses a real, verifiable finding as the opening hook.

**When to use:** Any time the audit returns a high-severity finding.

**Example (EN - meta description missing):**
```
Jane, I noticed example.com has no meta description.
Google shows random text snippets in search results instead.
Quick win, 5 minutes of work. Intentional, or an oversight?
```

**Why it works:**
- Hyper-specific (not "your SEO could be better")
- States the consequence, not just the problem
- Low-friction binary CTA

### Pattern B: Competitor Gap

Requires manual competitor name insertion. High impact when the competitor is well-known to the prospect.

**Template:**
```
[contact], [COMPETITOR] shows up in ChatGPT for [industry], [company] doesn't yet.
I looked at why. Relevant?
```

**When to use:** When you know a direct competitor the prospect cares about.

### Pattern C: Blog/Content Not Indexed

Specific to companies with a blog that isn't getting indexed. Highly personalized because it shows you actually looked at their content.

**Example:**
```
I noticed your blog on example.com isn't being picked up well by search engines.
The content is there, but it's not surfacing in searches.
Usually 1-2 technical fixes. On your radar?
```

### Pattern D: Free Tool Offer

Lowest friction. Links to or describes a free analysis tool.

**When to use:** When other patterns don't fit, or for very cold prospects.

### Pattern E: AI Visibility Angle (Peer Comparison)

The universal fallback. Positions you as a researcher, not a vendor. Uses peer comparison (industry/region benchmarks) as social proof.

**Example:**
```
I tested whether example.com shows up in ChatGPT and Perplexity.
Most IT service providers in Berlin don't yet.
I have the results for Example Co. Relevant?
```

**When to use:** Audit failed, no findings, all positive findings, or as a primary angle when AI visibility is the core value prop.

## Follow-Up Sequence

Every pattern generates a 3-touch follow-up sequence with angle rotation:

| Touch | Timing | Angle |
|-------|--------|-------|
| 1 (first_dm) | Day 0 | Specific finding + soft CTA |
| 2 (followup) | Day 3 | Concrete fix preview + offer to share |
| 3 (followup_2) | Day 10 | Industry peer comparison (new angle) |
| 4 (followup_3) | Day 21 | Clean breakup |

The follow-up sequence adapts based on whether findings exist:
- **With findings:** Touch 2 reveals the specific fix ("Had another look - meta description is missing, 5 min fix. Happy to share the overview.")
- **No findings (clean site):** Touch 2 pivots to AI visibility angle ("Technically clean, but not showing up in ChatGPT/Perplexity...")
- **Audit failed:** Touch 2 uses pure comparison angle

## Language Support

All patterns are available in both English (`language="en"`) and German (`language="de"`).

German output is calibrated for DACH B2B norms:
- Formal address for Finance/Legal/Medical/Consulting (Herr/Frau Nachname)
- Informal first-name for Tech/Startup
- Real German umlauts (no oe/ue/ae substitutions)
- Shorter CTAs ("Relevant?" not "Would you be interested in learning more?")

## Character Limits

| Message | Limit | Why |
|---------|-------|-----|
| Connection note | 280 chars | LinkedIn connection request limit |
| First DM | ~500 chars | LinkedIn DM best practice |
| Follow-ups | ~500 chars | LinkedIn DM best practice |

opengtm does not hard-truncate messages, but templates are designed to stay within these limits.
