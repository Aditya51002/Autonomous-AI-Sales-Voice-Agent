import pytest

from apps.agent.language import Language, LanguageTracker, classify, requested_language


@pytest.mark.parametrize(
    "text, expected",
    [
        ("We need an invoicing tool", Language.ENGLISH),
        ("मुझे बिल बनाने का सॉफ्टवेयर चाहिए", Language.HINDI),
        ("हमारी team को invoice software चाहिए", Language.HINGLISH),
        ("mujhe billing software chahiye", Language.HINGLISH),
        ("what is the main price for me", Language.ENGLISH),
        ("12345", None),
    ],
)
def test_classify(text, expected):
    assert classify(text) == expected


def test_single_roman_hindi_word_needs_stt_confirmation():
    assert classify("price kya", "en-IN") == Language.ENGLISH
    assert classify("price kya", "hi-IN") == Language.HINGLISH


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Can you speak in Hindi?", Language.HINDI),
        ("English please", Language.ENGLISH),
        ("Hindi mein bataiye", Language.HINDI),
        ("हिंदी में बात कीजिए", Language.HINDI),
        ("Do you support Hindi invoices?", None),
    ],
)
def test_requested_language(text, expected):
    assert requested_language(text) == expected


def test_short_filler_does_not_switch():
    tracker = LanguageTracker()
    tracker.update("मुझे एक नया सॉफ्टवेयर चाहिए")
    assert tracker.update("ok thanks") == Language.HINDI
    assert tracker.update("Now tell me about the pricing") == Language.ENGLISH


def test_first_short_utterance_sets_language():
    assert LanguageTracker().update("नमस्ते") == Language.HINDI


def test_explicit_request_switches_even_when_short():
    tracker = LanguageTracker()
    tracker.update("We need an invoicing tool")
    assert tracker.update("Hindi please") == Language.HINDI


def test_tts_codes():
    assert Language.ENGLISH.tts_code == "en-IN"
    assert Language.HINDI.tts_code == "hi-IN"
    assert Language.HINGLISH.tts_code == "hi-IN"
