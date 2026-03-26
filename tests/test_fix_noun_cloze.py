"""Tests for fix_noun_cloze_articles.py — article detection."""
import pytest

import anki_george_german.fix_noun_cloze_articles as fnc


# ═══════════════════════════════════════════════════════════════════════════
# A. find_preceding_article_or_contraction()
# ═══════════════════════════════════════════════════════════════════════════


class TestFindPrecedingArticle:

    def test_definite_article(self):
        """Finds 'den' before 'Apfel'."""
        result = fnc.find_preceding_article_or_contraction("Ich esse den Apfel.", "Apfel")
        assert result == "den"

    def test_possessive_not_article(self):
        """Possessive 'Mein' is not treated as an article."""
        result = fnc.find_preceding_article_or_contraction("Mein Hund bellt laut.", "Hund")
        assert result is None

    def test_no_article(self):
        """No article when noun starts the sentence or has no article."""
        result = fnc.find_preceding_article_or_contraction("Brot ist gut.", "Brot")
        assert result is None

    def test_article_after_punctuation(self):
        """Article is found even after punctuation."""
        result = fnc.find_preceding_article_or_contraction("Ja, der Hund bellt.", "Hund")
        assert result == "der"

    def test_indefinite_article(self):
        """Finds indefinite article 'eine'."""
        result = fnc.find_preceding_article_or_contraction("Sie hat eine Katze.", "Katze")
        assert result == "eine"

    def test_separable_verb_tilde(self):
        """With ~-separated cloze_word, only the first part is used."""
        result = fnc.find_preceding_article_or_contraction("Er machte die Tür auf.", "Tür~auf")
        assert result == "die"
