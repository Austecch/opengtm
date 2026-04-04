"""
qualify.py - ICP scoring and lead qualification.

Scores leads 0-100 on ICP fit using signals from research output.
Returns tier (hot/warm/cold) and recommended action.

Scoring dimensions:
  - Company size signals       (0-20 pts)
  - Industry fit               (0-25 pts)
  - Digital maturity           (0-15 pts)
  - Pain signals               (0-20 pts)
  - Revenue/budget signals     (0-10 pts)
  - Contact quality            (0-10 pts)
"""

from __future__ import annotations

from typing import Optional


# Industry fit tiers. Add or override via icp_profile dicts.
INDUSTRY_TIERS: dict[str, int] = {
    # Tier 1: Strong ICP (25 pts) - high digital awareness, B2B buyers
    "B2B SaaS": 25,
    "SaaS": 25,
    "IT Services": 25,
    "Cybersecurity": 25,
    "Systemhaus": 25,
    # Tier 2: Good ICP (20 pts) - decent digital budgets, understand value
    "Recruiting": 20,
    "Personalberatung": 20,
    "Marketing & Advertising": 20,
    "Design": 20,
    "Management Consulting": 20,
    # Tier 3: Moderate ICP (15 pts) - can convert, need more education
    "E-Commerce": 15,
    "Financial Services": 15,
    "Accounting": 15,
    "Steuerberater": 15,
    "Steuerberatung": 15,
    "Legal Services": 15,
    # Tier 4: Lower ICP (8 pts) - possible but harder sales cycles
    "Real Estate": 8,
    "Immobilien": 8,
    "Medical": 8,
    "Industrial": 8,
    "Logistik": 8,
    "Architektur": 8,
    # Tier 5: Poor ICP (3 pts) - rarely a good fit
    "Gastronomie": 3,
    "Fitness": 3,
    "Handwerk": 3,
    "Bildung": 3,
}

# ICP profiles: named preset configurations for qualify()
ICP_PROFILES: dict[str, dict] = {
    "saas": {
        "name": "B2B SaaS / Tech",
        "top_industries": ["B2B SaaS", "SaaS", "IT Services", "Cybersecurity"],
        "ideal_size_range": (10, 200),
        "require_blog": False,
        "pain_weight": 1.2,  # Extra weight on pain signals for this ICP
    },
    "agency": {
        "name": "Marketing / Design Agencies",
        "top_industries": ["Marketing & Advertising", "Design", "IT Services"],
        "ideal_size_range": (5, 100),
        "require_blog": True,
        "pain_weight": 1.1,
    },
    "professional_services": {
        "name": "Professional Services (Law, Finance, Consulting)",
        "top_industries": ["Legal Services", "Financial Services", "Accounting", "Management Consulting"],
        "ideal_size_range": (5, 150),
        "require_blog": False,
        "pain_weight": 1.0,
    },
    "default": {
        "name": "General B2B",
        "top_industries": list(INDUSTRY_TIERS.keys()),
        "ideal_size_range": (5, 200),
        "require_blog": False,
        "pain_weight": 1.0,
    },
}


def _score_company_size(research_data: dict) -> tuple[int, list[str]]:
    """
    Score 0-20 based on inferred company size.
    Signals: team page presence, number of findings (proxy for site complexity),
    blog/news presence, social link diversity.
    """
    score = 0
    reasons = []

    findings = research_data.get("findings", [])
    has_blog = research_data.get("has_blog_or_news", False)
    has_social = research_data.get("has_social_links", False)
    title_text = research_data.get("title_tag_text", "")

    # A site with a blog and social links suggests at least a few employees
    if has_blog:
        score += 6
        reasons.append("Has blog/news (company with content capacity)")
    if has_social:
        score += 4
        reasons.append("Has social media presence")

    # More findings = more complex/larger site
    n_findings = len(findings)
    if n_findings >= 4:
        score += 6
        reasons.append(f"Complex site ({n_findings} audit signals = larger org)")
    elif n_findings >= 2:
        score += 3
        reasons.append(f"Medium site complexity ({n_findings} audit signals)")
    else:
        score += 1

    # Title with specific niche/positioning signals a real business
    if title_text and len(title_text) > 10:
        score += 4
        reasons.append("Specific title tag (positioned company)")

    return min(score, 20), reasons


