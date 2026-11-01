# Plan 011: Shared Vocabularies

## Status: Done — PRs 1-4 shipped

Tracks [issue #46](https://github.com/gotofritz/nutrisho-django-prototype/issues/46).

## Goal

Make the global lookup tables safe with more than one account. Recipes are
owner-scoped, but `Ingredient`, `Tag`, `Cuisine` and `Source` are global, so
any account could rewrite every user's ingredients. Decided with the owner:

- Editing existing base ingredients (`onion`) is limited to staff.
- Users can still add ingredients staff have never heard of. These stay
  **private to the user who added them until staff promote them** to global.
- Tags are both global (staff-curated) and per-user.
- Cuisines are one global list, curated up front; users cannot add to it.

## Pattern

`Ingredient` and `Tag` get `owner = FK(User, null=True, on_delete=CASCADE)`.
`NULL` means global; a value means private to that user. Existing rows migrate
as global. Uniqueness becomes two partial constraints:
`UniqueConstraint(Lower(name), condition=Q(owner__isnull=True))` for globals and
`UniqueConstraint(Lower(name), "owner")` for private rows. `Cuisine` gets no
owner.

## PRs

1. **Lock the clean-up tool to staff** (closes #46). `htmx_staff_required` on
   every `ingredients/manage/` route, HTMX-aware 403, tests with `other_user`
   on every route, decision recorded in `docs/initial-context.md`.
2. **Private ingredients + Promote.** `Ingredient.owner`; `resolve_ingredient`
   resolves global, then the user's own, then creates a private row; the
   datalist shows global plus own. Staff get a Promote action in the clean-up
   tool that makes a private row global and merges any same-named private rows
   of other users into it (repointing both FKs, as merge does). A private row
   may only replace ingredients in its owner's recipes (`IngredientScopeError`).
   A version of the tool for non-staff, scoped to their own private
   ingredients, is backlog (#93). Must land before plan 008 (aliases), whose
   aliases are then global and staff-defined.
3. **Global and private tags.** `Tag.owner`, same constraints; tags are edited
   on the metadata form as comma-separated names (before this, only Django
   admin could). A recipe can carry global tags and its owner's private tags,
   never another user's. Global tags are curated in Django admin; a Promote
   action for tags can follow if private tags need it.
4. **Curated cuisine list.** Three levels, `area.region.subregion`, via
   `parent = FK("self")`; a recipe may point at any depth (`middle east`,
   `med.italy`, `med.italy.sicily`). Areas: `eu`, `med`, `middle east`,
   `africa`, `asia` (with the Pacific islands), `south asia`, `anglo` (US, UK,
   Ireland, Canada, Australia, New Zealand) and `latin` (the rest of the
   Americas). `fusion` and `modern` are global tags rather than cuisines: the
   cuisine records where the cook is based. Seeded by migration 0021, which
   folds existing flat cuisines in; the editor only picks from the tree; staff
   edit it in Django admin.

## Follow-ups

- Users' own clean-up tool for private ingredients: #93 (backlog).
- Sources stay global; revisit if they need to be per user.
- Filtering recipes by a cuisine node and everything under it, once there is
  a recipe filter to put it in.
