"""Tests for recipe_filters template tags."""

from decimal import Decimal
from fractions import Fraction

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step


def test_format_quantity_strips_trailing_zeros():
    """Format quantity strips trailing zeros."""
    from decimal import Decimal

    from recipes.templatetags.recipe_filters import format_quantity

    assert format_quantity(Decimal("4.00")) == "4"
    assert format_quantity(Decimal("2.50")) == "2.5"
    assert format_quantity(Decimal("2.55")) == "2.55"
    assert format_quantity(Decimal("0.50")) == "0.5"
    assert format_quantity(Decimal("100.00")) == "100"
    assert format_quantity(None) == ""


def test_scale_filter_removed():
    """Scale filter must not exist — quantity is full-recipe amount, not per-serving."""
    from recipes.templatetags import recipe_filters

    assert not hasattr(recipe_filters, "scale")


@pytest.mark.django_db
def test_recipe_detail_renders_raw_quantities(client: Client, user):
    """Recipe detail page renders raw (unscaled) quantities until data is migrated."""
    recipe = Recipe.objects.create(recipe_name="Scale Test", owner=user, servings=4)
    Step.objects.create(recipe=recipe, step_text="Mix", index_in_sequence=1)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    ing = Ingredient.objects.create(ingredient_name="flour")
    IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=1,
        quantity=Decimal("2.50"),
        unit="cups",
        preparation="",
    )

    client.force_login(user)
    response = client.get(recipe.get_absolute_url())
    assert response.status_code == 200
    content = response.content.decode()
    assert "ingredient-quantity" in content
    # raw quantity rendered; scaling not applied until data is migrated
    assert '<span class="ingredient-quantity">2.5<' in content


def test_format_quantity_never_uses_exponent_notation():
    """Scaled values can carry exponents (1E+2, 3.1E-7); the page shows plain digits."""
    from recipes.templatetags.recipe_filters import format_quantity

    assert format_quantity(Decimal("1E+2")) == "100"
    assert format_quantity(Decimal("3.1E-7")) == "0.00000031"


def test_scaled_quantity_without_scale_is_the_stored_quantity():
    """No scale (the unscaled page) passes the stored quantity through."""
    from recipes.templatetags.recipe_filters import scaled_quantity

    assert scaled_quantity(_iir(Decimal("2.50")), None) == Decimal("2.50")
    assert scaled_quantity(_iir(None), Fraction(3, 2)) is None


def test_scaled_quantity_scales_and_rounds_for_display():
    """2 for 3 servings is 0.67 for 1."""
    from recipes.templatetags.recipe_filters import scaled_quantity

    assert scaled_quantity(_iir(Decimal("2")), Fraction(1, 3)) == Decimal("0.67")


def test_ingredient_name_at_follows_the_given_quantity():
    """The plural follows the displayed quantity, not the stored one."""
    from recipes.templatetags.recipe_filters import ingredient_name_at

    assert ingredient_name_at(_iir(Decimal("0.5")), Decimal("1")) == "onion"
    assert ingredient_name_at(_iir(Decimal("1")), Decimal("2")) == "onions"
    assert ingredient_name_at(_iir(Decimal("1"), unit="g"), Decimal("2")) == "onion"
    assert ingredient_name_at(IngredientInRecipe(quantity=Decimal("1")), Decimal("2")) == ""


def _iir(quantity: Decimal | None, unit: str = "") -> IngredientInRecipe:
    """An unsaved IIR carrying just what the display filter reads."""
    return IngredientInRecipe(
        ingredient=Ingredient(ingredient_name="onion"), quantity=quantity, unit=unit
    )


def test_display_ingredient_name_pluralises_above_one():
    """Display ingredient name pluralises above one."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("2"))) == "onions"


def test_display_ingredient_name_pluralises_below_one():
    """0.5 is not 1, so it reads as a plural — 'half onions', not 'half onion'."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("0.5"))) == "onions"


