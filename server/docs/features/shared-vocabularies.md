# Shared vocabularies (multi-user)

Nutrisho is multi-user (#46). Recipes belong to their owner; the vocabularies
they draw on are split by who may change them:

- **Ingredients**: a global, staff-curated list plus a private list per user
  (plan 011). Only staff rename, merge or delete global ingredients, which is
  why the clean-up tool is staff-only. Typing an unknown name in the recipe
  editor creates a row private to the recipe's owner (`Ingredient.owner`);
  staff promote it to global in the clean-up tool.
- **Tags**: global tags curated by staff (in Django admin, owner blank) plus
  private tags per user (`Tag.owner`). The metadata form takes tags as
  comma-separated names, which `set_tags` (`services/recipe_metadata.py`) resolves: `resolve_tag` finds a global tag, then the owner's
  own, and creates a private one on a miss. Unique ignoring case within the
  global list and within each owner's tags; migration 0019 merged existing
  case-only duplicates into the most-used spelling.
- **Units**: global units curated by staff (in Django admin, owner blank) plus
  private units per user (`Unit.owner`, #154). The recipe editor and the
  import resolve a unit with `resolve_unit`: a global unit, then the owner's
  own, and a private one made on a miss, but never from a size word or an
  amount phrase. A private unit has no dimension until staff promote it in the
  unit tool at `/recipes/units/manage/`, which also adds, edits, merges and
  deletes units. Aliases are global only. See `units.md`.
- **Cuisines**: one global, curated tree, `area.region.subregion`
  (`med.italy.sicily`), via `Cuisine.parent` (PROTECT). A recipe points at any
  depth: `middle east` for a dish many countries claim, `med.italy` with no
  region. Areas are not all places: `anglo` is the US, UK, Ireland, Canada,
  Australia and New Zealand. Migration 0021 seeds the list agreed with the
  owner and folds the old flat names in (adjectives such as `Italian` via its
  `ALIASES`, else a node name occurring once; `fusion` and `modern` became
  global **tags**, being styles, not places; anything unmatched stays as a
  top-level row for staff). Users pick from the tree or type a new one, as
  with tags (#171): the editor's datalist holds the dotted paths the user
  sees (`cuisine_paths(owner=...)`: the global tree plus their own nodes),
  `find_cuisine` takes a path or an unambiguous bare name, and on a miss
  `resolve_cuisine` makes the missing levels private to the recipe's owner
  (`Cuisine.owner`), inside the deepest node the path names
  (`med.italy.marche` inside the global `med.italy`; a bare `fika` becomes an
  area of their own). It refuses, making nothing, a bare name more than one
  node has, a blank part or a fourth level: a form error in the editor, a
  warning on import. The metadata form only checks the name
  (`check_cuisine`); `create_recipe` and `save_metadata` make it in the
  save's transaction, as tags are. A private node sits inside a global node
  or one of its owner's, never another user's, and no global node sits
  inside a private one (`Cuisine.clean()`). Staff edit
  the tree in the cuisine tool at `/recipes/cuisines/manage/` (linked from the
  home page next to "Manage ingredients"; Django admin works too).
  `Cuisine.clean()` forbids dots in names, loops and a fourth level, and the
  tool's `CuisineForm` surfaces those and the uniqueness rules as form errors.
  Names are unique ignoring case among siblings
  (`cuisine_ci_unique_per_parent`) and among areas (`cuisine_ci_unique`),
  the global tree and each user's own nodes apart
  (`cuisine_ci_unique_private_per_parent`, `cuisine_ci_unique_private`), so
  two users may each have a `marche` under `med.italy`. The tool lists every
  user's nodes, each marked "private to" its owner; Edit's "Make it global"
  moves one into the shared tree once its parent is global, and Merge folds
  one into a global node, its owner's recipes following. A private node is
  never a survivor or replacement for a node that is not its owner's
  (`CuisineOwnerError`), since those recipes' owners could not see it. Nodes
  staff add are global, inside a global node.
  The tool is a smaller sibling of the ingredient one: a searchable list of
  every path, the staff member's own recipes for the selection, and Add,
  Edit (rename or move), Merge and Delete. Its pure functions live in
  `services/cuisine_admin.py`. Merge and Delete act on every user's recipes,
  Delete's replacement is optional (without one, recipes lose their cuisine),
  and both refuse a node unless everything inside it is selected too (nodes
  then go leaves first, as `parent` is PROTECT). "Unused only" lists nodes with
  no recipe from any user on them or below them, so a dead branch can be
  selected and deleted whole. The list sorts A to Z or in the order
  nodes were added (by primary key; there is no timestamp), so rows that
  predate the seeded tree sit above its first area, `eu`. The recipe page shows the
  cuisine path in the description block, marked `no-print`, linked to the
  recipe list filtered by it; its tags follow, A to Z, each linked to the list
  filtered by that tag.

Every route that changes a global row checks `is_staff`, and its tests use the
`other_user` fixture to show a signed-in non-staff user is refused and nothing
is written.
