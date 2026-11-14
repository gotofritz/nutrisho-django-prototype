"""Column 2 of the ingredient clean-up tool lists a page at a time (#80).

It used to render every ingredient on each search keystroke (597 KB at 2,000
rows). Now it shows the first page, and "Show more" appends the next one. The
number of rows on show travels with every request as `limit`, so an action or
Cancel brings the column back as long as it was, and select-all only reaches
the rows on show.
"""

import re

import pytest

from recipes.views import ingredient_admin

MANAGE_URL = "/recipes/ingredients/manage/"
SEARCH_URL = MANAGE_URL + "search/"
MORE_URL = MANAGE_URL + "more/"
CANCEL_URL = MANAGE_URL + "cancel/"
RECIPES_URL = MANAGE_URL + "recipes/"
EDIT_URL = MANAGE_URL + "edit/"

PAGE = 3


@pytest.fixture
def user(user):
    """The default user, made staff: the clean-up tool is staff-only (#46)."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    """Pages of three, so a handful of rows spans several."""
    monkeypatch.setattr(ingredient_admin, "PAGE_SIZE", PAGE)


@pytest.fixture
def eight(make_ingredient) -> list[int]:
    """Eight ingredients, `a` to `h`; their ids in listing order."""
    return [make_ingredient(name).pk for name in "abcdefgh"]


def listed(html: str) -> list[int]:
    """The ids of the rows column 2 shows, in order."""
    return [
        int(pk)
        for pk in re.findall(
            r'class="ingredient-pick"\s+name="ingredient_ids"\s+value="(\d+)"', html
        )
    ]


def limit_value(html: str) -> int:
    """The row count the page carries for the next request."""
    match = re.search(r'id="ingredient-limit"[^>]*value="(\d+)"', html)
    assert match is not None, "no #ingredient-limit input"
    return int(match.group(1))


def more_button(html: str) -> str | None:
    """The Show-more button's text, or None when there is none."""
    match = re.search(r'<button[^>]*class="show-more[^"]*"[^>]*>\s*(.*?)\s*</button>', html, re.S)
    return match.group(1) if match else None


@pytest.mark.django_db
def test_the_column_shows_the_first_page(auth_client, eight):
    """Only `PAGE_SIZE` rows render, but the count is of every match."""
    html = auth_client.get(MANAGE_URL).content.decode()
    assert listed(html) == eight[:PAGE]
    assert "8 found" in html
    assert limit_value(html) == PAGE
    assert more_button(html) == "Show 3 more (3 of 8 shown)"


@pytest.mark.django_db
def test_no_more_button_when_everything_fits(auth_client, make_ingredient):
    """A short list has nothing more to show."""
    make_ingredient("onion")
    html = auth_client.get(MANAGE_URL).content.decode()
    assert len(listed(html)) == 1
    assert more_button(html) is None


@pytest.mark.django_db
def test_more_appends_the_next_page(auth_client, eight):
    """The next rows, a new button, and the header with the longer limit."""
    html = auth_client.get(MORE_URL, {"limit": PAGE}).content.decode()
    assert listed(html) == eight[PAGE : 2 * PAGE]
    assert more_button(html) == "Show 2 more (6 of 8 shown)"
    assert limit_value(html) == 2 * PAGE
    assert re.search(r'id="ingredient-count"[^>]*hx-swap-oob="true"', html)


@pytest.mark.django_db
def test_the_last_page_has_no_button(auth_client, eight):
    """Once every row is on show, the button goes."""
    html = auth_client.get(MORE_URL, {"limit": 2 * PAGE}).content.decode()
    assert listed(html) == eight[2 * PAGE :]
    assert more_button(html) is None
    assert limit_value(html) == 8


@pytest.mark.django_db
def test_more_keeps_the_filters(auth_client, make_ingredient):
    """The next page is of the filtered list."""
    for name in ("apple", "apricot", "aubergine", "avocado", "banana", "fig"):
        make_ingredient(name)
    html = auth_client.get(MORE_URL, {"limit": PAGE, "q": "a"}).content.decode()
    names = re.findall(r'class="ingredient-name">([^<]+)<', html)
    assert names == ["avocado", "banana"]


