"""Custom template filters for recipes."""

from html.parser import HTMLParser

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_ALLOWED_TAGS = frozenset({"i", "b", "s", "u"})


class _StepHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _ALLOWED_TAGS:
            self._parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in _ALLOWED_TAGS:
            self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._parts.append(escape(data))

    def result(self) -> str:
        return "".join(self._parts)


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
    sanitizer = _StepHtmlSanitizer()
    sanitizer.feed(value)
    return mark_safe(sanitizer.result())
