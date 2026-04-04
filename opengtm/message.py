"""
message.py - Outreach message generation from audit findings.

Adapted from SignalDash prospect-engine.py build_messages().
Generates personalized LinkedIn connection requests + DM sequences
based on specific website audit findings.

Supports English and German (DACH-calibrated) output.
Language is controlled by OPENGTM_LANGUAGE env var or language parameter.

Pattern framework:
  A - Specific technical finding (title, meta, broken element, etc.)
  B - Competitor gap (manual competitor name required)
  C - Blog/content not indexed
  D - Free tool / resource offer
  E - AI visibility angle (peer comparison)
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional


DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "en")


# ---------------------------------------------------------------------------
# Language strings (EN + DE)
# ---------------------------------------------------------------------------

_STRINGS = {
    "en": {
        "connection_micro": {
            "no_meta": "I noticed {domain} doesn't have a meta description.",
            "meta_issue": "I checked {domain} and noticed some quick wins on the meta description.",
            "content": "Your blog on {domain} has untapped SEO potential.",
            "generic": "I had a look at {domain} and noticed a few things.",
        },
        "connection_variants": {
            "micro": [
                "{micro} Exploring {industry_nom} in {region}. Connect?",
                "Exploring {industry_nom} and AI visibility. {micro} Connect?",
                "{micro} Happy to share. Connect?",
            ],
            "no_micro": [
                "Looking at how {industry_nom} rank in AI search (ChatGPT, Perplexity). Have data on {domain}. Connect?",
                "Comparing {industry_nom} in AI search engines. {company} is on my list. Connect?",
                "Researching AI visibility of {industry_nom} in {region}. Have results for {domain}. Connect?",
            ],
        },
        "pat_d": "{addr}do you know your AI visibility? You can check how {domain} ranks in ChatGPT and Perplexity in 60 seconds. Worth a look?",
        "pat_e": "{addr}I tested whether {domain} shows up in ChatGPT and Perplexity. Most {industry_nom} in {region} don't yet. I have the results for {company}. Relevant?",
        "pat_b": "{addr}[COMPETITOR] shows up in ChatGPT for {industry_nom}, {company} doesn't yet. I looked at why. Relevant?",
        "blog_pat_c": "{addr}I noticed your blog on {domain} isn't being picked up well by search engines. The content is there, but it's not surfacing in searches. Usually 1-2 technical fixes. On your radar?",
        "meta_missing": "{addr}I noticed {domain} has no meta description. Google shows random text snippets in search results instead. Quick win, 5 minutes of work. {extra}",
        "meta_short": "{addr}the meta description on {domain} is quite short{char_info}. With 120-160 characters you'd get significantly more clicks from search results. {extra}",
        "meta_long": "{addr}the meta description on {domain} gets cut off in search results. Your core message doesn't come through fully. {extra}",
        "title_generic": "{addr}the title tag on {domain} says \"{title_preview}\". A more specific title would improve rankings for relevant searches. {extra}",
        "title_long": "{addr}the title tag on {domain} is {title_len} characters, but Google only shows 60. Your main message gets cut off. {extra}",
        "title_stuffed": "{addr}the title tag on {domain} says \"{title_preview}\". Google prefers clear, focused titles over keyword lists today. {extra}",
        "broken_placeholder": "{addr}there's placeholder text visible on {domain} that probably shouldn't be there. Search engines and visitors notice this. Quick fix. {extra}",
        "broken_links": "{addr}I noticed some links on {domain} go nowhere (href=\"#\"). Quick fix that improves user experience. {extra}",
        "broken_generic": "{addr}there are a few broken elements on {domain} that visitors might notice. Usually quick fixes. {extra}",
        "language_mismatch": "{addr}I noticed parts of {domain} are in one language while the rest is in another. Search engines can't assign a clear language to the site. Quick fix. {extra}",
        "social_links": "{addr}there are no links to {company}'s social media profiles on {domain}. Visitors and search engines miss trust signals. {extra}",
        "schema": "{addr}{domain} doesn't use schema markup yet. With it you could stand out in Google with rich snippets (ratings, prices, FAQ). {extra}",
        "generic_findings": "{addr}I had a look at {domain} and found {n_str} that could improve your visibility. Can I send you the details?",
        "extra_one": "Intentional, or an oversight?",
        "extra_multi": "On your radar?",
        "fu1_base": "Had another look at {domain}. {bestfix}. {rest} Happy to share the overview.",
        "fu2_base": "Quick data point: of 20+ {industry_nom} in {region}, about 60% have the same issues as {domain}. Seems industry-typical. Want to know where you stand?",
        "fu3_base": "Last message on {domain}. If this isn't the right time, no problem. The findings stay with us if that changes.",
        "fu1_no_findings": "Made a comparison: AI visibility of {domain} vs other {industry_nom} in {region}. Can I send you the results?",
        "fu2_no_findings": "Quick stat: only about 20% of {industry_nom} in {region} get recommended by AI search engines. I have the data for {company}, happy to share.",
        "fu1_clean": "Had another look at {domain}: technically clean, but not visible in ChatGPT and Perplexity. More common than you'd think. Can I show you why?",
        "fu2_clean": "Quick stat: even technically clean sites like {domain} are often invisible to AI search engines. I have the comparison with other {industry_nom} in {region}, happy to share.",
        "bestfix": {
            "meta_description_missing": "meta description is missing entirely, can be added in 5 minutes",
            "meta_description": "optimizing the meta description directly improves click-through from Google",
            "title_tag": "adjusting the title tag is the fastest lever for better search rankings",
            "content_indexing": "blog content isn't being indexed, usually 1-2 technical settings",
            "social_links": "adding social media links builds trust signals on the website",
            "broken_element": "a broken element on the homepage can be fixed quickly",
            "schema": "schema markup is missing, rich snippets would help you stand out in search",
            "language_mismatch": "language inconsistency confuses search engines, quick to unify",
            "default": "a quick win can be implemented right away",
        },
    },
    "de": {
        "connection_micro": {
            "no_meta": "Mir ist aufgefallen, dass {domain} keine Meta-Description hat.",
            "meta_issue": "Habe mir {domain} angeschaut, bei der Meta-Description gibt es Quick Wins.",
            "content": "Euer Blog auf {domain} hat ungenutztes SEO-Potenzial.",
            "generic": "Habe mir {domain} angeschaut, ein paar Sachen aufgefallen.",
        },
        "connection_variants": {
            "micro": [
                "{micro} Schaue mir gerade {industry_nom} in {region} an. Vernetzen?",
                "Schaue mir gerade {industry_nom} und KI-Sichtbarkeit an. {micro} Vernetzen?",
                "{micro} Kann ich gern teilen. Vernetzen?",
            ],
            "no_micro": [
                "Schaue mir gerade an, wie {industry_nom} bei ChatGPT und Perplexity abschneiden. Habe Daten zu {domain}. Vernetzen?",
                "Vergleiche gerade {industry_nom} bei KI-Suchmaschinen. {company} ist dabei. Vernetzen?",
                "Recherchiere KI-Sichtbarkeit von {industry_nom} in {region}. Habe Ergebnisse für {domain}. Vernetzen?",
            ],
        },
        "pat_d": "{addr}kennt ihr eure KI-Sichtbarkeit? Auf einem Check-Tool kann man in 60 Sekunden sehen wie {domain} bei ChatGPT und Perplexity abschneidet. Spannend?",
        "pat_e": "{addr}habe getestet, ob {domain} bei ChatGPT und Perplexity auftaucht. Bei den meisten {industry_nom} in {region} ist das noch nicht der Fall. Habe die Ergebnisse für {company}. Relevant?",
        "pat_b": "{addr}[WETTBEWERBER] taucht bei ChatGPT für {industry_nom} auf, {company} noch nicht. Habe mir angeschaut woran das liegt. Relevant?",
        "blog_pat_c": "{addr}mir ist aufgefallen, dass euer Blog auf {domain} von Suchmaschinen kaum erfasst wird. Die Inhalte sind da, kommen aber bei Suchanfragen nicht an. Liegt meistens an 1-2 technischen Kleinigkeiten. Habt ihr das auf dem Schirm?",
        "meta_missing": "{addr}mir ist aufgefallen, dass {domain} keine Meta-Description hat. Google zeigt dann zufällige Textfragmente in den Suchergebnissen. Ist ein Quick Win, 5 Minuten Arbeit. {extra}",
        "meta_short": "{addr}die Meta-Description von {domain} ist recht kurz{char_info}. Mit 120-160 Zeichen holt ihr deutlich mehr Klicks aus den Suchergebnissen raus. {extra}",
        "meta_long": "{addr}die Meta-Description von {domain} wird in den Suchergebnissen abgeschnitten. Eure Kernaussage kommt dadurch nicht komplett an. {extra}",
        "title_generic": "{addr}im Title-Tag von {domain} steht \"{title_preview}\". Mit einem spezifischeren Title würde {company_first} bei relevanten Suchen besser ankommen. {extra}",
        "title_long": "{addr}der Title-Tag von {domain} hat {title_len} Zeichen, Google zeigt aber nur 60. Eure Kernaussage wird abgeschnitten. {extra}",
        "title_stuffed": "{addr}im Title-Tag von {domain} steht \"{title_preview}\". Google bevorzugt heute klare, fokussierte Titles statt Keyword-Listen. {extra}",
        "broken_placeholder": "{addr}auf {domain} ist ein Platzhaltertext sichtbar, der vermutlich nicht da sein sollte. Fällt Besuchern und Suchmaschinen auf. Schnell behebbar. {extra}",
        "broken_links": "{addr}mir ist aufgefallen, dass auf {domain} einige Links ins Leere führen (href=\"#\"). Lässt sich schnell fixen und verbessert die Nutzererfahrung. {extra}",
        "broken_generic": "{addr}auf {domain} gibt es ein paar defekte Elemente, die Besuchern auffallen könnten. Meistens schnell behebbar. {extra}",
        "language_mismatch": "{addr}mir ist aufgefallen, dass auf {domain} Teile in einer Sprache sind, der Rest in einer anderen. Suchmaschinen können die Seite dadurch keiner Sprache klar zuordnen. Schnell behebbar. {extra}",
        "social_links": "{addr}auf {domain} verweist nichts auf eure Social-Media-Profile. Besucher und Suchmaschinen finden dadurch keine weiteren Vertrauenssignale. {extra}",
        "schema": "{addr}{domain} nutzt noch kein Schema Markup. Damit könntet ihr bei Google mit Rich Snippets auffallen, z.B. Bewertungen, Preise, FAQ. {extra}",
        "generic_findings": "{addr}habe mir {domain} angeschaut und {n_str} gefunden, die eure KI-Sichtbarkeit verbessern könnten. Kann ich euch die Details schicken?",
        "extra_one": "Ist das bewusst so oder ein Versehen?",
        "extra_multi": "Habt ihr das auf dem Schirm?",
        "fu1_base": "Habe mir {domain} nochmal angeschaut. {bestfix}. {rest} Übersicht kann ich gern schicken.",
        "fu2_base": "Kurzer Datenpunkt: von 20+ {industry_nom} in {region} haben ca. 60% dieselben Themen wie {domain}. Scheint branchentypisch. Wollt ihr wissen wo ihr im Vergleich steht?",
        "fu3_base": "Letzte Nachricht zu {domain}. Falls gerade kein Thema, völlig ok. Die Ergebnisse bleiben bei uns, falls sich das ändert.",
        "fu1_no_findings": "Habe einen Vergleich gemacht: KI-Sichtbarkeit von {domain} vs. andere {industry_nom} in {region}. Kann ich euch die Ergebnisse schicken?",
        "fu2_no_findings": "Kurzer Datenpunkt: von den {industry_nom} in {region} werden nur ca. 20% von KI-Suchmaschinen empfohlen. Habe die Daten für {company}, kann ich gern teilen.",
        "fu1_clean": "Habe mir {domain} nochmal angeschaut: technisch sauber, aber bei ChatGPT und Perplexity nicht sichtbar. Kommt häufiger vor als man denkt. Kann ich euch zeigen woran das liegt?",
        "fu2_clean": "Kurzer Datenpunkt: auch technisch saubere Seiten wie {domain} sind oft bei KI-Suchmaschinen unsichtbar. Habe den Vergleich mit anderen {industry_nom} in {region}, kann ich gern teilen.",
        "bestfix": {
            "meta_description_missing": "Meta-Description fehlt komplett, lässt sich in 5 Minuten ergänzen",
            "meta_description": "Meta-Description optimieren bringt direkt mehr Klicks aus Google",
            "title_tag": "Title-Tag anpassen ist der schnellste Hebel für bessere Suchergebnisse",
            "content_indexing": "Blog-Inhalte werden nicht indexiert, meistens liegt es an 1-2 technischen Einstellungen",
            "social_links": "Social-Media-Links auf der Website einbinden stärkt die Vertrauenssignale",
            "broken_element": "ein defektes Element auf der Startseite lässt sich schnell beheben",
            "schema": "Schema Markup fehlt, mit Rich Snippets hebt ihr euch in den Suchergebnissen ab",
            "language_mismatch": "Sprachmix verwirrt Suchmaschinen, lässt sich schnell vereinheitlichen",
            "default": "ein Quick Win lässt sich direkt umsetzen",
        },
    },
}

# Industry display names for messages (nominative form)
INDUSTRY_DISPLAY: dict[str, dict[str, str]] = {
    "en": {
        "IT Services": "IT service providers",
        "Marketing & Advertising": "marketing agencies",
        "Financial Services": "financial service firms",
        "Accounting": "accounting firms",
        "Legal Services": "law firms",
        "Management Consulting": "consulting firms",
        "Design": "design agencies",
        "Recruiting": "recruiting firms",
        "E-Commerce": "e-commerce companies",
        "Cybersecurity": "cybersecurity firms",
        "SaaS": "SaaS companies",
        "B2B SaaS": "B2B SaaS companies",
        "Medical": "medical practices",
        "Real Estate": "real estate companies",
        "Industrial": "industrial companies",
        "Systemhaus": "IT solution providers",
    },
    "de": {
        "IT Services": "IT-Dienstleistern",
        "Marketing & Advertising": "Agenturen",
        "Financial Services": "Steuerberatungen und Finanzdienstleistern",
        "Accounting": "Wirtschaftsprüfern und Kanzleien",
        "Legal Services": "Kanzleien",
        "Management Consulting": "Beratungen",
        "Design": "Designbüros und Agenturen",
        "Recruiting": "Personalberatungen",
        "Personalberatung": "Personalberatungen",
        "E-Commerce": "E-Commerce-Unternehmen",
        "Cybersecurity": "Cybersecurity-Unternehmen",
        "SaaS": "SaaS-Unternehmen",
        "B2B SaaS": "B2B SaaS-Unternehmen",
        "Medical": "Privatkliniken und Praxen",
        "Real Estate": "Immobilienunternehmen",
        "Immobilien": "Immobilienunternehmen",
        "Industrial": "Industrieunternehmen",
        "Steuerberater": "Steuerberatern",
        "Steuerberatung": "Steuerberatungen",
        "Systemhaus": "Systemhäusern",
    },
}


def _hash_variant(key: str, domain: str, n: int) -> int:
    """Deterministic variant selector (same domain always gets same variant)."""
    return int(hashlib.md5((key + domain).encode()).hexdigest(), 16) % n


def _get_address(contact_name: str, contact_title: str = "", industry: str = "", language: str = "en") -> str:
    """Build a personalized address prefix for the message."""
    if not contact_name:
        return ""
    parts = contact_name.strip().split()
    formal_industries = {
        "Financial Services", "Accounting", "Legal Services",
        "Management Consulting", "Medical", "Real Estate",
    }
    if industry in formal_industries:
        if language == "de":
            female_indicators = [
                "geschäftsführerin", "inhaberin", "gründerin", "partnerin",
                "direktorin", "leiterin", "managerin", "beraterin",
                "rechtsanwältin", "steuerberaterin",
            ]
            is_female = any(t in contact_title.lower() for t in female_indicators)
            prefix = "Frau" if is_female else "Herr"
            return f"{prefix} {parts[-1]}, "
        else:
            return f"{parts[0]}, "
    return f"{parts[0]}, "


def generate_messages(
    domain: str,
    company: str,
    contact_name: str = "",
    industry: str = "",
    audit: Optional[dict] = None,
    region: str = "",
    contact_title: str = "",
    language: str = "",
) -> dict:
    """
    Generate a full outreach message set from audit findings.

    Args:
        domain:        Company website domain
        company:       Company name
        contact_name:  Decision-maker's name (for personalization)
        industry:      Industry vertical
        audit:         Dict from research.py (findings, title_tag_text, etc.)
        region:        City/region for peer comparison messages
        contact_title: Contact's job title (used for formal/informal address)
        language:      "en" or "de" (defaults to DEFAULT_LANGUAGE env var or "en")

    Returns:
        Dict with: pattern (A/B/C/D/E), pattern_reason, best_finding,
                   connection_note, first_dm, followup, followup_2, followup_3,
                   alternatives (list of other pattern options)
    """
    lang = language or DEFAULT_LANGUAGE
    if lang not in _STRINGS:
        lang = "en"
    s = _STRINGS[lang]

    if domain.startswith("www."):
        domain = domain[4:]

    industry_nom = INDUSTRY_DISPLAY.get(lang, {}).get(industry) or (
        INDUSTRY_DISPLAY["en"].get(industry, industry or ("companies" if lang == "en" else "Unternehmen"))
    )
    addr = _get_address(contact_name, contact_title, industry, lang)
    company_first = company.split()[0] if company else domain
    reg = region or ("the region" if lang == "en" else "der Region")

    # Build follow-ups (audit-failed branch)
    fu1_fail = s["fu1_no_findings"].format(
        domain=domain, industry_nom=industry_nom, region=reg, company=company
    )
    fu2_fail = s["fu2_no_findings"].format(
        domain=domain, industry_nom=industry_nom, region=reg, company=company
    )
    fu3 = s["fu3_base"].format(domain=domain)

    # Build always-available patterns
    pat_d = s["pat_d"].format(addr=addr, domain=domain)
    pat_e = s["pat_e"].format(addr=addr, domain=domain, industry_nom=industry_nom, region=reg, company=company)
    pat_b = s["pat_b"].format(addr=addr, domain=domain, industry_nom=industry_nom, company=company)

    alternatives = [
        {"pattern": "D", "reason": "Free tool / resource offer", "dm": pat_d},
        {"pattern": "E", "reason": "AI visibility angle (peer comparison)", "dm": pat_e},
        {"pattern": "B", "reason": "Competitor gap (fill in competitor name manually)", "dm": pat_b},
    ]

    # Build connection note
    _micro = ""
    if audit and audit.get("findings"):
        meta_text = audit.get("meta_description_text", "")
        ffindings = audit["findings"]
        if meta_text and "MISSING" in str(meta_text).upper():
            _micro = s["connection_micro"]["no_meta"].format(domain=domain)
        elif any(f.get("type") == "meta_description" for f in ffindings):
            _micro = s["connection_micro"]["meta_issue"].format(domain=domain)
        elif any(f.get("type") == "content_indexing" for f in ffindings):
            _micro = s["connection_micro"]["content"].format(domain=domain)
        elif ffindings:
            _micro = s["connection_micro"]["generic"].format(domain=domain)

    if _micro:
        variants = s["connection_variants"]["micro"]
        cn = variants[_hash_variant("sd1", domain, len(variants))].format(
            micro=_micro, industry_nom=industry_nom, region=reg
        )
    else:
        variants = s["connection_variants"]["no_micro"]
        cn = variants[_hash_variant("sd1", domain, len(variants))].format(
            industry_nom=industry_nom, region=reg, domain=domain, company=company
        )

    def _fu(bestfix_key: str, n_rest: int) -> tuple[str, str, str]:
        bestfix = s["bestfix"].get(bestfix_key, s["bestfix"]["default"])
        if n_rest == 0:
            rest = ""
        elif n_rest == 1:
            rest = "Plus 1 more." if lang == "en" else "Dazu noch 1 weiterer Punkt."
        else:
            rest = f"Plus {n_rest} more." if lang == "en" else f"Dazu noch {n_rest} weitere Punkte."
        fu1 = s["fu1_base"].format(domain=domain, bestfix=bestfix, rest=rest).strip()
        fu2_v = [
            s["fu2_base"].format(domain=domain, industry_nom=industry_nom, region=reg),
        ]
        return fu1, fu2_v[0], fu3

    def _clean_fu() -> tuple[str, str, str]:
        return (
            s["fu1_clean"].format(domain=domain, industry_nom=industry_nom, region=reg),
            s["fu2_clean"].format(domain=domain, industry_nom=industry_nom, region=reg),
            fu3,
        )

    def _failed_fu() -> tuple[str, str, str]:
        return fu1_fail, fu2_fail, fu3

    # --- No audit or audit failed ---
    if not audit:
        return {
            "pattern": "E", "pattern_reason": "No audit data, AI visibility angle",
            "best_finding": "",
            "connection_note": cn, "first_dm": pat_e,
            "followup": fu1_fail, "followup_2": fu2_fail, "followup_3": fu3,
            "alternatives": alternatives,
        }

    assessment = audit.get("overall_assessment", "")
    audit_failed = any(w in assessment.lower() for w in ["failed", "error", "unable", "could not"])
    findings = audit.get("findings", [])

    if not findings and audit_failed:
        fu1, fu2, _ = _failed_fu()
        return {
            "pattern": "E", "pattern_reason": "Audit failed, AI visibility angle",
            "best_finding": "",
            "connection_note": cn, "first_dm": pat_e,
            "followup": fu1, "followup_2": fu2, "followup_3": fu3,
            "alternatives": alternatives,
        }

    if not findings:
        fu1, fu2, _ = _clean_fu()
        return {
            "pattern": "E", "pattern_reason": "No findings, clean site - AI visibility angle",
            "best_finding": "",
            "connection_note": cn, "first_dm": pat_e,
            "followup": fu1, "followup_2": fu2, "followup_3": fu3,
            "alternatives": alternatives,
        }

    # Filter out positive-sounding findings
    positive_words = [
        "present", "optimally", "well within", "well-optimized", "well optimized",
        "active and", "actively provided", "no immediately visible",
        "strong foundational", "clear call-to-action", "gut aufgestellt",
    ]
    problem_findings = [
        f for f in findings
        if not any(w in f.get("detail", "").lower() for w in positive_words)
    ]

    if not problem_findings:
        fu1, fu2, _ = _clean_fu()
        return {
            "pattern": "E", "pattern_reason": "All findings are positive",
            "best_finding": assessment,
            "connection_note": cn, "first_dm": pat_e,
            "followup": fu1, "followup_2": fu2, "followup_3": fu3,
            "alternatives": alternatives,
        }

    sev_order = {"high": 0, "medium": 1, "low": 2}
    sorted_findings = sorted(problem_findings, key=lambda f: sev_order.get(f.get("severity", "low"), 2))
    best = sorted_findings[0]
    ftype = best.get("type", "")
    detail = best.get("detail", "")
    evidence = best.get("evidence", "")
    extra_count = len(problem_findings) - 1
    extra = (s["extra_one"] if extra_count <= 0 else s["extra_multi"])

    title_text = audit.get("title_tag_text", "")
    meta_text = audit.get("meta_description_text", "")
    has_blog = audit.get("has_blog_or_news", False)

    # Helper to build return dict
    def _ret(pattern: str, reason: str, dm: str, bestfix_key: str) -> dict:
        fu1, fu2_v, _ = _fu(bestfix_key, extra_count)
        alternatives_copy = [a for a in alternatives]
        return {
            "pattern": pattern, "pattern_reason": reason,
            "best_finding": detail,
            "connection_note": cn, "first_dm": dm,
            "followup": fu1, "followup_2": fu2_v, "followup_3": fu3,
            "alternatives": alternatives_copy,
        }

    # Pattern C: blog exists but content not indexed
    negative_signals = [
        "not indexed", "not being indexed", "noindex", "blocked from",
        "not crawlable", "not accessible to search", "404", "not discoverable",
        "poor indexing", "indexing issue", "hidden from search",
        "nicht indexiert", "nicht erfasst", "noindex tag",
    ]
    content_findings = [f for f in findings if f["type"] == "content_indexing"]
    problem_content = [
        f for f in content_findings
        if any(n in f.get("detail", "").lower() for n in negative_signals)
    ]
    if has_blog and problem_content:
        dm = s["blog_pat_c"].format(addr=addr, domain=domain)
        alternatives.insert(0, {"pattern": "C", "reason": "Blog/content not indexed", "dm": dm})
        fu1, fu2_v, _ = _fu("content_indexing", extra_count)
        return {
            "pattern": "C", "pattern_reason": "Blog/content not indexed",
            "best_finding": problem_content[0]["detail"],
            "connection_note": cn, "first_dm": dm,
            "followup": fu1, "followup_2": fu2_v, "followup_3": fu3,
            "alternatives": alternatives,
        }

    # Skip content_indexing as best if no blog
    if ftype == "content_indexing" and not has_blog and len(sorted_findings) > 1:
        best = sorted_findings[1]
        ftype = best.get("type", "")
        detail = best.get("detail", "")
        evidence = best.get("evidence", "")

    # Pattern A: meta description
    if ftype == "meta_description":
        if "MISSING" in str(meta_text).upper() or "missing" in detail.lower():
            dm = s["meta_missing"].format(addr=addr, domain=domain, extra=extra)
            return _ret("A", "Meta description missing", dm, "meta_description_missing")
        import re
        meta_len = len(meta_text) if meta_text and meta_text != "MISSING" else 0
        detail_l = detail.lower()
        is_short = meta_len < 120 or any(w in detail_l for w in ["too short", "zu kurz", "extremely short"])
        if is_short:
            char_match = re.search(r"(\d+)\s*(?:characters|chars|zeichen)", detail_l)
            char_info = f" ({char_match.group(1)} chars)" if char_match else ""
            dm = s["meta_short"].format(addr=addr, domain=domain, char_info=char_info, extra=extra)
        else:
            dm = s["meta_long"].format(addr=addr, domain=domain, extra=extra)
        return _ret("A", "Meta description issue", dm, "meta_description")

    # Pattern A: title tag
    if ftype == "title_tag":
        generic_words = ["homepage", "willkommen", "home", "startseite", "welcome"]
        is_generic = any(w in title_text.lower() for w in generic_words)
        is_long = len(title_text) > 60
        is_stuffed = title_text.count(",") > 2 or title_text.count("|") > 2
        title_preview = title_text[:50]
        title_len = len(title_text)

        if is_generic:
            dm = s["title_generic"].format(
                addr=addr, domain=domain, title_preview=title_preview,
                company_first=company_first, extra=extra
            )
        elif is_long:
            dm = s["title_long"].format(addr=addr, domain=domain, title_len=title_len, extra=extra)
        elif is_stuffed:
            dm = s["title_stuffed"].format(
                addr=addr, domain=domain, title_preview=title_preview, extra=extra
            )
        else:
            dm = s["title_generic"].format(
                addr=addr, domain=domain, title_preview=title_preview,
                company_first=company_first, extra=extra
            )
        return _ret("A", f"Title tag: {detail[:50]}", dm, "title_tag")

    # Pattern A: broken elements
    if ftype == "broken_element":
        detail_l = detail.lower()
        if any(w in detail_l for w in ["placeholder", "platzhalter"]) and any(
            w in detail_l for w in ["visible", "plain text", "sichtbar", "shortcode"]
        ):
            dm = s["broken_placeholder"].format(addr=addr, domain=domain, extra=extra)
        elif "#" in evidence or "anchor" in detail_l:
            dm = s["broken_links"].format(addr=addr, domain=domain, extra=extra)
        else:
            dm = s["broken_generic"].format(addr=addr, domain=domain, extra=extra)
        return _ret("A", "Broken elements", dm, "broken_element")

    # Pattern A: language mismatch
    if ftype == "language_mismatch":
        dm = s["language_mismatch"].format(addr=addr, domain=domain, extra=extra)
        return _ret("A", "Language mismatch", dm, "language_mismatch")

    # Pattern A: missing social links
    if ftype == "social_links":
        dm = s["social_links"].format(addr=addr, domain=domain, company=company, extra=extra)
        return _ret("A", "Missing social links", dm, "social_links")

    # Pattern A: missing schema
    if ftype == "schema":
        dm = s["schema"].format(addr=addr, domain=domain, extra=extra)
        return _ret("A", "Missing schema markup", dm, "schema")

    # Generic Pattern A fallback
    n = len(problem_findings)
    if lang == "en":
        n_str = f"{n} thing{'s' if n > 1 else ''}"
    else:
        n_str = "eine Sache" if n == 1 else f"ein paar Sachen"
    dm = s["generic_findings"].format(addr=addr, domain=domain, n_str=n_str)
    return _ret("A", "Multiple technical issues", dm, "default")
