"""Every control is keyboard-reachable and named (#60; WCAG 2.1.1, 4.1.2, 1.3.1).

The URLconf is walked, as in `tests/test_route_access.py`, and every page and
partial a signed-in staff owner can GET is parsed the way assistive tech reads
it. A new template is checked the moment a route renders it:

- whatever starts a request on a click is a real control (a link with an
  ``href``, a button or a form field), so Tab reaches it and Enter works;
- every link and button has a name, from its text or ``aria-label``;
- every form field has a label: a ``<label>``, ``aria-label`` or
  ``aria-labelledby``, never just a placeholder.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from recipes.models import Cuisine, Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step

_PARAM = re.compile(r"<(?:\w+:)?(\w+)>")
# Django's own admin and auth pages are not ours to change.
_SKIPPED_PREFIXES = ("admin/", "accounts/")
# These POSTs only render a blank draft form; nothing is written until it is saved.
_DRAFT_ROUTES = ("steps/add/", "groups/add/", "ingredients/add/")

HX_VERBS = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")
CONTROLS = {"a", "button", "form", "input", "select", "textarea"}
VOID = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
UNLABELLED_INPUTS = {"hidden", "submit", "button", "reset", "image"}


@dataclass
class Problem:
    """One control that fails a check, with enough of it to find the template."""

    kind: str
    tag: str
    attrs: dict[str, str | None]

    def __str__(self) -> str:
        """Show the check and the attributes that identify the element."""
        shown = {k: v for k, v in self.attrs.items() if k in {"id", "class", "name", "type"}}
        shown.update({k: v for k, v in self.attrs.items() if k.startswith("hx-")})
        return f"{self.kind}: <{self.tag} {shown}>"


@dataclass
class _Open:
    tag: str
    attrs: dict[str, str | None]
    text: list[str] = field(default_factory=list)
    hidden: bool = False


@dataclass
class Audit(HTMLParser):
    """Collects every control on a page and what names it."""

    problems: list[Problem] = field(default_factory=list)
    _stack: list[_Open] = field(default_factory=list)
    _fields: list[tuple[str, dict[str, str | None], bool]] = field(default_factory=list)
    _label_for: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Initialise the parser."""
        super().__init__()

    def _hidden(self) -> bool:
        return any(o.hidden for o in self._stack)

    def _in_label(self) -> bool:
        return any(o.tag == "label" for o in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Check request triggers and fields; open elements whose text names them."""
        a = dict(attrs)
        verbs = [v for v in HX_VERBS if v in a]
        trigger = a.get("hx-trigger") or ""
        clicked = not trigger or "click" in trigger
        if verbs and clicked and tag not in CONTROLS:
            self.problems.append(Problem("click target is not a control", tag, a))
        if tag == "a" and "href" not in a:
            self.problems.append(Problem("link without href cannot be focused", tag, a))
        if tag == "label" and a.get("for"):
            self._label_for.add(a["for"] or "")
        if tag in {"select", "textarea"} or (
            tag == "input" and (a.get("type") or "text") not in UNLABELLED_INPUTS
        ):
            self._fields.append((tag, a, self._in_label()))
        if tag in VOID:
            return
        self._stack.append(_Open(tag, a, hidden=a.get("aria-hidden") == "true"))

    def handle_endtag(self, tag: str) -> None:
        """Close an element; a closed link or button must have a name."""
        while self._stack:
            o = self._stack.pop()
            if o.tag in {"a", "button"}:
                name = o.attrs.get("aria-label") or o.attrs.get("aria-labelledby")
                if not (name or "".join(o.text).strip()):
                    self.problems.append(Problem(f"{o.tag} has no name", o.tag, o.attrs))
            if o.tag == tag:
                break

    def handle_data(self, data: str) -> None:
        """Visible text names every link or button it sits in."""
        if self._hidden():
            return
        for o in self._stack:
            if o.tag in {"a", "button"}:
                o.text.append(data)

    def close(self) -> None:
        """Finish parsing, then check every field has a label."""
        super().close()
        for tag, a, wrapped in self._fields:
            named = a.get("aria-label") or a.get("aria-labelledby")
            if not (named or wrapped or a.get("id") in self._label_for):
                self.problems.append(Problem("field has no label", tag, a))


def audit(html: str) -> list[str]:
    """Every problem on a page, as text."""
    parsed = Audit()
    parsed.feed(html)
    parsed.close()
    return [str(p) for p in parsed.problems]


def _walk(patterns: list, prefix: str = "") -> Iterator[str]:
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern)


ROUTES = [r for r in _walk(get_resolver().url_patterns) if not r.startswith(_SKIPPED_PREFIXES)]


@pytest.fixture
def staff(user) -> User:
    """The default user, made staff so the clean-up tools render too."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def staff_client(staff: User) -> Client:
    """A client logged in as the staff owner."""
    client = Client()
    client.force_login(staff)
    return client


@pytest.fixture
def path_values(staff: User) -> dict[str, str]:
    """A recipe with two named groups, a titled step and a substitute, owned by staff."""
    recipe = Recipe.objects.create(recipe_name="Leek Soup", owner=staff, servings=4)
    step = Step.objects.create(
        recipe=recipe, step_title="Leeks", step_text="Sweat", index_in_sequence=0
    )
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Broth", index_in_sequence=0)
    IngredientGroup.objects.create(recipe=recipe, group_name="Garnish", index_in_sequence=1)
    leek = Ingredient.objects.create(ingredient_name="leek")
    iir = IngredientInRecipe.objects.create(
        ingredient=leek,
        substitute=Ingredient.objects.create(ingredient_name="onion"),
        ingredient_group=group,
        index_in_sequence=0,
    )
    cuisine = Cuisine.objects.create(cuisine="Welsh")
    return {
        "recipe_id": str(recipe.pk),
        "step_id": str(step.pk),
        "group_id": str(group.pk),
        "iir_id": str(iir.pk),
        "ingredient_id": str(leek.pk),
        "cuisine_id": str(cuisine.pk),
        "field_name": "recipe_name",
    }


def _url(route: str, values: dict[str, str]) -> str:
    return "/" + _PARAM.sub(lambda m: values[m.group(1)], route)


def _pages(client: Client, values: dict[str, str]) -> Iterator[tuple[str, str]]:
    """Every HTML page or partial the staff owner can GET, plus the drafts."""
    recipe = reverse("recipes:recipe", args=[values["recipe_id"]])
    extra = [("get", f"{recipe}?edit=1"), ("get", reverse("recipes:home") + "?q=leek")]
    walked = [("get", _url(r, values)) for r in ROUTES]
    drafts = [("post", _url(r, values)) for r in ROUTES if r.endswith(_DRAFT_ROUTES)]
    for method, url in walked + extra + drafts:
        response = getattr(client, method)(url, HTTP_HX_REQUEST="true")
        if response.status_code in {200, 422} and "html" in response.get("Content-Type", ""):
            yield f"{method.upper()} {url}", response.content.decode()


@pytest.mark.django_db
def test_every_page_and_partial_has_keyboard_reachable_named_controls(
    staff_client: Client, path_values: dict[str, str]
) -> None:
    """No page or partial has a click-only element, an unnamed control or an unlabelled field."""
    pages = dict(_pages(staff_client, path_values))
    assert len(pages) > 20, sorted(pages)
    problems = {url: found for url, html in pages.items() if (found := audit(html))}
    report = "\n".join(f"{url}\n  " + "\n  ".join(found) for url, found in problems.items())
    assert problems == {}, report


@pytest.mark.parametrize(
    ("html", "problem"),
    [
        ('<span hx-get="/x/">Edit</span>', "click target is not a control"),
        ('<a hx-get="/x/">Open</a>', "link without href"),
        ('<button type="button"><svg aria-hidden="true"></svg></button>', "button has no name"),
        ('<input type="text" placeholder="New group name">', "field has no label"),
        ("<select><option>1</option></select>", "field has no label"),
    ],
    ids=["span-trigger", "link-no-href", "icon-button", "placeholder-only", "select"],
)
def test_audit_finds_each_kind_of_problem(html: str, problem: str) -> None:
    """The audit itself catches what #60 lists, so a pass means something."""
    found = audit(html)
    assert len(found) == 1, found
    assert problem in found[0]


@pytest.mark.parametrize(
    "html",
    [
        '<button type="button" aria-label="Move step 1 up">&uarr;</button>',
        '<label for="q">Search</label><input type="search" id="q">',
        '<label><input type="checkbox"> Select all</label>',
        '<input type="checkbox" aria-label="Select leek">',
        '<div hx-get="/x/" hx-trigger="load"></div>',
        '<div hx-get="/x/" hx-trigger="change target:.pick"></div>',
        '<a href="/x/" hx-get="/x/">Open</a>',
    ],
)
def test_audit_passes_named_controls(html: str) -> None:
    """Named and labelled controls, and requests nobody clicks, pass."""
    assert audit(html) == []
