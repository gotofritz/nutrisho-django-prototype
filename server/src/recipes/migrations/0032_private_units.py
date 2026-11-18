"""Units become a shared vocabulary: global ones plus each user's own (#154).

Every existing unit stays global. Going back, the units are one global list
again, so a private unit's rows keep its name as `legacy_unit` text (as before
#67) and the private units go.
"""

import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


def private_units_to_legacy_text(apps, schema_editor):
    """Write each private unit's name into its rows' `legacy_unit`, then delete it."""
    unit_model = apps.get_model("recipes", "Unit")
    row_model = apps.get_model("recipes", "IngredientInRecipe")
    for unit in unit_model.objects.filter(owner__isnull=False):
        row_model.objects.filter(unit=unit).update(unit=None, legacy_unit=unit.name)
    unit_model.objects.filter(owner__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0031_api_token"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="unit",
            name="unit_name_ci_unique",
        ),
        migrations.AddField(
            model_name="unit",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="private_units",
                to=settings.AUTH_USER_MODEL,
                verbose_name="private to this user; blank means global (staff-curated)",
            ),
        ),
        migrations.AlterField(
            model_name="unit",
            name="dimension",
            field=models.CharField(
                blank=True,
                choices=[("mass", "Mass"), ("volume", "Volume"), ("count", "Count")],
                default="",
                max_length=8,
                verbose_name="blank only on a private unit",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                condition=models.Q(("owner__isnull", True)),
                name="unit_name_ci_unique",
                violation_error_message="That unit already exists.",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("owner"),
                name="unit_name_ci_unique_per_owner",
                violation_error_message="You already have that unit.",
            ),
        ),
        # Last, so that it runs first going back, before the global constraint.
        migrations.RunPython(migrations.RunPython.noop, private_units_to_legacy_text),
    ]
