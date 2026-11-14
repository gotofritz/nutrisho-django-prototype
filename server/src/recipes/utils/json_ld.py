"""Read schema.org `Recipe` JSON-LD, as recipe sites embed it in their pages (#78).

Sites disagree on the shape. The recipe may sit alone, in a list, in an
`@graph`, or under another node's `mainEntity`; a yield may be `4`, `"4
servings"` or a list of both; instructions may be one block of HTML, a list of
strings, or `HowToStep`s grouped in `HowToSection`s. These helpers take whatever
a page offers and return plain values. Framework-free, like the other utils.
"""

import re

from recipes.utils.plain_text import plain_text
from recipes.utils.scaling import MAX_SERVINGS

STEP_TITLE_MAX_LENGTH = 128  # Step.step_title

_MAX_DEPTH = 10
_BLOCK_TAG = re.compile(r"<\s*/?\s*(?:p|br|li|div|ol|ul|h[1-6])\b[^>]*>", re.IGNORECASE)
_NUMBERED_STEP = re.compile(r"^step\s*\d+[.:]?$", re.IGNORECASE)
_ELLIPSIS = ("…", "...")

type Json = dict[str, object] | list[object] | str | int | float | bool | None


def _types(node: dict[str, object]) -> list[str]:
    """`@type` as a list of bare names: `schema:Recipe` and full IRIs are `Recipe`."""
    value = node.get("@type")
    values = value if isinstance(value, list) else [value]
    return [re.split(r"[/:#]", v)[-1] for v in values if isinstance(v, str)]


def find_recipes(data: object, *, _depth: int = 0) -> list[dict[str, object]]:
    """Every `Recipe` node in `data`, in document order; never one inside another."""
    if _depth > _MAX_DEPTH:
        return []
    if isinstance(data, list):
        return [found for item in data for found in find_recipes(item, _depth=_depth + 1)]
    if not isinstance(data, dict):
        return []
    if "Recipe" in _types(data):
        return [data]
    return [found for value in data.values() for found in find_recipes(value, _depth=_depth + 1)]


def text_of(value: object) -> str:
    """A text property as plain text: its first value, a node's `@id` or `url`, tags removed."""
    if isinstance(value, list):
        return next((text for item in value if (text := text_of(item))), "")
    if isinstance(value, dict):
        return text_of(value.get("@id") or value.get("url") or value.get("name"))
    if isinstance(value, bool) or value is None:
        return ""
    return plain_text(str(value))


def servings_from_yield(value: object) -> int | None:
    """The first whole number `recipeYield` names, if `Recipe.servings` can hold it."""
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, bool) or item is None:
            continue
        match = re.search(r"\d+", str(item))
        if match is not None and 1 <= int(match.group()) <= MAX_SERVINGS:
            return int(match.group())
    return None


def ingredient_lines(value: object) -> list[str]:
    """`recipeIngredient` as plain-text lines, blanks dropped."""
    values = value if isinstance(value, list) else [value]
    return [line for item in values if (line := text_of(item))]


def instruction_steps(value: object, *, _depth: int = 0) -> list[tuple[str, str]]:
    """`recipeInstructions` as `(title, text)` steps, in order.

    A block of text is one step per paragraph, line or list item. A
    `HowToStep`'s `name` is its title when it says something the text does not:
    sites often repeat the text there, or write `Step 3`. A `HowToSection`'s
    name titles its first step.
    """
    if _depth > _MAX_DEPTH or value is None:
        return []
    if isinstance(value, list):
        return [step for item in value for step in instruction_steps(item, _depth=_depth + 1)]
    if isinstance(value, dict):
        if "HowToSection" in _types(value):
            return _section_steps(value, depth=_depth)
        return _how_to_step(value, depth=_depth)
    return [("", line) for line in _paragraphs(str(value))]


def _paragraphs(text: str) -> list[str]:
    """The non-blank paragraphs of a block of text or HTML, each as plain text."""
    lines = _BLOCK_TAG.sub("\n", text).splitlines()
    return [para for line in lines if (para := plain_text(line))]


def _how_to_step(node: dict[str, object], *, depth: int) -> list[tuple[str, str]]:
    name = text_of(node.get("name"))
    text = text_of(node.get("text"))
    if not text:
        if "itemListElement" in node:
            return instruction_steps(node["itemListElement"], _depth=depth + 1)
        return [("", name)] if name else []
    if not name or _says_nothing_more(name, text):
        return [("", text)]
    if len(name) > STEP_TITLE_MAX_LENGTH:
        return [("", f"{name} {text}")]
    return [(name, text)]


def _says_nothing_more(name: str, text: str) -> bool:
    """Whether a step's `name` repeats, truncates or merely numbers its text."""
    if name == text or _NUMBERED_STEP.match(name):
        return True
    for ellipsis in _ELLIPSIS:
        if name.endswith(ellipsis) and text.startswith(name.removesuffix(ellipsis).rstrip()):
            return True
    return False


def _section_steps(node: dict[str, object], *, depth: int) -> list[tuple[str, str]]:
    steps = instruction_steps(node.get("itemListElement"), _depth=depth + 1)
    section = text_of(node.get("name"))
    if not steps or not section:
        return steps
    title, text = steps[0]
    title = f"{section}: {title}" if title else section
    return [(title[:STEP_TITLE_MAX_LENGTH], text), *steps[1:]]
