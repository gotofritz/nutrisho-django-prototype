"""Page structure (#74): language, landmarks, heading outline, contrast, list actions.

Each page is parsed with the stdlib HTML parser, so the tests read the document
the way assistive tech does: which landmarks it has, which headings in which
order, and what each control is called.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step

ROOT = Path(__file__).resolve().parents[2]
STYLE_CSS = ROOT / "src" / "recipes" / "static" / "css" / "style.css"
TEMPLATES = ROOT / "src" / "recipes" / "templates"

HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}
NAMED = {"a", "button"}
SVG_TEXT = {"svg", "path", "g", "circle", "rect"}


@dataclass
class Control:
    """A link or button, its accessible name, and the id of the <li> it sits in."""

    tag: str
    name: str
    item_id: str | None


@dataclass
class Outline(HTMLParser):
    """The landmarks, headings and named controls of one page."""

    lang: str | None = None
    landmarks: list[tuple[str, str | None]] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)
    _stack: list[str] = field(default_factory=list)
    _heading: list[str] | None = None
    _heading_level: int = 0
    _control: list[str] | None = None
    _control_tag: str = ""
    _control_aria: str | None = None
    _item_id: str | None = None

    def __post_init__(self) -> None:
        """Initialise the parser."""
        super().__init__()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record landmarks and open headings and controls."""
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if tag in {"main", "nav"}:
            self.landmarks.append((tag, a.get("aria-label")))
        if tag == "li" and a.get("id"):
            self._item_id = a["id"]
        if tag in HEADINGS:
            self._heading = []
            self._heading_level = int(tag[1])
        if tag in NAMED and self._control is None:
            self._control = []
            self._control_tag = tag
            self._control_aria = a.get("aria-label")
        if tag not in VOID:
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        """Close headings and controls."""
        if tag in HEADINGS and self._heading is not None:
            self.headings.append((self._heading_level, " ".join("".join(self._heading).split())))
            self._heading = None
        if tag == self._control_tag and self._control is not None:
            name = self._control_aria or " ".join("".join(self._control).split())
            self.controls.append(Control(tag=tag, name=name, item_id=self._item_id))
            self._control = None
        if tag == "li":
            self._item_id = None
        while self._stack:
            if self._stack.pop() == tag:
                break

    def handle_data(self, data: str) -> None:
        """Collect text for whatever heading or control is open."""
        if any(t in SVG_TEXT for t in self._stack):
            return
        if self._heading is not None:
            self._heading.append(data)
        if self._control is not None:
            self._control.append(data)


def outline(html: str) -> Outline:
    """Parse a page into its outline."""
    parsed = Outline()
    parsed.feed(html)
    parsed.close()
    return parsed


@pytest.fixture
def recipe(user) -> Recipe:
    """A recipe with a step and one named ingredient group."""
    recipe = Recipe.objects.create(recipe_name="Leek Soup", owner=user, servings=2)
    Step.objects.create(recipe=recipe, step_text="Boil water", index_in_sequence=0)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Broth", index_in_sequence=0)
    IngredientInRecipe.objects.create(
        ingredient=Ingredient.objects.create(ingredient_name="leek"),
        ingredient_group=group,
        index_in_sequence=0,
    )
    return recipe


