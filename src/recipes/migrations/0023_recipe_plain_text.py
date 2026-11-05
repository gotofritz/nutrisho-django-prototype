"""Store the tag-free text of recipe names and descriptions (#32).

Since #17 a title can hold inline tags, so `Foo` and `<u>Foo</u>` were two
names, and a search for `u` matched every underlined title. `plain_name` and
`plain_description` hold the text a reader sees (`Recipe.save()` keeps them
current); search reads them, and the per-owner name rule moves onto
`plain_name`.

An owner may already have two names that differ only by markup, and adding
the index on top of them would fail with a bare `UNIQUE constraint failed`.
The pre-flight check names them instead. It never edits data: which title to
keep is the owner's call.
"""

from collections import defaultdict

from django.conf import settings
from django.core.management.base import CommandError
from django.db import migrations, models

from recipes.utils.plain_text import plain_text


def reject_markup_only_clashes(apps, schema_editor):
    """Abort with an actionable message if one owner's names read the same."""
    Recipe = apps.get_model("recipes", "Recipe")
    names: dict[tuple[int, str], list[str]] = defaultdict(list)
    for owner_id, name in Recipe.objects.values_list("owner_id", "recipe_name"):
        names[(owner_id, plain_text(name))].append(name)
    groups = sorted(", ".join(sorted(group)) for group in names.values() if len(group) > 1)
    if not groups:
        return
    listed = "\n  ".join(groups)
    raise CommandError(
        "Cannot make recipe names unique by their text: each line below is one "
        f"user's recipes whose names differ only by markup.\n\n  {listed}\n\n"
        "Rename or delete all but one of each (the app runs fine without this "
        "migration), then re-run migrate."
    )


def backfill_plain_text(apps, schema_editor):
    """Fill both plain columns from the typed ones."""
    Recipe = apps.get_model("recipes", "Recipe")
    rows = list(Recipe.objects.only("recipe_name", "short_description"))
    for row in rows:
        row.plain_name = plain_text(row.recipe_name)
        row.plain_description = plain_text(row.short_description)
    Recipe.objects.bulk_update(rows, ["plain_name", "plain_description"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0022_long_prose_text_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(reject_markup_only_clashes, migrations.RunPython.noop),
        migrations.AddField(
            model_name="recipe",
            name="plain_description",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                verbose_name="short_description without inline tags",
            ),
        ),
        migrations.AddField(
            model_name="recipe",
            name="plain_name",
            field=models.CharField(
                default="",
                editable=False,
                max_length=200,
                verbose_name="recipe_name without inline tags",
            ),
        ),
        migrations.RunPython(backfill_plain_text, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="recipe",
            name="recipes_recipe_unique_name_per_owner",
        ),
        migrations.AddConstraint(
            model_name="recipe",
            constraint=models.UniqueConstraint(
                fields=("owner", "plain_name"),
                name="recipes_recipe_unique_plain_name_per_owner",
            ),
        ),
    ]
