"""Monthly deck health check: ease resets, lapse velocity, triage list.

Replaces the old deck_stats command with richer diagnostics and actionable
ease-reset intervention for cards stuck in Anki's ease death spiral.

Usage:
  anki-german health              # dry run — report only
  anki-german health --apply      # reset ease + apply health tags
"""

from collections import Counter, defaultdict

from ._anki import anki, DECK, MODEL

# ── Constants ──────────────────────────────────────────────────────────────────

EASE_RESET_THRESHOLD = 1800   # permille — cards below 180% get reset
EASE_RESET_TARGET = 2500      # permille — healthy default (250%)
MIN_REPS_FOR_RESET = 6        # don't reset barely-started cards

LAPSE_VELOCITY_HIGH = 2.0     # lapses/month — flagged
LAPSE_VELOCITY_WARN = 1.0     # lapses/month — mentioned

TEMPLATE_NAMES = {0: "EN→DE", 1: "DE→EN", 2: "Cloze", 3: "Listening"}
HEALTH_TAG_PREFIX = "health::"


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_all_cards():
    """Fetch all cards in the deck, in 500-card batches."""
    card_ids = anki("findCards", query=f'"deck:{DECK}"')
    cards = []
    for i in range(0, len(card_ids), 500):
        cards.extend(anki("cardsInfo", cards=card_ids[i:i + 500]))
    return cards


def lapse_velocity(lapses, interval):
    """Lapses per month, using current interval as age proxy."""
    return (lapses / max(interval, 1)) * 30


def template_label(card):
    """Human-readable template name from card info."""
    model = card.get("modelName", "")
    if model == MODEL:
        return TEMPLATE_NAMES.get(card.get("ord", -1), f"ord={card.get('ord')}")
    return model


def word_from_card(card):
    """Extract the Word field value (falls back to Prefix or GrammarTerm)."""
    fields = card.get("fields", {})
    for key in ("Word", "Prefix", "GrammarTerm"):
        val = fields.get(key, {}).get("value", "")
        if val:
            return val
    return "?"


def translation_from_card(card):
    """Extract the WordTranslation field value (falls back to CoreMeaning)."""
    fields = card.get("fields", {})
    for key in ("WordTranslation", "CoreMeaning"):
        val = fields.get(key, {}).get("value", "")
        if val:
            return val
    return "?"


# ── Core analysis ──────────────────────────────────────────────────────────────

def analyse(cards):
    """Classify cards and compute per-note aggregates.

    Returns (summary, notes) where:
      summary — dict with card distribution counts
      notes   — dict of note_id -> note analysis
    """
    new, learning, review, suspended = [], [], [], []
    ease_factors = []   # percent, active cards only
    intervals = []      # days, active cards only
    lapses_list = []    # active cards only

    # Per-note grouping
    note_cards = defaultdict(list)  # note_id -> [card_info, ...]

    for c in cards:
        queue = c.get("queue", 0)
        if queue == -1:
            suspended.append(c)
        elif queue == 0:
            new.append(c)
        elif queue == 1:
            learning.append(c)
            ease_factors.append(c.get("factor", 0) / 10)
            intervals.append(c.get("interval", 0))
            lapses_list.append(c.get("lapses", 0))
        elif queue == 2:
            review.append(c)
            ease_factors.append(c.get("factor", 0) / 10)
            intervals.append(c.get("interval", 0))
            lapses_list.append(c.get("lapses", 0))

        note_cards[c["note"]].append(c)

    # Template breakdown (all cards)
    tmpl_counts = Counter()
    for c in cards:
        tmpl_counts[template_label(c)] += 1

    # Due today
    due_ids = anki("findCards", query=f'"deck:{DECK}" is:due')

    summary = {
        "total": len(cards),
        "new": len(new),
        "learning": len(learning),
        "review": len(review),
        "suspended": len(suspended),
        "due_today": len(due_ids),
        "ease_factors": ease_factors,
        "intervals": intervals,
        "lapses_list": lapses_list,
        "tmpl_counts": tmpl_counts,
    }

    # Per-note analysis
    notes = {}
    for note_id, ncards in note_cards.items():
        word = word_from_card(ncards[0])
        translation = translation_from_card(ncards[0])

        active_cards = [c for c in ncards if c.get("queue", 0) not in (-1, 0)]

        ease_reset_cards = []
        high_vel_cards = []
        struggling_count = 0

        for c in active_cards:
            ease = c.get("factor", 0)
            reps = c.get("reps", 0)
            lapses = c.get("lapses", 0)
            interval = c.get("interval", 0)
            vel = lapse_velocity(lapses, interval)
            tmpl = template_label(c)

            if ease < EASE_RESET_THRESHOLD and reps >= MIN_REPS_FOR_RESET:
                ease_reset_cards.append({
                    "card_id": c["cardId"],
                    "template": tmpl,
                    "ease": ease / 10,
                    "lapses": lapses,
                    "interval": interval,
                    "velocity": vel,
                })

            if vel >= LAPSE_VELOCITY_HIGH:
                high_vel_cards.append({
                    "card_id": c["cardId"],
                    "template": tmpl,
                    "velocity": vel,
                    "lapses": lapses,
                    "interval": interval,
                })

            if vel >= LAPSE_VELOCITY_WARN:
                struggling_count += 1

        worst_vel = max(
            (lapse_velocity(c.get("lapses", 0), c.get("interval", 0))
             for c in active_cards),
            default=0.0,
        )

        notes[note_id] = {
            "word": word,
            "translation": translation,
            "ease_reset_cards": ease_reset_cards,
            "high_vel_cards": high_vel_cards,
            "struggling_count": struggling_count,
            "worst_velocity": worst_vel,
            "note_id": note_id,
        }

    return summary, notes


