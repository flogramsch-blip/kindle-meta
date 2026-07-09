"""Tests für Spracherkennung und Fuzzy-Trefferbewertung."""

from kindle_meta import lang, matching
from kindle_meta.models import BookMetadata

DE = (
    "Der Roman erzählt die Geschichte eines Mannes, der nicht mehr weiß, was "
    "richtig ist und was falsch. Es ist ein Buch über die Zeit und das Leben, "
    "und darüber, dass nicht alles so bleibt, wie es einmal war."
)
EN = (
    "The novel tells the story of a man who is not sure what is right and what "
    "is wrong. It is a book about time and life, and about the fact that not "
    "everything stays the way it once was."
)


def test_detect_german():
    assert lang.detect(DE) == "de"


def test_detect_english():
    assert lang.detect(EN) == "en"


def test_detect_too_short():
    assert lang.detect("Hallo Welt") is None
    assert lang.detect(None) is None


def test_similarity_bounds():
    assert matching.similarity("Der Steppenwolf", "Der Steppenwolf") == 1.0
    assert matching.similarity("", "x") == 0.0
    assert 0.0 < matching.similarity("Der Steppenwolf", "Steppenwolf") < 1.0


def test_rank_prefers_closest_title():
    ref = BookMetadata(title="Der Steppenwolf", authors=["Hermann Hesse"])
    a = BookMetadata(title="Ganz anderes Buch", authors=["Wer Anders"])
    b = BookMetadata(title="Der Steppenwolf", authors=["Hermann Hesse"], publisher="Suhrkamp")
    ranked = matching.rank(ref, [a, b])
    assert ranked[0] is b


def test_rank_isbn_match_wins():
    ref = BookMetadata(title="X", isbn="9783161484100")
    weak = BookMetadata(title="X gutes Match", publisher="V")
    isbn_hit = BookMetadata(title="Ganz anders", isbn="978-3-16-148410-0")
    ranked = matching.rank(ref, [weak, isbn_hit])
    assert ranked[0] is isbn_hit
