"""Custom template filters for recipes."""

from html.parser import HTMLParser

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_INLINE_TAGS = frozenset({"i", "b", "s", "u"})
_TITLE_TAGS = frozenset({"s", "u"})


class _InlineHtmlSanitizer(HTMLParser):
    """Keep only `allowed` tags, attribute-free and balanced; escape everything else.

    Balanced because the output is dropped into a larger page: an unclosed `<u>`
    would underline everything after it. A closing tag closes whatever is still
    open inside it, a closing tag with nothing to close is dropped, and anything
    left open is closed at the end. With `line_breaks`, new lines and `<br>`
    both come out as `<br>`.
    """

    def __init__(self, allowed: frozenset[str], *, line_breaks: bool = False) -> None:
        super().__init__()
        self._allowed = allowed
        self._line_breaks = line_breaks
        self._parts: list[str] = []
        self._open: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:  # noqa: ARG002 - HTMLParser API
        if tag == "br" and self._line_breaks:
            self._parts.append("<br>")
        elif tag in self._allowed:
            self._parts.append(f"<{tag}>")
            self._open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self._open:
            return
        while (closing := self._open.pop()) != tag:
            self._parts.append(f"</{closing}>")
        self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        text = escape(data)
        if self._line_breaks:
            text = text.replace("\r\n", "\n").replace("\n", "<br>")
        self._parts.append(text)

    def result(self) -> str:
        self.close()
        self._parts.extend(f"</{tag}>" for tag in reversed(self._open))
        self._open.clear()
        return "".join(self._parts)


def _sanitize(value: str, allowed: frozenset[str], *, line_breaks: bool = False) -> str:
    sanitizer = _InlineHtmlSanitizer(allowed, line_breaks=line_breaks)
    sanitizer.feed(value)
    return mark_safe(sanitizer.result())


@register.filter
def format_quantity(value: object) -> str:
    """Format decimal quantity, stripping trailing zeros (e.g. 2.50 → 2.5, 4.00 → 4)."""
    if value is None:
        return ""
    s = str(value)
    return s.rstrip("0").rstrip(".") if "." in s else s


@register.filter
def display_ingredient_name(iir: object) -> str:
    """Name of `iir`'s ingredient, pluralised when the quantity calls for it.

    Takes the whole `IngredientInRecipe` because the decision needs three of its
    fields at once. Plural when the quantity is recorded and is not 1 (`0.5
    onions`, `2 onions`), **and** only when `unit` is empty: `200 g onion` must
    stay singular, and that check is what keeps mass nouns safe. `recipe_scale`
    persists scaled quantities, so this is the only thing standing between a
    doubled recipe and "2 onion".
    """
    ingredient = getattr(iir, "ingredient", None)
    if ingredient is None:
        return ""
    quantity = getattr(iir, "quantity", None)
    if quantity is None or quantity == 1 or getattr(iir, "unit", ""):
        return ingredient.ingredient_name
    return ingredient.plural


@register.filter
def safe_step_html(value: str) -> str:
    """Render step text allowing only i, b, s, u HTML tags; escape everything else."""
    return _sanitize(value, _INLINE_TAGS)


@register.filter
def safe_title_html(value: str) -> str:
    """Render a recipe title allowing only s and u HTML tags; escape everything else."""
    return _sanitize(value, _TITLE_TAGS)


@register.filter
def safe_blurb_html(value: str) -> str:
    """Render a blurb allowing i, b, s, u and line breaks; escape everything else.

    The blurb is edited in a textarea, so its new lines become `<br>`.
    """
    return _sanitize(value, _INLINE_TAGS, line_breaks=True)
