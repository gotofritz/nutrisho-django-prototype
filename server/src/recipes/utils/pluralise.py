"""English pluralisation rule for ingredient names (plan 009).

Display-only: a plural is the presentation form of one `Ingredient` at a quantity
other than 1, never a second row. Kept free of Django imports so the rule is
testable on its own; `Ingredient.plural` layers the `plural_name` override on top,
which is what covers the irregulars this rule deliberately does not chase
(`fish`, `broccoli`, `avocado`, `clove of garlic`).
"""

import re

_VOWELS = "aeiou"

# The word to inflect, plus whatever trailing whitespace followed it. Only the last
# word is inflected, so "spring onion" -> "spring onions".
_LAST_WORD = re.compile(r"(\S+)(\s*)$")


def _inflect(word: str) -> str:
    """Pluralise one bare word by the rule table in docs/plans/009."""
    lowered = word.lower()
    # Food nouns ending in -s are nearly always already plural or mass (oats,
    # chives, capers, asparagus), so -es would be wrong far more often than right.
    if lowered.endswith("s"):
        return word
    if lowered.endswith(("x", "z", "ch", "sh")):
        return word + "es"
    if lowered.endswith("y") and len(lowered) > 1 and lowered[-2] not in _VOWELS:
        return word[:-1] + "ies"
    if lowered.endswith("o") and len(lowered) > 1 and lowered[-2] not in _VOWELS:
        return word + "es"
    if lowered.endswith("i"):
        return word + "es"
    if lowered.endswith("fe"):
        return word[:-2] + "ves"
    if lowered.endswith("f"):
        return word[:-1] + "ves"
    return word + "s"


def pluralise(name: str) -> str:
    """The plural display form of `name`, inflecting its last word only.

    Surrounding whitespace is preserved rather than stripped, so the caller gets
    back exactly what it passed in apart from the inflection. A blank name has no
    last word and comes back unchanged.
    """
    match = _LAST_WORD.search(name)
    if match is None:
        return name
    word, trailing = match.group(1), match.group(2)
    return name[: match.start(1)] + _inflect(word) + trailing