@pytest.fixture
def staff_client(user) -> Client:
    """The default user, made staff, logged in."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(user)
    return client


def _get(client: Client, url: str, **headers: str) -> str:
    response = client.get(url, headers=headers)
    assert response.status_code == 200, url
    return response.content.decode()


# --- language (WCAG 3.1.1) ---------------------------------------------------


def test_base_template_declares_english() -> None:
    """Every page extends base.html, so its <html> names the language."""
    assert '<html class="no-js" lang="en">' in (TEMPLATES / "recipes" / "base.html").read_text()


@pytest.mark.django_db
def test_login_page_declares_english() -> None:
    """The login page, the first one anyone sees, is in English."""
    assert outline(_get(Client(), reverse("login"))).lang == "en"


# --- landmarks (WCAG 1.3.1, 2.4.1) --------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    ["recipes:home", "recipes:new", "recipes:ingredient_manage", "recipes:cuisine_manage"],
)
def test_page_has_exactly_one_main(staff_client: Client, url_name: str) -> None:
    """Each page wraps its content in one <main>."""
    mains = [
        lm for lm in outline(_get(staff_client, reverse(url_name))).landmarks if lm[0] == "main"
    ]
    assert len(mains) == 1


@pytest.mark.django_db
def test_login_page_has_exactly_one_main() -> None:
    """The login page, which used to bring its own <main>, still has just one."""
    mains = [lm for lm in outline(_get(Client(), reverse("login"))).landmarks if lm[0] == "main"]
    assert len(mains) == 1


@pytest.mark.django_db
def test_metadata_page_has_exactly_one_main(auth_client: Client, recipe: Recipe) -> None:
    """The metadata form page wraps its content in one <main>."""
    page = outline(_get(auth_client, reverse("recipes:metadata_edit", args=[recipe.pk])))
    assert [lm for lm in page.landmarks if lm[0] == "main"] == [("main", None)]


@pytest.mark.django_db
@pytest.mark.parametrize("boosted", [False, True], ids=["full", "boosted"])
def test_recipe_page_has_main_and_labelled_navbar(
    auth_client: Client, recipe: Recipe, boosted: bool
) -> None:
    """The recipe page has one <main> and the navbar is a labelled <nav>, full or boosted."""
    headers = {"HX-Request": "true", "HX-Boosted": "true"} if boosted else {}
    page = outline(_get(auth_client, recipe.get_absolute_url(), **headers))
    assert [lm for lm in page.landmarks if lm[0] == "main"] == [("main", None)]
    assert ("nav", "Recipes") in page.landmarks


@pytest.mark.django_db
def test_recipe_page_navs_are_all_labelled(auth_client: Client, recipe: Recipe) -> None:
    """More than one <nav> on a page must each have a name to tell them apart."""
    navs = [
        lm
        for lm in outline(_get(auth_client, recipe.get_absolute_url())).landmarks
        if lm[0] == "nav"
    ]
    assert all(label for _, label in navs), navs


# --- headings (WCAG 1.3.1, 2.4.6) ---------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("boosted", [False, True], ids=["full", "boosted"])
def test_recipe_page_heading_outline(auth_client: Client, recipe: Recipe, boosted: bool) -> None:
    """The title is the <h1>, Method and Ingredients are <h2>, groups are <h3>."""
    headers = {"HX-Request": "true", "HX-Boosted": "true"} if boosted else {}
    page = outline(_get(auth_client, recipe.get_absolute_url(), **headers))
    assert page.headings == [(1, "Leek Soup"), (2, "Method"), (2, "Ingredients"), (3, "Broth")]


@pytest.mark.django_db
def test_scaled_recipe_page_heading_outline(auth_client: Client, recipe: Recipe) -> None:
    """A scaled page keeps the same outline, with read-only groups."""
    page = outline(_get(auth_client, f"{recipe.get_absolute_url()}?servings=4"))
    assert page.headings == [(1, "Leek Soup"), (2, "Method"), (2, "Ingredients"), (3, "Broth")]


@pytest.mark.django_db
def test_recipe_title_h1_is_the_focus_target(auth_client: Client, recipe: Recipe) -> None:
    """app.js moves focus to h1[tabindex=-1] after a boosted visit (#61)."""
    html = _get(auth_client, recipe.get_absolute_url())
    assert re.search(r'<h1 class="recipe-title" tabindex="-1">', html)


@pytest.mark.django_db
def test_group_display_partial_is_an_h3(auth_client: Client, recipe: Recipe) -> None:
    """The group heading an inline edit swaps back in is still an <h3>."""
    group = IngredientGroup.objects.get(recipe=recipe)
    html = _get(auth_client, reverse("recipes:group_display", args=[recipe.pk, group.pk]))
    assert outline(html).headings == [(3, "Broth")]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "title"),
    [
        ("recipes:ingredient_manage", "Manage ingredients"),
        ("recipes:cuisine_manage", "Manage cuisines"),
    ],
)
def test_manager_page_has_an_h1(staff_client: Client, url_name: str, title: str) -> None:
    """The staff tools open with a heading that names them."""
    headings = outline(_get(staff_client, reverse(url_name))).headings
    assert headings[:1] == [(1, title)]


# --- contrast (WCAG 1.4.11) ---------------------------------------------------


def _rule(selector: str) -> str:
    css = STYLE_CSS.read_text()
    match = re.search(rf"(?m)^{re.escape(selector)} \{{(?P<body>[^}}]*)\}}", css)
    assert match, selector
    return match.group("body")


@pytest.mark.parametrize(
    "selector",
    [
        'textarea,\ninput[type="text"]',
        ".move-btns button",
        ".login-field input",
        ".site-search input,\n.recipe-search input,\n.recipe-search select",
    ],
)
def test_input_borders_are_at_least_3_to_1(selector: str) -> None:
    """Field and move-button borders use #767676 (4.5:1 on white), not silver or #ccc."""
    assert "--color-field-border: #767676;" in _rule(":root")
    body = _rule(selector)
    assert "border: 1px solid var(--color-field-border);" in body, body


def test_no_tailwind_gray_400_borders_on_inputs() -> None:
    """Tailwind's gray-400 is about 2.6:1 on white, too faint for a field's edge."""
    offenders = [
        str(path.relative_to(TEMPLATES))
        for path in TEMPLATES.rglob("*.html")
        for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", path.read_text())
        if "border-gray-400" in tag
    ]
    assert offenders == []


# --- recipe list actions (WCAG 2.4.4) ------------------------------------------


@pytest.mark.django_db
def test_recipe_list_actions_name_their_recipe(auth_client: Client, user, make_recipe) -> None:
    """Every action in a row says which recipe it acts on, and the name comes first."""
    make_recipe(owner=user, name="Leek Soup")
    make_recipe(owner=user, name="Pea Soup")
    page = outline(_get(auth_client, reverse("recipes:home")))
    rows: dict[str, list[str]] = {}
    for control in page.controls:
        if control.item_id and control.item_id.startswith("recipe-"):
            rows.setdefault(control.item_id, []).append(control.name)
    assert len(rows) == 2
    for names in rows.values():
        title = names[0]
        assert title in {"Leek Soup", "Pea Soup"}, names
        assert all(title in name for name in names[1:]), names
        assert len(names) > 1, names
