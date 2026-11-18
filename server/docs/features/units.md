# Units (`models/unit.py`, `name_resolution.find_unit`/`resolve_unit`, `normalise_units`)

Issue #67, made a shared vocabulary in #154 (plan 012 M1).
`IngredientInRecipe.unit` is a foreign key to `Unit`. Each unit has a canonical
singular `name` (`tbsp`, `clove`, `g`), an optional `plural_name` and a
`dimension`: `mass`, `volume` or `count`. Shopping lists, conversion and
nutrition can rely on one row per unit and on its dimension.

## Global and private units

Like ingredients, units are a global list curated by staff in Django admin
(`owner` blank) plus each user's own (`Unit.owner`). Names are unique ignoring
case within the global list (`unit_name_ci_unique`) and within each user's own
(`unit_name_ci_unique_per_owner`); a private unit may share a name with
another user's, or with a global one, which wins. A private unit has no
dimension, since only staff decide what a user's word measures. Staff make one
global with Promote in the unit tool (below), or in admin by clearing its owner,
and `Unit.clean` then asks for a dimension. A user's units are deleted with
them.

## The staff unit tool

`/recipes/units/manage/`, linked from the Config page for staff, is built like
the cuisine tool (`views/unit_admin.py`, `services/unit_admin.py`,
`forms/unit_admin_forms.py`): column 1 has the search (names and aliases),
*Private only*, *Unused only*, the sort (A to Z or order added) and the
actions; column 2 lists every unit with its dimension, whose it is, how many
rows of any user's recipes use it, and its aliases; column 3 the staff
member's own recipes using the selection. Every route is staff-only.

- **Add** a global unit: name, plural and dimension.
- **Edit** one unit's name, plural and dimension, and a global unit's aliases,
  typed comma-separated. A name or alias that already means a unit is a form
  error. A private unit stays its owner's.
- **Promote** private units, as the ingredient tool does: each becomes global
  with the dimension picked, or joins the global unit of the same name, and
  every other user's unit of that name joins it too, rows and all.
- **Merge** units into the one picked: every user's rows move to it and the
  others go. A global survivor takes their aliases and, unless unticked, their
  names as aliases, so a user typing the old name again gets the survivor.
- **Delete** units: their rows move to a global replacement, or keep the
  unit's name as `legacy_unit` text, so nothing is lost.

A private unit may only replace units in its owner's recipes: Merge or Delete
that would put one in another user's recipe is refused (`UnitScopeError`)
and writes nothing.

## Resolving input

`UnitAlias` maps input-only spellings to a unit (`tablespoon` → `tbsp`), the
same shape as ingredient aliases (plan 008): no recipe references an alias,
and a name is a unit or an alias, never both. Names and aliases are unique
ignoring case, so `l` and `L` are one unit.

`find_unit(text, owner=...)` looks a unit up. It ignores case, extra spaces and
a trailing full stop, then tries the unit's name, its plural, an alias, and an
alias's plural (`Tbsp`, `tbsp.`, `tablespoons`, `cloves`), among the global
units and `owner`'s own, global first; `owner=None` sees the global ones only.
It never creates a unit. Aliases are global, and may only point at a global
unit (`UnitAlias.clean`).

`resolve_unit(text, owner=...)` is how typed or imported text becomes a unit:
`find_unit`, or on a miss a new unit private to `owner`, named as tidied. It
returns None for blank text and for a size word (`small`) or an amount phrase
(`to taste`), which never become units (`utils/unit_words.py`). The recipe
editor's unit field (`IngredientInRecipeForm`) refuses those with an error
naming the field they belong in; anything else is resolved inside the row's
write (`ingredient_groups.resolve_row_names`), so a refused form makes no unit.
The field's datalist offers the global units and the owner's own.

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
Reversing `0032_private_units` likewise writes each private unit's name into
its rows' `legacy_unit` and deletes the private units.

`normalise_units` (`make manage ARGS="normalise_units"`) moves it, through
`services/unit_normalisation.py`. It is a dry run by default: one line per
distinct value, how many rows carry it, and what it becomes. It reads the
global units only, since one value may be in many users' rows, and never makes
a private unit.

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
