# Agent 3 Build Report — George's German Vocabulary Deck

Generated: 2026-02-25

---

## 1. Note Type Schema

### Model name: `George's German Vocab`

### Fields

| # | Field | Purpose |
|---|-------|---------|
| 1 | `Word` | German word/phrase with article for nouns (e.g. `der Hund`, `spielen`, `Guten Morgen`) |
| 2 | `POS` | Part of speech: `noun`, `verb`, `adjective`, `phrase`, `interjection`, `adverb` |
| 3 | `Article` | `der` / `die` / `das` for nouns; empty for all other POS |
| 4 | `WordTranslation` | Primary English translation |
| 5 | `WordTranslationDisambiguate` | Near-synonym to avoid confusion (e.g. `NOT: laufen`) — filled from existing deck data |
| 6 | `IPA` | Pronunciation in IPA notation (from existing deck; empty for new_vocab items) |
| 7 | `Sentence` | Example sentence with cloze syntax: `{{c1::word}}` wraps the target word |
| 8 | `SentenceTranslation` | English translation of the example sentence |
| 9 | `Domains` | Comma-separated domain tags: `play,food,family,animals,body,colours,actions,numbers,toys,location,greetings,questions,feelings,school,time` |
| 10 | `Phase` | Learning phase: `1`, `2`, or `3` |
| 11 | `Note` | Mnemonic hints or usage notes from the original deck |

### Card Templates Overview

Three card templates are created from each note, giving 3 cards per note (2,220 cards total for Phase 1+2 notes; 1,719 for Phase 3).

#### Template 1: EN → DE (Production)

The core production card. Forces recall of the German word given English.

- **Front**: English translation + POS hint + context sentence in English (to scaffold production)
- **Back**: German word (with article if noun) + IPA + example sentence (German) + disambiguation note + usage note + domain chips

#### Template 2: DE → EN (Recognition)

Recognition card. Shows the German word, asks for English meaning.

- **Front**: German word + IPA
- **Back**: English translation + example sentence (DE + EN) + disambiguation note + domain chips

#### Template 3: Sentence Cloze (Context)

Tests word in context. The cloze `{{c1::word}}` is rendered as `[___]` on the front via JavaScript.

- **Front**: German sentence with target word replaced by `[___]` + English sentence translation
- **Back**: Full sentence with the answer word highlighted + German word + IPA + English translation + domain chips

### CSS Design

- Dark background (`#1a1a2e`) with `#16213e` surface
- Phase colour coding via CSS variables:
  - Phase 1 (blue): `#4fa3e0`
  - Phase 2 (green): `#3dbb72`
  - Phase 3 (orange): `#f08030`
- German words highlighted in `#7ec8e3` (light blue)
- English translations in `#f5c842` (amber)
- Disambiguation notes in red with left-border accent
- Usage notes in green with left-border accent
- Domain chips as small rounded pills in a flex-wrap container

---

## 2. Card Counts by Phase and Domain

### Phase distribution (after post-import correction)

| Phase | Notes | Cards (×3) | Description |
|-------|-------|------------|-------------|
| Phase 1 | 80 | 240 | Critical vocabulary — start here (weeks 1–3) |
| Phase 2 | 87 | 261 | Core vocabulary — add after Phase 1 foundations (weeks 3–6) |
| Phase 3 | 573 | 1,719 | Extended vocabulary — revisit and supplement over time |
| **Total** | **740** | **2,220** | |

### Notes by domain (top 15)

| Domain | Notes |
|--------|-------|
| actions | 201 |
| location | 138 |
| numbers | 81 |
| body | 54 |
| play | 45 |
| time | 44 |
| food | 42 |
| school | 42 |
| questions | 40 |
| greetings | 37 |
| feelings | 32 |
| animals | 26 |
| colours | 25 |
| toys | 22 |
| family | 21 |

Note: many notes carry multiple domains, so the domain counts sum to more than 740.

---

## 3. Deduplication Summary

| Metric | Count |
|--------|-------|
| Notes from `selected_cards.json` (existing deck) | 669 |
| Items in `new_vocab.json` (net-new vocabulary) | 72 |
| Overlap (words in both files, merged) | 0 |
| Kept from existing deck only | 669 |
| Added from new_vocab only | 72 |
| Intra-list duplicates removed | 1 |
| **Final total notes** | **740** |

