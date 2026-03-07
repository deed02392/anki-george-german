#!/usr/bin/env python3
"""
Agent 2: Vocabulary analyser for German child-conversation Anki deck.

Reads deck_export.json, scores existing notes for child-conversation relevance,
and produces:
  - selected_cards.json   (matched existing notes with scores)
  - new_vocab.json        (net-new vocabulary items to add)
  - report.md             (human-readable summary)
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
PIPELINE_DIR = Path(__file__).parent
INPUT_FILE = PIPELINE_DIR / "deck_export.json"
OUT_DIR = PIPELINE_DIR
OUT_SELECTED = OUT_DIR / "selected_cards.json"
OUT_NEW_VOCAB = OUT_DIR / "new_vocab.json"
OUT_REPORT = OUT_DIR / "report.md"

# ---------------------------------------------------------------------------
# Domain keyword lists  (German and English, lowercase)
# ---------------------------------------------------------------------------
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "play": [
        "spielen", "spiel", "spielzeug", "spielen", "rennen", "laufen",
        "springen", "bauen", "zeichnen", "malen", "werfen", "fangen",
        "verstecken", "klettern", "schaukeln", "rutschen",
        "play", "game", "toy", "run", "jump", "build", "draw", "throw",
        "catch", "hide", "climb", "swing", "slide",
    ],
    "toys": [
        "spielzeug", "puppe", "teddy", "ball", "baustein", "puzzle",
        "auto", "lego", "drachen", "kreisel", "schaukel",
        "rutsche", "sandkasten", "buntstift", "farbe",
        "toy", "doll", "block", "lego", "kite", "top", "sandbox",
        "crayon", "puppet",
    ],
    "food": [
        "essen", "trinken", "frühstück", "mittagessen", "abendessen",
        "hunger", "durst", "kochen", "backen", "schmecken",
        "brot", "milch", "wasser", "saft", "apfel", "banane",
        "obst", "gemüse", "fleisch", "käse", "ei", "kuchen",
        "keks", "süßigkeit", "schokolade", "suppe", "nudeln",
        "reis", "kartoffel", "tomate", "möhre", "joghurt",
        "eat", "drink", "breakfast", "lunch", "dinner", "hungry", "thirsty",
        "cook", "bake", "bread", "milk", "water", "juice", "apple",
        "banana", "fruit", "vegetable", "meat", "cheese", "egg", "cake",
        "cookie", "chocolate", "soup", "pasta", "rice", "potato",
        "tomato", "carrot", "yogurt", "food", "meal",
    ],
    "family": [
        "mama", "papa", "mutter", "vater", "bruder", "schwester",
        "oma", "opa", "großmutter", "großvater", "oma", "opa",
        "tante", "onkel", "kind", "baby", "geschwister", "familie",
        "mum", "mom", "dad", "father", "mother", "brother", "sister",
        "grandma", "grandpa", "grandmother", "grandfather",
        "aunt", "uncle", "child", "baby", "sibling", "family",
    ],
    "school": [
        "schule", "kindergarten", "lernen", "malen", "buch",
        "stift", "lehrer", "lehrerin", "klasse", "unterricht",
        "hausaufgabe", "lesen", "schreiben", "rechnen", "bleistift",
        "heft", "tasche", "schulbus", "pause", "kita",
        "school", "kindergarten", "learn", "paint", "book",
        "pen", "pencil", "teacher", "class", "lesson", "homework",
        "read", "write", "calculate", "notebook", "bag", "break",
    ],
    "animals": [
        "hund", "katze", "pferd", "vogel", "fisch", "maus",
        "hase", "kaninchen", "kuh", "schwein", "schaf", "ziege",
        "huhn", "ente", "frosch", "schlange", "schildkröte",
        "elefant", "löwe", "tiger", "bär", "affe", "delfin",
        "tier", "zoo",
        "dog", "cat", "horse", "bird", "fish", "mouse",
        "rabbit", "cow", "pig", "sheep", "goat", "chicken",
        "duck", "frog", "snake", "turtle", "elephant", "lion",
        "tiger", "bear", "monkey", "dolphin", "animal",
    ],
    "feelings": [
        "glücklich", "traurig", "müde", "ängstlich", "gelangweilt",
        "aufgeregt", "wütend", "fröhlich", "weinen", "lachen",
        "angst", "freude", "lieben", "mögen", "hassen",
        "happy", "sad", "tired", "scared", "bored", "excited",
        "angry", "joyful", "cry", "laugh", "fear", "joy",
        "love", "like", "hate", "feeling", "emotion",
    ],
    "body": [
        "kopf", "auge", "nase", "mund", "ohr", "haar",
        "hand", "finger", "arm", "bein", "fuß", "bauch",
        "rücken", "schulter", "knie", "zahn", "zunge", "körper",
        "head", "eye", "nose", "mouth", "ear", "hair",
        "hand", "finger", "arm", "leg", "foot", "belly",
        "back", "shoulder", "knee", "tooth", "tongue", "body",
    ],
    "colours": [
        "rot", "blau", "grün", "gelb", "orange", "lila",
        "rosa", "schwarz", "weiß", "grau", "braun", "farbe",
        "bunt", "hell", "dunkel",
        "red", "blue", "green", "yellow", "orange", "purple",
        "pink", "black", "white", "grey", "gray", "brown", "colour",
        "color", "colorful", "light", "dark",
    ],
    "numbers": [
        "eins", "zwei", "drei", "vier", "fünf", "sechs",
        "sieben", "acht", "neun", "zehn", "elf", "zwölf",
        "dreizehn", "vierzehn", "fünfzehn", "sechzehn",
        "siebzehn", "achtzehn", "neunzehn", "zwanzig",
        "nummer", "zahl", "anzahl", "rechnen", "zählen",
        "one", "two", "three", "four", "five", "six",
        "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "twenty", "number", "count",
    ],
    "greetings": [
        "hallo", "tschüss", "bitte", "danke", "entschuldigung",
        "guten morgen", "guten abend", "gute nacht", "willkommen",
        "auf wiedersehen", "wie geht", "wie heißt", "mein name",
        "hello", "bye", "please", "thank", "sorry", "excuse",
        "good morning", "good night", "welcome", "goodbye",
        "how are you", "my name",
    ],
    "questions": [
        "wo", "was", "wer", "wie", "warum", "wann",
        "kannst du", "magst du", "willst du", "darf ich",
        "welche", "welcher", "welches", "wohin", "woher",
        "where", "what", "who", "how", "why", "when",
        "can you", "do you like", "do you want", "may i",
        "which",
    ],
    "location": [
        "hier", "dort", "da", "drinnen", "draußen", "oben",
        "unten", "neben", "auf", "unter", "hinter", "vor",
        "links", "rechts", "mitte", "innen", "außen",
        "here", "there", "inside", "outside", "above", "below",
        "next to", "on", "under", "behind", "in front",
        "left", "right", "middle",
    ],
    "time": [
        "heute", "morgen", "gestern", "jetzt", "später",
        "immer", "manchmal", "oft", "nie", "bald",
        "früh", "spät", "tag", "nacht", "woche",
        "today", "tomorrow", "yesterday", "now", "later",
        "always", "sometimes", "often", "never", "soon",
        "early", "late", "day", "night", "week",
    ],
    "actions": [
        "gehen", "kommen", "machen", "sehen", "hören",
        "essen", "trinken", "schlafen", "aufwachen", "anziehen",
        "spielen", "lachen", "weinen", "helfen", "zeigen",
        "geben", "nehmen", "bringen", "suchen", "finden",
        "sitzen", "stehen", "liegen", "laufen", "rennen",
        "springen", "werfen", "fangen", "öffnen", "schließen",
        "go", "come", "make", "do", "see", "hear",
        "eat", "drink", "sleep", "wake", "dress", "play",
        "laugh", "cry", "help", "show", "give", "take",
        "bring", "look for", "find", "sit", "stand", "lie",
        "run", "jump", "throw", "catch", "open", "close",
    ],
}

# Fundamental words that should always get a boost
FUNDAMENTAL_WORDS = {
    # core modal / auxiliary verbs
    "sein", "haben", "werden", "können", "müssen", "wollen", "sollen",
    "dürfen", "mögen",
    # core verbs – actions
    "gehen", "kommen", "machen", "sehen", "hören", "fühlen",
    "essen", "trinken", "schlafen", "spielen", "laufen", "helfen",
    "geben", "nehmen", "sagen", "wissen", "denken", "lachen", "weinen",
    "lesen", "schreiben", "zeigen", "bringen", "finden", "suchen",
    "sitzen", "stehen", "liegen", "rennen", "springen", "werfen", "fangen",
    "bauen", "zeichnen", "malen", "lernen", "singen", "tanzen",
    "anziehen", "aufräumen", "aufwachen", "öffnen", "schließen",
    "verstecken", "klettern", "lieben", "mögen",
    # core nouns – family
    "kind", "mutter", "vater", "mama", "papa", "bruder", "schwester",
    "oma", "opa", "baby", "freund", "freundin", "familie",
    # core nouns – things
    "hund", "katze", "pferd", "vogel", "fisch", "tier",
    "haus", "zimmer", "garten", "schule", "kindergarten",
    "buch", "ball", "spielzeug", "puppe", "auto",
    "essen", "brot", "milch", "wasser", "apfel",
    # core adjectives
    "gut", "schlecht", "groß", "klein", "neu", "alt", "viel", "mehr",
    "schön", "lustig", "toll", "lecker", "müde", "glücklich", "traurig",
    "schnell", "langsam",
    # function / social words
    "ja", "nein", "bitte", "danke", "hallo",
    # question words
    "wo", "was", "wer", "wie", "warum", "wann",
    # colours
    "rot", "blau", "grün", "gelb", "schwarz", "weiß",
    # numbers 1-10
    "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
    # time
    "heute", "morgen", "jetzt", "später", "immer", "manchmal",
    # location
    "hier", "dort", "oben", "unten",
}

# Words / patterns to penalise as too abstract/academic/legal
PENALISE_PATTERNS = [
    r"\bjuristisch\b", r"\brechtlich\b", r"\bparlament\b",
    r"\bwirtschaft\b", r"\bfinanziell\b", r"\bphilosoph\b",
    r"\bwissenschaft\b", r"\bpolitisch\b", r"\bstaatlich\b",
    r"\bgesetz\b", r"\bvertrag\b", r"\bkonferenz\b",
    r"\bprozent\b", r"\bstatistik\b", r"\banalyse\b",
    r"\bstrategie\b", r"\borganisation\b", r"\binstitut\b",
    r"\bregierung\b", r"\bminister\b", r"\bpräsident\b",
    r"\bstruktur\b", r"\bkonzept\b", r"\bprinzip\b",
]

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def get_scheduling_status(sched: dict) -> str:
    interval = sched.get("best_interval_days", 0)
    queue = sched.get("queue", 0)
    card_type = sched.get("card_type", 0)

    if queue in (-2, -1) or card_type == 0 and sched.get("reps", 0) == 0:
        return "new"
    if interval == 0:
        return "new"
    if interval <= 7:
        return "learning"
    if interval <= 21:
        return "young"
    return "mature"


def match_domains(word: str, translation: str) -> list[str]:
    """Return list of matched domain names.

    Uses word-boundary matching to avoid false positives from substrings
    (e.g. 'essen' inside 'Weltmeisterschaft').
    """
    # For matching we use only the bare Word field (stripped of article)
    # plus the English translation.  We do NOT match against the full
    # combined string to avoid picking up incidental substrings.
    word_bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", word.strip().lower())
    # Also check the infinitive if the word ends in common suffixes
    # We tokenise word_bare (handles compound words roughly by also checking
    # if the whole bare word equals a keyword, and checks the translation word-
    # by-word).
    trans_lower = translation.lower()

    matched = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        domain_matched = False
        for kw in keywords:
            # Strategy 1: exact match on bare word
            if word_bare == kw:
                domain_matched = True
                break
            # Strategy 2: word starts with keyword (catch inflections like
            # "spielen" -> "spiel", "essen" -> "ess")  – only for longer kws
            if len(kw) >= 4 and word_bare.startswith(kw):
                domain_matched = True
                break
            # Strategy 3: keyword is a multi-word phrase – check with word boundary
            if " " in kw:
                if kw in (word_bare + " " + trans_lower):
                    domain_matched = True
                    break
            # Strategy 4: check translation using word-boundary regex
            # (handles English keywords like "eat", "dog" etc.)
            if re.search(r"\b" + re.escape(kw) + r"\b", trans_lower):
                domain_matched = True
                break
            # Strategy 5: keyword exactly matches one of the comma-separated
            # translation tokens (e.g. "to eat, to consume" -> "to eat")
            trans_tokens = [t.strip().lower() for t in re.split(r"[,;/]", trans_lower)]
            for tok in trans_tokens:
                # strip leading "to " for verb comparison
                tok_bare = re.sub(r"^to\s+", "", tok).strip()
                if tok_bare == kw or tok == kw:
                    domain_matched = True
                    break
            if domain_matched:
                break
        if domain_matched:
            matched.append(domain)
    return matched


def score_note(note: dict, domains: list[str]) -> float:
    """Compute a 0-10 priority score.

    Scoring rationale (all capped at 10):
      - Base per matched domain:    1.0 each  (max 3.0)
      - Fundamental word bonus:     4.0
      - High-value domain bonus:    0.5 per domain
      - Has example sentence:       0.5
      - New/learning scheduling:   +1.0
      - Young scheduling:          +0.5
      - Abstract/academic penalty: -3.0
      - Very short non-function:   -1.0
    """
    if not domains:
        return 0.0

    word = note["fields"]["Word"].strip()
    word_lower = word.lower()
    translation = note["fields"]["WordTranslation"].strip().lower()
    sentence = note["fields"]["Sentence"].strip()
    sched = note["scheduling"]
    status = get_scheduling_status(sched)

    score = 0.0

    # Base: 1 point per domain (max 3)
    score += min(len(domains), 3) * 1.0

    # Bonus for fundamental words – raised from 3.0 to 4.0
    bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", word_lower).strip()
    if bare in FUNDAMENTAL_WORDS or word_lower in FUNDAMENTAL_WORDS:
        score += 4.0

    # Bonus if word appears in high-value interaction domains
    high_value = {"play", "food", "family", "animals", "greetings",
                  "feelings", "actions", "questions"}
    hv_count = sum(1 for d in domains if d in high_value)
    score += hv_count * 0.5

    # Bonus for having an example sentence
    if sentence:
        score += 0.5

    # Boost for new/learning cards (high relevance + not yet learned = priority)
    if status in ("new", "learning"):
        score += 1.0
    elif status == "young":
        score += 0.5

    # Penalise abstract/academic patterns
    combined_lower = (word + " " + translation).lower()
    for pat in PENALISE_PATTERNS:
        if re.search(pat, combined_lower):
            score -= 3.0
            break

    # Penalise very short function words that aren't question/greeting words
    if len(word) <= 2 and "questions" not in domains and "greetings" not in domains:
        score -= 1.0

    return round(min(max(score, 0.0), 10.0), 2)


# ---------------------------------------------------------------------------
# Net-new vocabulary
# ---------------------------------------------------------------------------

NEW_VOCAB_RAW: list[dict] = [
    # --- GREETINGS & SOCIAL ---
    {"word": "Hallo", "article": None, "pos": "interjection", "translation": "hello", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Hallo! Wie heißt du?", "example_sentence_en": "Hello! What's your name?", "notes": ""},
    {"word": "Tschüss", "article": None, "pos": "interjection", "translation": "bye, goodbye", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Tschüss! Bis morgen!", "example_sentence_en": "Bye! See you tomorrow!", "notes": ""},
    {"word": "Auf Wiedersehen", "article": None, "pos": "phrase", "translation": "goodbye (formal)", "domains": ["greetings"], "priority": 7, "example_sentence_de": "Auf Wiedersehen, Frau Müller!", "example_sentence_en": "Goodbye, Mrs Müller!", "notes": ""},
    {"word": "Guten Morgen", "article": None, "pos": "phrase", "translation": "good morning", "domains": ["greetings", "time"], "priority": 10, "example_sentence_de": "Guten Morgen! Hast du gut geschlafen?", "example_sentence_en": "Good morning! Did you sleep well?", "notes": ""},
    {"word": "Guten Abend", "article": None, "pos": "phrase", "translation": "good evening", "domains": ["greetings", "time"], "priority": 7, "example_sentence_de": "Guten Abend! Wie war dein Tag?", "example_sentence_en": "Good evening! How was your day?", "notes": ""},
    {"word": "Gute Nacht", "article": None, "pos": "phrase", "translation": "good night", "domains": ["greetings", "time"], "priority": 9, "example_sentence_de": "Gute Nacht! Schlaf gut!", "example_sentence_en": "Good night! Sleep well!", "notes": ""},
    {"word": "bitte", "article": None, "pos": "adverb", "translation": "please; you're welcome", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Kannst du mir bitte helfen?", "example_sentence_en": "Can you please help me?", "notes": ""},
    {"word": "danke", "article": None, "pos": "interjection", "translation": "thank you", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Danke für das Spielzeug!", "example_sentence_en": "Thank you for the toy!", "notes": ""},
    {"word": "Entschuldigung", "article": None, "pos": "interjection", "translation": "excuse me; sorry", "domains": ["greetings"], "priority": 9, "example_sentence_de": "Entschuldigung, darf ich vorbei?", "example_sentence_en": "Excuse me, may I get past?", "notes": ""},
    {"word": "Wie heißt du?", "article": None, "pos": "phrase", "translation": "What's your name?", "domains": ["greetings", "questions"], "priority": 10, "example_sentence_de": "Hallo! Wie heißt du? Ich heiße Lukas.", "example_sentence_en": "Hello! What's your name? My name is Lukas.", "notes": ""},
    {"word": "Ich heiße ...", "article": None, "pos": "phrase", "translation": "My name is ...", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Ich heiße Emma.", "example_sentence_en": "My name is Emma.", "notes": ""},
    {"word": "Wie alt bist du?", "article": None, "pos": "phrase", "translation": "How old are you?", "domains": ["greetings", "questions"], "priority": 9, "example_sentence_de": "Wie alt bist du? Ich bin sechs Jahre alt.", "example_sentence_en": "How old are you? I am six years old.", "notes": ""},
    {"word": "Ich bin ... Jahre alt.", "article": None, "pos": "phrase", "translation": "I am ... years old.", "domains": ["greetings", "numbers"], "priority": 9, "example_sentence_de": "Ich bin fünf Jahre alt.", "example_sentence_en": "I am five years old.", "notes": ""},
    {"word": "Wie geht es dir?", "article": None, "pos": "phrase", "translation": "How are you?", "domains": ["greetings", "feelings"], "priority": 9, "example_sentence_de": "Wie geht es dir? Mir geht es gut, danke!", "example_sentence_en": "How are you? I'm fine, thank you!", "notes": ""},
    {"word": "Mir geht es gut.", "article": None, "pos": "phrase", "translation": "I'm fine / I'm doing well.", "domains": ["greetings", "feelings"], "priority": 9, "example_sentence_de": "Mir geht es gut, danke!", "example_sentence_en": "I'm fine, thank you!", "notes": ""},

    # --- QUESTION PATTERNS ---
    {"word": "Wo ist ...?", "article": None, "pos": "phrase", "translation": "Where is ...?", "domains": ["questions", "location"], "priority": 10, "example_sentence_de": "Wo ist mein Ball?", "example_sentence_en": "Where is my ball?", "notes": ""},
    {"word": "Was ist das?", "article": None, "pos": "phrase", "translation": "What is that?", "domains": ["questions"], "priority": 10, "example_sentence_de": "Was ist das? Das ist ein Hund!", "example_sentence_en": "What is that? That is a dog!", "notes": ""},
    {"word": "Wer ist das?", "article": None, "pos": "phrase", "translation": "Who is that?", "domains": ["questions", "family"], "priority": 9, "example_sentence_de": "Wer ist das? Das ist meine Mama.", "example_sentence_en": "Who is that? That is my mum.", "notes": ""},
    {"word": "Kannst du ...?", "article": None, "pos": "phrase", "translation": "Can you ...?", "domains": ["questions", "actions"], "priority": 10, "example_sentence_de": "Kannst du das sehen?", "example_sentence_en": "Can you see that?", "notes": ""},
    {"word": "Magst du ...?", "article": None, "pos": "phrase", "translation": "Do you like ...?", "domains": ["questions", "feelings"], "priority": 10, "example_sentence_de": "Magst du Schokolade?", "example_sentence_en": "Do you like chocolate?", "notes": ""},
    {"word": "Willst du ...?", "article": None, "pos": "phrase", "translation": "Do you want to ...?", "domains": ["questions", "actions"], "priority": 10, "example_sentence_de": "Willst du mit mir spielen?", "example_sentence_en": "Do you want to play with me?", "notes": ""},
    {"word": "Darf ich ...?", "article": None, "pos": "phrase", "translation": "May I ...? / Am I allowed to ...?", "domains": ["questions"], "priority": 9, "example_sentence_de": "Darf ich das haben?", "example_sentence_en": "May I have that?", "notes": ""},
    {"word": "Warum?", "article": None, "pos": "adverb", "translation": "Why?", "domains": ["questions"], "priority": 9, "example_sentence_de": "Warum weinst du?", "example_sentence_en": "Why are you crying?", "notes": ""},
    {"word": "Wann?", "article": None, "pos": "adverb", "translation": "When?", "domains": ["questions", "time"], "priority": 9, "example_sentence_de": "Wann essen wir?", "example_sentence_en": "When do we eat?", "notes": ""},
    {"word": "Wohin gehst du?", "article": None, "pos": "phrase", "translation": "Where are you going?", "domains": ["questions", "location", "actions"], "priority": 8, "example_sentence_de": "Wohin gehst du? Ich gehe in den Garten.", "example_sentence_en": "Where are you going? I'm going to the garden.", "notes": ""},
    {"word": "Hast du ... ?", "article": None, "pos": "phrase", "translation": "Do you have ...?", "domains": ["questions"], "priority": 9, "example_sentence_de": "Hast du einen Stift?", "example_sentence_en": "Do you have a pen?", "notes": ""},

    # --- FAMILY ---
    {"word": "die Mama", "article": "die", "pos": "noun", "translation": "mum, mom", "domains": ["family"], "priority": 10, "example_sentence_de": "Mama, kannst du mir helfen?", "example_sentence_en": "Mum, can you help me?", "notes": ""},
    {"word": "der Papa", "article": "der", "pos": "noun", "translation": "dad", "domains": ["family"], "priority": 10, "example_sentence_de": "Papa, schau mal!", "example_sentence_en": "Dad, look!", "notes": ""},
    {"word": "die Mutter", "article": "die", "pos": "noun", "translation": "mother", "domains": ["family"], "priority": 9, "example_sentence_de": "Meine Mutter kocht Suppe.", "example_sentence_en": "My mother is cooking soup.", "notes": ""},
    {"word": "der Vater", "article": "der", "pos": "noun", "translation": "father", "domains": ["family"], "priority": 9, "example_sentence_de": "Mein Vater liest ein Buch.", "example_sentence_en": "My father is reading a book.", "notes": ""},
    {"word": "der Bruder", "article": "der", "pos": "noun", "translation": "brother", "domains": ["family"], "priority": 10, "example_sentence_de": "Mein Bruder spielt mit Lego.", "example_sentence_en": "My brother is playing with Lego.", "notes": ""},
    {"word": "die Schwester", "article": "die", "pos": "noun", "translation": "sister", "domains": ["family"], "priority": 10, "example_sentence_de": "Meine Schwester singt ein Lied.", "example_sentence_en": "My sister is singing a song.", "notes": ""},
    {"word": "die Oma", "article": "die", "pos": "noun", "translation": "grandma", "domains": ["family"], "priority": 9, "example_sentence_de": "Oma backt Kuchen.", "example_sentence_en": "Grandma is baking a cake.", "notes": ""},
    {"word": "der Opa", "article": "der", "pos": "noun", "translation": "grandpa", "domains": ["family"], "priority": 9, "example_sentence_de": "Opa liest mir eine Geschichte vor.", "example_sentence_en": "Grandpa reads me a story.", "notes": ""},
    {"word": "die Großmutter", "article": "die", "pos": "noun", "translation": "grandmother", "domains": ["family"], "priority": 7, "example_sentence_de": "Die Großmutter wohnt in Berlin.", "example_sentence_en": "The grandmother lives in Berlin.", "notes": ""},
    {"word": "der Großvater", "article": "der", "pos": "noun", "translation": "grandfather", "domains": ["family"], "priority": 7, "example_sentence_de": "Der Großvater hat einen Hund.", "example_sentence_en": "The grandfather has a dog.", "notes": ""},
    {"word": "das Baby", "article": "das", "pos": "noun", "translation": "baby", "domains": ["family"], "priority": 8, "example_sentence_de": "Das Baby schläft.", "example_sentence_en": "The baby is sleeping.", "notes": ""},
    {"word": "der Freund", "article": "der", "pos": "noun", "translation": "friend (male)", "domains": ["family", "greetings"], "priority": 10, "example_sentence_de": "Das ist mein Freund Tim.", "example_sentence_en": "This is my friend Tim.", "notes": ""},
    {"word": "die Freundin", "article": "die", "pos": "noun", "translation": "friend (female)", "domains": ["family", "greetings"], "priority": 10, "example_sentence_de": "Meine Freundin heißt Anna.", "example_sentence_en": "My friend's name is Anna.", "notes": ""},

    # --- PLAY & TOYS ---
    {"word": "spielen", "article": None, "pos": "verb", "translation": "to play", "domains": ["play", "actions"], "priority": 10, "example_sentence_de": "Willst du mit mir spielen?", "example_sentence_en": "Do you want to play with me?", "notes": ""},
    {"word": "das Spielzeug", "article": "das", "pos": "noun", "translation": "toy, toys", "domains": ["toys", "play"], "priority": 10, "example_sentence_de": "Das Spielzeug liegt auf dem Boden.", "example_sentence_en": "The toy is on the floor.", "notes": ""},
    {"word": "die Puppe", "article": "die", "pos": "noun", "translation": "doll", "domains": ["toys", "play"], "priority": 9, "example_sentence_de": "Meine Puppe hat blaue Augen.", "example_sentence_en": "My doll has blue eyes.", "notes": ""},
    {"word": "das Auto", "article": "das", "pos": "noun", "translation": "car", "domains": ["toys", "play"], "priority": 9, "example_sentence_de": "Das rote Auto ist mein liebstes Spielzeug.", "example_sentence_en": "The red car is my favourite toy.", "notes": ""},
    {"word": "der Ball", "article": "der", "pos": "noun", "translation": "ball", "domains": ["toys", "play"], "priority": 10, "example_sentence_de": "Wirf mir den Ball!", "example_sentence_en": "Throw me the ball!", "notes": ""},
    {"word": "der Baustein", "article": "der", "pos": "noun", "translation": "building block", "domains": ["toys", "play"], "priority": 9, "example_sentence_de": "Wir bauen einen Turm aus Bausteinen.", "example_sentence_en": "We are building a tower from blocks.", "notes": ""},
    {"word": "das Puzzle", "article": "das", "pos": "noun", "translation": "puzzle, jigsaw", "domains": ["toys", "play"], "priority": 8, "example_sentence_de": "Das Puzzle hat 50 Teile.", "example_sentence_en": "The puzzle has 50 pieces.", "notes": ""},
    {"word": "rennen", "article": None, "pos": "verb", "translation": "to run", "domains": ["play", "actions"], "priority": 9, "example_sentence_de": "Lass uns um die Wette rennen!", "example_sentence_en": "Let's race each other!", "notes": ""},
    {"word": "springen", "article": None, "pos": "verb", "translation": "to jump", "domains": ["play", "actions"], "priority": 9, "example_sentence_de": "Ich kann hoch springen.", "example_sentence_en": "I can jump high.", "notes": ""},
    {"word": "bauen", "article": None, "pos": "verb", "translation": "to build", "domains": ["play", "actions"], "priority": 9, "example_sentence_de": "Wir bauen eine Burg aus Sand.", "example_sentence_en": "We're building a sandcastle.", "notes": ""},
    {"word": "zeichnen", "article": None, "pos": "verb", "translation": "to draw", "domains": ["play", "school", "actions"], "priority": 9, "example_sentence_de": "Kannst du einen Hund zeichnen?", "example_sentence_en": "Can you draw a dog?", "notes": ""},
    {"word": "werfen", "article": None, "pos": "verb", "translation": "to throw", "domains": ["play", "actions"], "priority": 8, "example_sentence_de": "Wirf den Ball zu mir!", "example_sentence_en": "Throw the ball to me!", "notes": ""},
    {"word": "fangen", "article": None, "pos": "verb", "translation": "to catch; to catch (a person in chase)", "domains": ["play", "actions"], "priority": 8, "example_sentence_de": "Ich fange dich!", "example_sentence_en": "I'll catch you!", "notes": ""},
    {"word": "verstecken", "article": None, "pos": "verb", "translation": "to hide", "domains": ["play", "actions"], "priority": 8, "example_sentence_de": "Lass uns Verstecken spielen!", "example_sentence_en": "Let's play hide and seek!", "notes": ""},
    {"word": "klettern", "article": None, "pos": "verb", "translation": "to climb", "domains": ["play", "actions"], "priority": 8, "example_sentence_de": "Er klettert auf den Baum.", "example_sentence_en": "He is climbing the tree.", "notes": ""},
    {"word": "der Teddy", "article": "der", "pos": "noun", "translation": "teddy bear", "domains": ["toys"], "priority": 8, "example_sentence_de": "Ich schlafe immer mit meinem Teddy.", "example_sentence_en": "I always sleep with my teddy bear.", "notes": ""},
    {"word": "das Lego", "article": "das", "pos": "noun", "translation": "Lego", "domains": ["toys", "play"], "priority": 8, "example_sentence_de": "Wir spielen mit Lego.", "example_sentence_en": "We are playing with Lego.", "notes": ""},
    {"word": "der Sandkasten", "article": "der", "pos": "noun", "translation": "sandpit, sandbox", "domains": ["toys", "play"], "priority": 8, "example_sentence_de": "Die Kinder spielen im Sandkasten.", "example_sentence_en": "The children are playing in the sandpit.", "notes": ""},
    {"word": "die Schaukel", "article": "die", "pos": "noun", "translation": "swing", "domains": ["toys", "play"], "priority": 8, "example_sentence_de": "Kannst du mich auf der Schaukel anschieben?", "example_sentence_en": "Can you push me on the swing?", "notes": ""},
    {"word": "die Rutsche", "article": "die", "pos": "noun", "translation": "slide (playground)", "domains": ["toys", "play"], "priority": 8, "example_sentence_de": "Die Rutsche ist sehr schnell.", "example_sentence_en": "The slide is very fast.", "notes": ""},
    {"word": "das Spiel", "article": "das", "pos": "noun", "translation": "game", "domains": ["play"], "priority": 9, "example_sentence_de": "Das Spiel macht Spaß!", "example_sentence_en": "The game is fun!", "notes": ""},

    # --- FOOD ---
    {"word": "essen", "article": None, "pos": "verb", "translation": "to eat", "domains": ["food", "actions"], "priority": 10, "example_sentence_de": "Willst du jetzt essen?", "example_sentence_en": "Do you want to eat now?", "notes": ""},
    {"word": "trinken", "article": None, "pos": "verb", "translation": "to drink", "domains": ["food", "actions"], "priority": 10, "example_sentence_de": "Ich möchte Wasser trinken.", "example_sentence_en": "I would like to drink water.", "notes": ""},
    {"word": "das Essen", "article": "das", "pos": "noun", "translation": "food; meal", "domains": ["food"], "priority": 10, "example_sentence_de": "Das Essen ist fertig!", "example_sentence_en": "The food is ready!", "notes": ""},
    {"word": "der Hunger", "article": "der", "pos": "noun", "translation": "hunger", "domains": ["food", "feelings"], "priority": 9, "example_sentence_de": "Ich habe Hunger. Können wir essen?", "example_sentence_en": "I'm hungry. Can we eat?", "notes": ""},
    {"word": "der Durst", "article": "der", "pos": "noun", "translation": "thirst", "domains": ["food", "feelings"], "priority": 9, "example_sentence_de": "Ich habe Durst. Kann ich Wasser haben?", "example_sentence_en": "I'm thirsty. Can I have water?", "notes": ""},
    {"word": "das Frühstück", "article": "das", "pos": "noun", "translation": "breakfast", "domains": ["food", "time"], "priority": 9, "example_sentence_de": "Zum Frühstück esse ich Brot mit Butter.", "example_sentence_en": "For breakfast I eat bread with butter.", "notes": ""},
    {"word": "das Mittagessen", "article": "das", "pos": "noun", "translation": "lunch", "domains": ["food", "time"], "priority": 8, "example_sentence_de": "Zum Mittagessen gibt es Nudeln.", "example_sentence_en": "For lunch there is pasta.", "notes": ""},
    {"word": "das Abendessen", "article": "das", "pos": "noun", "translation": "dinner, supper", "domains": ["food", "time"], "priority": 8, "example_sentence_de": "Beim Abendessen essen wir zusammen.", "example_sentence_en": "We eat together at dinner.", "notes": ""},
    {"word": "das Brot", "article": "das", "pos": "noun", "translation": "bread", "domains": ["food"], "priority": 9, "example_sentence_de": "Magst du Brot mit Käse?", "example_sentence_en": "Do you like bread with cheese?", "notes": ""},
    {"word": "die Milch", "article": "die", "pos": "noun", "translation": "milk", "domains": ["food"], "priority": 9, "example_sentence_de": "Trinkst du gerne Milch?", "example_sentence_en": "Do you like drinking milk?", "notes": ""},
    {"word": "das Wasser", "article": "das", "pos": "noun", "translation": "water", "domains": ["food"], "priority": 10, "example_sentence_de": "Darf ich bitte ein Glas Wasser haben?", "example_sentence_en": "May I please have a glass of water?", "notes": ""},
    {"word": "der Saft", "article": "der", "pos": "noun", "translation": "juice", "domains": ["food"], "priority": 8, "example_sentence_de": "Ich möchte Apfelsaft, bitte.", "example_sentence_en": "I would like apple juice, please.", "notes": ""},
    {"word": "der Apfel", "article": "der", "pos": "noun", "translation": "apple", "domains": ["food"], "priority": 8, "example_sentence_de": "Ich esse gerne einen roten Apfel.", "example_sentence_en": "I like eating a red apple.", "notes": ""},
    {"word": "die Banane", "article": "die", "pos": "noun", "translation": "banana", "domains": ["food"], "priority": 8, "example_sentence_de": "Die Banane ist gelb.", "example_sentence_en": "The banana is yellow.", "notes": ""},
    {"word": "der Kuchen", "article": "der", "pos": "noun", "translation": "cake", "domains": ["food"], "priority": 9, "example_sentence_de": "Magst du Kuchen?", "example_sentence_en": "Do you like cake?", "notes": ""},
    {"word": "der Keks", "article": "der", "pos": "noun", "translation": "biscuit, cookie", "domains": ["food"], "priority": 8, "example_sentence_de": "Darf ich noch einen Keks haben?", "example_sentence_en": "May I have another cookie?", "notes": ""},
    {"word": "die Schokolade", "article": "die", "pos": "noun", "translation": "chocolate", "domains": ["food"], "priority": 9, "example_sentence_de": "Magst du Schokolade?", "example_sentence_en": "Do you like chocolate?", "notes": ""},
    {"word": "die Nudeln", "article": "die", "pos": "noun", "translation": "pasta, noodles", "domains": ["food"], "priority": 8, "example_sentence_de": "Heute gibt es Nudeln mit Tomatensoße.", "example_sentence_en": "Today we're having pasta with tomato sauce.", "notes": ""},
    {"word": "die Suppe", "article": "die", "pos": "noun", "translation": "soup", "domains": ["food"], "priority": 8, "example_sentence_de": "Die Suppe ist heiß.", "example_sentence_en": "The soup is hot.", "notes": ""},
    {"word": "das Obst", "article": "das", "pos": "noun", "translation": "fruit", "domains": ["food"], "priority": 8, "example_sentence_de": "Iss mehr Obst!", "example_sentence_en": "Eat more fruit!", "notes": ""},
    {"word": "das Gemüse", "article": "das", "pos": "noun", "translation": "vegetables", "domains": ["food"], "priority": 8, "example_sentence_de": "Magst du Gemüse?", "example_sentence_en": "Do you like vegetables?", "notes": ""},
    {"word": "das Ei", "article": "das", "pos": "noun", "translation": "egg", "domains": ["food"], "priority": 8, "example_sentence_de": "Ich mag gekochte Eier.", "example_sentence_en": "I like boiled eggs.", "notes": ""},
    {"word": "der Käse", "article": "der", "pos": "noun", "translation": "cheese", "domains": ["food"], "priority": 8, "example_sentence_de": "Magst du Käse auf dem Brot?", "example_sentence_en": "Do you like cheese on your bread?", "notes": ""},
    {"word": "die Kartoffel", "article": "die", "pos": "noun", "translation": "potato", "domains": ["food"], "priority": 7, "example_sentence_de": "Wir essen heute Abend Kartoffeln.", "example_sentence_en": "We are having potatoes tonight.", "notes": ""},
    {"word": "lecker", "article": None, "pos": "adjective", "translation": "delicious, yummy", "domains": ["food"], "priority": 9, "example_sentence_de": "Das ist lecker!", "example_sentence_en": "That's delicious!", "notes": ""},
    {"word": "das Glas", "article": "das", "pos": "noun", "translation": "glass (drinking)", "domains": ["food"], "priority": 8, "example_sentence_de": "Kann ich ein Glas Wasser haben?", "example_sentence_en": "Can I have a glass of water?", "notes": ""},
    {"word": "der Teller", "article": "der", "pos": "noun", "translation": "plate", "domains": ["food"], "priority": 8, "example_sentence_de": "Iss alles vom Teller!", "example_sentence_en": "Eat everything on the plate!", "notes": ""},
    {"word": "die Gabel", "article": "die", "pos": "noun", "translation": "fork", "domains": ["food"], "priority": 7, "example_sentence_de": "Benutze die Gabel zum Essen.", "example_sentence_en": "Use the fork for eating.", "notes": ""},
    {"word": "der Löffel", "article": "der", "pos": "noun", "translation": "spoon", "domains": ["food"], "priority": 7, "example_sentence_de": "Nimm einen Löffel für die Suppe.", "example_sentence_en": "Take a spoon for the soup.", "notes": ""},

    # --- ANIMALS ---
    {"word": "der Hund", "article": "der", "pos": "noun", "translation": "dog", "domains": ["animals"], "priority": 10, "example_sentence_de": "Der Hund bellt laut.", "example_sentence_en": "The dog is barking loudly.", "notes": ""},
    {"word": "die Katze", "article": "die", "pos": "noun", "translation": "cat", "domains": ["animals"], "priority": 10, "example_sentence_de": "Die Katze schläft auf dem Sofa.", "example_sentence_en": "The cat is sleeping on the sofa.", "notes": ""},
    {"word": "das Pferd", "article": "das", "pos": "noun", "translation": "horse", "domains": ["animals"], "priority": 9, "example_sentence_de": "Das Pferd läuft schnell.", "example_sentence_en": "The horse runs fast.", "notes": ""},
    {"word": "der Vogel", "article": "der", "pos": "noun", "translation": "bird", "domains": ["animals"], "priority": 9, "example_sentence_de": "Der Vogel singt im Baum.", "example_sentence_en": "The bird is singing in the tree.", "notes": ""},
    {"word": "der Fisch", "article": "der", "pos": "noun", "translation": "fish", "domains": ["animals"], "priority": 9, "example_sentence_de": "Der Fisch schwimmt im Wasser.", "example_sentence_en": "The fish is swimming in the water.", "notes": ""},
    {"word": "die Maus", "article": "die", "pos": "noun", "translation": "mouse", "domains": ["animals"], "priority": 8, "example_sentence_de": "Die Maus hat Angst vor der Katze.", "example_sentence_en": "The mouse is afraid of the cat.", "notes": ""},
    {"word": "der Hase", "article": "der", "pos": "noun", "translation": "rabbit, hare", "domains": ["animals"], "priority": 8, "example_sentence_de": "Der Hase springt im Garten.", "example_sentence_en": "The rabbit is jumping in the garden.", "notes": ""},
    {"word": "die Kuh", "article": "die", "pos": "noun", "translation": "cow", "domains": ["animals"], "priority": 8, "example_sentence_de": "Die Kuh sagt Muh!", "example_sentence_en": "The cow says moo!", "notes": ""},
    {"word": "das Schwein", "article": "das", "pos": "noun", "translation": "pig", "domains": ["animals"], "priority": 8, "example_sentence_de": "Das Schwein lebt auf dem Bauernhof.", "example_sentence_en": "The pig lives on the farm.", "notes": ""},
    {"word": "die Ente", "article": "die", "pos": "noun", "translation": "duck", "domains": ["animals"], "priority": 8, "example_sentence_de": "Die Enten schwimmen im Teich.", "example_sentence_en": "The ducks are swimming in the pond.", "notes": ""},
    {"word": "der Frosch", "article": "der", "pos": "noun", "translation": "frog", "domains": ["animals"], "priority": 8, "example_sentence_de": "Der Frosch springt ins Wasser.", "example_sentence_en": "The frog jumps into the water.", "notes": ""},
    {"word": "der Elefant", "article": "der", "pos": "noun", "translation": "elephant", "domains": ["animals"], "priority": 8, "example_sentence_de": "Der Elefant hat eine lange Nase.", "example_sentence_en": "The elephant has a long nose.", "notes": ""},
    {"word": "der Löwe", "article": "der", "pos": "noun", "translation": "lion", "domains": ["animals"], "priority": 8, "example_sentence_de": "Der Löwe ist der König der Tiere.", "example_sentence_en": "The lion is the king of the animals.", "notes": ""},
    {"word": "der Bär", "article": "der", "pos": "noun", "translation": "bear", "domains": ["animals"], "priority": 8, "example_sentence_de": "Der Bär schläft den ganzen Winter.", "example_sentence_en": "The bear sleeps all winter.", "notes": ""},
    {"word": "der Affe", "article": "der", "pos": "noun", "translation": "monkey, ape", "domains": ["animals"], "priority": 7, "example_sentence_de": "Der Affe klettert auf den Baum.", "example_sentence_en": "The monkey climbs the tree.", "notes": ""},
    {"word": "das Tier", "article": "das", "pos": "noun", "translation": "animal", "domains": ["animals"], "priority": 9, "example_sentence_de": "Was ist dein Lieblingstier?", "example_sentence_en": "What is your favourite animal?", "notes": ""},
    {"word": "das Schaf", "article": "das", "pos": "noun", "translation": "sheep", "domains": ["animals"], "priority": 7, "example_sentence_de": "Das Schaf sagt Bäh!", "example_sentence_en": "The sheep says baa!", "notes": ""},
    {"word": "das Huhn", "article": "das", "pos": "noun", "translation": "chicken", "domains": ["animals"], "priority": 7, "example_sentence_de": "Das Huhn legt Eier.", "example_sentence_en": "The chicken lays eggs.", "notes": ""},

    # --- FEELINGS ---
    {"word": "glücklich", "article": None, "pos": "adjective", "translation": "happy", "domains": ["feelings"], "priority": 10, "example_sentence_de": "Ich bin glücklich!", "example_sentence_en": "I am happy!", "notes": ""},
    {"word": "traurig", "article": None, "pos": "adjective", "translation": "sad", "domains": ["feelings"], "priority": 10, "example_sentence_de": "Warum bist du traurig?", "example_sentence_en": "Why are you sad?", "notes": ""},
    {"word": "müde", "article": None, "pos": "adjective", "translation": "tired", "domains": ["feelings"], "priority": 9, "example_sentence_de": "Ich bin sehr müde.", "example_sentence_en": "I am very tired.", "notes": ""},
    {"word": "ängstlich", "article": None, "pos": "adjective", "translation": "scared, anxious", "domains": ["feelings"], "priority": 8, "example_sentence_de": "Bist du ängstlich?", "example_sentence_en": "Are you scared?", "notes": ""},
    {"word": "gelangweilt", "article": None, "pos": "adjective", "translation": "bored", "domains": ["feelings"], "priority": 8, "example_sentence_de": "Ich bin gelangweilt. Wollen wir spielen?", "example_sentence_en": "I'm bored. Shall we play?", "notes": ""},
    {"word": "aufgeregt", "article": None, "pos": "adjective", "translation": "excited", "domains": ["feelings"], "priority": 8, "example_sentence_de": "Ich bin aufgeregt wegen meines Geburtstags!", "example_sentence_en": "I'm excited about my birthday!", "notes": ""},
    {"word": "wütend", "article": None, "pos": "adjective", "translation": "angry", "domains": ["feelings"], "priority": 8, "example_sentence_de": "Ich bin wütend!", "example_sentence_en": "I am angry!", "notes": ""},
    {"word": "fröhlich", "article": None, "pos": "adjective", "translation": "cheerful, joyful", "domains": ["feelings"], "priority": 9, "example_sentence_de": "Das Kind ist fröhlich.", "example_sentence_en": "The child is cheerful.", "notes": ""},
    {"word": "die Angst", "article": "die", "pos": "noun", "translation": "fear", "domains": ["feelings"], "priority": 8, "example_sentence_de": "Hast du keine Angst?", "example_sentence_en": "Aren't you scared?", "notes": ""},
    {"word": "mögen", "article": None, "pos": "verb", "translation": "to like", "domains": ["feelings", "actions"], "priority": 10, "example_sentence_de": "Ich mag Hunde sehr.", "example_sentence_en": "I like dogs very much.", "notes": ""},
    {"word": "lieben", "article": None, "pos": "verb", "translation": "to love", "domains": ["feelings", "actions"], "priority": 9, "example_sentence_de": "Ich liebe dich!", "example_sentence_en": "I love you!", "notes": ""},
    {"word": "weinen", "article": None, "pos": "verb", "translation": "to cry", "domains": ["feelings", "actions"], "priority": 9, "example_sentence_de": "Warum weinst du?", "example_sentence_en": "Why are you crying?", "notes": ""},
    {"word": "lachen", "article": None, "pos": "verb", "translation": "to laugh", "domains": ["feelings", "actions"], "priority": 9, "example_sentence_de": "Das macht mich lachen!", "example_sentence_en": "That makes me laugh!", "notes": ""},
    {"word": "der Spaß", "article": "der", "pos": "noun", "translation": "fun", "domains": ["feelings", "play"], "priority": 9, "example_sentence_de": "Das macht Spaß!", "example_sentence_en": "That's fun!", "notes": ""},

    # --- BODY ---
    {"word": "der Kopf", "article": "der", "pos": "noun", "translation": "head", "domains": ["body"], "priority": 9, "example_sentence_de": "Mein Kopf tut weh.", "example_sentence_en": "My head hurts.", "notes": ""},
    {"word": "das Auge", "article": "das", "pos": "noun", "translation": "eye", "domains": ["body"], "priority": 9, "example_sentence_de": "Sie hat blaue Augen.", "example_sentence_en": "She has blue eyes.", "notes": ""},
    {"word": "die Nase", "article": "die", "pos": "noun", "translation": "nose", "domains": ["body"], "priority": 9, "example_sentence_de": "Meine Nase ist kalt.", "example_sentence_en": "My nose is cold.", "notes": ""},
    {"word": "der Mund", "article": "der", "pos": "noun", "translation": "mouth", "domains": ["body"], "priority": 9, "example_sentence_de": "Mach bitte den Mund auf.", "example_sentence_en": "Please open your mouth.", "notes": ""},
    {"word": "das Ohr", "article": "das", "pos": "noun", "translation": "ear", "domains": ["body"], "priority": 9, "example_sentence_de": "Ich höre mit meinen Ohren.", "example_sentence_en": "I hear with my ears.", "notes": ""},
    {"word": "das Haar", "article": "das", "pos": "noun", "translation": "hair", "domains": ["body"], "priority": 8, "example_sentence_de": "Sie hat langes Haar.", "example_sentence_en": "She has long hair.", "notes": ""},
    {"word": "die Hand", "article": "die", "pos": "noun", "translation": "hand", "domains": ["body"], "priority": 9, "example_sentence_de": "Gib mir deine Hand.", "example_sentence_en": "Give me your hand.", "notes": ""},
    {"word": "der Finger", "article": "der", "pos": "noun", "translation": "finger", "domains": ["body"], "priority": 8, "example_sentence_de": "Ich habe zehn Finger.", "example_sentence_en": "I have ten fingers.", "notes": ""},
    {"word": "der Arm", "article": "der", "pos": "noun", "translation": "arm", "domains": ["body"], "priority": 8, "example_sentence_de": "Mein Arm ist lang.", "example_sentence_en": "My arm is long.", "notes": ""},
    {"word": "das Bein", "article": "das", "pos": "noun", "translation": "leg", "domains": ["body"], "priority": 8, "example_sentence_de": "Er hat Schmerzen im Bein.", "example_sentence_en": "He has pain in his leg.", "notes": ""},
    {"word": "der Fuß", "article": "der", "pos": "noun", "translation": "foot", "domains": ["body"], "priority": 8, "example_sentence_de": "Mein Fuß ist nass.", "example_sentence_en": "My foot is wet.", "notes": ""},
    {"word": "der Bauch", "article": "der", "pos": "noun", "translation": "belly, stomach", "domains": ["body", "food"], "priority": 8, "example_sentence_de": "Mein Bauch tut weh.", "example_sentence_en": "My stomach hurts.", "notes": ""},
    {"word": "der Zahn", "article": "der", "pos": "noun", "translation": "tooth", "domains": ["body"], "priority": 8, "example_sentence_de": "Ich putze meine Zähne.", "example_sentence_en": "I brush my teeth.", "notes": ""},
    {"word": "der Körper", "article": "der", "pos": "noun", "translation": "body", "domains": ["body"], "priority": 8, "example_sentence_de": "Ich zeige dir die Teile des Körpers.", "example_sentence_en": "I'll show you the parts of the body.", "notes": ""},
    {"word": "die Schulter", "article": "die", "pos": "noun", "translation": "shoulder", "domains": ["body"], "priority": 7, "example_sentence_de": "Er tätschelt mir die Schulter.", "example_sentence_en": "He pats me on the shoulder.", "notes": ""},
    {"word": "das Knie", "article": "das", "pos": "noun", "translation": "knee", "domains": ["body"], "priority": 7, "example_sentence_de": "Ich habe mein Knie aufgeschlagen.", "example_sentence_en": "I've scraped my knee.", "notes": ""},

    # --- COLOURS ---
    {"word": "rot", "article": None, "pos": "adjective", "translation": "red", "domains": ["colours"], "priority": 10, "example_sentence_de": "Das ist ein roter Ball.", "example_sentence_en": "That is a red ball.", "notes": ""},
    {"word": "blau", "article": None, "pos": "adjective", "translation": "blue", "domains": ["colours"], "priority": 10, "example_sentence_de": "Der Himmel ist blau.", "example_sentence_en": "The sky is blue.", "notes": ""},
    {"word": "grün", "article": None, "pos": "adjective", "translation": "green", "domains": ["colours"], "priority": 10, "example_sentence_de": "Das Gras ist grün.", "example_sentence_en": "The grass is green.", "notes": ""},
    {"word": "gelb", "article": None, "pos": "adjective", "translation": "yellow", "domains": ["colours"], "priority": 10, "example_sentence_de": "Die Banane ist gelb.", "example_sentence_en": "The banana is yellow.", "notes": ""},
    {"word": "orange", "article": None, "pos": "adjective", "translation": "orange", "domains": ["colours"], "priority": 9, "example_sentence_de": "Ich mag die orange Farbe.", "example_sentence_en": "I like the colour orange.", "notes": ""},
    {"word": "lila", "article": None, "pos": "adjective", "translation": "purple", "domains": ["colours"], "priority": 9, "example_sentence_de": "Das ist ein lila Schmetterling.", "example_sentence_en": "That is a purple butterfly.", "notes": ""},
    {"word": "rosa", "article": None, "pos": "adjective", "translation": "pink", "domains": ["colours"], "priority": 9, "example_sentence_de": "Sie trägt ein rosa Kleid.", "example_sentence_en": "She is wearing a pink dress.", "notes": ""},
    {"word": "schwarz", "article": None, "pos": "adjective", "translation": "black", "domains": ["colours"], "priority": 10, "example_sentence_de": "Die Katze ist schwarz.", "example_sentence_en": "The cat is black.", "notes": ""},
    {"word": "weiß", "article": None, "pos": "adjective", "translation": "white", "domains": ["colours"], "priority": 10, "example_sentence_de": "Der Schnee ist weiß.", "example_sentence_en": "The snow is white.", "notes": ""},
    {"word": "grau", "article": None, "pos": "adjective", "translation": "grey", "domains": ["colours"], "priority": 8, "example_sentence_de": "Der Elefant ist grau.", "example_sentence_en": "The elephant is grey.", "notes": ""},
    {"word": "braun", "article": None, "pos": "adjective", "translation": "brown", "domains": ["colours"], "priority": 8, "example_sentence_de": "Der Hund ist braun.", "example_sentence_en": "The dog is brown.", "notes": ""},
    {"word": "die Farbe", "article": "die", "pos": "noun", "translation": "colour; paint", "domains": ["colours", "play"], "priority": 9, "example_sentence_de": "Welche Farbe magst du am liebsten?", "example_sentence_en": "Which colour do you like best?", "notes": ""},

    # --- NUMBERS ---
    {"word": "eins", "article": None, "pos": "numeral", "translation": "one", "domains": ["numbers"], "priority": 10, "example_sentence_de": "Ich habe einen Bruder.", "example_sentence_en": "I have one brother.", "notes": ""},
    {"word": "zwei", "article": None, "pos": "numeral", "translation": "two", "domains": ["numbers"], "priority": 10, "example_sentence_de": "Ich habe zwei Hände.", "example_sentence_en": "I have two hands.", "notes": ""},
    {"word": "drei", "article": None, "pos": "numeral", "translation": "three", "domains": ["numbers"], "priority": 10, "example_sentence_de": "Wir haben drei Katzen.", "example_sentence_en": "We have three cats.", "notes": ""},
    {"word": "vier", "article": None, "pos": "numeral", "translation": "four", "domains": ["numbers"], "priority": 10, "example_sentence_de": "Ein Hund hat vier Beine.", "example_sentence_en": "A dog has four legs.", "notes": ""},
    {"word": "fünf", "article": None, "pos": "numeral", "translation": "five", "domains": ["numbers"], "priority": 10, "example_sentence_de": "Ich bin fünf Jahre alt.", "example_sentence_en": "I am five years old.", "notes": ""},
    {"word": "sechs", "article": None, "pos": "numeral", "translation": "six", "domains": ["numbers"], "priority": 10, "example_sentence_de": "Sie ist sechs Jahre alt.", "example_sentence_en": "She is six years old.", "notes": ""},
    {"word": "sieben", "article": None, "pos": "numeral", "translation": "seven", "domains": ["numbers"], "priority": 9, "example_sentence_de": "Die Woche hat sieben Tage.", "example_sentence_en": "The week has seven days.", "notes": ""},
    {"word": "acht", "article": None, "pos": "numeral", "translation": "eight", "domains": ["numbers"], "priority": 9, "example_sentence_de": "Ich schlafe acht Stunden.", "example_sentence_en": "I sleep eight hours.", "notes": ""},
    {"word": "neun", "article": None, "pos": "numeral", "translation": "nine", "domains": ["numbers"], "priority": 9, "example_sentence_de": "Das Puzzle hat neun Teile.", "example_sentence_en": "The puzzle has nine pieces.", "notes": ""},
    {"word": "zehn", "article": None, "pos": "numeral", "translation": "ten", "domains": ["numbers"], "priority": 9, "example_sentence_de": "Ich habe zehn Finger.", "example_sentence_en": "I have ten fingers.", "notes": ""},
    {"word": "elf", "article": None, "pos": "numeral", "translation": "eleven", "domains": ["numbers"], "priority": 8, "example_sentence_de": "Es ist elf Uhr.", "example_sentence_en": "It is eleven o'clock.", "notes": ""},
    {"word": "zwölf", "article": None, "pos": "numeral", "translation": "twelve", "domains": ["numbers"], "priority": 8, "example_sentence_de": "Ein Jahr hat zwölf Monate.", "example_sentence_en": "A year has twelve months.", "notes": ""},
    {"word": "zwanzig", "article": None, "pos": "numeral", "translation": "twenty", "domains": ["numbers"], "priority": 7, "example_sentence_de": "Ich zähle bis zwanzig.", "example_sentence_en": "I count to twenty.", "notes": ""},
    {"word": "zählen", "article": None, "pos": "verb", "translation": "to count", "domains": ["numbers", "school"], "priority": 8, "example_sentence_de": "Kannst du bis zehn zählen?", "example_sentence_en": "Can you count to ten?", "notes": ""},

    # --- SCHOOL / KINDERGARTEN ---
    {"word": "die Schule", "article": "die", "pos": "noun", "translation": "school", "domains": ["school"], "priority": 9, "example_sentence_de": "Wann gehst du in die Schule?", "example_sentence_en": "When do you go to school?", "notes": ""},
    {"word": "der Kindergarten", "article": "der", "pos": "noun", "translation": "kindergarten, nursery", "domains": ["school"], "priority": 9, "example_sentence_de": "Im Kindergarten male ich gerne.", "example_sentence_en": "At kindergarten I like to paint.", "notes": ""},
    {"word": "lernen", "article": None, "pos": "verb", "translation": "to learn", "domains": ["school", "actions"], "priority": 9, "example_sentence_de": "Ich lerne viele neue Wörter.", "example_sentence_en": "I am learning many new words.", "notes": ""},
    {"word": "malen", "article": None, "pos": "verb", "translation": "to paint, to colour in", "domains": ["school", "play", "actions"], "priority": 9, "example_sentence_de": "Ich male ein Bild von meiner Familie.", "example_sentence_en": "I am painting a picture of my family.", "notes": ""},
    {"word": "das Buch", "article": "das", "pos": "noun", "translation": "book", "domains": ["school"], "priority": 9, "example_sentence_de": "Lies mir ein Buch vor!", "example_sentence_en": "Read me a book!", "notes": ""},
    {"word": "der Stift", "article": "der", "pos": "noun", "translation": "pen, pencil, felt-tip", "domains": ["school", "play"], "priority": 8, "example_sentence_de": "Leihst du mir deinen Stift?", "example_sentence_en": "Can you lend me your pen?", "notes": ""},
    {"word": "der Bleistift", "article": "der", "pos": "noun", "translation": "pencil", "domains": ["school"], "priority": 8, "example_sentence_de": "Ich brauche einen Bleistift.", "example_sentence_en": "I need a pencil.", "notes": ""},
    {"word": "der Buntstift", "article": "der", "pos": "noun", "translation": "coloured pencil, crayon", "domains": ["school", "colours"], "priority": 8, "example_sentence_de": "Male mit dem roten Buntstift.", "example_sentence_en": "Colour it with the red crayon.", "notes": ""},
    {"word": "die Lehrerin", "article": "die", "pos": "noun", "translation": "teacher (female)", "domains": ["school"], "priority": 8, "example_sentence_de": "Meine Lehrerin ist nett.", "example_sentence_en": "My teacher is nice.", "notes": ""},
    {"word": "der Lehrer", "article": "der", "pos": "noun", "translation": "teacher (male)", "domains": ["school"], "priority": 8, "example_sentence_de": "Der Lehrer liest uns eine Geschichte vor.", "example_sentence_en": "The teacher reads us a story.", "notes": ""},
    {"word": "die Pause", "article": "die", "pos": "noun", "translation": "break, recess", "domains": ["school"], "priority": 8, "example_sentence_de": "In der Pause spielen wir draußen.", "example_sentence_en": "During break we play outside.", "notes": ""},
    {"word": "die Hausaufgabe", "article": "die", "pos": "noun", "translation": "homework", "domains": ["school"], "priority": 7, "example_sentence_de": "Hast du deine Hausaufgaben gemacht?", "example_sentence_en": "Have you done your homework?", "notes": ""},
    {"word": "lesen", "article": None, "pos": "verb", "translation": "to read", "domains": ["school", "actions"], "priority": 9, "example_sentence_de": "Kannst du schon lesen?", "example_sentence_en": "Can you read already?", "notes": ""},
    {"word": "schreiben", "article": None, "pos": "verb", "translation": "to write", "domains": ["school", "actions"], "priority": 8, "example_sentence_de": "Schreib deinen Namen auf das Bild.", "example_sentence_en": "Write your name on the picture.", "notes": ""},

    # --- ACTIONS (core verbs) ---
    {"word": "gehen", "article": None, "pos": "verb", "translation": "to go, to walk", "domains": ["actions"], "priority": 10, "example_sentence_de": "Wollen wir in den Park gehen?", "example_sentence_en": "Shall we go to the park?", "notes": ""},
    {"word": "kommen", "article": None, "pos": "verb", "translation": "to come", "domains": ["actions"], "priority": 10, "example_sentence_de": "Komm her!", "example_sentence_en": "Come here!", "notes": ""},
    {"word": "machen", "article": None, "pos": "verb", "translation": "to do, to make", "domains": ["actions"], "priority": 10, "example_sentence_de": "Was machst du?", "example_sentence_en": "What are you doing?", "notes": ""},
    {"word": "sehen", "article": None, "pos": "verb", "translation": "to see", "domains": ["actions"], "priority": 10, "example_sentence_de": "Kannst du das sehen?", "example_sentence_en": "Can you see that?", "notes": ""},
    {"word": "hören", "article": None, "pos": "verb", "translation": "to hear, to listen", "domains": ["actions"], "priority": 9, "example_sentence_de": "Kannst du das hören?", "example_sentence_en": "Can you hear that?", "notes": ""},
    {"word": "schlafen", "article": None, "pos": "verb", "translation": "to sleep", "domains": ["actions", "time"], "priority": 9, "example_sentence_de": "Wann schläfst du?", "example_sentence_en": "When do you sleep?", "notes": ""},
    {"word": "aufwachen", "article": None, "pos": "verb", "translation": "to wake up", "domains": ["actions", "time"], "priority": 8, "example_sentence_de": "Ich wache früh auf.", "example_sentence_en": "I wake up early.", "notes": ""},
    {"word": "anziehen", "article": None, "pos": "verb", "translation": "to put on (clothes), to get dressed", "domains": ["actions"], "priority": 8, "example_sentence_de": "Zieh deine Jacke an!", "example_sentence_en": "Put your jacket on!", "notes": ""},
    {"word": "helfen", "article": None, "pos": "verb", "translation": "to help", "domains": ["actions"], "priority": 10, "example_sentence_de": "Kannst du mir helfen?", "example_sentence_en": "Can you help me?", "notes": ""},
    {"word": "zeigen", "article": None, "pos": "verb", "translation": "to show", "domains": ["actions"], "priority": 9, "example_sentence_de": "Zeig mir, wie das geht!", "example_sentence_en": "Show me how that works!", "notes": ""},
    {"word": "geben", "article": None, "pos": "verb", "translation": "to give", "domains": ["actions"], "priority": 9, "example_sentence_de": "Kannst du mir den Ball geben?", "example_sentence_en": "Can you give me the ball?", "notes": ""},
    {"word": "nehmen", "article": None, "pos": "verb", "translation": "to take", "domains": ["actions"], "priority": 9, "example_sentence_de": "Nimm die Puppe.", "example_sentence_en": "Take the doll.", "notes": ""},
    {"word": "bringen", "article": None, "pos": "verb", "translation": "to bring", "domains": ["actions"], "priority": 9, "example_sentence_de": "Kannst du mir bitte Wasser bringen?", "example_sentence_en": "Can you please bring me water?", "notes": ""},
    {"word": "suchen", "article": None, "pos": "verb", "translation": "to look for, to search", "domains": ["actions", "play"], "priority": 8, "example_sentence_de": "Ich suche meinen Teddy.", "example_sentence_en": "I'm looking for my teddy.", "notes": ""},
    {"word": "finden", "article": None, "pos": "verb", "translation": "to find", "domains": ["actions"], "priority": 9, "example_sentence_de": "Ich habe meinen Ball gefunden!", "example_sentence_en": "I found my ball!", "notes": ""},
    {"word": "sitzen", "article": None, "pos": "verb", "translation": "to sit", "domains": ["actions"], "priority": 8, "example_sentence_de": "Sitz bitte still!", "example_sentence_en": "Please sit still!", "notes": ""},
    {"word": "stehen", "article": None, "pos": "verb", "translation": "to stand", "domains": ["actions"], "priority": 8, "example_sentence_de": "Steh bitte auf.", "example_sentence_en": "Please stand up.", "notes": ""},
    {"word": "laufen", "article": None, "pos": "verb", "translation": "to walk; to run", "domains": ["actions", "play"], "priority": 9, "example_sentence_de": "Nicht so schnell laufen!", "example_sentence_en": "Don't run so fast!", "notes": ""},
    {"word": "öffnen", "article": None, "pos": "verb", "translation": "to open", "domains": ["actions"], "priority": 7, "example_sentence_de": "Kannst du die Tür öffnen?", "example_sentence_en": "Can you open the door?", "notes": ""},
    {"word": "schließen", "article": None, "pos": "verb", "translation": "to close", "domains": ["actions"], "priority": 7, "example_sentence_de": "Bitte schließ das Fenster.", "example_sentence_en": "Please close the window.", "notes": ""},
    {"word": "singen", "article": None, "pos": "verb", "translation": "to sing", "domains": ["actions", "play"], "priority": 8, "example_sentence_de": "Willst du ein Lied singen?", "example_sentence_en": "Do you want to sing a song?", "notes": ""},
    {"word": "tanzen", "article": None, "pos": "verb", "translation": "to dance", "domains": ["actions", "play"], "priority": 8, "example_sentence_de": "Wollen wir tanzen?", "example_sentence_en": "Shall we dance?", "notes": ""},
    {"word": "aufräumen", "article": None, "pos": "verb", "translation": "to tidy up, to clear up", "domains": ["actions"], "priority": 8, "example_sentence_de": "Räum dein Zimmer auf!", "example_sentence_en": "Tidy up your room!", "notes": ""},

    # --- LOCATION ---
    {"word": "hier", "article": None, "pos": "adverb", "translation": "here", "domains": ["location"], "priority": 10, "example_sentence_de": "Komm hier her!", "example_sentence_en": "Come here!", "notes": ""},
    {"word": "dort", "article": None, "pos": "adverb", "translation": "there", "domains": ["location"], "priority": 9, "example_sentence_de": "Schau dort drüben!", "example_sentence_en": "Look over there!", "notes": ""},
    {"word": "drinnen", "article": None, "pos": "adverb", "translation": "inside, indoors", "domains": ["location"], "priority": 8, "example_sentence_de": "Wir spielen heute drinnen.", "example_sentence_en": "We are playing inside today.", "notes": ""},
    {"word": "draußen", "article": None, "pos": "adverb", "translation": "outside, outdoors", "domains": ["location"], "priority": 8, "example_sentence_de": "Darf ich draußen spielen?", "example_sentence_en": "May I play outside?", "notes": ""},
    {"word": "oben", "article": None, "pos": "adverb", "translation": "up, above, upstairs", "domains": ["location"], "priority": 8, "example_sentence_de": "Der Ball ist da oben.", "example_sentence_en": "The ball is up there.", "notes": ""},
    {"word": "unten", "article": None, "pos": "adverb", "translation": "down, below, downstairs", "domains": ["location"], "priority": 8, "example_sentence_de": "Der Schuh liegt unten.", "example_sentence_en": "The shoe is down below.", "notes": ""},
    {"word": "neben", "article": None, "pos": "preposition", "translation": "next to, beside", "domains": ["location"], "priority": 8, "example_sentence_de": "Sitz neben mir!", "example_sentence_en": "Sit next to me!", "notes": ""},
    {"word": "hinter", "article": None, "pos": "preposition", "translation": "behind", "domains": ["location"], "priority": 8, "example_sentence_de": "Das Kätzchen ist hinter dem Sofa.", "example_sentence_en": "The kitten is behind the sofa.", "notes": ""},
    {"word": "vor", "article": None, "pos": "preposition", "translation": "in front of; before", "domains": ["location", "time"], "priority": 8, "example_sentence_de": "Steh vor mir!", "example_sentence_en": "Stand in front of me!", "notes": ""},
    {"word": "links", "article": None, "pos": "adverb", "translation": "left", "domains": ["location"], "priority": 8, "example_sentence_de": "Geh nach links!", "example_sentence_en": "Go left!", "notes": ""},
    {"word": "rechts", "article": None, "pos": "adverb", "translation": "right", "domains": ["location"], "priority": 8, "example_sentence_de": "Geh nach rechts!", "example_sentence_en": "Go right!", "notes": ""},

    # --- TIME ---
    {"word": "heute", "article": None, "pos": "adverb", "translation": "today", "domains": ["time"], "priority": 10, "example_sentence_de": "Was machen wir heute?", "example_sentence_en": "What are we doing today?", "notes": ""},
    {"word": "morgen", "article": None, "pos": "adverb", "translation": "tomorrow", "domains": ["time"], "priority": 10, "example_sentence_de": "Bis morgen!", "example_sentence_en": "See you tomorrow!", "notes": ""},
    {"word": "gestern", "article": None, "pos": "adverb", "translation": "yesterday", "domains": ["time"], "priority": 8, "example_sentence_de": "Gestern war ich krank.", "example_sentence_en": "Yesterday I was ill.", "notes": ""},
    {"word": "jetzt", "article": None, "pos": "adverb", "translation": "now", "domains": ["time"], "priority": 10, "example_sentence_de": "Wir essen jetzt.", "example_sentence_en": "We are eating now.", "notes": ""},
    {"word": "später", "article": None, "pos": "adverb", "translation": "later", "domains": ["time"], "priority": 9, "example_sentence_de": "Können wir das später machen?", "example_sentence_en": "Can we do that later?", "notes": ""},
    {"word": "immer", "article": None, "pos": "adverb", "translation": "always", "domains": ["time"], "priority": 8, "example_sentence_de": "Ich schlafe immer gut.", "example_sentence_en": "I always sleep well.", "notes": ""},
    {"word": "manchmal", "article": None, "pos": "adverb", "translation": "sometimes", "domains": ["time"], "priority": 8, "example_sentence_de": "Manchmal esse ich Schokolade.", "example_sentence_en": "Sometimes I eat chocolate.", "notes": ""},
    {"word": "bald", "article": None, "pos": "adverb", "translation": "soon", "domains": ["time"], "priority": 8, "example_sentence_de": "Wir kommen bald nach Hause.", "example_sentence_en": "We'll be home soon.", "notes": ""},
    {"word": "früh", "article": None, "pos": "adverb", "translation": "early; morning", "domains": ["time"], "priority": 8, "example_sentence_de": "Ich stehe früh auf.", "example_sentence_en": "I get up early.", "notes": ""},
    {"word": "der Tag", "article": "der", "pos": "noun", "translation": "day", "domains": ["time"], "priority": 9, "example_sentence_de": "Wie war dein Tag?", "example_sentence_en": "How was your day?", "notes": ""},
    {"word": "die Nacht", "article": "die", "pos": "noun", "translation": "night", "domains": ["time"], "priority": 9, "example_sentence_de": "Gute Nacht!", "example_sentence_en": "Good night!", "notes": ""},
    {"word": "der Morgen", "article": "der", "pos": "noun", "translation": "morning", "domains": ["time"], "priority": 8, "example_sentence_de": "Am Morgen esse ich Brot.", "example_sentence_en": "In the morning I eat bread.", "notes": ""},
    {"word": "der Abend", "article": "der", "pos": "noun", "translation": "evening", "domains": ["time"], "priority": 8, "example_sentence_de": "Am Abend lese ich ein Buch.", "example_sentence_en": "In the evening I read a book.", "notes": ""},

    # --- MISCELLANEOUS / HIGH UTILITY ---
    {"word": "nein", "article": None, "pos": "interjection", "translation": "no", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Nein, das will ich nicht.", "example_sentence_en": "No, I don't want that.", "notes": ""},
    {"word": "ja", "article": None, "pos": "interjection", "translation": "yes", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Ja, ich mag das!", "example_sentence_en": "Yes, I like that!", "notes": ""},
    {"word": "gut", "article": None, "pos": "adjective", "translation": "good", "domains": ["greetings", "feelings"], "priority": 10, "example_sentence_de": "Das ist sehr gut!", "example_sentence_en": "That is very good!", "notes": ""},
    {"word": "schlecht", "article": None, "pos": "adjective", "translation": "bad", "domains": ["feelings"], "priority": 8, "example_sentence_de": "Das schmeckt nicht schlecht.", "example_sentence_en": "That doesn't taste bad.", "notes": ""},
    {"word": "groß", "article": None, "pos": "adjective", "translation": "big, large, tall", "domains": ["play"], "priority": 9, "example_sentence_de": "Ich will groß werden.", "example_sentence_en": "I want to grow big.", "notes": ""},
    {"word": "klein", "article": None, "pos": "adjective", "translation": "small, little", "domains": ["play"], "priority": 9, "example_sentence_de": "Das ist ein kleiner Hund.", "example_sentence_en": "That is a small dog.", "notes": ""},
    {"word": "schnell", "article": None, "pos": "adjective", "translation": "fast, quick", "domains": ["play", "actions"], "priority": 8, "example_sentence_de": "Lauf schnell!", "example_sentence_en": "Run fast!", "notes": ""},
    {"word": "langsam", "article": None, "pos": "adjective", "translation": "slow", "domains": ["play", "actions"], "priority": 7, "example_sentence_de": "Geh langsamer!", "example_sentence_en": "Go slower!", "notes": ""},
    {"word": "laut", "article": None, "pos": "adjective", "translation": "loud, noisy", "domains": ["play"], "priority": 7, "example_sentence_de": "Sei nicht so laut!", "example_sentence_en": "Don't be so loud!", "notes": ""},
    {"word": "leise", "article": None, "pos": "adjective", "translation": "quiet, soft (sound)", "domains": ["play"], "priority": 7, "example_sentence_de": "Sei bitte leise, das Baby schläft.", "example_sentence_en": "Please be quiet, the baby is sleeping.", "notes": ""},
    {"word": "schön", "article": None, "pos": "adjective", "translation": "beautiful, nice, lovely", "domains": ["feelings"], "priority": 9, "example_sentence_de": "Das ist sehr schön!", "example_sentence_en": "That is very beautiful!", "notes": ""},
    {"word": "lustig", "article": None, "pos": "adjective", "translation": "funny, amusing", "domains": ["feelings", "play"], "priority": 8, "example_sentence_de": "Das ist sehr lustig!", "example_sentence_en": "That is very funny!", "notes": ""},
    {"word": "toll", "article": None, "pos": "adjective", "translation": "great, awesome, cool", "domains": ["feelings", "play"], "priority": 9, "example_sentence_de": "Das ist toll!", "example_sentence_en": "That's great!", "notes": ""},
    {"word": "der Name", "article": "der", "pos": "noun", "translation": "name", "domains": ["greetings"], "priority": 8, "example_sentence_de": "Was ist dein Name?", "example_sentence_en": "What is your name?", "notes": ""},
    {"word": "das Haus", "article": "das", "pos": "noun", "translation": "house, home", "domains": ["location"], "priority": 9, "example_sentence_de": "Ich gehe nach Hause.", "example_sentence_en": "I am going home.", "notes": ""},
    {"word": "das Zimmer", "article": "das", "pos": "noun", "translation": "room", "domains": ["location"], "priority": 8, "example_sentence_de": "Mein Zimmer ist groß.", "example_sentence_en": "My room is big.", "notes": ""},
    {"word": "der Garten", "article": "der", "pos": "noun", "translation": "garden, yard", "domains": ["location", "play"], "priority": 8, "example_sentence_de": "Wir spielen im Garten.", "example_sentence_en": "We are playing in the garden.", "notes": ""},
    {"word": "der Baum", "article": "der", "pos": "noun", "translation": "tree", "domains": ["location", "animals"], "priority": 7, "example_sentence_de": "Der Vogel sitzt im Baum.", "example_sentence_en": "The bird is sitting in the tree.", "notes": ""},
    {"word": "das Lied", "article": "das", "pos": "noun", "translation": "song", "domains": ["play"], "priority": 8, "example_sentence_de": "Singen wir ein Lied!", "example_sentence_en": "Let's sing a song!", "notes": ""},
    {"word": "die Geschichte", "article": "die", "pos": "noun", "translation": "story", "domains": ["school", "play"], "priority": 8, "example_sentence_de": "Erzähl mir eine Geschichte!", "example_sentence_en": "Tell me a story!", "notes": ""},
    {"word": "das Geburtstag", "article": "der", "pos": "noun", "translation": "birthday", "domains": ["greetings", "time"], "priority": 8, "example_sentence_de": "Wann ist dein Geburtstag?", "example_sentence_en": "When is your birthday?", "notes": "notes: masculine: der Geburtstag"},
    {"word": "der Geburtstag", "article": "der", "pos": "noun", "translation": "birthday", "domains": ["greetings", "time"], "priority": 9, "example_sentence_de": "Alles Gute zum Geburtstag!", "example_sentence_en": "Happy birthday!", "notes": ""},
    {"word": "sehr", "article": None, "pos": "adverb", "translation": "very", "domains": ["greetings", "feelings"], "priority": 8, "example_sentence_de": "Ich bin sehr glücklich.", "example_sentence_en": "I am very happy.", "notes": ""},
    {"word": "auch", "article": None, "pos": "adverb", "translation": "also, too", "domains": ["greetings"], "priority": 8, "example_sentence_de": "Ich auch!", "example_sentence_en": "Me too!", "notes": ""},
    {"word": "nicht", "article": None, "pos": "adverb", "translation": "not", "domains": ["greetings"], "priority": 10, "example_sentence_de": "Das ist nicht mein Ball.", "example_sentence_en": "That is not my ball.", "notes": ""},
    {"word": "noch", "article": None, "pos": "adverb", "translation": "still, yet, more", "domains": ["time"], "priority": 7, "example_sentence_de": "Ich will noch mehr Kuchen.", "example_sentence_en": "I want more cake.", "notes": ""},
    {"word": "Komm!", "article": None, "pos": "phrase", "translation": "Come! / Come on!", "domains": ["actions", "greetings"], "priority": 9, "example_sentence_de": "Komm, wir spielen draußen!", "example_sentence_en": "Come on, let's play outside!", "notes": "imperative of kommen"},
    {"word": "Schau mal!", "article": None, "pos": "phrase", "translation": "Look! / Look at that!", "domains": ["actions", "greetings"], "priority": 9, "example_sentence_de": "Schau mal, ein Regenbogen!", "example_sentence_en": "Look, a rainbow!", "notes": ""},
    {"word": "Lass uns ...!", "article": None, "pos": "phrase", "translation": "Let's ...!", "domains": ["actions", "play", "greetings"], "priority": 9, "example_sentence_de": "Lass uns Fußball spielen!", "example_sentence_en": "Let's play football!", "notes": ""},
    {"word": "Ich weiß nicht.", "article": None, "pos": "phrase", "translation": "I don't know.", "domains": ["greetings", "questions"], "priority": 8, "example_sentence_de": "Ich weiß nicht, wo der Ball ist.", "example_sentence_en": "I don't know where the ball is.", "notes": ""},
    {"word": "Ich verstehe nicht.", "article": None, "pos": "phrase", "translation": "I don't understand.", "domains": ["greetings"], "priority": 9, "example_sentence_de": "Ich verstehe nicht. Kannst du das wiederholen?", "example_sentence_en": "I don't understand. Can you repeat that?", "notes": ""},
    {"word": "Noch einmal, bitte.", "article": None, "pos": "phrase", "translation": "Once more, please.", "domains": ["greetings"], "priority": 8, "example_sentence_de": "Noch einmal, bitte! Das war lustig.", "example_sentence_en": "Once more, please! That was fun.", "notes": ""},
    {"word": "das Wort", "article": "das", "pos": "noun", "translation": "word", "domains": ["school"], "priority": 7, "example_sentence_de": "Ich lerne viele neue Wörter.", "example_sentence_en": "I am learning many new words.", "notes": ""},
]


def deduplicate_new_vocab(new_vocab: list[dict], existing_words: set[str]) -> list[dict]:
    """Remove new vocab items already in the existing deck."""
    result = []
    seen_words: set[str] = set()
    for item in new_vocab:
        w_lower = item["word"].lower().strip()
        # Remove article prefix for comparison
        bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", w_lower).strip()
        # Also strip punctuation for phrases
        bare_clean = re.sub(r"[?.!…]", "", bare).strip()

        # Skip if word (or bare form) already in existing deck
        skip = False
        for variant in [w_lower, bare, bare_clean]:
            if variant in existing_words:
                skip = True
                break
            # Check stemmed form
            if any(variant.startswith(ex[:4]) and len(ex) >= 4 for ex in existing_words if len(ex) >= 4 and ex == variant):
                skip = True
                break

        # Skip duplicates within new_vocab itself
        if bare_clean in seen_words:
            skip = True

        if not skip:
            result.append(item)
            seen_words.add(bare_clean)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Agent 2: Child-Conversation Vocabulary Analyser")
    print("=" * 60)

    # Load deck
    print(f"\nLoading deck from {INPUT_FILE} ...")
    with open(INPUT_FILE, encoding="utf-8") as f:
        notes = json.load(f)
    print(f"  Loaded {len(notes)} notes.")

    # Build set of existing words for deduplication
    existing_words: set[str] = set()
    for note in notes:
        w = note["fields"]["Word"].lower().strip()
        t = note["fields"]["WordTranslation"].lower().strip()
        existing_words.add(w)
        existing_words.add(t)
        # bare form
        bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", w).strip()
        existing_words.add(bare)

    # ---------- Step 1: Score existing notes ----------
    print("\nScoring existing notes ...")
    selected = []
    domain_counts: dict[str, int] = {d: 0 for d in DOMAIN_KEYWORDS}

    for i, note in enumerate(notes):
        if i % 500 == 0:
            print(f"  Processed {i}/{len(notes)} notes ...")

        word = note["fields"]["Word"]
        translation = note["fields"]["WordTranslation"]
        second_trans = note["fields"].get("WordSecondTranslation", "")
        sentence = note["fields"].get("Sentence", "")
        ipa = note["fields"].get("IPA", "")

        domains = match_domains(word, translation + " " + second_trans)
        if not domains:
            continue

        score = score_note(note, domains)
        if score <= 0:
            continue

        status = get_scheduling_status(note["scheduling"])
        has_sentence = bool(sentence.strip())
        has_ipa = bool(ipa.strip())

        for d in domains:
            domain_counts[d] += 1

        selected.append({
            **note,
            "child_domains": domains,
            "priority_score": score,
            "has_sentence": has_sentence,
            "has_ipa": has_ipa,
            "scheduling_status": status,
        })

    # Sort by priority descending
    selected.sort(key=lambda x: x["priority_score"], reverse=True)
    print(f"  Selected {len(selected)} child-relevant notes.")

    # ---------- Step 2: Net-new vocabulary ----------
    print("\nDeduplicating net-new vocabulary ...")
    new_vocab = deduplicate_new_vocab(NEW_VOCAB_RAW, existing_words)
    # Also deduplicate the "das Geburtstag" duplicate we included
    seen = set()
    deduped_new_vocab = []
    for item in new_vocab:
        key = re.sub(r"^(der|die|das|ein|eine)\s+", "", item["word"].lower().strip())
        key = re.sub(r"[?.!…]", "", key).strip()
        if key not in seen:
            seen.add(key)
            deduped_new_vocab.append(item)
    new_vocab = deduped_new_vocab
    new_vocab.sort(key=lambda x: x["priority"], reverse=True)
    print(f"  Net-new vocabulary items: {len(new_vocab)}")

    # ---------- Save outputs ----------
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nWriting {OUT_SELECTED} ...")
    with open(OUT_SELECTED, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)

    print(f"Writing {OUT_NEW_VOCAB} ...")
    with open(OUT_NEW_VOCAB, "w", encoding="utf-8") as f:
        json.dump(new_vocab, f, ensure_ascii=False, indent=2)

    # ---------- Report ----------
    print(f"\nGenerating {OUT_REPORT} ...")

    # Priority buckets
    high = [n for n in selected if n["priority_score"] >= 8]
    medium = [n for n in selected if 5 <= n["priority_score"] < 8]
    low = [n for n in selected if n["priority_score"] < 5]

    with_sentence = sum(1 for n in selected if n["has_sentence"])

    # Scheduling breakdown
    sched_counts: dict[str, int] = {"new": 0, "learning": 0, "young": 0, "mature": 0}
    for n in selected:
        sched_counts[n["scheduling_status"]] += 1

    # New vocab domain breakdown
    new_domain_counts: dict[str, int] = {d: 0 for d in DOMAIN_KEYWORDS}
    new_pos_counts: dict[str, int] = {}
    for item in new_vocab:
        for d in item["domains"]:
            new_domain_counts[d] = new_domain_counts.get(d, 0) + 1
        pos = item["pos"]
        new_pos_counts[pos] = new_pos_counts.get(pos, 0) + 1

    top20_existing = selected[:20]
    top20_new = sorted(new_vocab, key=lambda x: x["priority"], reverse=True)[:20]

    report_lines = [
        "# Agent 2 Vocabulary Analysis Report",
        "",
        f"*Generated: 2026-02-25*",
        "",
        "## Overview",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total notes in existing deck | {len(notes)} |",
        f"| Notes matched as child-relevant | {len(selected)} |",
        f"| Notes with example sentences | {with_sentence} |",
        f"| Net-new vocabulary items | {len(new_vocab)} |",
        "",
        "## Matched Notes by Domain",
        "",
        "| Domain | Count |",
        "|---|---|",
    ]
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            report_lines.append(f"| {domain} | {count} |")

    report_lines += [
        "",
        "## Priority Distribution (Existing Deck)",
        "",
        f"| Priority Band | Count |",
        f"|---|---|",
        f"| High (8–10) | {len(high)} |",
        f"| Medium (5–7) | {len(medium)} |",
        f"| Low (0–4) | {len(low)} |",
        "",
        "## Scheduling Status (Matched Notes)",
        "",
        f"| Status | Count |",
        f"|---|---|",
        f"| New (unseen) | {sched_counts['new']} |",
        f"| Learning (<= 7d interval) | {sched_counts['learning']} |",
        f"| Young (8–21d interval) | {sched_counts['young']} |",
        f"| Mature (> 21d interval) | {sched_counts['mature']} |",
        "",
        "## Top 20 Highest-Priority Existing Cards",
        "",
        "| # | Word | Translation | Score | Domains | Status |",
        "|---|---|---|---|---|---|",
    ]
    for i, n in enumerate(top20_existing, 1):
        w = n["fields"]["Word"]
        t = n["fields"]["WordTranslation"]
        s = n["priority_score"]
        d = ", ".join(n["child_domains"])
        st = n["scheduling_status"]
        report_lines.append(f"| {i} | {w} | {t} | {s} | {d} | {st} |")

    report_lines += [
        "",
        "## Net-New Vocabulary: Domain Breakdown",
        "",
        "| Domain | Count |",
        "|---|---|",
    ]
    for domain, count in sorted(new_domain_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            report_lines.append(f"| {domain} | {count} |")

    report_lines += [
        "",
        "## Net-New Vocabulary: Part-of-Speech Breakdown",
        "",
        "| POS | Count |",
        "|---|---|",
    ]
    for pos, count in sorted(new_pos_counts.items(), key=lambda x: -x[1]):
        report_lines.append(f"| {pos} | {count} |")

    report_lines += [
        "",
        "## Top 20 Highest-Priority New Vocabulary Items",
        "",
        "| # | Word | Translation | Priority | Domains |",
        "|---|---|---|---|---|",
    ]
    for i, item in enumerate(top20_new, 1):
        w = item["word"]
        t = item["translation"]
        p = item["priority"]
        d = ", ".join(item["domains"])
        report_lines.append(f"| {i} | {w} | {t} | {p} | {d} |")

    report_lines += [
        "",
        "## Learning Roadmap",
        "",
        "### Phase 1 – Weeks 1–2: Survival Communication",
        "",
        "Focus on the words that allow the learner to exchange names, basic social phrases, and hold the simplest interactions.",
        "",
        "**Priority areas:**",
        "- All greetings and social phrases (Hallo, Tschüss, Bitte, Danke, Entschuldigung)",
        "- Core question patterns: Wie heißt du? Was ist das? Wo ist ...? Willst du ...? Magst du ...?",
        "- Numbers 1–10",
        "- Basic family words: Mama, Papa, Bruder, Schwester",
        "- High-priority actions: gehen, kommen, machen, sehen, helfen, geben",
        "- Key feelings: glücklich, traurig, müde",
        "",
        "**Existing deck cards to focus on (mature = review; new/learning = learn first):**",
        "Review all matched cards with `priority_score >= 8` in the greetings, questions, family, and actions domains.",
        "",
        "### Phase 2 – Weeks 3–4: Topics & Play",
        "",
        "Extend to the topic domains most used in child interaction.",
        "",
        "**Priority areas:**",
        "- Animals (Hund, Katze, Pferd, Vogel, Fisch, and ~8 more)",
        "- Food & drink (essen, trinken, Hunger, Durst, Brot, Milch, Wasser, Apfel, lecker)",
        "- Play verbs (spielen, rennen, springen, bauen, zeichnen, werfen, fangen)",
        "- Colours (rot, blau, grün, gelb, schwarz, weiß + 4 more)",
        "- Body parts (Kopf, Auge, Nase, Mund, Ohr, Hand, Bein, Fuß)",
        "- Location words (hier, dort, drinnen, draußen, oben, unten)",
        "",
        "### Phase 3 – Weeks 5–6+: Fluency & Nuance",
        "",
        "Polish and expand into the remaining domains for natural child-level conversation.",
        "",
        "**Priority areas:**",
        "- School vocabulary (Schule, Kindergarten, lernen, Buch, Stift, malen, lesen)",
        "- Time expressions (heute, morgen, jetzt, später, immer, manchmal)",
        "- Remaining adjectives (groß, klein, schnell, langsam, schön, lustig, toll)",
        "- Useful phrases (Schau mal!, Lass uns ...!, Ich weiß nicht., Ich verstehe nicht.)",
        "- Numbers 11–20",
        "- Feelings (ängstlich, gelangweilt, aufgeregt, wütend, fröhlich)",
        "",
        "---",
        "*Report generated by Agent 2. Source: deck_export.json (4028 notes).*",
    ]

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    # Final summary
    print("\n" + "=" * 60)
    print("DONE")
    print(f"  selected_cards.json : {len(selected)} notes")
    print(f"  new_vocab.json      : {len(new_vocab)} items")
    print(f"  report.md           : written")
    print("=" * 60)


if __name__ == "__main__":
    main()
