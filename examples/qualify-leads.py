#!/usr/bin/env python3
"""
qualify-leads.py - Standalone ICP qualification example.

Shows how to use opengtm's qualify module in isolation,
without running the full discovery + research pipeline.

Usage:
    python examples/qualify-leads.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from opengtm.qualify import qualify, qualify_batch, ICP_PROFILES


# Example leads with mocked audit data (in practice, this comes from research.py)
SAMPLE_LEADS = [
    {
        "domain": "example-saas.com",
        "company": "Example SaaS Co",
        "industry": "B2B SaaS",
        "contact_name": "Jane Smith",
        "linkedin_url": "https://linkedin.com/in/janesmith",
        "audit": {
            "contact": {"name": "Jane Smith", "title": "CEO", "linkedin_url": "https://linkedin.com/in/janesmith"},
            "findings": [
                {"type": "meta_description", "severity": "high", "detail": "Meta description missing", "evidence": ""},
                {"type": "social_links", "severity": "medium", "detail": "No social links on homepage", "evidence": ""},
            ],
            "has_blog_or_news": True,
            "has_social_links": False,
            "site_language": "en",
            "overall_assessment": "Good site with missing meta description and social links",
        },
    },
    {
        "domain": "local-bakery.com",
        "company": "Schmidt's Bakery",
        "industry": "Gastronomie",
        "contact_name": "",
        "linkedin_url": None,
        "audit": {
            "contact": {"name": "", "title": "", "linkedin_url": None},
            "findings": [],
            "has_blog_or_news": False,
            "has_social_links": False,
            "site_language": "de",
            "overall_assessment": "Simple site, no major issues",
        },
    },
    {
        "domain": "it-consulting-berlin.de",
        "company": "IT Consulting Berlin GmbH",
        "industry": "IT Services",
        "contact_name": "Klaus Müller",
        "linkedin_url": "https://linkedin.com/in/klausmuller",
        "audit": {
            "contact": {
                "name": "Klaus Müller", "title": "Geschäftsführer",
                "email": "k.mueller@it-consulting-berlin.de",
                "linkedin_url": "https://linkedin.com/in/klausmuller",
            },
            "findings": [
                {"type": "title_tag", "severity": "high", "detail": "Title says 'Willkommen' - too generic", "evidence": "Willkommen"},
                {"type": "meta_description", "severity": "high", "detail": "Meta description is 45 chars - too short", "evidence": "IT Beratung Berlin"},
                {"type": "schema", "severity": "low", "detail": "No schema markup", "evidence": ""},
                {"type": "social_links", "severity": "medium", "detail": "No social links", "evidence": ""},
            ],
            "has_blog_or_news": True,
            "has_social_links": False,
            "site_language": "de",
            "overall_assessment": "Generic title and short meta description are main issues",
        },
    },
]


def main():
    print("opengtm - ICP Qualification Example")
    print("=" * 50)

    # Show available profiles
    print("\nAvailable ICP profiles:")
    for name, profile in ICP_PROFILES.items():
        print(f"  {name}: {profile['name']}")

    # Score individual lead
    print("\n--- Single lead qualification (SaaS profile) ---")
    result = qualify(SAMPLE_LEADS[0], icp_profile="saas")
    print(f"Company: {result['company']}")
    print(f"Score:   {result['score']}/100")
    print(f"Tier:    {result['tier'].upper()}")
    print(f"Action:  {result['recommended_action']}")
    print("Why:")
    for reason in result["reasons"]:
        print(f"  - {reason}")
    print("Breakdown:")
    for dim, score in result["breakdown"].items():
        print(f"  {dim}: {score}")

    # Score batch
    print("\n--- Batch qualification (default profile) ---")
    results = qualify_batch(SAMPLE_LEADS, icp_profile="default", verbose=True)

    print("\n--- Results sorted by score ---")
    for r in results:
        q = r["qualification"]
        print(
            f"  [{q['tier'].upper():4}] {q['score']:3}/100  "
            f"{r['company']} ({r['domain']})"
        )

    # Custom profile example
    print("\n--- Custom ICP profile ---")
    custom_profile = {
        "name": "High-growth startups",
        "top_industries": ["B2B SaaS", "SaaS", "Cybersecurity"],
        "ideal_size_range": (20, 500),
        "require_blog": True,
        "pain_weight": 1.5,  # Extra weight on pain signals
    }
    result_custom = qualify(SAMPLE_LEADS[2], custom_profile=custom_profile)
    print(f"{result_custom['company']}: {result_custom['score']}/100 [{result_custom['tier'].upper()}]")
    print(f"Action: {result_custom['recommended_action']}")


if __name__ == "__main__":
    main()
