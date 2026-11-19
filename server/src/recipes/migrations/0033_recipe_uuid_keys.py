"""Recipes get UUID keys, so a client can name a recipe before it saves (#156).

`AlterField` alone is not enough on SQLite: it copies each integer id into the
new text column as its decimal text, so recipe 10 would be stored as `10`, which
no UUID matches, and no recipe would load. So the ids, and every column that
points at them, are rewritten as the 32-digit hex Django stores a UUID as:
recipe 10 becomes `00000000-0000-0000-0000-00000000000a`. Numbers sort in the
same order as their hex, and new ids are version 7, so ordering by id is still
ordering by age.

Going back, a numbered recipe gets its number again, and the recipes made since
get the numbers after the highest one, oldest first.
"""

import uuid

from django.db import migrations, models

# Each column holding a recipe's id: the key, then the foreign keys to it.
_COLUMNS = [
    ("recipes_recipe", "id"),
    ("recipes_step", "recipe_id"),
    ("recipes_ingredientgroup", "recipe_id"),
    ("recipes_tag_recipe", "recipe_id"),
]
_UUID_HEX_LENGTH = 32
_LARGEST_NUMBER = 2**63 - 1  # SQLite's largest integer


def numbers_to_hex(apps, schema_editor):
    """Rewrite each copied decimal id as 32-digit hex."""
    with schema_editor.connection.cursor() as cursor:
        for table, column in _COLUMNS:
            cursor.execute(
                f"UPDATE {table} SET {column} = printf('%032x', CAST({column} AS INTEGER)) "
                f"WHERE length({column}) < {_UUID_HEX_LENGTH}"
            )


def hex_to_numbers(apps, schema_editor):
    """Give every recipe an integer id again, keeping a number it had before."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id FROM recipes_recipe ORDER BY id")
        ids = [uuid.UUID(row[0]) for row in cursor.fetchall()]
        kept = [i.int for i in ids if i.int <= _LARGEST_NUMBER]
        following = iter(range(max(kept, default=0) + 1, _LARGEST_NUMBER))
        for old in ids:
            number = old.int if old.int <= _LARGEST_NUMBER else next(following)
            for table, column in _COLUMNS:
                cursor.execute(
                    f"UPDATE {table} SET {column} = %s WHERE {column} = %s", [number, old.hex]
                )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0032_private_units"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recipe",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid7, editable=False, primary_key=True, serialize=False
            ),
        ),
        migrations.RunPython(numbers_to_hex, hex_to_numbers),
    ]