@pytest.mark.django_db
def test_more_keeps_the_header_in_step_with_the_selection(auth_client, eight):
    """All three shown rows ticked, then three unticked arrive: the box goes dashed."""
    html = auth_client.get(
        MORE_URL, {"limit": PAGE, "ingredient_ids": eight[:PAGE]}
    ).content.decode()
    assert "8 found / 3 selected" in html
    assert 'data-indeterminate="true"' in html


@pytest.mark.django_db
def test_limit_keeps_a_longer_column(auth_client, eight):
    """A request that carries `limit` re-renders as many rows."""
    html = auth_client.get(CANCEL_URL, {"limit": 2 * PAGE}).content.decode()
    assert listed(html) == eight[: 2 * PAGE]
    assert limit_value(html) == 2 * PAGE


@pytest.mark.django_db
@pytest.mark.parametrize("raw", ["", "junk", "-4", "0", "1"])
def test_a_missing_or_short_limit_is_one_page(auth_client, eight, raw):
    """Never fewer than a page, whatever arrives."""
    html = auth_client.get(SEARCH_URL, {"limit": raw}).content.decode()
    assert listed(html) == eight[:PAGE]


@pytest.mark.django_db
def test_a_selected_row_past_the_page_still_shows(auth_client, eight):
    """After a rename sorts the selection further down, it stays visible and ticked."""
    html = auth_client.get(SEARCH_URL, {"ingredient_ids": [eight[6]]}).content.decode()
    assert listed(html) == eight[:7]
    assert limit_value(html) == 7
    assert re.search(rf'value="{eight[6]}"\s+checked', html)


@pytest.mark.django_db
def test_select_all_reaches_only_the_rows_on_show(auth_client, eight):
    """Rows not yet loaded are never selected unseen."""
    html = auth_client.get(SEARCH_URL, {"toggle_all": "1", "limit": PAGE}).content.decode()
    assert "8 found / 3 selected" in html
    assert re.search(r'id="select-all"\s+checked', html)


@pytest.mark.django_db
def test_select_all_clears_when_every_row_on_show_is_selected(auth_client, eight):
    """The page's rows all ticked counts as all selected."""
    html = auth_client.get(
        SEARCH_URL, {"toggle_all": "1", "limit": PAGE, "ingredient_ids": eight[:PAGE]}
    ).content.decode()
    assert "8 found / 0 selected" in html


@pytest.mark.django_db
def test_a_tick_keeps_the_header_on_the_rows_on_show(auth_client, eight):
    """The header the tick refreshes judges select-all by the shown rows."""
    html = auth_client.get(
        RECIPES_URL, {"limit": PAGE, "ingredient_ids": eight[:PAGE]}
    ).content.decode()
    assert re.search(r'id="select-all"\s+checked', html)
    assert limit_value(html) == PAGE


@pytest.mark.django_db
def test_the_workspace_carries_the_limit(auth_client, eight):
    """The workspace replaces column 2, so it keeps the row count for Cancel."""
    html = auth_client.get(
        EDIT_URL, {"limit": 2 * PAGE, "ingredient_ids": [eight[0]]}
    ).content.decode()
    assert limit_value(html) == 2 * PAGE


def test_every_request_back_to_the_column_sends_the_limit():
    """Every hx-include in the tool names #ingredient-limit, except the filters.

    Search and the filter boxes start the list afresh, so they leave it out.
    """
    from pathlib import Path

    folder = Path(ingredient_admin.__file__).parents[1] / "templates/recipes/ingredient_admin"
    for template in folder.glob("*.html"):
        for include in re.findall(r'hx-include="([^"]*)"', template.read_text()):
            if template.name == "manager.html":
                assert "#ingredient-limit" not in include, template.name
            else:
                assert "#ingredient-limit" in include, f"{template.name}: {include}"
