"""Tests for the storybook redesign (#76).

Every signed-in page shares one header; the recipe list reads as a book's
contents page; the login page is a spread with the lineout plate; the recipe
sheet keeps its printed look while its tools move into the margin. The CSS is
plain and hand-written, so no template may lean on Tailwind utilities.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse

from recipes.models import IngredientGroup, Recipe
from recipes.services.name_resolution import find_cuisine

TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "recipes" / "templates"

# Utility classes the old Tailwind build supplied; plain CSS has no rule for them.
TAILWIND_UTILITY = re.compile(
    r"^(?:flex|grow|shrink-0|sticky|rounded|border|underline|"
    r"(?:p|px|py|pb|pt|m|mb|mt|gap|top|h|w|min-w|max-w|min-h|basis|text|bg|"
    r"border|border-b|font|decoration|items|justify|overflow|overflow-[xy]|"
    r"cursor|disabled:[\w-]+|break)-[\w\[\]\-%.]+)$"
)


def _class_tokens(path: Path) -> list[str]:
    return [
        token
        for value in re.findall(r'class="([^"{]*)"', path.read_text())
        for token in value.split()
    ]


def test_no_template_uses_tailwind_utilities():
    """Layout lives in style.css; a utility class would now style nothing."""
    offenders = {
        str(path.relative_to(TEMPLATES)): hits
        for path in TEMPLATES.rglob("*.html")
        if (hits := [t for t in _class_tokens(path) if TAILWIND_UTILITY.match(t)])
    }
    assert offenders == {}


# --- the shared header ---------------------------------------------------------


def _site_nav(html: str) -> str:
    match = re.search(r'<nav[^>]*aria-label="Site"[^>]*>(.*?)</nav>', html, flags=re.DOTALL)
    assert match, "site navigation missing"
    return match.group(1)


@pytest.fixture
def recipe(user) -> Recipe:
    """A recipe owned by the default user."""
    return Recipe.objects.create(recipe_name="Leek Soup", owner=user, servings=2)


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/recipes/", "/recipes/new/", "recipe"])
def test_signed_in_pages_share_the_site_header(auth_client: Client, recipe: Recipe, url: str):
    """The list, a recipe and the new-recipe form all carry the same navigation."""
    page = recipe.get_absolute_url() if url == "recipe" else url
    nav = _site_nav(auth_client.get(page).content.decode())

    assert f'href="{reverse("recipes:home")}"' in nav
    assert f'href="{reverse("recipes:new")}"' in nav
    assert 'action="/accounts/logout/"' in nav


@pytest.mark.django_db
def test_boosted_recipe_page_carries_the_site_header(auth_client: Client, recipe: Recipe):
    """A boosted visit replaces the whole body, so the partial brings the header too."""
    html = auth_client.get(
        recipe.get_absolute_url(), HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true"
    ).content.decode()

    assert 'action="/accounts/logout/"' in _site_nav(html)


@pytest.mark.django_db
def test_staff_tools_are_in_the_header_for_staff_only(auth_client: Client, user: User):
    """Ingredients and Cuisines are staff tools, so only staff see the links."""
    tools = (reverse("recipes:ingredient_manage"), reverse("recipes:cuisine_manage"))
    nav = _site_nav(auth_client.get("/recipes/").content.decode())
    assert not any(url in nav for url in tools)

    User.objects.filter(pk=user.pk).update(is_staff=True)
    nav = _site_nav(auth_client.get("/recipes/").content.decode())
    assert all(url in nav for url in tools)


@pytest.mark.django_db
def test_header_marks_the_current_page(auth_client: Client):
    """The link to the page you are on says so to assistive tech."""
    nav = _site_nav(auth_client.get("/recipes/").content.decode())

    assert re.search(r'<a href="/recipes/" aria-current="page"', nav)


@pytest.mark.django_db
def test_login_page_has_no_site_header(client: Client):
    """Signed out, there is nowhere to navigate to."""
    assert 'aria-label="Site"' not in client.get("/accounts/login/").content.decode()


# --- the contents page ---------------------------------------------------------


@pytest.mark.django_db
def test_contents_line_shows_cuisine_servings_and_blurb(auth_client: Client, user: User):
    """Each entry names its kitchen and servings, with the blurb beneath."""
    Recipe.objects.create(
        recipe_name="Baba ganoush",
        owner=user,
        servings=6,
        cuisine=find_cuisine("middle east.levant.lebanon"),
        short_description="Smoky <b>eggplant</b> dip.",
    )
    html = auth_client.get("/recipes/").content.decode()

    assert re.search(r'class="contents-meta">\s*Lebanon, serves 6\s*<', html)
    assert re.search(r'class="recipe-blurb">\s*Smoky eggplant dip\.\s*<', html)


@pytest.mark.django_db
def test_contents_line_without_a_cuisine_shows_servings_only(auth_client: Client, recipe: Recipe):
    """No cuisine, no dangling comma."""
    html = auth_client.get("/recipes/").content.decode()

    assert re.search(r'class="contents-meta">\s*serves 2\s*<', html)


@pytest.mark.django_db
def test_contents_numbering_continues_on_later_pages(auth_client: Client, user: User):
    """Page two starts at XXI, not at I again."""
    for n in range(25):
        Recipe.objects.create(recipe_name=f"Soup {n}", owner=user, servings=1)
    first = auth_client.get("/recipes/").content.decode()
    second = auth_client.get("/recipes/?page=2").content.decode()

    assert re.search(r'<ol id="recipe-list" class="contents" start="1">', first)
    assert re.search(r'<ol id="recipe-list" class="contents" start="21">', second)


@pytest.mark.django_db
def test_contents_query_count_does_not_grow_with_cuisines(
    auth_client: Client, user: User, django_assert_max_num_queries
):
    """Each line's cuisine comes with its recipe, not one query per line."""
    for name in ("med.italy", "med.italy.sicily", "middle east"):
        Recipe.objects.create(recipe_name=name, owner=user, cuisine=find_cuisine(name))
    auth_client.get("/recipes/")  # warm the session and cuisine caches
    with django_assert_max_num_queries(6):
        auth_client.get("/recipes/")


