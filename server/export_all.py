"""Export every user's recipes, for comparing a database before and after migration 0033.

Run in server/ with `uv run python manage.py shell < export_all.py`, with
OUT set to the file to write. The recipe ids go to OUT.ids, so OUT itself
should be identical before and after the migration.
"""

import json
import os

from django.contrib.auth.models import User

from recipes.models import Recipe
from recipes.services.recipe_export import export_recipes

out = os.environ["OUT"]
documents = {}
for user in User.objects.order_by("username"):
    document = export_recipes(owner=user)
    document.pop("exported_at")
    documents[user.username] = document
with open(out, "w") as f:
    json.dump(documents, f, indent=1, sort_keys=True)
ids = Recipe.objects.order_by("id").values_list("id", flat=True)
with open(out + ".ids", "w") as f:
    f.write("\n".join(str(i) for i in ids) + "\n")
print(f"{sum(len(d['recipes']) for d in documents.values())} recipes written to {out}")
