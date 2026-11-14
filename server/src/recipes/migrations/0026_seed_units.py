"""Seed the unit vocabulary and its aliases (#67).

A starting list of the units recipes use; staff edit it in Django admin
afterwards. It lives here rather than in a data file so this migration always
does the same thing. Abbreviations are invariant (`200 g`), so their plural is
their name; words inflect by the rule (`cup` → `cups`, `leaf` → `leaves`), and
the plural of a unit or of an alias resolves without an alias of its own.

Existing values are not touched: `normalise_units` reviews and moves them.
"""

from django.db import migrations

# name -> (dimension, plural override, aliases)
UNITS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # mass
    "mg": ("mass", "mg", ("milligram", "milligramme", "mgs")),
    "g": ("mass", "g", ("gram", "gramme", "gr", "gm", "grm")),
    "kg": ("mass", "kg", ("kilogram", "kilogramme", "kilo", "kilos", "kgs")),
    "oz": ("mass", "oz", ("ounce", "ozs")),
    "lb": ("mass", "lb", ("pound", "lbs")),
    # volume
    "ml": ("volume", "ml", ("millilitre", "milliliter", "mls")),
    "cl": ("volume", "cl", ("centilitre", "centiliter")),
    "dl": ("volume", "dl", ("decilitre", "deciliter")),
    "l": ("volume", "l", ("litre", "liter", "ltr", "lt")),
    "tsp": ("volume", "tsp", ("teaspoon", "tsps", "tspn")),
    "tbsp": ("volume", "tbsp", ("tablespoon", "tbs", "tbl", "tblsp", "tbsps", "tbspn")),
    "fl oz": ("volume", "fl oz", ("fluid ounce", "floz", "fl. oz")),
    "cup": ("volume", "", ()),
    "pint": ("volume", "", ("pt",)),
    # count
    "piece": ("count", "", ("pc", "pcs")),
    "clove": ("count", "", ()),
    "sprig": ("count", "", ()),
    "slice": ("count", "", ()),
    "bunch": ("count", "", ()),
    "handful": ("count", "", ()),
    "pinch": ("count", "", ()),
    "dash": ("count", "", ()),
    "drop": ("count", "", ()),
    "stick": ("count", "", ()),
    "stalk": ("count", "", ()),
    "leaf": ("count", "", ()),
    "head": ("count", "", ()),
    "sheet": ("count", "", ()),
    "knob": ("count", "", ()),
    "rasher": ("count", "", ()),
    "fillet": ("count", "", ()),
    "tin": ("count", "", ("can",)),
    "jar": ("count", "", ()),
    "packet": ("count", "", ("pack", "pkt")),
    "sachet": ("count", "", ()),
}


def seed(apps, schema_editor):
    """Create every unit and alias that is not there yet."""
    unit_model = apps.get_model("recipes", "Unit")
    alias_model = apps.get_model("recipes", "UnitAlias")
    for name, (dimension, plural_name, aliases) in UNITS.items():
        unit, _ = unit_model.objects.get_or_create(
            name=name, defaults={"dimension": dimension, "plural_name": plural_name}
        )
        for alias in aliases:
            alias_model.objects.get_or_create(alias_name=alias, defaults={"unit": unit})


def unseed(apps, schema_editor):
    """Remove the seeded units that no recipe uses; their aliases cascade."""
    unit_model = apps.get_model("recipes", "Unit")
    used = apps.get_model("recipes", "IngredientInRecipe").objects.values("unit")
    unit_model.objects.filter(name__in=UNITS).exclude(pk__in=used).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0025_unit_vocabulary"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