def test_display_ingredient_name_keeps_the_singular_at_exactly_one():
    """Display ingredient name keeps the singular at exactly one."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("1"))) == "onion"
    # value comparison, not string: 1.00 is still one
    assert display_ingredient_name(_iir(Decimal("1.00"))) == "onion"


def test_display_ingredient_name_keeps_the_singular_with_a_unit():
    """The unit check is what keeps mass nouns safe: 200 g onion, never onions."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("200"), unit="g")) == "onion"


def test_display_ingredient_name_keeps_the_singular_without_a_quantity():
    """Display ingredient name keeps the singular without a quantity."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(None)) == "onion"


def test_display_ingredient_name_honours_the_plural_name_override():
    """Display ingredient name honours the plural name override."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    iir = IngredientInRecipe(
        ingredient=Ingredient(ingredient_name="broccoli", plural_name="broccoli"),
        quantity=Decimal("3"),
        unit="",
    )
    assert display_ingredient_name(iir) == "broccoli"


@pytest.mark.django_db
def test_recipe_detail_pluralises_a_countable_ingredient(client: Client, user):
    """A stored quantity of 2 renders as "2 onions"."""
    recipe = Recipe.objects.create(recipe_name="Plural Test", owner=user, servings=4)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    onion = Ingredient.objects.create(ingredient_name="onion")
    IngredientInRecipe.objects.create(
        ingredient=onion, ingredient_group=group, index_in_sequence=1, quantity=Decimal("2")
    )

    client.force_login(user)
    content = client.get(recipe.get_absolute_url()).content.decode()
    assert '<span class="ingredient-name">onions</span>' in content


@pytest.mark.django_db
def test_recipe_detail_keeps_the_singular_at_one_and_with_a_unit(client: Client, user):
    """Recipe detail keeps the singular at one and with a unit."""
    recipe = Recipe.objects.create(recipe_name="Singular Test", owner=user, servings=4)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    onion = Ingredient.objects.create(ingredient_name="onion")
    garlic = Ingredient.objects.create(ingredient_name="garlic")
    IngredientInRecipe.objects.create(
        ingredient=onion, ingredient_group=group, index_in_sequence=1, quantity=Decimal("1")
    )
    IngredientInRecipe.objects.create(
        ingredient=garlic,
        ingredient_group=group,
        index_in_sequence=2,
        quantity=Decimal("200"),
        unit="g",
    )

    client.force_login(user)
    content = client.get(recipe.get_absolute_url()).content.decode()
    assert '<span class="ingredient-name">onion</span>' in content
    assert '<span class="ingredient-name">garlic</span>' in content
    assert "garlics" not in content


def test_display_ingredient_name_is_blank_for_a_missing_row():
    """A mistyped template variable resolves to "", not an IIR — don't crash the page."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name("") == ""


def test_safe_title_html_keeps_underline_and_strikethrough():
    """A title may carry underline and strikethrough."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html("<u>Ragú</u> <s>alla</s> bolognese") == (
        "<u>Ragú</u> <s>alla</s> bolognese"
    )


def test_safe_title_html_drops_bold_and_italic():
    """Bold and italic are blurb formatting; a title drops the tags and keeps the text."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html("<b>Big</b> <i>soup</i>") == "Big soup"


def test_safe_title_html_escapes_everything_else():
    """Anything outside the allowed tags is dropped, and text is escaped."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html('<script>x()</script><a href="/">Fish</a> & chips') == (
        "x()Fish &amp; chips"
    )


def test_safe_title_html_closes_unclosed_tags():
    """An unclosed tag would underline everything after the title on the page."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html("<u>Ragú") == "<u>Ragú</u>"


def test_safe_title_html_drops_stray_closing_tags():
    """A closing tag with nothing to close is dropped, not emitted."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html("Ragú</u></div>") == "Ragú"


