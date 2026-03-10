"""Unified CLI for anki-george-german."""
import argparse
import sys


def dispatch(args):
    """Lazy-import the target module and run the command."""
    if args.command == "generate":
        from .generate_vocab import cmd_text, cmd_domain, cmd_enrich
        {"text": cmd_text, "domain": cmd_domain, "enrich": cmd_enrich}[args.gen_command](args)
    elif args.command == "enrich-ipa":
        from .enrich_ipa_audio import run
        run(args)
    elif args.command == "fix":
        if args.fix_command == "disambig":
            from .fix_disambiguations import run
        elif args.fix_command == "ipa":
            from .fix_missing_ipa import run
        elif args.fix_command == "noun-cloze":
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
    elif args.command == "query":
        from .query_note import run
        run(args)


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
    text_p.add_argument("--paragraphs")
    text_p.add_argument("--domain", default="")
    text_p.add_argument("--phase", type=int, default=4)
    text_p.add_argument("--batch-size", type=int, default=10)
    text_p.add_argument("--sentences", type=int, default=2)
    text_p.add_argument("--dry-run", action="store_true")
    text_p.add_argument("--enrich", action="store_true")

    domain_p = gen_sub.add_parser("domain", help="Generate vocab from a topic brief")
    domain_p.add_argument("--brief", required=True)
    domain_p.add_argument("--source", required=True)
    domain_p.add_argument("--count", type=int, default=30)
    domain_p.add_argument("--domain", default="")
    domain_p.add_argument("--phase", type=int, default=4)
    domain_p.add_argument("--sentences", type=int, default=2)
    domain_p.add_argument("--dry-run", action="store_true")

    enrich_p = gen_sub.add_parser("enrich", help="Add sentences to existing cards")
    enrich_p.add_argument("--source", required=True)
    enrich_p.add_argument("--sentences", type=int, default=3)
    enrich_p.add_argument("--batch-size", type=int, default=10)
    enrich_p.add_argument("--dry-run", action="store_true")

    # -- enrich-ipa ----------------------------------------------------
    ipa_p = sub.add_parser("enrich-ipa", help="IPA/audio from Wiktionary")
    ipa_p.add_argument("--dry-run", action="store_true")
    ipa_p.add_argument("--ipa-only", action="store_true")
    ipa_p.add_argument("--audio-only", action="store_true")
    ipa_p.add_argument("--audio-delay", type=float, default=5.0)

    # -- fix -----------------------------------------------------------
    fix = sub.add_parser("fix", help="Fix existing card data")
    fix_sub = fix.add_subparsers(dest="fix_command", required=True)
    disambig_p = fix_sub.add_parser("disambig", help="Disambiguate shared translations")
    disambig_p.add_argument("--dry-run", action="store_true")
    fix_ipa_p = fix_sub.add_parser("ipa", help="Backfill IPA via LLM")
    fix_ipa_p.add_argument("--dry-run", action="store_true")
    noun_cloze_p = fix_sub.add_parser("noun-cloze", help="Fix article in cloze words")
    noun_cloze_p.add_argument("--dry-run", action="store_true")

    # -- unsuspend -----------------------------------------------------
    unsuspend_p = sub.add_parser("unsuspend", help="Unsuspend mature cards")
    unsuspend_p.add_argument("--apply", action="store_true")
    unsuspend_p.add_argument("--max", type=int, default=None)

    # -- simple commands -----------------------------------------------
    sub.add_parser("stats", help="Deck analysis and problem cards")
    sub.add_parser("templates", help="Push CSS/templates to Anki")
    sub.add_parser("prefixes", help="Sync prefix data to Anki")
    query_p = sub.add_parser("query", help="Look up a word")
    query_p.add_argument("word", nargs="?", default="der Saft")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch(args)
