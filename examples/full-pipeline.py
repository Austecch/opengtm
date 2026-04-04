#!/usr/bin/env python3
"""
full-pipeline.py - End-to-end opengtm pipeline example.

Runs: discover -> research -> qualify -> message -> (optional) sync
Saves intermediate results at each step for resume capability.

Usage:
    python examples/full-pipeline.py
    python examples/full-pipeline.py --industry "B2B SaaS" --region "Berlin" --limit 5
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path

# Add parent dir to path if running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from opengtm.discover import discover
from opengtm.research import research
from opengtm.qualify import qualify_batch
from opengtm.message import generate_messages
from opengtm.sync import sync_leads, build_sync_payload
from opengtm.outreach import OutreachSequence


def main():
    parser = argparse.ArgumentParser(description="opengtm full pipeline example")
    parser.add_argument("--industry", default="B2B SaaS", help="Industry vertical")
    parser.add_argument("--region", default="Berlin", help="City or region")
    parser.add_argument("--limit", type=int, default=5, help="Number of companies to discover")
    parser.add_argument("--language", choices=["en", "de"], default="en", help="Message language")
    parser.add_argument("--icp-profile", default="saas",
                        choices=["default", "saas", "agency", "professional_services"])
    parser.add_argument("--dry-run", action="store_true", help="Skip CRM sync")
    parser.add_argument("--output-dir", default="/tmp/opengtm-example")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"opengtm Full Pipeline Example")
    print(f"Industry: {args.industry} | Region: {args.region} | Limit: {args.limit}")
    print(f"{'='*60}\n")

    # Step 1: Discover
    print("STEP 1: DISCOVER")
    print("-" * 40)
    prospects = discover(
        industry=args.industry,
        region=args.region,
        limit=args.limit,
        verbose=True,
    )

    if not prospects:
        print("No companies found. Check your GEMINI_API_KEY and try again.")
        sys.exit(1)

    discovered_path = output_dir / "1-discovered.json"
    with open(discovered_path, "w") as f:
        json.dump(prospects, f, indent=2)
    print(f"\nSaved {len(prospects)} companies -> {discovered_path}\n")

    # Step 2: Research
    print("STEP 2: RESEARCH")
    print("-" * 40)
    researched = []
    for i, p in enumerate(prospects):
        print(f"\n[{i+1}/{len(prospects)}] {p['company']} ({p['domain']})")
        audit = research(
            domain=p["domain"],
            company=p["company"],
            industry=p["industry"],
            verbose=True,
        )
        contact = audit.get("contact", {})
        researched.append({
            **p,
            "contact_name": contact.get("name", ""),
            "contact_title": contact.get("title", ""),
            "contact_email": contact.get("email"),
            "linkedin_url": contact.get("linkedin_url"),
            "audit": audit,
        })
        if i < len(prospects) - 1:
            time.sleep(3)

    researched_path = output_dir / "2-researched.json"
    with open(researched_path, "w") as f:
        json.dump(researched, f, indent=2)
    print(f"\nSaved {len(researched)} researched leads -> {researched_path}\n")

    # Step 3: Qualify
    print("STEP 3: QUALIFY")
    print("-" * 40)
    qualified = qualify_batch(
        researched,
        icp_profile=args.icp_profile,
        verbose=True,
    )

    hot = sum(1 for r in qualified if r["qualification"]["tier"] == "hot")
    warm = sum(1 for r in qualified if r["qualification"]["tier"] == "warm")
    cold = sum(1 for r in qualified if r["qualification"]["tier"] == "cold")
    print(f"\nQualification: {hot} hot, {warm} warm, {cold} cold")

    qualified_path = output_dir / "3-qualified.json"
    with open(qualified_path, "w") as f:
        json.dump(qualified, f, indent=2)
    print(f"Saved -> {qualified_path}\n")

    # Step 4: Generate messages
    print("STEP 4: GENERATE MESSAGES")
    print("-" * 40)
    for lead in qualified:
        messages = generate_messages(
            domain=lead["domain"],
            company=lead["company"],
            contact_name=lead.get("contact_name", ""),
            industry=lead.get("industry", ""),
            audit=lead.get("audit"),
            region=args.region,
            contact_title=lead.get("contact_title", ""),
            language=args.language,
        )
        lead["messages"] = messages
        tier = lead["qualification"]["tier"]
        score = lead["qualification"]["score"]
        print(f"  [{tier.upper()}:{score}] {lead['company']}: Pattern {messages['pattern']}")

    with_messages_path = output_dir / "4-with-messages.json"
    with open(with_messages_path, "w") as f:
        json.dump(qualified, f, indent=2)
    print(f"\nSaved -> {with_messages_path}\n")

    # Step 5: Load into outreach sequence
    print("STEP 5: OUTREACH SEQUENCE")
    print("-" * 40)
    seq = OutreachSequence(daily_limit=20)
    added = seq.add_leads(qualified)
    seq_path = output_dir / "5-sequence.json"
    seq.export(str(seq_path))
    print(f"Added {added} leads to outreach sequence -> {seq_path}")
    seq.print_queue()

    # Step 6: Sync (optional)
    print("\nSTEP 6: CRM SYNC")
    print("-" * 40)
    if args.dry_run or not os.environ.get("CRM_WEBHOOK_URL"):
        print("Skipped (dry run or CRM_WEBHOOK_URL not set)")
        print("Set CRM_WEBHOOK_URL in your .env to enable sync.")
    else:
        sync_data = [build_sync_payload(lead) for lead in qualified]
        result = sync_leads(sync_data, dry_run=args.dry_run, verbose=True)
        print(f"Synced: {result['synced']}")

    # Show sample output
    print(f"\n{'='*60}")
    print("SAMPLE OUTPUT (first hot/warm lead)")
    print(f"{'='*60}")
    sample = next((r for r in qualified if r["qualification"]["tier"] in ("hot", "warm")), qualified[0])
    m = sample["messages"]
    q = sample["qualification"]
    print(f"\nCompany:     {sample['company']} ({sample['domain']})")
    print(f"Score:       {q['score']}/100 [{q['tier'].upper()}]")
    print(f"Pattern:     {m['pattern']}")
    print(f"\nConnection note ({len(m['connection_note'])} chars):")
    print(f"  {m['connection_note']}")
    print(f"\nFirst DM:")
    print(f"  {m['first_dm']}")
    print(f"\nFollow-up 1 (Day 3):")
    print(f"  {m['followup']}")
    print(f"\nWhy qualified:")
    for reason in q.get("reasons", [])[:3]:
        print(f"  - {reason}")

    print(f"\nAll output files in: {output_dir}")


if __name__ == "__main__":
    main()