def test_safe_title_html_keeps_trailing_entity_like_text():
    """Text ending in something that looks like an entity is not swallowed."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html("Fish &chips") == "Fish &amp;chips"


def test_safe_blurb_html_keeps_basic_formatting():
    """A blurb may carry bold, italic, underline and strikethrough."""
    from recipes.templatetags.recipe_filters import safe_blurb_html

    assert safe_blurb_html("<b>a</b> <i>b</i> <u>c</u> <s>d</s>") == (
        "<b>a</b> <i>b</i> <u>c</u> <s>d</s>"
    )


def test_safe_blurb_html_turns_new_lines_into_line_breaks():
    """New lines typed into the textarea survive as line breaks."""
    from recipes.templatetags.recipe_filters import safe_blurb_html

    assert safe_blurb_html("one\ntwo\r\nthree") == "one<br>two<br>three"


def test_safe_blurb_html_keeps_typed_line_breaks():
    """A `<br>` written by hand is a new line too."""
    from recipes.templatetags.recipe_filters import safe_blurb_html

    assert safe_blurb_html("one<br>two<br/>three") == "one<br>two<br>three"


def test_safe_blurb_html_escapes_everything_else():
    """Anything outside the allowed tags is dropped, and text is escaped."""
    from recipes.templatetags.recipe_filters import safe_blurb_html

    assert safe_blurb_html('<img src=x onerror="x()"><b onclick="x()">hi</b> <3') == (
        "<b>hi</b> &lt;3"
    )


def test_safe_step_html_closes_misnested_tags():
    """Closing an outer tag closes the ones nested inside it."""
    from recipes.templatetags.recipe_filters import safe_step_html

    assert safe_step_html("<b><i>x</b>y</i>") == "<b><i>x</i></b>y"


@pytest.mark.parametrize(
    ("stored", "rendered"),
    [
        ("Bake (oven<gas 4) for 20 min. Rest.", "Bake (oven&lt;gas 4) for 20 min. Rest."),
        (
            "Mix until temp<a few degrees. Then serve hot.",
            "Mix until temp&lt;a few degrees. Then serve hot.",
        ),
        ("a<b", "a&lt;b"),
        ("a</b", "a&lt;/b"),
        ("a<!b", "a&lt;!b"),
        ("a<!-- b", "a&lt;!-- b"),
    ],
)
def test_safe_step_html_keeps_text_after_a_stray_less_than(stored: str, rendered: str):
    """A `<` that never becomes a tag is text, not the start of a tag to swallow (#50)."""
    from recipes.templatetags.recipe_filters import safe_step_html

    assert safe_step_html(stored) == rendered


def test_safe_title_html_keeps_text_after_a_stray_less_than():
    """Titles share the sanitiser, so they keep the text too (#50)."""
    from recipes.templatetags.recipe_filters import safe_title_html

    assert safe_title_html("<u>Ragú</u> for 2<4 people") == "<u>Ragú</u> for 2&lt;4 people"
    assert safe_title_html("<u>Fish<chips") == "<u>Fish&lt;chips</u>"


def test_safe_blurb_html_keeps_text_and_line_breaks_after_a_stray_less_than():
    """Blurbs share the sanitiser, and the kept text still gets its line breaks (#50)."""
    from recipes.templatetags.recipe_filters import safe_blurb_html

    assert safe_blurb_html("oven<gas 4\nthen rest") == "oven&lt;gas 4<br>then rest"


@pytest.mark.parametrize("seed", range(200))
def test_safe_step_html_keeps_the_visible_text_of_tagless_input(seed: int):
    """Input that holds no tag at all comes out with every character of its text (#50).

    Without `>` nothing can close a tag, so whatever the parser makes of the
    `<`s, all of the input is text and must survive escaping.
    """
    from html import unescape
    from random import Random

    from recipes.templatetags.recipe_filters import safe_step_html

    rng = Random(seed)
    stored = "".join(rng.choices("ab1 <</!-?.()\"'", k=rng.randint(1, 30)))

    assert unescape(safe_step_html(stored)) == stored
