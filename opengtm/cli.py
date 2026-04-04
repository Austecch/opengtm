"""
cli.py - Unified CLI entrypoint for opengtm.

Commands:
  opengtm discover  - Find companies by industry + region
  opengtm research  - Research a domain (contact + website audit)
  opengtm qualify   - Score ICP fit for a list of leads
  opengtm message   - Generate outreach messages from audit data
  opengtm pipeline  - Run full end-to-end pipeline
  opengtm outreach  - Show/manage outreach sequence queue
  opengtm sync      - Push leads to Google Sheet CRM
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_dotenv():
    """Load .env file from current directory if present."""
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")


def cmd_discover(args):
    from .discover import discover as _discover
    print(f"[discover] {args.industry} | {args.region} | limit {args.limit}", flush=True)
    results = _discover(
        industry=args.industry,
        region=args.region,
        limit=args.limit,
        validate=not args.no_validate,
        verbose=True,
    )
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n{len(results)} companies -> {args.output}", flush=True)


def cmd_research(args):
    from .research import research as _research
    import time

    if args.domain:
        result = _research(
            domain=args.domain,
            company=args.company or args.domain,
            industry=args.industry or "",
            verbose=True,
        )
        output = [{"domain": args.domain, "company": args.company or args.domain, "research": result}]
    elif args.input:
        with open(args.input) as f:
            leads = json.load(f)
        output = []
        for i, lead in enumerate(leads):
            print(f"\n[{i+1}/{len(leads)}] {lead.get('company', lead['domain'])}", flush=True)
            result = _research(
                domain=lead["domain"],
                company=lead.get("company", ""),
                industry=lead.get("industry", ""),
                verbose=True,
            )
            output.append({**lead, "audit": result})
            if i < len(leads) - 1:
                time.sleep(3)
    else:
        print("ERROR: provide --domain or --input", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n{len(output)} researched -> {args.output}", flush=True)


def cmd_qualify(args):
    from .qualify import qualify_batch

    with open(args.input) as f:
        leads = json.load(f)

    print(f"[qualify] Scoring {len(leads)} leads (ICP profile: {args.icp_profile})", flush=True)
    results = qualify_batch(leads, icp_profile=args.icp_profile, verbose=True)

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    hot = sum(1 for r in results if r["qualification"]["tier"] == "hot")
    warm = sum(1 for r in results if r["qualification"]["tier"] == "warm")
    cold = sum(1 for r in results if r["qualification"]["tier"] == "cold")
    print(f"\nResults: {hot} hot, {warm} warm, {cold} cold -> {args.output}", flush=True)


def cmd_message(args):
    from .message import generate_messages

    with open(args.input) as f:
        leads = json.load(f)

    lang = args.language or os.environ.get("DEFAULT_LANGUAGE", "en")
    region = args.region or ""

    print(f"[message] Generating for {len(leads)} leads (language: {lang})", flush=True)
    results = []
    patterns = {}
    for lead in leads:
        audit = lead.get("audit") or lead.get("research") or {}
        if isinstance(audit, dict) and "research" in audit:
            audit = audit["research"]
        messages = generate_messages(
            domain=lead.get("domain", ""),
            company=lead.get("company", ""),
            contact_name=lead.get("contact_name", ""),
            industry=lead.get("industry", ""),
            audit=audit,
            region=region,
            contact_title=lead.get("contact_title", ""),
            language=lang,
        )
        results.append({**lead, "messages": messages})
        p = messages["pattern"]
        patterns[p] = patterns.get(p, 0) + 1
        print(f"  {lead.get('company', lead.get('domain', '?'))}: Pattern {p}", flush=True)

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nPatterns: {dict(sorted(patterns.items()))}", flush=True)
    print(f"{len(results)} messages -> {args.output}", flush=True)


def cmd_pipeline(args):
    """Full end-to-end pipeline: discover -> research -> qualify -> message -> sync."""
    import time
    from .discover import discover as _discover
    from .research import research as _research
    from .qualify import qualify_batch
    from .message import generate_messages
    from .sync import sync_leads, build_sync_payload

    lang = args.language or os.environ.get("DEFAULT_LANGUAGE", "en")
    output_path = args.output or f"/tmp/opengtm-pipeline-{args.industry.replace(' ', '-').lower()}.json"

    print(f"{'='*60}", flush=True)
    print(f"PIPELINE: {args.industry} | {args.region} | limit {args.limit}", flush=True)
    print(f"{'='*60}", flush=True)

    # Step 1: Discover
    print(f"\nSTEP 1: DISCOVER", flush=True)
    prospects = _discover(
        industry=args.industry,
        region=args.region,
        limit=args.limit,
        verbose=True,
    )
    if not prospects:
        print("No companies discovered. Exiting.", flush=True)
        sys.exit(1)

    # Step 2: Research
    print(f"\nSTEP 2: RESEARCH ({len(prospects)} companies)", flush=True)
    researched = []
    for i, p in enumerate(prospects):
        print(f"\n  [{i+1}/{len(prospects)}] {p['company']} ({p['domain']})", flush=True)
        audit = _research(
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

    # Step 3: Qualify
    print(f"\nSTEP 3: QUALIFY", flush=True)
    qualified = qualify_batch(
        researched,
        icp_profile=args.icp_profile,
        verbose=True,
    )

    # Step 4: Generate messages
    print(f"\nSTEP 4: GENERATE MESSAGES", flush=True)
    for lead in qualified:
        messages = generate_messages(
            domain=lead["domain"],
            company=lead["company"],
            contact_name=lead.get("contact_name", ""),
            industry=lead.get("industry", ""),
            audit=lead.get("audit"),
            region=args.region,
            contact_title=lead.get("contact_title", ""),
            language=lang,
        )
        lead["messages"] = messages
        print(f"  {lead['company']}: Pattern {messages['pattern']}", flush=True)

    # Save results
    with open(output_path, "w") as f:
        json.dump(qualified, f, indent=2, ensure_ascii=False)
    print(f"\nResults -> {output_path}", flush=True)

    # Step 5: Sync (optional)
    if not args.no_sync and os.environ.get("CRM_WEBHOOK_URL"):
        print(f"\nSTEP 5: SYNC TO CRM", flush=True)
        sync_data = [build_sync_payload(lead) for lead in qualified]
        sync_leads(sync_data, dry_run=args.dry_run, verbose=True)
    elif args.no_sync:
        print(f"\nSTEP 5: SYNC SKIPPED (--no-sync)", flush=True)
    else:
        print(f"\nSTEP 5: SYNC SKIPPED (CRM_WEBHOOK_URL not set)", flush=True)

    # Summary
    hot = sum(1 for r in qualified if r["qualification"]["tier"] == "hot")
    warm = sum(1 for r in qualified if r["qualification"]["tier"] == "warm")
    cold = sum(1 for r in qualified if r["qualification"]["tier"] == "cold")
    print(f"\n{'='*60}", flush=True)
    print(f"PIPELINE COMPLETE", flush=True)
    print(f"  Discovered:  {len(prospects)}", flush=True)
    print(f"  Researched:  {len(researched)}", flush=True)
    print(f"  Qualified:   {hot} hot, {warm} warm, {cold} cold", flush=True)
    print(f"{'='*60}", flush=True)


def cmd_outreach(args):
    from .outreach import OutreachSequence

    if args.action == "status":
        if not args.state_file or not Path(args.state_file).exists():
            print("ERROR: --state-file required and must exist for status", file=sys.stderr)
            sys.exit(1)
        seq = OutreachSequence.load(args.state_file)
        stats = seq.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.action == "queue":
        if not args.state_file or not Path(args.state_file).exists():
            print("ERROR: --state-file required and must exist for queue", file=sys.stderr)
            sys.exit(1)
        seq = OutreachSequence.load(args.state_file)
        seq.print_queue(touch=args.touch)

    elif args.action == "load":
        if not args.input:
            print("ERROR: --input required for load", file=sys.stderr)
            sys.exit(1)
        with open(args.input) as f:
            leads = json.load(f)
        state_path = args.state_file or "/tmp/opengtm-outreach-state.json"
        if Path(state_path).exists():
            seq = OutreachSequence.load(state_path, daily_limit=args.daily_limit)
        else:
            seq = OutreachSequence(daily_limit=args.daily_limit)
        added = seq.add_leads(leads)
        seq.export(state_path)
        print(f"Added {added} new leads to sequence -> {state_path}", flush=True)
        stats = seq.get_stats()
        print(f"Total: {stats['total_leads']} leads | {stats['due_today']} due today", flush=True)


def cmd_sync(args):
    from .sync import sync_leads, build_sync_payload

    with open(args.input) as f:
        leads = json.load(f)

    # Build sync payload
    sync_data = [build_sync_payload(lead) for lead in leads if lead.get("messages", {}).get("pattern") != "SKIP"]
    skipped = len(leads) - len(sync_data)

    if skipped:
        print(f"[sync] Skipping {skipped} SKIP-pattern leads", flush=True)

    sync_leads(sync_data, dry_run=args.dry_run, verbose=True)


def main():
    _load_dotenv()

    parser = argparse.ArgumentParser(
        prog="opengtm",
        description="AI-powered GTM automation: discover leads, research, score ICP, generate outreach.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  opengtm discover --industry "B2B SaaS" --region "Berlin" --limit 20
  opengtm research --domain example.com --company "Acme" --industry "SaaS"
  opengtm qualify --input discovered.json --icp-profile saas
  opengtm message --input qualified.json --language en
  opengtm pipeline --industry "IT Services" --region "Hamburg" --limit 10
  opengtm outreach load --input qualified.json --state-file seq.json
  opengtm outreach queue --state-file seq.json
  opengtm sync --input generated.json --dry-run
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # discover
    p_disc = sub.add_parser("discover", help="Find companies via Gemini + Google Search")
    p_disc.add_argument("--industry", "-i", required=True, help="Industry (e.g. 'B2B SaaS', 'IT Services')")
    p_disc.add_argument("--region", "-r", required=True, help="City or region (e.g. 'Berlin', 'San Francisco')")
    p_disc.add_argument("--limit", "-n", type=int, default=20, help="Max companies to return (default 20)")
    p_disc.add_argument("--output", "-o", default="/tmp/opengtm-discovered.json")
    p_disc.add_argument("--no-validate", action="store_true", help="Skip URL reachability check")

    # research
    p_res = sub.add_parser("research", help="Research domains: extract contact + run website audit")
    p_res.add_argument("--domain", "-d", help="Single domain to research")
    p_res.add_argument("--company", "-c", help="Company name (with --domain)")
    p_res.add_argument("--industry", help="Industry (with --domain)")
    p_res.add_argument("--input", help="JSON file with leads [{domain, company, industry}]")
    p_res.add_argument("--output", "-o", default="/tmp/opengtm-researched.json")

    # qualify
    p_qual = sub.add_parser("qualify", help="Score leads on ICP fit (0-100)")
    p_qual.add_argument("--input", required=True, help="JSON file with researched leads")
    p_qual.add_argument("--icp-profile", default="default",
                        choices=["default", "saas", "agency", "professional_services"],
                        help="ICP profile to score against (default: default)")
    p_qual.add_argument("--output", "-o", default="/tmp/opengtm-qualified.json")

    # message
    p_msg = sub.add_parser("message", help="Generate outreach messages from audit findings")
    p_msg.add_argument("--input", required=True, help="JSON file with qualified leads")
    p_msg.add_argument("--language", choices=["en", "de"], help="Message language (default: en)")
    p_msg.add_argument("--region", help="Region for peer comparison messages")
    p_msg.add_argument("--output", "-o", default="/tmp/opengtm-messages.json")

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="Full pipeline: discover -> research -> qualify -> message -> sync")
    p_pipe.add_argument("--industry", "-i", required=True)
    p_pipe.add_argument("--region", "-r", required=True)
    p_pipe.add_argument("--limit", "-n", type=int, default=10)
    p_pipe.add_argument("--language", choices=["en", "de"], help="Message language (default: en)")
    p_pipe.add_argument("--icp-profile", default="default",
                        choices=["default", "saas", "agency", "professional_services"])
    p_pipe.add_argument("--output", "-o", help="Output JSON path")
    p_pipe.add_argument("--no-sync", action="store_true", help="Skip CRM sync step")
    p_pipe.add_argument("--dry-run", action="store_true", help="Do not write to CRM")

    # outreach
    p_out = sub.add_parser("outreach", help="Manage multi-touch outreach sequences")
    p_out.add_argument("action", choices=["load", "queue", "status"],
                       help="load: add leads | queue: show due today | status: stats")
    p_out.add_argument("--input", help="JSON file with leads (for load action)")
    p_out.add_argument("--state-file", help="Sequence state JSON file path")
    p_out.add_argument("--touch", type=int, choices=[1, 2, 3, 4],
                       help="Filter queue to specific touch number")
    p_out.add_argument("--daily-limit", type=int, default=DEFAULT_DAILY_LIMIT,
                       help=f"Max connection requests per day (default: {DEFAULT_DAILY_LIMIT})")

    # sync
    p_sync = sub.add_parser("sync", help="Sync leads to Google Sheet CRM via webhook")
    p_sync.add_argument("--input", required=True, help="JSON file with generated leads")
    p_sync.add_argument("--dry-run", action="store_true", help="Print without posting")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "discover": cmd_discover,
        "research": cmd_research,
        "qualify": cmd_qualify,
        "message": cmd_message,
        "pipeline": cmd_pipeline,
        "outreach": cmd_outreach,
        "sync": cmd_sync,
    }
    dispatch[args.command](args)


# Allow running as: python -m opengtm
if __name__ == "__main__":
    main()
