# Ingredient Clean-up Tool (`recipes/services/`, `recipes/views/ingredient_admin.py`)

A self-contained subsystem under `/recipes/ingredients/manage/`, separate from both
the per-recipe inline editor and Django admin. `Ingredient` rows are shared by every
recipe, so this is where duplicates and spelling variants get edited, deleted or
merged. Staff-only (see [shared vocabularies](shared-vocabularies.md)); the `manage/` URL prefix keeps it clear
of the per-recipe `<recipe_id>/ingredients/...` routes.

The UI is four Miller columns — actions, ingredients, matching recipes, recipe
preview. Clicking an action collapses columns 2-4 into a full-width workspace panel
and turns the clicked button into Cancel. Column 4 is a fresh inert template, not a
trimmed `partials/_recipe_content.html`: that one pulls in the navbars and its field
includes carry `hx-get` edit triggers.

Column 4 follows column 3 rather than holding state of its own: every response
that rebuilds the matches rebuilds the preview with it. Exactly one match previews
itself — there is nothing else to pick — and any other count clears the pane, so a
preview can never outlive the matches it came from.

**Services layer.** `recipes/services/ingredient_admin.py` holds pure query and
mutation functions with no HTTP concerns, so the HTMX views stay thin and the
behaviour is testable without a client. Views own request parsing, guards and
partial selection; services own the ORM.

**Typed names resolve case-insensitively.** `recipes/services/name_resolution.py`
is the only place the recipe editor turns a typed ingredient, tag or cuisine name
into a row: `resolve_ingredient` / `resolve_tag` strip the name, match it ignoring
case (keeping the stored spelling) and create it as typed only on a miss;
`find_ingredient` / `find_tag` / `find_cuisine` look up without creating, and
nothing creates a cuisine (see [shared vocabularies](shared-vocabularies.md)). The names carry a
`Lower(...)` unique constraint, so a raw `get_or_create(name=...)` would 500 on
`Onion` when `onion` exists (#34). Ingredient lookups take `owner` (the recipe's
owner) and see only the global list plus that owner's private rows, a global row
winning over a private one of the same name; a miss creates a row **private** to
the owner (plan 011). `suggest_ingredient_names(text, owner=...)` feeds the editor's
autocomplete from the same two sources, so no user ever sees another's private names.

**Resolve on input, store and display canonical (#66, plan 008).** After the
name misses, `find_ingredient` tries, in order: a visible row whose **plural**
(rule or `plural_name` override, ignoring case) is the typed name, so `2 onions`
links the stored `onion`; then an **alias** in `IngredientAlias`, or an alias's
rule plural, which resolves to the alias's canonical row (`eggplant`/`eggplants`
→ `aubergine`). Global rows win over private ones at every step. Aliases are
input-only: no recipe references one, so storage, display and export always
show the canonical name. They are global and staff-defined (plan 011): an
alias's canonical is always a global row, and a name is either an ingredient or
an alias, never both — `IngredientAlias.clean` and `IngredientForm` refuse a
clash, and the services below fold any same-named rows in before adding one.

**Selection lives in the request.** Checkboxes post `ingredient_ids`; every
re-rendered partial echoes them back. There is no client-side store: a change or a
search refreshes its own column and swaps the other affected fragments out of
band, so header counts, the tri-state select-all box and the enabled/disabled
state of Edit/Delete/Merge are all server-rendered. The column-2 header's
select-all box is the subsystem's only JavaScript: `indeterminate` is a DOM
property with no HTML attribute, so the dashed state cannot be rendered. The box
carries `data-indeterminate`, and an `htmx.onLoad` handler in `app.js` sets the
property from it on page load and after every swap, out-of-band ones included.
The row checkboxes trigger their column with `hx-trigger="change
target:.ingredient-pick"`, so a tick of the select-all box inside the same
column fires only its own request. The workspace carries the selection as
hidden inputs, since it replaces the column holding the checkboxes. `hx-include`
must name the inputs themselves (`.ingredient-pick:checked`, `.workspace-pick`) —
pointing it at a container element sends nothing.

**Repointing rule (important).** `IngredientInRecipe.ingredient` *and* `.substitute`
are both `on_delete=PROTECT`. No ingredient can be deleted while either FK
references it, so `delete_ingredients` and `merge_ingredients` repoint **both** onto
the replacement or survivor inside one transaction before deleting. Repointing an FK
leaves `index_in_sequence` alone, so recipe ordering is unaffected and
`utils/sequencing.py` is not involved. A delete with no usable replacement answers
422 and writes nothing rather than letting PROTECT surface as a 500. A recipe that
already held the survivor and a victim keeps both rows; de-duplicating a group is
out of scope.

