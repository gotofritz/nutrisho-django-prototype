"""Merge and split rules for step text (issue #18).

Pure functions, no Django imports, like ``step_title.py``.
"""


def join_step_texts(texts: list[str]) -> str:
    """Append step texts in order, one space apart."""
    return " ".join(text.strip() for text in texts)


def split_step_text(text: str, *, at: int) -> tuple[str, str] | None:
    """Split text at the cursor offset ``at``, or None if that is senseless.

    A cursor inside a word moves back to the start of that word, so a split
    never cuts a word in two. The split is senseless — None — when either half
    would be blank, i.e. the cursor is not after the first word and before the
    last. Both halves come back trimmed.
    """
    if not 0 < at < len(text):
        return None
    while at > 0 and not text[at - 1].isspace() and not text[at].isspace():
        at -= 1
    head, tail = text[:at].rstrip(), text[at:].lstrip()
    if not head or not tail:
        return None
    return head, tail
