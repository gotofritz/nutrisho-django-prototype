"""The recipe search as URL parameters (#32): `q`, `in`, `cuisine`, `tag`, `page`.

The URL is the state, as with `?servings=N`: a search is bookmarkable, and the
list hands it to the recipe page so prev/next walk the same results.
"""

from collections.abc import Mapping
from urllib.parse import urlencode

from recipes.services.recipe_search import DEFAULT_FIELD, SEARCH_FIELDS, RecipeSearch

# Longer than any sensible query; the parser caps the number of terms anyway.
_MAX_QUERY_LENGTH = 200


def _positive_int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() and int(value) > 0 else None


def search_from(params: Mapping[str, str]) -> RecipeSearch:
    """The search in `params`; anything malformed falls back to its default."""
    field = params.get("in") or DEFAULT_FIELD
    return RecipeSearch(
        query=(params.get("q") or "").strip()[:_MAX_QUERY_LENGTH],
        field=field if field in SEARCH_FIELDS else DEFAULT_FIELD,
        cuisine_id=_positive_int(params.get("cuisine")),
        tag_id=_positive_int(params.get("tag")),
    )


def search_querystring(search: RecipeSearch, *, page: int = 1) -> str:
    """`?q=…&in=…` for the non-default parts of `search`, or "" when there are none."""
    params: dict[str, str] = {}
    if search.query:
        params["q"] = search.query
    if search.field != DEFAULT_FIELD:
        params["in"] = search.field
    if search.cuisine_id:
        params["cuisine"] = str(search.cuisine_id)
    if search.tag_id:
        params["tag"] = str(search.tag_id)
    if page > 1:
        params["page"] = str(page)
    return f"?{urlencode(params)}" if params else ""
