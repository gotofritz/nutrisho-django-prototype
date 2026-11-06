# Pluralisation (`recipes/utils/pluralise.py`, `Ingredient.plural`)

A plural is the display form of **one** ingredient at a quantity other than 1,
never a second row: `1 onion` and `2 onions` are the same `Ingredient`. It is
therefore presentation, computed on render, and nothing persists it — the
database always holds the canonical singular.

`recipes/utils/pluralise.py` holds the rule as a pure function with no Django
imports, so it is testable on its own. It inflects the **last word only**
(`spring onion` → `spring onions`) and leaves names already ending in `-s`
alone, since food nouns ending in `-s` are nearly always already plural or mass
(`oats`, `chives`, `asparagus`). `Ingredient.plural` layers the `plural_name`
override on top: blank derives from the rule, a value wins verbatim, and a value
equal to the singular makes the noun invariant (`broccoli`, `fish`). The
override is what covers the irregulars the rule deliberately does not chase, and
it is editable in the clean-up tool's Edit panel.

Two conditions gate the swap, both in `display_ingredient_name`: the quantity is
recorded and is not 1, **and** `unit` is empty. The unit check is what keeps mass
nouns safe — `200 g onion` must never become `200 g onions`. A page scaled with
`?servings=N` decides on the displayed quantity instead (`ingredient_name_at`), so
doubling 1 onion reads "2 onions".
