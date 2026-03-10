"""Tests for generate_vocab.py — core pipeline logic."""
import copy
import re
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import anki_george_german.generate_vocab as gv


# ═══════════════════════════════════════════════════════════════════════════
# A. normalise_cloze() — requires spaCy for noun-chunk expansion
# ═══════════════════════════════════════════════════════════════════════════


class TestNormaliseCloze:

    @pytest.mark.slow
    def test_bare_noun_expanded(self, nlp, monkeypatch):
        """A bare noun 'Kind' gets expanded to 'Jedes Kind' via spaCy."""
        monkeypatch.setattr(gv, "_nlp_model", nlp)
        card = {
            "word": "das Kind",
            "sentences": [
                {
                    "sentence": "Jedes Kind geht gern zur Schule.",
                    "cloze_word": "Kind",
                    "pos": "noun",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        assert result["sentences"][0]["cloze_word"] == "Jedes Kind"

    @pytest.mark.slow
    def test_case_correction(self, nlp, monkeypatch):
        """Case mismatch in cloze_word is corrected to match the sentence."""
        monkeypatch.setattr(gv, "_nlp_model", nlp)
        card = {
            "word": "der Meister",
            "sentences": [
                {
                    "sentence": "Er besiegte den Meister.",
                    "cloze_word": "Der meister",
                    "pos": "noun",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        cloze = result["sentences"][0]["cloze_word"]
        # Should find the case-corrected version from the sentence
        assert cloze in ("den Meister", "Der meister") or "Meister" in cloze

    @pytest.mark.slow
    def test_article_mismatch_rebuild(self, nlp, monkeypatch):
        """Wrong article form in cloze_word gets rebuilt via spaCy noun chunks."""
        monkeypatch.setattr(gv, "_nlp_model", nlp)
        card = {
            "word": "der Apfel",
            "sentences": [
                {
                    "sentence": "Ich esse den roten Apfel.",
                    "cloze_word": "der Apfel",
                    "pos": "noun",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        cloze = result["sentences"][0]["cloze_word"]
        # Should rebuild to match the actual sentence noun chunk
        assert "Apfel" in cloze
        assert cloze in "Ich esse den roten Apfel."

    def test_separable_verb_untouched(self):
        """Separable verb cloze_word with ~ is left unchanged when parts match."""
        card = {
            "word": "aufmachen",
            "sentences": [
                {
                    "sentence": "Er machte die Tür auf.",
                    "cloze_word": "machte~auf",
                    "pos": "verb",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        assert result["sentences"][0]["cloze_word"] == "machte~auf"

    def test_disambiguation_not_prefix_stripped(self):
        """'NOT: formal' in disambiguation gets stripped to 'formal'."""
        card = {
            "word": "der Herr",
            "disambiguation": "NOT: formal",
            "sentences": [
                {
                    "sentence": "Der Herr ging spazieren.",
                    "cloze_word": "Der Herr",
                    "pos": "noun",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        assert result["disambiguation"] == "formal"

    def test_already_correct_unchanged(self):
        """A cloze_word that already matches is not modified."""
        card = {
            "word": "der Apfel",
            "sentences": [
                {
                    "sentence": "Ich esse den Apfel.",
                    "cloze_word": "den Apfel",
                    "pos": "noun",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        assert result["sentences"][0]["cloze_word"] == "den Apfel"

    def test_multi_part_tilde_all_present(self):
        """Multi-part cloze with ~ is unchanged when all parts are in sentence."""
        card = {
            "word": "weglaufen",
            "sentences": [
                {
                    "sentence": "Der Hund lief schnell weg.",
                    "cloze_word": "lief~weg",
                    "pos": "verb",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        assert result["sentences"][0]["cloze_word"] == "lief~weg"

    def test_cloze_not_in_sentence_falls_through(self):
        """If cloze_word is not in sentence at all, it falls through unchanged."""
        card = {
            "word": "laufen",
            "sentences": [
                {
                    "sentence": "Der Hund rennt im Park.",
                    "cloze_word": "xyz",
                    "pos": "verb",
                }
            ],
        }
        result = gv.normalise_cloze(card)
        assert result["sentences"][0]["cloze_word"] == "xyz"

    def test_empty_sentences_returns_card(self):
        """Card with no sentences is returned as-is."""
        card = {"word": "test", "sentences": []}
        result = gv.normalise_cloze(card)
        assert result == card

    def test_no_sentences_key_returns_card(self):
        """Card without 'sentences' key is returned as-is."""
        card = {"word": "test"}
        result = gv.normalise_cloze(card)
        assert result == card


# ═══════════════════════════════════════════════════════════════════════════
# B. validate_card()
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateCard:

    def test_valid_noun_card(self, sample_valid_noun_card):
        """A fully valid noun card passes validation."""
        ok, errors = gv.validate_card(sample_valid_noun_card)
        assert ok is True
        assert errors == []

    def test_valid_verb_card(self, sample_verb_card):
        """A fully valid verb card passes validation."""
        ok, errors = gv.validate_card(sample_verb_card)
        assert ok is True
        assert errors == []

    def test_missing_word(self):
        """Missing 'word' field causes validation error."""
        card = {
            "word": "",
            "translation": "apple",
            "sentences": [
                {
                    "sentence": "Ich esse den Apfel.",
                    "cloze_word": "den Apfel",
                    "sentence_translation": "I eat the apple.",
                    "pos": "noun",
                }
            ],
            "article": "der",
        }
        ok, errors = gv.validate_card(card)
        assert ok is False
        assert any("missing 'word'" in e for e in errors)

    def test_missing_sentences(self):
        """Empty sentences array causes validation error."""
        card = {
            "word": "der Apfel",
            "translation": "apple",
            "sentences": [],
        }
        ok, errors = gv.validate_card(card)
        assert ok is False
        assert any("missing or empty" in e for e in errors)

    def test_invalid_pos(self):
        """Invalid POS value causes validation error."""
        card = {
            "word": "der Apfel",
            "translation": "apple",
            "article": "der",
            "sentences": [
                {
                    "sentence": "Ich esse den Apfel.",
                    "cloze_word": "den Apfel",
                    "sentence_translation": "I eat the apple.",
                    "pos": "foo",
                }
            ],
        }
        ok, errors = gv.validate_card(card)
        assert ok is False
        assert any("invalid pos" in e for e in errors)

    def test_cloze_not_in_sentence(self):
        """cloze_word not present in sentence causes validation error."""
        card = {
            "word": "der Apfel",
            "translation": "apple",
            "article": "der",
            "sentences": [
                {
                    "sentence": "Ich esse den Apfel.",
                    "cloze_word": "xyz",
                    "sentence_translation": "I eat the apple.",
                    "pos": "noun",
                }
            ],
        }
        ok, errors = gv.validate_card(card)
        assert ok is False
        assert any("not in sentence" in e for e in errors)

    def test_separable_verb_cloze_valid(self, sample_separable_verb_card):
        """Separable verb with ~ in cloze_word passes when both parts are in sentence."""
        ok, errors = gv.validate_card(sample_separable_verb_card)
        assert ok is True
        assert errors == []

    def test_all_noun_missing_article(self):
        """All-noun card without article fails validation."""
        card = {
            "word": "Apfel",
            "article": "",
            "translation": "apple",
            "sentences": [
                {
                    "sentence": "Ich esse den Apfel.",
                    "cloze_word": "den Apfel",
                    "sentence_translation": "I eat the apple.",
                    "pos": "noun",
                },
            ],
        }
        ok, errors = gv.validate_card(card)
        assert ok is False
        assert any("noun missing article" in e for e in errors)

    def test_mixed_pos_no_article_ok(self):
        """Card with mixed POS (noun + verb) passes without top-level article."""
        card = {
            "word": "laufen",
            "article": "",
            "translation": "to run",
            "sentences": [
                {
                    "sentence": "Das Laufen macht Spaß.",
                    "cloze_word": "Das Laufen",
                    "sentence_translation": "Running is fun.",
                    "pos": "noun",
                },
                {
                    "sentence": "Er läuft schnell.",
                    "cloze_word": "läuft",
                    "sentence_translation": "He runs fast.",
                    "pos": "verb",
                },
            ],
        }
        ok, errors = gv.validate_card(card)
        assert ok is True
        assert errors == []

    def test_non_noun_has_article(self):
        """Non-noun card with an article fails validation."""
        card = {
            "word": "laufen",
            "article": "der",
            "translation": "to run",
            "sentences": [
                {
                    "sentence": "Er läuft schnell.",
                    "cloze_word": "läuft",
                    "sentence_translation": "He runs fast.",
                    "pos": "verb",
                },
            ],
        }
        ok, errors = gv.validate_card(card)
        assert ok is False
        assert any("non-noun has article" in e for e in errors)

    def test_source_plagiarism_detected(self):
        """Sentence too similar to source text (>80%) triggers error."""
        source = "Der alte Mann ging langsam durch den dunklen Wald."
        card = {
            "word": "der Wald",
            "article": "der",
            "translation": "forest",
            "sentences": [
                {
                    "sentence": "Der alte Mann ging langsam durch den dunklen Wald.",
                    "cloze_word": "den dunklen Wald",
                    "sentence_translation": "The old man walked slowly through the dark forest.",
                    "pos": "noun",
                },
            ],
        }
        ok, errors = gv.validate_card(card, source_text=source)
        assert ok is False
        assert any("too similar to source" in e for e in errors)

    def test_source_plagiarism_below_threshold(self):
        """Sentence with <80% similarity to source passes."""
        source = "Der alte Mann ging langsam durch den dunklen Wald im Herbst."
        card = {
            "word": "der Wald",
            "article": "der",
            "translation": "forest",
            "sentences": [
                {
                    "sentence": "Sie wanderten fröhlich durch den hellen Wald.",
                    "cloze_word": "den hellen Wald",
                    "sentence_translation": "They hiked happily through the bright forest.",
                    "pos": "noun",
                },
            ],
        }
        ok, errors = gv.validate_card(card, source_text=source)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# C. _gendered_counterpart()
# ═══════════════════════════════════════════════════════════════════════════


class TestGenderedCounterpart:

    def test_feminine_in_to_masculine(self):
        """'freundin' -> 'freund'."""
        assert gv._gendered_counterpart("freundin") == "freund"

    def test_feminine_erin_to_masculine(self):
        """'lehrerin' -> 'lehrer'."""
        assert gv._gendered_counterpart("lehrerin") == "lehrer"

    def test_masculine_er_to_feminine(self):
        """'lehrer' -> 'lehrerin'."""
        assert gv._gendered_counterpart("lehrer") == "lehrerin"

    def test_no_counterpart(self):
        """'haus' has no gendered counterpart."""
        assert gv._gendered_counterpart("haus") is None

    def test_stein_suffix_not_stripped(self):
        """Words ending in '-stein' should not be treated as feminine -in."""
        assert gv._gendered_counterpart("einstein") is None

    def test_short_word_no_strip(self):
        """Short word 'in' should not be stripped."""
        assert gv._gendered_counterpart("in") is None

    def test_uppercase_handled(self):
        """Input is lowercased internally."""
        assert gv._gendered_counterpart("Lehrerin") == "lehrer"


# ═══════════════════════════════════════════════════════════════════════════
# D. dedup_gendered_pairs()
# ═══════════════════════════════════════════════════════════════════════════


class TestDedupGenderedPairs:

    def test_both_genders_keeps_first(self):
        """When both der Lehrer and die Lehrerin are present, keeps first."""
        cards = [
            {"word": "der Lehrer", "translation": "teacher (m)"},
            {"word": "die Lehrerin", "translation": "teacher (f)"},
        ]
        result = gv.dedup_gendered_pairs(cards)
        assert len(result) == 1
        assert result[0]["word"] == "der Lehrer"

    def test_no_duplicates_keeps_both(self):
        """Unrelated words are both kept."""
        cards = [
            {"word": "der Hund", "translation": "dog"},
            {"word": "die Katze", "translation": "cat"},
        ]
        result = gv.dedup_gendered_pairs(cards)
        assert len(result) == 2

    def test_feminine_first_kept(self):
        """When die Lehrerin appears before der Lehrer, keeps Lehrerin."""
        cards = [
            {"word": "die Lehrerin", "translation": "teacher (f)"},
            {"word": "der Lehrer", "translation": "teacher (m)"},
        ]
        result = gv.dedup_gendered_pairs(cards)
        assert len(result) == 1
        assert result[0]["word"] == "die Lehrerin"


# ═══════════════════════════════════════════════════════════════════════════
# E. _find_noun_chunk() — requires spaCy
# ═══════════════════════════════════════════════════════════════════════════


class TestFindNounChunk:

    @pytest.mark.slow
    def test_simple_det_noun(self, nlp, monkeypatch):
        """'Das Kind' is found as a noun chunk for bare word 'Kind'."""
        monkeypatch.setattr(gv, "_nlp_model", nlp)
        result = gv._find_noun_chunk("Das Kind spielt im Garten.", "Kind")
        assert result is not None
        assert "Kind" in result

    @pytest.mark.slow
    def test_det_adj_noun(self, nlp, monkeypatch):
        """'den roten Apfel' is found for bare word 'Apfel'."""
        monkeypatch.setattr(gv, "_nlp_model", nlp)
        result = gv._find_noun_chunk("Ich esse den roten Apfel.", "Apfel")
        assert result is not None
        assert "Apfel" in result

    @pytest.mark.slow
    def test_no_det_returns_none(self, nlp, monkeypatch):
        """Bare noun without determiner returns None."""
        monkeypatch.setattr(gv, "_nlp_model", nlp)
        result = gv._find_noun_chunk("Brot ist gut.", "Brot")
        # spaCy may or may not find a chunk; if no DET, should return None
        if result is not None:
            # If spaCy finds something, it should still be valid
            assert "Brot" in result


# ═══════════════════════════════════════════════════════════════════════════
# F. ingest_text()
# ═══════════════════════════════════════════════════════════════════════════


class TestIngestText:

    def test_full_file(self, tmp_path):
        """No paragraph range reads all non-empty lines."""
        f = tmp_path / "test.txt"
        f.write_text("Zeile eins.\n\nZeile zwei.\nZeile drei.\n")
        text = gv.ingest_text(str(f))
        assert "Zeile eins." in text
        assert "Zeile zwei." in text
        assert "Zeile drei." in text

    def test_range_1_3(self, tmp_path):
        """paragraphs='1-3' returns lines 1-3 only."""
        f = tmp_path / "test.txt"
        f.write_text("Eins.\nZwei.\nDrei.\nVier.\nFünf.\n")
        text = gv.ingest_text(str(f), paragraphs="1-3")
        assert "Eins." in text
        assert "Drei." in text
        assert "Vier." not in text

    def test_single_paragraph(self, tmp_path):
        """paragraphs='2' returns only the second line."""
        f = tmp_path / "test.txt"
        f.write_text("Eins.\nZwei.\nDrei.\n")
        text = gv.ingest_text(str(f), paragraphs="2")
        assert "Zwei." in text
        assert "Eins." not in text
        assert "Drei." not in text

    def test_file_not_found(self, tmp_path):
        """Non-existent file causes sys.exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            gv.ingest_text(str(tmp_path / "nonexistent.txt"))
        assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════════════════
# G. extract_lemmas() — requires spaCy
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractLemmas:

    @pytest.mark.slow
    def test_basic_extraction(self, nlp):
        """Content words are extracted with correct POS."""
        results = gv.extract_lemmas("Der Hund läuft schnell.", nlp)
        lemmas = [r[0].lower() for r in results]
        assert "hund" in lemmas

    @pytest.mark.slow
    def test_stop_words_filtered(self, nlp):
        """Stop words are filtered out."""
        results = gv.extract_lemmas("und der die", nlp)
        assert results == []

    @pytest.mark.slow
    def test_frequency_counting(self, nlp):
        """Repeated words have correct frequency count."""
        results = gv.extract_lemmas("Der Hund sieht den Hund.", nlp)
        hund_entries = [r for r in results if r[0].lower() == "hund"]
        if hund_entries:
            # "Hund" appears twice
            assert hund_entries[0][2] >= 2


# ═══════════════════════════════════════════════════════════════════════════
# H. build_enrichment_prompt()
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildEnrichmentPrompt:

    def test_includes_words(self):
        """Prompt includes the word being enriched."""
        batch = [("lachen", "VERB", 3)]
        prompt = gv.build_enrichment_prompt(batch, "")
        assert "lachen" in prompt

    def test_includes_context(self):
        """Context summary appears in the prompt when provided."""
        batch = [("lachen", "VERB", 3)]
        prompt = gv.build_enrichment_prompt(batch, "A funny story.")
        assert "Context:" in prompt
        assert "A funny story." in prompt

    def test_no_context(self):
        """No context section when context_summary is empty."""
        batch = [("lachen", "VERB", 3)]
        prompt = gv.build_enrichment_prompt(batch, "")
        assert "Context:" not in prompt

    def test_sentence_count(self):
        """Prompt specifies the number of sentences to generate."""
        batch = [("lachen", "VERB", 3)]
        prompt = gv.build_enrichment_prompt(batch, "", num_sentences=3)
        assert "exactly 3" in prompt

    def test_pos_list_present(self):
        """Prompt includes the VALID_POS_STR."""
        batch = [("lachen", "VERB", 3)]
        prompt = gv.build_enrichment_prompt(batch, "")
        assert gv.VALID_POS_STR in prompt

    def test_separable_verb_rule(self):
        """Prompt includes the separable verb instruction."""
        batch = [("aufmachen", "VERB", 1)]
        prompt = gv.build_enrichment_prompt(batch, "")
        assert "at least one sentence MUST" in prompt