# ── Report printer ─────────────────────────────────────────────────────────────

def print_report(summary, notes, dry_run):
    """Print the full health report."""

    # 1. Card distribution
    print(f"\n── Card Distribution ──")
    print(f"  New (unseen):  {summary['new']}")
    print(f"  Learning:      {summary['learning']}")
    print(f"  Review:        {summary['review']}")
    print(f"  Suspended:     {summary['suspended']}")
    print(f"  Total:         {summary['total']}")

    print(f"\n  By template:")
    for tmpl, count in sorted(summary["tmpl_counts"].items()):
        print(f"    {tmpl:<20} {count:>4}")

    print(f"\n  Due today:     {summary['due_today']}")

    # 2. Ease & interval stats
    ease_factors = summary["ease_factors"]
    intervals = summary["intervals"]
    lapses_list = summary["lapses_list"]

    if ease_factors:
        avg_ease = sum(ease_factors) / len(ease_factors)
        low = sum(1 for e in ease_factors if e < 180)
        struggling = sum(1 for e in ease_factors if 180 <= e < 200)
        ok = sum(1 for e in ease_factors if 200 <= e < 250)
        good = sum(1 for e in ease_factors if e >= 250)

        print(f"\n── Ease Factor (active cards) ──")
        print(f"  Average:   {avg_ease:.0f}%")
        print(f"  < 180%:    {low:>4}  (ease death spiral)")
        print(f"  180-199%:  {struggling:>4}  (struggling)")
        print(f"  200-249%:  {ok:>4}  (adequate)")
        print(f"  250%+:     {good:>4}  (comfortable)")

    if intervals:
        print(f"\n── Interval Distribution (active cards) ──")
        buckets = Counter()
        for iv in intervals:
            if iv <= 0:
                buckets["learning"] += 1
            elif iv < 7:
                buckets["< 1 week"] += 1
            elif iv < 30:
                buckets["1-4 weeks"] += 1
            elif iv < 90:
                buckets["1-3 months"] += 1
            elif iv < 365:
                buckets["3-12 months"] += 1
            else:
                buckets["1+ year"] += 1

        for label in ["learning", "< 1 week", "1-4 weeks", "1-3 months",
                       "3-12 months", "1+ year"]:
            count = buckets.get(label, 0)
            bar = "█" * (count // 3)
            print(f"  {label:<14} {count:>4}  {bar}")

    if lapses_list:
        total_lapses = sum(lapses_list)
        cards_with_lapses = sum(1 for l in lapses_list if l > 0)
        avg_lapses = total_lapses / len(lapses_list)
        print(f"\n── Lapse Totals (active cards) ──")
        print(f"  Total lapses:      {total_lapses}")
        print(f"  Cards with lapses: {cards_with_lapses}/{len(lapses_list)}")
        print(f"  Average lapses:    {avg_lapses:.1f}")

    # 3. Lapse velocity distribution
    active_notes = [n for n in notes.values() if n["worst_velocity"] > 0]
    high_vel = [n for n in active_notes if n["worst_velocity"] >= LAPSE_VELOCITY_HIGH]
    warn_vel = [n for n in active_notes
                if LAPSE_VELOCITY_WARN <= n["worst_velocity"] < LAPSE_VELOCITY_HIGH]
    low_vel = [n for n in active_notes if n["worst_velocity"] < LAPSE_VELOCITY_WARN]

    print(f"\n── Lapse Velocity (per note, worst card) ──")
    print(f"  > {LAPSE_VELOCITY_HIGH}/mo:      {len(high_vel):>4}  (high)")
    print(f"  {LAPSE_VELOCITY_WARN}-{LAPSE_VELOCITY_HIGH}/mo:   {len(warn_vel):>4}  (watch)")
    print(f"  < {LAPSE_VELOCITY_WARN}/mo:      {len(low_vel):>4}  (fine)")

    # 4. Ease reset candidates
    reset_notes = [n for n in notes.values() if n["ease_reset_cards"]]
    print(f"\n── Ease Reset Candidates ({sum(len(n['ease_reset_cards']) for n in reset_notes)} cards across {len(reset_notes)} notes) ──")
    print(f"   Threshold: ease < {EASE_RESET_THRESHOLD / 10:.0f}% with {MIN_REPS_FOR_RESET}+ reps → reset to {EASE_RESET_TARGET / 10:.0f}%")
    print()

    if reset_notes:
        for n in sorted(reset_notes, key=lambda n: n["ease_reset_cards"][0]["ease"]):
            for rc in n["ease_reset_cards"]:
                print(f"  {n['word']:<30} [{rc['template']:<10}]  "
                      f"ease={rc['ease']:>5.0f}%  lapses={rc['lapses']:>2}  "
                      f"vel={rc['velocity']:.1f}/mo")
    else:
        print("  None — no cards in ease death spiral.")

    # 5. Triage list (notes with any struggling cards)
    triage = [n for n in notes.values()
              if n["struggling_count"] >= 3 or n["ease_reset_cards"] or n["high_vel_cards"]]
    triage.sort(key=lambda n: (-n["struggling_count"], -n["worst_velocity"]))

    print(f"\n── Triage List ({len(triage)} notes needing attention) ──")
    print()
    if triage:
        for n in triage[:40]:
            flags = []
            if n["ease_reset_cards"]:
                flags.append("ease-reset")
            if n["high_vel_cards"]:
                flags.append("high-vel")
            if n["struggling_count"] >= 3:
                flags.append(f"struggle×{n['struggling_count']}")
            flag_str = ", ".join(flags)
            print(f"  {n['word']:<25} {n['translation']:<25} "
                  f"vel={n['worst_velocity']:>4.1f}/mo  [{flag_str}]")
        if len(triage) > 40:
            print(f"  ... and {len(triage) - 40} more")
    else:
        print("  All clear — no notes need attention.")

    # 6. Footer
    print()
    if dry_run:
        print("DRY RUN — pass --apply to reset ease and apply health:: tags")
    else:
        print("Applied — ease resets executed and health:: tags updated.")


# ── Apply actions ──────────────────────────────────────────────────────────────

def apply_actions(notes):
    """Execute ease resets and apply health tags."""

    # Collect all note IDs that currently have any health:: tag
    tagged_ids = anki("findNotes", query=f'"deck:{DECK}" "tag:{HEALTH_TAG_PREFIX}*"')

    # Clear old health tags
    if tagged_ids:
        # Get current tags to find health:: ones
        existing_notes = anki("notesInfo", notes=tagged_ids)
        health_tags = set()
        for n in existing_notes:
            for tag in n.get("tags", []):
                if tag.startswith(HEALTH_TAG_PREFIX):
                    health_tags.add(tag)
        for tag in health_tags:
            anki("removeTags", notes=tagged_ids, tags=tag)

    # Collect actions
    ease_reset_cards = []    # (card_id, target_ease)
    ease_reset_note_ids = set()
    high_vel_note_ids = set()
    struggling_note_ids = set()

    for note_id, n in notes.items():
        if n["ease_reset_cards"]:
            ease_reset_note_ids.add(note_id)
            for rc in n["ease_reset_cards"]:
                ease_reset_cards.append(rc["card_id"])

        if n["high_vel_cards"]:
            high_vel_note_ids.add(note_id)

        if n["struggling_count"] >= 3:
            struggling_note_ids.add(note_id)

    # Execute ease resets
    reset_count = 0
    if ease_reset_cards:
        anki("setEaseFactors",
             cards=ease_reset_cards,
             easeFactors=[EASE_RESET_TARGET] * len(ease_reset_cards))
        reset_count = len(ease_reset_cards)

    # Apply tags
    if ease_reset_note_ids:
        anki("addTags", notes=list(ease_reset_note_ids),
             tags=f"{HEALTH_TAG_PREFIX}ease-reset")
    if high_vel_note_ids:
        anki("addTags", notes=list(high_vel_note_ids),
             tags=f"{HEALTH_TAG_PREFIX}high-lapse-velocity")
    if struggling_note_ids:
        anki("addTags", notes=list(struggling_note_ids),
             tags=f"{HEALTH_TAG_PREFIX}struggling-word")

    tag_total = len(ease_reset_note_ids | high_vel_note_ids | struggling_note_ids)
    print(f"\n  Ease reset: {reset_count} card(s) → {EASE_RESET_TARGET / 10:.0f}%")
    print(f"  Tags applied to {tag_total} note(s)")


# ── Entry point ────────────────────────────────────────────────────────────────

def run(args):
    """Execute health check with pre-parsed args (called by CLI dispatcher)."""
    dry_run = not args.apply

    print("Fetching card data from Anki...")
    cards = fetch_all_cards()
    print(f"  {len(cards)} cards total")

    if not cards:
        print("No cards found.")
        return

    summary, notes = analyse(cards)
    print_report(summary, notes, dry_run)

    if not dry_run:
        apply_actions(notes)
