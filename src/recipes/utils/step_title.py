"""Split a heading off the front of a step's text (plan 010).

Scraped recipes write the heading of a step into the step itself, either wrapped
in an inline tag (`<u>RAGÚ</u>: Sauté the beef`) or shouted in capitals
(`FOR THE STOCK: soak the kombu`). `Step.step_title` holds it as its own field,
and this is the rule that recognises one. Kept free of Django imports so it is
testable on its own; `scripts/backfill_step_titles.py` is its only caller.

The rule is deliberately narrow — `Add salt: to taste` is prose and must stay
whole — so it under-reaches rather than mangling a step.
"""

import re

# Mirrors Step.step_title's max_length: a longer run before the colon is prose.
MAX_TITLE_LENGTH = 128

# `<u>RAGÚ</u>: rest`. The backreference is what rejects `<u>RAGÚ</b>:`, and only
# the four tags `safe_step_html` allows are recognised.
_TAGGED = re.compile(r"^<(u|b|i|s)>(.+?)</\1>\s*:\s+(.+)$", re.DOTALL)


def sentence_case_heading(heading: str) -> str:
    """Lower a shouted heading to sentence case: `FOR THE STOCK` -> `For the stock`.

    Only headings that are *entirely* upper case are touched, so anything cased by
    hand survives verbatim. Proper nouns inside a shouted heading are lost with the
    shouting (`CLASSIC NEGIMISO` -> `Classic negimiso`); nothing in the text says
    which words they were, and the owner can fix one in the Edit panel.
    """
    if heading != heading.upper() or not any(c.isalpha() for c in heading):
        return heading
    lowered = heading.lower()
    for i, char in enumerate(lowered):
        if char.isalpha():
            return lowered[:i] + char.upper() + lowered[i + 1 :]
    return lowered


def split_step_title(text: str) -> tuple[str, str]:
    """Return `(title, remainder)`, or `("", text)` when there is no heading.

    A heading is either an inline-tag wrapper or an entirely upper-case run,
    closed by a colon and followed by whitespace and at least one more
    character. The tag itself is dropped: a title carries no markup.
    """
    stripped = text.strip()

    tagged = _TAGGED.match(stripped)
    if tagged:
        title, remainder = tagged.group(2).strip(), tagged.group(3).strip()
        if title and remainder and len(title) <= MAX_TITLE_LENGTH:
            return title, remainder
        return "", text

    head, colon, tail = stripped.partition(":")
    if not colon or not tail[:1].isspace():
        return "", text
    title, remainder = head.strip(), tail.strip()
    if (
        not remainder
        or not title
        or len(title) > MAX_TITLE_LENGTH
        or not any(c.isalpha() for c in title)
        or title != title.upper()
    ):
        return "", text
    return title, remainder
