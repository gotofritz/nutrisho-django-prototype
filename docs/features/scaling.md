# Scaling (`recipes/utils/scaling.py`, `recipes/services/recipe_scaling.py`)

Scaling is presentation, not a write (#36). `GET /recipes/<id>/?servings=N` shows
the recipe at N servings: the view parses N (`parse_servings`: a whole number from
1 to 32767, anything else is ignored and the stored recipe is shown), turns it into
an exact `Fraction` of the stored servings (`scale_factor`, None when N equals the
stored count) and the template scales each quantity on render with the
`scaled_quantity` filter. A quantity is multiplied before it is divided and every
view starts from the stored value, so nothing drifts (÷3 then ×3 is still `1`).
Display rounding is two decimals half up, but a non-zero amount below 0.01 keeps two
significant digits instead of showing as `0`. The URL is the state, so a scaled
page is bookmarkable and printable.

A scaled page renders `_scaled_ingredients.html`, a read-only list, instead of the
inline editors: those would show and save stored quantities, and the servings
field would be ambiguous. The "Serves N" line is followed by "scaled from M, not
saved · Reset"; Reset links to the unscaled page. Pluralisation follows the
displayed quantity (`ingredient_name_at`), so 1 onion doubled reads "2 onions".

The scale panel asks for a serving count rather than a factor. "Show" is a plain
GET to the recipe page; "Save as scaled copy" POSTs to `scale/copy/`, which calls
`save_scaled_copy`: `duplicate_recipe` (#35), then the copy's servings are set to N
and its quantities, still equal to the original's, are scaled and stored at the
column's two decimals. A quantity that would overflow `DecimalField(7, 2)` or round
a non-zero amount to `0.00` raises `ScaleError` inside the transaction, so nothing
is created and the panel shows the error (422). Nothing writes scaled values onto
an existing recipe.