@pytest.mark.django_db
def test_delete_is_not_on_the_contents_page(auth_client: Client, recipe: Recipe):
    """Delete sits apart from the everyday actions, on the recipe's own page (#75)."""
    contents = auth_client.get("/recipes/").content.decode()
    page = auth_client.get(recipe.get_absolute_url()).content.decode()

    assert reverse("recipes:delete", kwargs={"recipe_id": recipe.pk}) not in contents
    assert 'class="danger"' not in contents
    assert reverse("recipes:delete_panel", kwargs={"recipe_id": recipe.pk}) in page


# --- the login spread ------------------------------------------------------------


@pytest.mark.django_db
def test_login_page_shows_the_plate_and_copyright(client: Client):
    """The lineout plate fills one side; the copyright sits where a caption would."""
    html = client.get("/accounts/login/").content.decode()

    img = re.search(r'<img[^>]*src="/static/img/plate-lineout\.webp"[^>]*>', html)
    assert img, "plate missing"
    assert 'alt="' in img.group(0) and 'alt=""' not in img.group(0)
    assert re.search(r"<figcaption[^>]*>\s*&copy; 2022", html)
    assert finders.find("img/plate-lineout.webp")


# --- the recipe page ---------------------------------------------------------------


@pytest.mark.django_db
def test_recipe_tools_sit_in_the_margin_outside_the_sheet(auth_client: Client, recipe: Recipe):
    """The sheet is the printed recipe; the tools that act on it sit beside it."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    sheet = html[html.index("<main") : html.index("</main>")]
    margin = re.search(
        r'<aside[^>]*aria-label="Recipe tools"[^>]*>(.*?)</aside>', html, flags=re.DOTALL
    )

    assert margin, "recipe tools missing"
    assert 'data-panel-toggle="metadata-panel"' in margin.group(1)
    assert 'id="scale-panel"' in margin.group(1)
    assert "data-panel-toggle" not in sheet


@pytest.mark.django_db
def test_recipe_page_turns_to_the_previous_and_next_recipe(auth_client: Client, recipe: Recipe):
    """Previous and next sit at the foot of the page, like turning a page."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    nav = re.search(r'<nav[^>]*aria-label="Recipes"[^>]*>(.*?)</nav>', html, flags=re.DOTALL)

    assert nav, "page-turn navigation missing"
    assert 'rel="prev"' in nav.group(1)
    assert 'rel="next"' in nav.group(1)
    assert html.index("</main>") < nav.start()


