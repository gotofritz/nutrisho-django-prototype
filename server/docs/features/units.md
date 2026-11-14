# Units (`models/unit.py`, `name_resolution.find_unit`, `normalise_units`)

Issue #67. `IngredientInRecipe.unit` is a foreign key to `Unit`, a global,
staff-curated vocabulary edited in Django admin. Each unit has a canonical
singular `name` (`tbsp`, `clove`, `g`), an optional `plural_name` and a
`dimension`: `mass`, `volume` or `count`. Shopping lists, conversion and
nutrition can rely on one row per unit and on its dimension.

## Resolving input

`UnitAlias` maps input-only spellings to a unit (`tablespoon` → `tbsp`), the
same shape as ingredient aliases (plan 008): no recipe references an alias,
and a name is a unit or an alias, never both. Names and aliases are unique
ignoring case, so `l` and `L` are one unit.

`find_unit(text)` is the only way typed text becomes a unit. It ignores case,
extra spaces and a trailing full stop, then tries the unit's name, its plural,
an alias, and an alias's plural (`Tbsp`, `tbsp.`, `tablespoons`, `cloves`). It
never creates a unit. The recipe editor's unit field (`IngredientInRecipeForm`)
resolves through it and offers the vocabulary in a datalist. Anything that does
not resolve is a field error: a size word (`small`) or an amount phrase (`to
taste`) is told which field it belongs in (`utils/unit_words.py`), anything else
is "not a unit we know". Staff add a missing unit or alias in admin.

Migration `0026_seed_units` seeds the starting vocabulary and its aliases.

## Display

Units pluralise at render time by the same rule and gate as ingredient names
(see `pluralisation.md`): plural when the displayed quantity is recorded and is
not 1. `display_unit` uses the stored quantity and `unit_at` the scaled one, so
`1 clove` doubled reads `2 cloves`. Abbreviations are seeded with a plural equal
to their name, so they stay invariant (`200 g`). Any unit, canonical or legacy,
still keeps the ingredient name singular (`2 cloves garlic`).

## Legacy text and the clean-up command

Units typed before #67 were free text. Migration `0025_unit_vocabulary` keeps
that text in `IngredientInRecipe.legacy_unit` and leaves `unit` empty; the page
shows legacy text as stored, unpluralised, until it is moved. Reversing the
migration writes each canonical unit's name back into the text column.

`normalise_units` (`make manage ARGS="normalise_units"`) moves it, through
`services/unit_normalisation.py`. It is a dry run by default: one line per
distinct value, how many rows carry it, and what it becomes.

- A spelling of a unit (`Tbsp`, `tbs`, `cloves`) points the row at the unit.
- A size word (`small`, `large`) leads the `preparation` (`small, chopped`).
- An amount phrase (`to taste`) leads the `note`, and the quantity beside it
  is cleared, since scaling would multiply it.
- Anything else (`tbso`) is left as typed. Add an alias in admin, or edit the
  rows, and run it again.

`--apply` writes the plan in one transaction. It never truncates: a row whose
`preparation` or `note` has no room left is skipped and reported by id. Editing
a legacy row in the recipe editor resolves its unit too and clears the legacy
text. Once a production database reports "No legacy units left", a later
migration can drop `legacy_unit`.