def _score_industry_fit(industry: str, icp_profile: dict) -> tuple[int, list[str]]:
    """Score 0-25 based on industry tier and ICP profile match."""
    if not industry:
        return 5, ["No industry data (unknown fit)"]

    base = INDUSTRY_TIERS.get(industry, 5)

    top_industries = icp_profile.get("top_industries", [])
    if industry in top_industries:
        return 25, [f"{industry} is a top ICP industry for this profile"]

    if base >= 20:
        return base, [f"{industry} is a strong ICP industry (tier 1)"]
    elif base >= 15:
        return base, [f"{industry} is a good ICP industry (tier 2)"]
    elif base >= 8:
        return base, [f"{industry} is a moderate ICP fit (tier 3)"]
    else:
        return base, [f"{industry} is a weak ICP fit (tier 4-5)"]


def _score_digital_maturity(research_data: dict) -> tuple[int, list[str]]:
    """
    Score 0-15 based on digital sophistication.
    Higher maturity = understands the value of digital presence work.
    """
    score = 0
    reasons = []

    has_blog = research_data.get("has_blog_or_news", False)
    has_social = research_data.get("has_social_links", False)
    findings = research_data.get("findings", [])
    has_schema = any(f.get("type") == "schema" for f in findings)

    if has_blog:
        score += 5
        reasons.append("Has content/blog (invests in digital presence)")
    if has_social:
        score += 4
        reasons.append("Active on social media (digital-first mindset)")
    if has_schema:
        score += 3
        reasons.append("Uses schema markup (technically sophisticated)")

    # Site language: clean single-language site = more mature
    lang = research_data.get("site_language", "")
    if lang in ("en", "de"):
        score += 3
        reasons.append("Consistent site language (clean implementation)")
    elif lang == "mixed":
        reasons.append("Mixed language site (digital immaturity signal)")

    return min(score, 15), reasons


def _score_pain_signals(research_data: dict, pain_weight: float = 1.0) -> tuple[int, list[str]]:
    """
    Score 0-20 based on pain signal intensity.
    More pain = better opportunity (they need the work).
    """
    findings = research_data.get("findings", [])
    if not findings:
        return 5, ["No audit findings (clean site or audit failed)"]

    score = 0
    reasons = []

    sev_points = {"high": 5, "medium": 3, "low": 1}
    seen_types: set[str] = set()

    for f in findings:
        ftype = f.get("type", "other")
        severity = f.get("severity", "low")
        pts = sev_points.get(severity, 1)

        if ftype not in seen_types:
            score += pts
            seen_types.add(ftype)
            detail = f.get("detail", "")[:60]
            reasons.append(f"{severity.upper()} {ftype}: {detail}")

    # Cap and apply weight
    score = min(int(score * pain_weight), 20)
    return score, reasons


def _score_revenue_signals(research_data: dict) -> tuple[int, list[str]]:
    """
    Score 0-10 based on revenue/budget proxy signals.
    Pricing page, case studies, testimonials = they sell and have budget.
    """
    score = 0
    reasons = []

    title = research_data.get("title_tag_text", "").lower()
    assessment = research_data.get("overall_assessment", "").lower()
    findings = research_data.get("findings", [])

    # Blog = content investment = budget
    if research_data.get("has_blog_or_news", False):
        score += 3
        reasons.append("Has content/blog (budget for marketing)")

    # Social links = ongoing investment
    if research_data.get("has_social_links", False):
        score += 3
        reasons.append("Active social presence (marketing spend)")

    # Multiple high-severity findings = they have a real site that needs work
    high_sev = [f for f in findings if f.get("severity") == "high"]
    if len(high_sev) >= 2:
        score += 4
        reasons.append(f"{len(high_sev)} high-severity issues (site has investment but needs work)")
    elif len(high_sev) == 1:
        score += 2

    return min(score, 10), reasons