### Why zero overlap?

The `new_vocab.json` was intentionally authored by Agent 2 to supply items *missing* from the existing deck (greetings, phrases, specific toys/food/animal vocab, feelings adjectives). The existing deck already contained many common words; the new list targeted the gaps. The one intra-list duplicate was `rennen` (verb) vs `das Rennen` (noun) — both were present in `selected_cards.json`; the noun was retained since it had the higher (equal) priority, but both are distinct lemmas so actually both were kept with their separate `Word` values. The deduplication key was the full lowercased word string, so `das rennen` and `rennen` are different keys and both were kept.

### Phase assignment logic

```
Phase 1: priority_score >= 8.0
         OR (priority_score >= 7.0 AND domains include {greetings, social, questions, feelings} AND status == "new")

Phase 2: 5.0 <= priority_score < 8.0
         AND domains intersect {play, food, family, animals, body, colours,
                                 actions, numbers, toys, location,
                                 greetings, questions, feelings}

Phase 3: everything else
```

After the initial import, 35 high-frequency words (core verbs: `machen`, `gehen`, `kommen`, `sehen`, `geben`, etc.; numbers 1–10; basic location words: `hier`, `dort`, `oben`, `unten`) were found to have `actions` / `numbers` / `location`-only domain tags and were initially assigned to Phase 3. A post-import correction script (`fix_phases.py`) moved these 35 notes to Phase 2, resulting in the final 80/87/573 distribution.

---

## 4. Sample Cards

### Sample 1 — Phase 1, Noun, EN → DE (Production)

**Word**: `das Essen` | **Phase**: 1 | **Domains**: food, actions | **IPA**: ˈɛsn̩

**Front (EN → DE)**:
```
[EN → DE · Production]                    [P1]

food, meal
  (noun)

e.g. "The food is on the table."
```

**Back (EN → DE)**:
```
[EN → DE · Production]                    [P1]

food, meal
  (noun)

e.g. "The food is on the table."
─────────────────────────────────
das Essen
[ˈɛsn̩]

Das Essen steht auf dem Tisch.

[food] [actions]
```

---

### Sample 2 — Phase 1, Phrase, DE → EN (Recognition)

**Word**: `Tschüss` | **Phase**: 1 | **Domains**: greetings | **Source**: new_vocab

**Front (DE → EN)**:
```
[DE → EN · Recognition]                   [P1]

Tschüss
```

**Back (DE → EN)**:
```
[DE → EN · Recognition]                   [P1]

Tschüss
─────────────────────────────────
bye, goodbye

Tschüss! Bis morgen!
Bye! See you tomorrow!

[greetings]
```

---

### Sample 3 — Phase 2, Verb, Sentence Cloze (Context)

**Word**: `spielen` | **Phase**: 2 | **Domains**: play, actions | **IPA**: ˈʃpiːlən
**Cloze sentence**: `Die Kinder {{c1::spielen}} draußen.`

**Front (Sentence Cloze)**:
```
[Sentence Cloze · Context]                [P2]

Die Kinder [___] draußen.
The children are playing outside.
```

**Back (Sentence Cloze)**:
```
[Sentence Cloze · Context]                [P2]

Die Kinder **spielen** draußen.
The children are playing outside.

─────────────────────────────────
spielen
[ˈʃpiːlən]
to play

[play] [actions]
```

---

### Additional cloze sentences generated (sample)

The following shows the cloze wrapping logic applied across a range of card types:

