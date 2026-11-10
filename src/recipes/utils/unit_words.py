"""Words typed into the unit field that are not units (#67).

`2 small onion` came from `small` in the unit field; `to taste` there let
scaling multiply a meaningless quantity. A size describes the ingredient, so it
belongs in `preparation`; an amount phrase belongs in the `note`. Framework-free,
shared by the recipe editor (to say where the word goes) and the
`normalise_units` clean-up (to move it there).
"""

_SIZE_WORDS = frozenset({"small", "medium", "large", "big", "extra large", "extra-large"})
_NOTE_PHRASES = frozenset({"to taste", "as needed", "as required"})


def not_a_unit(text: str) -> str | None:
    """The field `text` belongs in, `preparation` or `note`, or None if it is neither."""
    word = " ".join(text.lower().split())
    if word in _SIZE_WORDS:
        return "preparation"
    if word in _NOTE_PHRASES:
        return "note"
    return None


def append_text(existing: str, word: str) -> str:
    """`existing` led by `word` (`small, chopped`), unless one of its parts already says it."""
    parts = [part.strip().lower() for part in existing.split(",")]
    if word.lower() in parts:
        return existing
    return f"{word}, {existing}" if existing else word
