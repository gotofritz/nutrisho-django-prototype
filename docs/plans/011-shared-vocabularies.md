# Plan 011: Shared Vocabularies

## Status: Draft — PR 1 in progress, open questions below

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
   of other users into it (repointing both FKs, as merge does). Open question:
   whether non-staff get a version of the tool scoped to their own private
   ingredients. Must land before plan 008 (aliases), whose aliases are then
   global and staff-defined.
3. **Global and private tags.** `Tag.owner`, same constraints; a way to add and
   remove tags in the recipe editor (there is none today, only Django admin).
   A recipe can carry global tags and its owner's private tags, never another
   user's.
4. **Curated cuisine list.** Draft the list for review first. Proposed shape:
   two levels via `parent = FK("self")` (Italian › Sicilian), so filtering by
   Italian finds Sicilian too. Loaded by a data migration; existing cuisines
   mapped onto the list; `resolve_cuisine` stops creating on a miss and the
   editor validates against the list.

## Open questions

- Cuisine list: two levels (recommended) or flat?
- Should non-staff users get a clean-up tool for their own private ingredients?
- Sources: stay global, or become private per user?