**Orphans.** `search_ingredients(query, unused_only=True)` lists ingredients no
`IngredientInRecipe` references as either ingredient or substitute — the rows that
can be deleted outright, since neither FK PROTECTs them. Nothing prunes them
automatically: renames (`get_or_create` keeps the old row), last-use deletions and
imports all leave orphans, and deciding they are junk is the owner's call.

**Saving an edit.** The Edit workspace holds one panel per selected ingredient,
each posting itself. Saving the only panel closes the workspace (via `HX-Retarget`
onto `#columns`, since the form targets itself) — re-rendering a lone panel looks
like nothing happened. Saving one of several marks it and leaves the rest open,
because closing would discard whatever is typed in them; the panels carry the
selection so the view can tell the two cases apart.

**Owner scoping.** Recipes are owner-scoped and column 3 stays that way, but
the tool works on every ingredient, global or private: the delete confirmation
counts affected recipes across all owners, since a delete reaches recipes the
current user cannot see. Column 2 and the merge chooser badge a private row with
its owner (`_owner_badge.html`). A private row may only replace ingredients in
its own owner's recipes: `delete_ingredients` (and so every merge) raises
`IngredientScopeError`, a 422 with nothing written, rather than repoint another
user's recipe onto a row that user cannot see.

**Promote** is the fifth column-1 action (plan 011). `promote_ingredients` makes
each selected private row global, or merges it into the global row that already
has its name, then merges every other user's private row of that name into the
result, so all their recipes share it. The confirmation lists what each row
will fold in; the promoted rows stay ticked. The **Private only** filter
narrows column 2 to promotion candidates.

**Staff only (#46).** Every route is wrapped in `htmx_staff_required`
(`recipes/views/_auth.py`): anonymous users go to the login page through the
login middleware, a signed-in user who is not `is_staff` gets 403. An htmx request gets a short
plain-text 403, which the htmx config never swaps, so the global banner reports
it; a full-page visit raises `PermissionDenied` and Django renders `403.html`.
The home page shows the "Manage ingredients" link to staff only.

**Canonical names.** British spelling wins, enforced by
`UniqueConstraint(Lower("ingredient_name"), name="ingredient_name_ci_unique")`
(migration 0013; since migration 0018 it covers global rows only, and
`ingredient_name_ci_unique_per_owner` does the same within each user's private
rows) and mirrored in `IngredientForm`, which points a clashing rename at
the merge action. Databases predating the constraint are cleaned up with the
`find_ingredient_duplicates` command, which lists case-only clashes; merge them
before migrating.

**Three variant classes.** Case (`Onion`/`onion`) is the constraint above.
**Plural** (`onion`/`onions`) is the third: since the plural is a display form,
an `onions` row is bad data, so `find_plural_duplicates` pairs each row with the
row spelling out its `plural`, `search_ingredients(plurals_only=True)` narrows
column 2 to those pairs (composing with the query and the unused filter), and
`find_ingredient_duplicates` reports both classes. Back-filling is a merge in
the tool, never a data migration: picking which row survives is the owner's
call.

**Merge plural** is the fourth column-1 action and the one that fixes such a
pair. `merge_plural_ingredients` repoints recipes exactly as `merge_ingredients`
does, then writes the deleted row's name **verbatim** onto the survivor's
`plural_name` — the point of the action, since a plain merge drops the spelling
and leaves the rule to guess (`chili`/`chilis` would come back as `chilies`).
Verbatim even when the rule agrees, so the plural column visibly shows where the
merged name went; any prior override is overwritten, the merge being the later
and more deliberate statement. `suggest_singular` preselects whichever half
pluralises into the other, falling back to the first. Capped at **exactly two**
selected: with two plural rows there is no way to tell which spelling wins.
`_SELECTION_BOUNDS` carries each action's `(minimum, maximum)`; every other
action is still minimum-only.

**Aliases** (`eggplant` → `aubergine`) cover variants differing by more than case
or number. They are created two ways. (1) **Explicitly**, by the **Alias**
action: exactly one ingredient selected, a workspace panel listing its aliases
with Remove buttons and an add field (`add_alias` / `remove_alias`). A private
ingredient takes no aliases until promoted. (2) **By merge**: `merge_ingredients`
into a global survivor records each victim's name as an alias, skipping names
that already resolve to the survivor (case variants, its plural). Either way,
`add_alias` treats a name that already exists as ingredient rows — anyone's —
as a merge: those rows fold into the canonical through `delete_ingredients`, so
no recipe is stranded. `delete_ingredients` hands a global replacement the
victims' aliases (so Merge, Merge plural, Promote and Delete-with-replacement
never orphan one); without one, aliases cascade with their ingredient. Capturing
an alias when a user picks a canonical for an unknown name during input (plan
008 phase 7) waits for an input flow that asks.

**Column-2 filters.** The views carry them as one typed mapping (`_Filters`:
`query`, `unused_only`, `plurals_only`, `private_only`), forwarded as `**filters` into the
context helpers, so adding a filter does not widen every call site.