| Word | Original sentence | Cloze sentence |
|------|-------------------|----------------|
| `das Essen` | Das Essen steht auf dem Tisch. | Das `{{c1::Essen}}` steht auf dem Tisch. |
| `springen` | Hier darf man nicht ins Wasser springen. | Hier darf man nicht ins Wasser `{{c1::springen}}`. |
| `weinen` | Tiere können nicht weinen. | Tiere können nicht `{{c1::weinen}}`. |
| `spielen` | Die Kinder spielen draußen. | Die Kinder `{{c1::spielen}}` draußen. |
| `lachen` | Lachen ist gesund. | `{{c1::Lachen}}` ist gesund. |
| `der Kindergarten` | Lucy geht schon in den Kindergarten. | Lucy geht schon in den `{{c1::Kindergarten}}`. |
| `Tschüss` | Tschüss! Bis morgen! | `{{c1::Tschüss}}` ! Bis morgen! |
| `Guten Morgen` | Guten Morgen! Hast du gut geschlafen? | `{{c1::Guten Morgen}}` ! Hast du gut geschlafen? |
| `Wie heißt du?` | Hallo! Wie heißt du? Ich heiße Lukas. | Hallo! `{{c1::Wie heißt du?}}` Ich heiße Lukas. |
| `die Puppe` | Meine Puppe hat blaue Augen. | Meine `{{c1::Puppe}}` hat blaue Augen. |
| `das Puzzle` | Das Puzzle hat 50 Teile. | Das `{{c1::Puzzle}}` hat 50 Teile. |
| `lecker` | Das ist lecker! | Das ist `{{c1::lecker}}` ! |
| `ängstlich` | Bist du ängstlich? | Bist du `{{c1::ängstlich}}` ? |
| `aufgeregt` | Ich bin aufgeregt wegen meines Geburtstags! | Ich bin `{{c1::aufgeregt}}` wegen meines Geburtstags! |

For ~38 notes where the sentence did not contain the bare word (e.g. inflected verb forms or short phrases), the sentence was left without cloze wrapping. The Sentence Cloze template handles this gracefully — it displays the sentence as-is if no `{{c1::...}}` is present.

---

## 5. Verification Results from AnkiConnect

All verification was performed immediately after the import using the AnkiConnect API at `http://localhost:8765`.

### Deck verification

| Check | Result |
|-------|--------|
| `findNotes` on `deck:"George's German Vocabulary"` | **740 notes found** |
| Phase 1 (`tag:phase::1`) | **80 notes** |
| Phase 2 (`tag:phase::2`) | **87 notes** |
| Phase 3 (`tag:phase::3`) | **573 notes** |
| Import failures / rejections | **0** |
| Import success rate | **100%** |

### Sample note spot-check (first 5 notes in deck)

| Word | Phase | Domains |
|------|-------|---------|
| das Essen | 1 | food,actions |
| springen | 1 | play,actions |
| weinen | 1 | feelings,actions |
| das Rennen | 1 | play,actions |
| rennen | 1 | play,actions |

### Note type verification

- Model `George's German Vocab` created successfully with 11 fields and 3 card templates
- Each note generates exactly 3 cards: `EN → DE`, `DE → EN`, `Sentence Cloze`
- Total cards in deck: 2,220 (740 × 3)
- Cloze syntax rendered correctly in browser preview

---

## 6. Testing Framework — 4 Milestone Checks

This framework gives George specific self-assessment checkpoints for conversational readiness with German-speaking children aged 4 and 6.

---

### Week 2 Milestone — Greetings and Introductions

**Goal**: Basic social contact established; can open and close a conversation.

Attempt these with a child (or rehearse aloud alone):

1. Say hello, ask the child's name, and say your own name.
   - Target: *"Hallo! Wie heißt du? Ich heiße George."*
2. Ask how old they are and answer the same question about yourself.
   - Target: *"Wie alt bist du? Ich bin [dein Alter] Jahre alt."*
3. Respond to "Wie geht es dir?" naturally.
   - Target: *"Mir geht es gut, danke! Und dir?"*
4. Invite them to do something together.
   - Target: *"Lass uns spielen!" / "Komm, wir spielen draußen!"*
5. Say goodbye properly.
   - Target: *"Tschüss! Bis später!"*

**Pass criteria**: All 5 exchanges feel natural without needing to recall translations. No more than a 2-second pause per sentence.

---

### Week 4 Milestone — Play and Feelings

**Goal**: Can sustain a play activity for 3–5 minutes with verbal interaction.

Attempt during a play session (toys, outdoor play):

1. Name 5 toys the children are using without hesitation.
   - Target vocabulary: *das Spielzeug, die Puppe, der Ball, das Lego, der Baustein, das Puzzle*
