"""Unified CLI for anki-george-german."""
import argparse
import sys

import argcomplete


def dispatch(args):
    """Lazy-import the target module and run the command."""
    if args.command == "generate":
        from .generate_vocab import cmd_text, cmd_domain, cmd_scan
        {"text": cmd_text, "domain": cmd_domain,
         "scan": cmd_scan}[args.gen_command](args)
    elif args.command == "enrich":
        if args.enrich_command == "sentences":
            from .generate_vocab import cmd_enrich
            cmd_enrich(args)
        elif args.enrich_command == "ipa":
            from .enrich_ipa_audio import run
            run(args)
        elif args.enrich_command == "disambig":
            from .fix_disambiguations import run
            run(args)
        elif args.enrich_command == "noun-cloze":
            from .fix_noun_cloze_articles import run
            run(args)
    elif args.command == "unsuspend":
        from .unsuspend_candidates import run
        run(args)
    elif args.command == "stats":
        from .deck_stats import main as run
        run()
    elif args.command == "templates":
        from .update_templates import main as run
        run()
    elif args.command == "prefixes":
        from .update_prefix_fields import main as run
        run()
    elif args.command == "grammar":
        from .update_grammar_fields import main as run
        run(args)
    elif args.command == "query":
        from .query_note import run
        run(args)
    elif args.command == "schedule":
        from .schedule import install, uninstall, status, run
        {"install": install, "uninstall": uninstall, "status": status,
         "_run": run}[args.sched_command](args)


def main():
    parser = argparse.ArgumentParser(
        prog="anki-german",
        description="George's German Vocabulary deck tools",
    )
    sub = parser.add_subparsers(dest="command")

    # -- generate ------------------------------------------------------
    gen = sub.add_parser("generate", help="Generate new vocabulary cards")
    gen_sub = gen.add_subparsers(dest="gen_command", required=True)

    text_p = gen_sub.add_parser("text", help="Extract vocab from a German text")
    text_p.add_argument("--file", required=True)
    text_p.add_argument("--source", required=True)
    text_p.add_argument("--select",
                        help="Section(s) to process (e.g. '3', '1-5', '1,3,5')")
    text_p.add_argument("--chapters-file",
                        help="JSON file with manual chapter definitions")
    text_p.add_argument("--chunk-minutes", type=int,
                        help="Force word-count chunking at N minutes")
    text_p.add_argument("--reading-speed", type=int, default=100,
                        help="Reading speed in wpm for chunking (default: 100)")
    text_p.add_argument("--paragraphs",
                        help="(Legacy) Paragraph range — bypasses chapter detection")
    text_p.add_argument("--phase", type=int, default=4)
    text_p.add_argument("--batch-size", type=int, default=10)
    text_p.add_argument("--sentences", type=int, default=2)
    text_p.add_argument("--dry-run", action="store_true")
    text_p.add_argument("--enrich", action="store_true")

    scan_p = gen_sub.add_parser("scan",
                                help="Preview book structure (chapters/chunks)")
    scan_p.add_argument("--file", required=True)
    scan_p.add_argument("--chunk-minutes", type=int)
    scan_p.add_argument("--reading-speed", type=int, default=100)

    domain_p = gen_sub.add_parser("domain", help="Generate vocab from a topic brief")
    domain_p.add_argument("--brief", required=True)
    domain_p.add_argument("--source", required=True)
    domain_p.add_argument("--count", type=int, default=30)
    domain_p.add_argument("--phase", type=int, default=4)
    domain_p.add_argument("--sentences", type=int, default=2)
    domain_p.add_argument("--dry-run", action="store_true")

    # -- enrich --------------------------------------------------------
    enrich = sub.add_parser("enrich", help="Improve existing cards")
    enrich_sub = enrich.add_subparsers(dest="enrich_command", required=True)

    sent_p = enrich_sub.add_parser("sentences",
                                   help="Add example sentences to existing cards")
    sent_p.add_argument("--source", required=True)
    sent_p.add_argument("--sentences", type=int, default=3)
    sent_p.add_argument("--batch-size", type=int, default=10)
    sent_p.add_argument("--dry-run", action="store_true")

    ipa_p = enrich_sub.add_parser("ipa", help="IPA/audio from Wiktionary + LLM")
    ipa_p.add_argument("words", nargs="*",
                       help="Specific words to enrich (default: all missing)")
    ipa_p.add_argument("--dry-run", action="store_true")
    ipa_p.add_argument("--ipa-only", action="store_true")
    ipa_p.add_argument("--audio-only", action="store_true")
    ipa_p.add_argument("--audio-delay", type=float, default=5.0)
    ipa_p.add_argument("--no-llm", action="store_true",
                       help="Skip LLM fallback for Wiktionary misses")

    disambig_p = enrich_sub.add_parser("disambig",
                                       help="Disambiguate shared translations")
    disambig_p.add_argument("--dry-run", action="store_true")

    noun_cloze_p = enrich_sub.add_parser("noun-cloze",
                                         help="Fix article in cloze words")
    noun_cloze_p.add_argument("--dry-run", action="store_true")

    # -- unsuspend -----------------------------------------------------
    unsuspend_p = sub.add_parser("unsuspend", help="Unsuspend mature cards")
    unsuspend_p.add_argument("--apply", action="store_true")
    unsuspend_p.add_argument("--max", type=int, default=None)

    # -- simple commands -----------------------------------------------
    sub.add_parser("stats", help="Deck analysis and problem cards")
    sub.add_parser("templates", help="Push CSS/templates to Anki")
    sub.add_parser("prefixes", help="Sync prefix data to Anki")
    grammar_p = sub.add_parser("grammar", help="Sync grammar term data to Anki")
    grammar_p.add_argument("--dry-run", action="store_true")
    query_p = sub.add_parser("query", help="Look up a word")
    query_p.add_argument("word", nargs="?", default="der Saft")

    # -- schedule --------------------------------------------------
    sched = sub.add_parser("schedule", help="Manage weekly auto-unsuspend")
    sched_sub = sched.add_subparsers(dest="sched_command", required=True)

    install_p = sched_sub.add_parser("install", help="Install launchd agent")
    install_p.add_argument("--day", default="MON",
        help="Day of week: MON-SUN (default: MON)")
    install_p.add_argument("--hour", type=int, default=9,
        help="Hour to run, 0-23 (default: 9)")
    install_p.add_argument("--max", type=int, default=5,
        help="Max cards per type per run (default: 5)")

    sched_sub.add_parser("uninstall", help="Remove launchd agent")
    sched_sub.add_parser("status", help="Show agent status and recent runs")

    run_p = sched_sub.add_parser("_run", help=argparse.SUPPRESS)
    run_p.add_argument("--max", type=int, default=5)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        dispatch(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        if "ConnectionError" in type(e).__name__ or "connection" in str(e).lower():
            print(f"\nConnection error: cannot reach remote service. Check VPN/network.",
                  file=sys.stderr)
        else:
            print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
