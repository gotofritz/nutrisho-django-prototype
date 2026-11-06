## v0.3.0 (2026-11-06)

### BREAKING CHANGE

- recipes can no longer be imported from or exported to YAML; `poe filldb` and `poe export` are gone.

### Feat

- search and filter the recipe list from every page (#32) (#116)
- add log-out and a proper login page (#59) (#115)
- turn cuisines into a curated global tree with a staff tool (#46) (#96)
- add private tags and edit tags on the metadata form (#46) (#95)
- keep users' new ingredients private until staff promote them (#46) (#94)
- show a banner when an htmx request fails (#37) (#91)
- scale recipes at display time instead of rewriting quantities (#36) (#89)
- log errors to stderr, add /healthz and optional Sentry (#43) (#86)
- **db**: configure SQLite for concurrent writes (#38) (#83)
- **steps**: merge, split at cursor and bulk delete steps (#18) (#33)
- accept basic html in recipe title and blurb (#17) (#31)
- remove YAML machinery and add a backup command (#27) (#29)
- **010**: step titles (#20) (#26)
- pluralise ingredient names at display time (#24) (#25)
- make recipe servings mandatory (#22)
- YAML export and servings (plan 003) (#9)

### Fix

- resolve a typed plural to the existing singular (#66) (#119)
- confirm before deleting a non-empty ingredient group (#51) (#113)
- require login by default on every route (#48) (#112)
- manage focus and announce changes after HTMX swaps (#61) (#101)
- keep text after a stray "<" in the HTML sanitiser (#50) (#99)
- make long prose fields TextFields (#49) (#97)
- restrict the ingredient clean-up tool to staff (#46) (#92)
- copy every field when duplicating a recipe (#35) (#88)
- replace user bootstrap with an env-driven owner command (#39) (#85)
- resolve ingredient and cuisine names case-insensitively (#34) (#82)
- **ci**: repair README badges and use a fast test password hasher (#30)
- remove tickboxes in css print (#16)
- wire inline editing in detail page; fix list delete HTMX swap (#13)
- add fix_duplicate_sequences command for migration 0007 blocker (#12)
