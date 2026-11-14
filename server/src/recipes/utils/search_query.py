"""Parse what is typed in the recipe search box (#32).

Words are separate terms and a recipe matching any of them is a result
(`aubergine pasta` finds recipes with either); quotes keep a phrase together
(`"olive oil"`) and a leading minus rules recipes out (`-mushroom`). A term
matches at the start of a word, so `pea` finds `peas` but not `chickpeas`, and a
plural finds the singular the database holds (`aubergines` → `aubergine`).
Framework-free: `recipes.services.recipe_search` turns this into queries.
"""

import re
from dataclasses import dataclass, field

# Each term is a handful of subqueries; a pasted paragraph must not run away.
MAX_TERMS = 10

# The reverse of `recipes.utils.pluralise`: `-ies` was `-y` or `-i` (berries,
# chillies), `-ves` was `-f` or `-fe` (a prefix match on `-f` finds both), and
# `-es` follows these endings only (tomatoes, dishes; not aubergines).
_ES_STEMS = ("x", "z", "ch", "sh", "o")
# Shorter guesses (`gas` → `ga`) match too much to be worth it.
_MIN_VARIANT = 3

_TOKEN = re.compile(r'(-?)"([^"]*)"?|(-?)(\S+)')


@dataclass
class ParsedQuery:
    """Terms to look for and terms that rule a recipe out, lower case, deduplicated."""

    terms: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        """True when there is anything to match or exclude."""
        return bool(self.terms or self.excluded)


def parse_query(text: str) -> ParsedQuery:
    """Split `text` into terms and exclusions, at most MAX_TERMS of them in all."""
    parsed = ParsedQuery()
    seen: set[tuple[str, str]] = set()
    for match in _TOKEN.finditer(text):
        minus = match.group(1) or match.group(3)
        term = " ".join((match.group(2) if match.group(2) is not None else match.group(4)).split())
        term = term.lower()
        if term in {"", "-"} or (minus, term) in seen:
            continue
        if len(parsed.terms) + len(parsed.excluded) >= MAX_TERMS:
            break
        seen.add((minus, term))
        (parsed.excluded if minus else parsed.terms).append(term)
    return parsed


def term_variants(term: str) -> list[str]:
    """`term` followed by the singulars it may be a plural of."""
    variants = [term]
    if term.endswith("s") and not term.endswith("ss"):
        variants.append(term[:-1])
        if term.endswith("ies"):
            variants += [term[:-3] + "y", term[:-3] + "i"]
        elif term.endswith("ves"):
            variants.append(term[:-3] + "f")
        elif term.endswith("es") and term[:-2].endswith(_ES_STEMS):
            variants.append(term[:-2])
    return [v for i, v in enumerate(variants) if i == 0 or len(v) >= _MIN_VARIANT]


def word_prefix_pattern(term: str) -> str:
    """A regular expression for `term` at the start of a word.

    `(^|\\W)` rather than `\\b`: Python's `re` (what Django's SQLite backend runs)
    and PostgreSQL both read it the same way, while `\\b` is a backspace there.
    """
    return r"(^|\W)" + re.escape(term)
