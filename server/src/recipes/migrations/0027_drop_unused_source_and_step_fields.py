"""Drop the columns no code path writes (#65).

`Source` (and `Recipe.source`), `Step.duration` and `Step.extra_info` were
never set by the editor, the old YAML import or any command; a recipe's source
lives in `source_instance`. Django admin could still have set them, so the
migration first checks that nothing would be lost, and stops if anything would.
"""

from django.core.management.base import CommandError
from django.db import migrations, models


def refuse_to_drop_data(apps, schema_editor) -> None:
    """Stop before dropping a column that holds data; nothing should."""
    Recipe = apps.get_model("recipes", "Recipe")
    Source = apps.get_model("recipes", "Source")
    Step = apps.get_model("recipes", "Step")
    in_use = {
        "Source rows": Source.objects.exists(),
        "Recipe.source": Recipe.objects.filter(source__isnull=False).exists(),
        "Step.duration": Step.objects.filter(duration__isnull=False).exists(),
        "Step.extra_info": Step.objects.exclude(extra_info="").exists(),
    }
    held = [name for name, used in in_use.items() if used]
    if held:
        msg = (
            f"Migration 0027 drops columns that hold data here: {', '.join(held)}. "
            "Copy what is worth keeping (into source_instance or step_text) first."
        )
        raise CommandError(msg)


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0026_seed_units"),
    ]

    operations = [
        migrations.RunPython(refuse_to_drop_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="recipe",
            name="source",
        ),
        migrations.RemoveField(
            model_name="step",
            name="duration",
        ),
        migrations.RemoveField(
            model_name="step",
            name="extra_info",
        ),
        migrations.AlterField(
            model_name="recipe",
            name="source_instance",
            field=models.CharField(
                blank=True,
                help_text="A book and page, or a web address.",
                max_length=200,
                verbose_name="source",
            ),
        ),
        migrations.DeleteModel(
            name="Source",
        ),
    ]