def _score_contact_quality(research_data: dict) -> tuple[int, list[str]]:
    """Score 0-10 based on how reachable the decision-maker is."""
    contact = research_data.get("contact", {})
    score = 0
    reasons = []

    name = contact.get("name", "")
    email = contact.get("email")
    linkedin = contact.get("linkedin_url")

    if name:
        score += 3
        reasons.append(f"Contact name found: {name}")
    if linkedin:
        score += 5
        reasons.append("LinkedIn profile found (direct outreach possible)")
    if email:
        score += 2
        reasons.append("Email found (email outreach possible)")

    if not name and not email and not linkedin:
        reasons.append("No contact info found (cold outreach only)")

    return min(score, 10), reasons


def qualify(
    lead: dict,
    icp_profile: str = "default",
    custom_profile: Optional[dict] = None,
) -> dict:
    """
    Score a lead on ICP fit (0-100) and return qualification result.

    Args:
        lead: Dict containing research_data (from research.py) plus:
              - domain (str)
              - company (str)
              - industry (str, optional)
              - region (str, optional)
        icp_profile: Named profile key from ICP_PROFILES, or "default"
        custom_profile: Override the ICP profile dict entirely

    Returns:
        Dict with: score (0-100), tier (hot/warm/cold), reasons (list),
                   recommended_action (str), breakdown (dict of dimension scores)
    """
    research_data = lead.get("audit") or lead.get("research_data") or lead
    industry = lead.get("industry", "")
    domain = lead.get("domain", "")
    company = lead.get("company", domain)

    profile = custom_profile or ICP_PROFILES.get(icp_profile, ICP_PROFILES["default"])
    pain_weight = profile.get("pain_weight", 1.0)

    # Score each dimension
    size_score, size_reasons = _score_company_size(research_data)
    industry_score, industry_reasons = _score_industry_fit(industry, profile)
    maturity_score, maturity_reasons = _score_digital_maturity(research_data)
    pain_score, pain_reasons = _score_pain_signals(research_data, pain_weight)
    revenue_score, revenue_reasons = _score_revenue_signals(research_data)
    contact_score, contact_reasons = _score_contact_quality(research_data)

    total = size_score + industry_score + maturity_score + pain_score + revenue_score + contact_score
    total = min(total, 100)

    # Determine tier
    if total >= 70:
        tier = "hot"
        action = "prioritize: connect on LinkedIn this week"
    elif total >= 45:
        tier = "warm"
        action = "connect: add to standard outreach sequence"
    else:
        tier = "cold"
        action = "nurture: low priority, add to long-term pool"

    # Build flat reasons list (top signals only)
    all_reasons = (
        industry_reasons[:1]
        + pain_reasons[:2]
        + contact_reasons[:1]
        + size_reasons[:1]
        + maturity_reasons[:1]
    )

    return {
        "domain": domain,
        "company": company,
        "score": total,
        "tier": tier,
        "recommended_action": action,
        "reasons": all_reasons,
        "breakdown": {
            "company_size": size_score,
            "industry_fit": industry_score,
            "digital_maturity": maturity_score,
            "pain_signals": pain_score,
            "revenue_signals": revenue_score,
            "contact_quality": contact_score,
        },
    }


def qualify_batch(
    leads: list[dict],
    icp_profile: str = "default",
    custom_profile: Optional[dict] = None,
    verbose: bool = True,
) -> list[dict]:
    """
    Qualify a list of leads and return sorted by score descending.

    Args:
        leads:        List of lead dicts (each with audit/research_data inside)
        icp_profile:  Named profile or "default"
        custom_profile: Override profile dict
        verbose:      Print progress

    Returns:
        List of qualification results sorted by score descending
    """
    results = []
    for lead in leads:
        result = qualify(lead, icp_profile=icp_profile, custom_profile=custom_profile)
        results.append({**lead, "qualification": result})
        if verbose:
            tier = result["tier"].upper()
            print(
                f"  {result['company']} ({result['domain']}): "
                f"{result['score']}/100 [{tier}] - {result['recommended_action']}",
                flush=True,
            )

    results.sort(key=lambda x: x["qualification"]["score"], reverse=True)
    return results