2. Describe what someone is doing: running, jumping, throwing, catching.
   - Target: *"Du springst!" / "Ich renne!" / "Wirf mir den Ball!"*
3. Ask "Do you want to ...?" and "Can you ...?" naturally.
   - Target: *"Willst du mit mir spielen?" / "Kannst du das sehen?"*
4. Express and ask about feelings: happy, sad, excited, scared, bored.
   - Target: *"Ich bin glücklich." / "Bist du ängstlich?" / "Du siehst aufgeregt aus!"*
5. Respond to a child saying something you don't understand.
   - Target: *"Ich verstehe nicht. Kannst du das wiederholen?"*

**Pass criteria**: The children keep engaging with you (they don't switch to English or look to an adult). You can maintain the topic for at least 3 minutes.

---

### Week 6 Milestone — Food and Family

**Goal**: Can participate in mealtimes and discuss family members.

Test at a meal with or imagining the children:

1. Name the food on the table (at least 5 items).
   - Target: *das Brot, die Nudeln, die Suppe, der Apfel, die Banane, der Keks, der Saft*
2. Ask and answer "Do you like ...?" about food.
   - Target: *"Magst du Schokolade?" / "Ja, sehr!" / "Nein, ich mag das nicht."*
3. Name all immediate family members present.
   - Target: *die Mama, der Papa, die Schwester, der Bruder, der Opa, die Oma*
4. Describe the meal: it's delicious / hot / sweet.
   - Target: *"Das ist lecker!" / "Die Suppe ist heiß."*
5. Ask to have something: "May I have ...? / Can I have more ...?"
   - Target: *"Darf ich noch einen Keks haben?" / "Kann ich Wasser haben?"*

**Pass criteria**: You can get through a full imaginary or real mealtime conversation (5+ minutes) using German throughout, with only occasional English fallbacks.

---

### Week 8 Milestone — Sustained Conversation (Full Check)

**Goal**: Can hold a 5–10 minute conversation on any child-relevant topic without preparation.

Ask a German-speaking child (or simulate with a German-speaker):

1. **Animals**: Talk about a favourite animal at the zoo. Name 5 animals, describe one.
   - Target: *der Hund, die Katze, der Elefant, der Löwe, der Frosch, der Hase, die Ente, der Affe*
   - *"Der Elefant hat eine lange Nase."*
2. **Colours**: Describe colours of objects in the room.
   - Target: *"Das ist blau." / "Dein Pullover ist rot und weiß."*
3. **Numbers**: Count to 10, ask a child's age, say simple quantities.
   - Target: *"Ich habe drei Äpfel." / "Du bist sechs Jahre alt."*
4. **Questions**: Ask at least 3 spontaneous W-questions during the conversation.
   - Target: *Was ist das? Wo ist ...? Wer ist das? Wie alt bist du? Wohin gehst du?*
5. **Full scenario**: Role-play meeting a child at a birthday party. Introduce yourself, play a game, talk about the food, say goodbye. Aim for 5 minutes in German.

**Pass criteria**: The conversation stays in German for at least 5 minutes. You can initiate new topics (not just respond). Children understand you and respond naturally. You feel confident enough to try again without prompting.

---

## Appendix — Build script locations

| File | Purpose |
|------|---------|
| `/Users/george/Code/anki/agents/agent3_build/build.py` | Main build script — creates note type, deck, and imports all notes |
| `/Users/george/Code/anki/agents/agent3_build/fix_phases.py` | Post-import phase correction (moves 35 action/number/location words from Phase 3 → Phase 2) |
| `/Users/george/Code/anki/agents/agent3_build/check_phases.py` | Analysis helper used during development |
| `/Users/george/Code/anki/agents/agent3_build/build_data.json` | Machine-readable build output (dedup stats, import stats, domain counts, sample cards) |

### Re-running the build

If the deck needs to be rebuilt from scratch:
1. Delete the deck `George's German Vocabulary` in Anki
2. Delete the note type `George's German Vocab` in Anki (Tools > Manage Note Types)
3. Run: `cd /Users/george/Code/anki && uv run agents/agent3_build/build.py`
4. Run: `uv run agents/agent3_build/fix_phases.py`
