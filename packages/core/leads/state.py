"""Merges each analysis into what is already known."""

import unicodedata

from packages.core.leads.models import CRITERIA, Extraction, LeadFacts

MAX_OBJECTIONS = 10
NEGATIVE_TURNS_FOR_FOLLOW_UP = 2


def _comparable(text: str) -> str:
    """Letters, marks and digits only, so punctuation and spacing do not matter."""
    return "".join(
        c for c in unicodedata.normalize("NFC", text).lower() if unicodedata.category(c)[0] in "LMN"
    )


def is_quoted_from(evidence: str, caller_text: str) -> bool:
    quote = _comparable(evidence)
    return len(quote) >= 2 and quote in _comparable(caller_text)


def merge(facts: LeadFacts, found: Extraction, caller_text: str) -> tuple[LeadFacts, list[str]]:
    """New facts and the names of those that changed.

    A qualification fact is accepted only if its evidence really appears in what
    the caller said, which blocks invented facts.
    """
    updated = facts.model_copy(deep=True)
    changed: list[str] = []

    for name in CRITERIA:
        new = getattr(found, name)
        if new is None or not is_quoted_from(new.evidence, caller_text):
            continue
        old = getattr(updated, name)
        # A later general remark must not erase a specific problem.
        if name == "need" and old and old.level == "specific" and new.level == "vague":
            continue
        # A later remark without a number must not erase a number.
        if name == "budget" and old and old.monthly_inr is not None and new.monthly_inr is None:
            continue
        if name == "timeline" and old and old.months is not None and new.months is None:
            continue
        setattr(updated, name, new)
        changed.append(name)

    for name in ("name", "company"):
        value = (getattr(found, name) or "").strip()[:80]
        if value and value != getattr(updated, name) and is_quoted_from(value, caller_text):
            setattr(updated, name, value)
            changed.append(name)

    known = {_comparable(item) for item in updated.objections}
    for objection in found.objections:
        text = objection.strip()[:120]
        if text and _comparable(text) not in known and len(updated.objections) < MAX_OBJECTIONS:
            updated.objections.append(text)
            known.add(_comparable(text))
            if "objections" not in changed:
                changed.append("objections")
    return updated, changed


def needs_follow_up(sentiments: list[str]) -> bool:
    """True once the caller has been negative for several turns in a row."""
    streak = 0
    for label in sentiments:
        streak = streak + 1 if label == "negative" else 0
        if streak >= NEGATIVE_TURNS_FOR_FOLLOW_UP:
            return True
    return False
