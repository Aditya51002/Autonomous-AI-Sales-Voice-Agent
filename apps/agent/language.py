"""Decides which language the agent should be speaking.

Pure functions with no network calls, so the rules are fast and testable.
The result is also told to the LLM on every turn (see prompts.turn_context).
"""

import copy
import re
from enum import Enum


class Language(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"
    HINGLISH = "hinglish"

    @property
    def tts_code(self) -> str:
        return "en-IN" if self is Language.ENGLISH else "hi-IN"


# Turns shorter than this ("haan", "ok thanks") do not switch an established language.
MIN_WORDS_TO_SWITCH = 3

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

# Romanised Hindi words that are not also English words.
_ROMAN_HINDI = frozenset(
    "hai hain kya nahi nahin mujhe chahiye aap hum humein kitna kitne kitni kaise "
    "kaisa mein ka ki ke raha rahi rahe karna karte batao bataiye accha achha theek "
    "haan kyunki lekin abhi bahut sakta sakte sakti hoga wala".split()
)

_REQUEST_PATTERNS = (
    # "speak in Hindi", "reply in English"
    r"\b(?:speak|talk|reply|answer|continue)\s+(?:to me\s+)?(?:in\s+)?(?P<lang>hindi|english|hinglish)\b",
    # "Hindi please"
    r"\b(?P<lang>hindi|english|hinglish)\s+please\b",
    # "Hindi mein baat kijiye"
    r"\b(?P<lang>hindi|english|angrezi|hinglish)\s+(?:mein|me|main)\s+(?:baat|bolo|boliye|bataiye|batao|samjhaiye)\b",
    # "हिंदी में बताइए"
    r"(?P<lang>हिंदी|हिन्दी|इंग्लिश|अंग्रेज़ी|अंग्रेजी)\s+में\s+(?:बात|बोल|बता|समझा)",
)

_REQUEST_NAMES = {
    "hindi": Language.HINDI,
    "हिंदी": Language.HINDI,
    "हिन्दी": Language.HINDI,
    "english": Language.ENGLISH,
    "angrezi": Language.ENGLISH,
    "इंग्लिश": Language.ENGLISH,
    "अंग्रेज़ी": Language.ENGLISH,
    "अंग्रेजी": Language.ENGLISH,
    "hinglish": Language.HINGLISH,
}


def requested_language(text: str) -> Language | None:
    """The language the caller explicitly asked for, if any."""
    for pattern in _REQUEST_PATTERNS:
        if match := re.search(pattern, text, re.IGNORECASE):
            return _REQUEST_NAMES[match.group("lang").lower()]
    return None


def classify(text: str, stt_language: str | None = None) -> Language | None:
    """Language of one utterance, or None if it is neither English nor Hindi."""
    words = text.split()
    devanagari = sum(1 for word in words if _DEVANAGARI.search(word))
    latin = [word for word in words if not _DEVANAGARI.search(word) and _LATIN.search(word)]

    if devanagari:
        return Language.HINGLISH if latin else Language.HINDI
    if not latin:
        return None

    markers = sum(1 for word in latin if word.strip(".,?!").lower() in _ROMAN_HINDI)
    heard_hindi = bool(stt_language) and stt_language.lower().startswith("hi")
    if markers >= 2 or (markers == 1 and heard_hindi):
        return Language.HINGLISH
    return Language.ENGLISH


class LanguageTracker:
    """Holds the conversation language across turns."""

    def __init__(self, initial: Language = Language.ENGLISH) -> None:
        self.current = initial
        self._established = False

    def preview(self, text: str, stt_language: str | None = None) -> Language:
        """What update() would return, without changing the tracker."""
        return copy.copy(self).update(text, stt_language)

    def update(self, text: str, stt_language: str | None = None) -> Language:
        if requested := requested_language(text):
            self.current, self._established = requested, True
            return self.current

        detected = classify(text, stt_language)
        if detected is None:
            return self.current

        is_substantive = len(text.split()) >= MIN_WORDS_TO_SWITCH
        if is_substantive or not self._established:
            self.current = detected
        self._established = self._established or is_substantive
        return self.current
