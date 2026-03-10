#!/usr/bin/env python3
"""Analyse Anki deck stats: problem cards, pace, ease distribution."""
import sys
from collections import Counter

from ._anki import anki, DECK, MODEL


def main():
    # Get all cards
    card_ids = anki("findCards", query=f'"deck:{DECK}"')
    print(f"Total cards: {len(card_ids)}")

    if not card_ids:
        sys.exit(0)

    cards = anki("cardsInfo", cards=card_ids)

    # Categorise
    new, learning, review, suspended = [], [], [], []
    ease_factors = []
    intervals = []
    lapses_list = []
    problem_cards = []

    for c in cards:
        queue = c.get("queue", 0)
        card_type = c.get("type", 0)

        if queue == -1:
            suspended.append(c)
            continue
        elif queue == 0:
            new.append(c)
            continue
        elif queue == 1:
            learning.append(c)
        elif queue == 2:
            review.append(c)

        ease = c.get("factor", 0) / 10  # Anki stores as permille
        interval = c.get("interval", 0)
        lapses = c.get("lapses", 0)
        reps = c.get("reps", 0)
        word = c.get("fields", {}).get("Word", {}).get("value", "?")
        tmpl = c.get("template", "?") if "template" in c else "?"

        ease_factors.append(ease)
        intervals.append(interval)
        lapses_list.append(lapses)

        # Problem cards: low ease or many lapses
        if (ease < 200 and reps > 3) or lapses >= 5:
            problem_cards.append({
                "word": word,
                "template": tmpl,
                "ease": ease,
                "interval": interval,
                "lapses": lapses,
                "reps": reps,
            })

    # Queue distribution
    print(f"\n── Card Distribution ──")
    print(f"  New (unseen):  {len(new)}")
    print(f"  Learning:      {len(learning)}")
    print(f"  Review:        {len(review)}")
    print(f"  Suspended:     {len(suspended)}")
    active = learning + review

    if not active:
        print("\nNo active cards to analyse.")
        sys.exit(0)

    # Ease factor distribution
    print(f"\n── Ease Factor (active cards) ──")
    if ease_factors:
        avg_ease = sum(ease_factors) / len(ease_factors)
        low_ease = sum(1 for e in ease_factors if e < 200)
        ok_ease = sum(1 for e in ease_factors if 200 <= e < 250)
        good_ease = sum(1 for e in ease_factors if e >= 250)
        print(f"  Average:  {avg_ease:.0f}%")
        print(f"  < 200%:   {low_ease} (struggling)")
        print(f"  200-249%: {ok_ease} (adequate)")
        print(f"  250%+:    {good_ease} (comfortable)")

    # Interval distribution
    print(f"\n── Interval Distribution (review cards) ──")
    if intervals:
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
            bar = "\u2588" * (count // 3)
            print(f"  {label:<14} {count:>4}  {bar}")

    # Lapse distribution
    print(f"\n── Lapse Distribution ──")
    if lapses_list:
        total_lapses = sum(lapses_list)
        cards_with_lapses = sum(1 for l in lapses_list if l > 0)
        avg_lapses = total_lapses / len(lapses_list) if lapses_list else 0
        print(f"  Total lapses:      {total_lapses}")
        print(f"  Cards with lapses: {cards_with_lapses}/{len(lapses_list)}")
        print(f"  Average lapses:    {avg_lapses:.1f}")

    # Problem cards
    print(f"\n── Problem Cards (ease < 200% or lapses >= 5) ──")
    if problem_cards:
        problem_cards.sort(key=lambda c: (c["ease"], -c["lapses"]))
        print(f"  Found {len(problem_cards)} problem cards:\n")
        for pc in problem_cards[:30]:
            print(f"  {pc['word']:<30} ease={pc['ease']:>3.0f}%  "
                  f"interval={pc['interval']:>4}d  "
                  f"lapses={pc['lapses']}  reps={pc['reps']}  "
                  f"[{pc['template']}]")
        if len(problem_cards) > 30:
            print(f"  ... and {len(problem_cards) - 30} more")
    else:
        print("  None! All active cards are in good shape.")

    # Due cards
    print(f"\n── Due Today ──")
    due_today = anki("findCards", query=f'"deck:{DECK}" is:due')
    print(f"  {len(due_today)} cards due")

    # Cards by template type
    print(f"\n── Cards by Template ──")
    template_counts = Counter()
    for c in cards:
        tmpl = c.get("template", "unknown") if "template" in c else "unknown"
        template_counts[tmpl] += 1
    # Try getting from cardType field
    type_counts = Counter()
    for c in cards:
        ct = c.get("css", "")  # not useful
        # Use ord field to determine template
        ord_val = c.get("ord", 0)
        model_name = c.get("modelName", "?")
        if model_name == MODEL:
            types = {0: "EN\u2192DE", 1: "DE\u2192EN", 2: "Cloze"}
            type_counts[types.get(ord_val, f"ord={ord_val}")] += 1
        else:
            type_counts[model_name] += 1

    for tmpl, count in sorted(type_counts.items()):
        print(f"  {tmpl:<20} {count:>4}")


if __name__ == "__main__":
    main()
