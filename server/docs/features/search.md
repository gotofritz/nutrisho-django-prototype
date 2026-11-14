# Search (`recipes/services/recipe_search.py`, `recipes/utils/search_query.py`)

Search lists the signed-in user's recipes (#32). The box at the top of every
signed-in page (`partials/_site_search.html`, rendered by `base.html` and again
by `_recipe_content.html` for a boosted visit) is a plain GET to the list. The
list renders a fuller box instead: where to look (everywhere, titles,
ingredients), a cuisine and a tag filter, and the ingredient tool's active
search, where typing or picking swaps `#search-results` only
(`partials/_search_results.html`, chosen by `HX-Target`) and pushes the URL.

The URL is the state, as with scaling: `q`, `in`, `cuisine`, `tag` and `page`
(`views/_search.py` parses them, ignoring anything malformed). `search_from`
builds a `RecipeSearch`; `search_recipes` turns it into one queryset.

- **Terms.** `parse_query` splits on spaces, keeps `"quoted phrases"` whole,
  reads `-term` as an exclusion and caps the total at `MAX_TERMS`. A recipe
  matching **any** term is a result; results rank by terms matched, then by
  terms in the title, then newest first, which is also the order of the
  unsearched list.
- **Matching.** A term matches at the start of a word, `(^|\W)term`, through
  `__iregex` (Django's SQLite backend runs Python's `re`; PostgreSQL reads the
  pattern the same way, unlike `\b`). `term_variants` adds the singulars a
  plural may come from, the reverse of `utils/pluralise.py`, so `aubergines`
  finds `aubergine`. Every match is an `EXISTS` or a single-row join (cuisine
  levels), so a recipe never repeats however many ingredients match.
- **Fields.** Everywhere: the plain-text title and description, ingredient and
  substitute names (and plural overrides), tags, and every level of the
  cuisine. Titles only, or ingredients only. Steps are not searched: their text
  carries inline tags too and has no plain-text column yet.
- **Filters.** The cuisine filter takes a node and everything below it; its
  choices are the nodes holding the user's recipes plus their ancestors. Tags
  offered are those on the user's recipes. 20 results a page.
- **What matched.** `matched_ingredients` fetches, in one query for the page,
  the ingredient names the terms found, shown as "with aubergine" under a
  result.

**Plain text.** Titles and descriptions are stored as typed, inline tags and
all (#17), so a raw `icontains` for `u` would match every underlined title.
`Recipe.save()` writes their tag-free text (`utils/plain_text.py`) into
`plain_name` and `plain_description`, adding them to `update_fields` when only
the typed field is saved; search reads only those. A recipe name is unique per
owner by `plain_name` (`recipes_recipe_unique_plain_name_per_owner`), so `Foo`
and `<u>Foo</u>` clash and the editor says so. Migration 0023 backfills both
columns and stops, naming the rows, if an owner already has names that differ
only by markup. Anything writing names must go through `save()`: a queryset
`update()` or `bulk_create` would leave the plain columns stale.

**Prev/next** on the recipe page walk the list the user came from: the result
links carry the search, and `_get_recipe_nav` takes the ids of
`search_recipes` for it, in list order, wrapping at both ends. The list icon
goes back to the page holding the recipe. A recipe outside the search (edited
since, or a hand-typed URL) walks the whole list instead, newest first.