@pytest.mark.django_db
def test_page_turn_arrows_sit_either_side_of_the_recipe(auth_client: Client, recipe: Recipe):
    """On a wide screen previous and next are quiet arrows fixed at the page's edges (#76)."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    nav = re.search(r'<nav[^>]*aria-label="Recipes"[^>]*>(.*?)</nav>', html, flags=re.DOTALL)
    assert nav

    for side, label in (("prev", "Previous recipe"), ("next", "Next recipe")):
        link = re.search(rf'<a [^>]*class="turn turn-{side}"[^>]*>(.*?)</a>', nav.group(1), re.S)
        assert link, side
        assert f'rel="{side}"' in link.group(0)
        assert f'title="{label}"' in link.group(0)
        assert '<span class="turn-arrow" aria-hidden="true">' in link.group(1)
        assert f'<span class="turn-label">{label}</span>' in link.group(1)

    css = (Path(finders.find("css/style.css"))).read_text()
    wide = css[css.index("@media (min-width: 1001px)") :]
    assert re.search(r"\.turn \{[^}]*position: fixed;[^}]*top: 50%;", wide)


# --- named controls on the sheet (#60) ----------------------------------------------


@pytest.mark.django_db
def test_margin_toggles_say_whether_their_panel_is_open(auth_client: Client, recipe: Recipe):
    """Each margin toggle starts closed; app.js keeps aria-expanded in step with its panel."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    toggles = re.findall(r"<button[^>]*data-panel-toggle[^>]*>", html, flags=re.DOTALL)

    assert len(toggles) == 3
    assert all('aria-expanded="false"' in toggle for toggle in toggles)
    assert "aria-expanded" in Path(finders.find("js/app.js")).read_text()


@pytest.mark.django_db
def test_row_checkboxes_and_move_buttons_name_their_row(
    auth_client: Client, recipe: Recipe, add_step, add_ingredient, make_ingredient
):
    """A screen reader hears which step, ingredient or group a control acts on."""
    add_step(recipe=recipe, text="Sweat the leeks in butter until soft.", title="Leeks")
    add_step(recipe=recipe, text="Add the stock and simmer.")
    add_ingredient(recipe=recipe, ingredient=make_ingredient("leek"))
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    group = IngredientGroup.objects.get(recipe=recipe)

    for label in (
        'aria-label="Select step: Leeks"',
        'aria-label="Move step Leeks up"',
        'aria-label="Move step Leeks down"',
        'aria-label="Select step: Add the stock and simmer."',
        'aria-label="Select leek"',
        'aria-label="Move leek up"',
        'aria-label="Move leek down"',
        f'aria-label="Move group {group.group_name or "untitled"} up"',
    ):
        assert label in html, label


def test_move_buttons_are_at_least_24px():
    """WCAG 2.5.8: the ↑/↓ targets are 24 by 24 pixels, however faint they look."""
    css = Path(finders.find("css/style.css")).read_text()
    rule = re.search(r"(?m)^\.move-btns button \{(?P<body>[^}]*)\}", css)

    assert rule
    assert "min-width: 24px;" in rule.group("body")
    assert "min-height: 24px;" in rule.group("body")
