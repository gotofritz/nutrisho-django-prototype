"""Tests for batch_load_yaml_recipes management command."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from django.contrib.auth.models import User as DjangoUser
from django.core.management import call_command
from django.core.management.base import CommandError

from recipes.management.commands.batch_load_yaml_recipes import _normalize_quantity
from recipes.models import Recipe


def make_yaml(
    title: str = "Test Soup",
    serves: int | None = 4,
    description: str = "A soup",
    directions: list[str] | None = None,
    groups: list | None = None,
) -> dict:
    """Build a minimal YAML dict matching the schema."""
    if directions is None:
        directions = ["Boil water", "Add ingredients"]
    if groups is None:
        groups = [
            {
                "name": None,
                "ingredient": [
                    {
                        "name": "salt",
                        "measurement": "tsp",
                        "preparation": None,
                        "quantity": "1.00",
                    }
                ],
            }
        ]

    ingredients: dict = {"group": groups}
    if serves is not None:
        ingredients["serves"] = serves

    return {
        "title": title,
        "description": description,
        "cuisine": None,
        "source": None,
        "tags": [],
        "directions": {"step": directions},
        "ingredients": ingredients,
    }


@pytest.fixture
def gotofritz(db):
    """Create the gotofritz user required by batch_load_yaml_recipes."""
    existing = DjangoUser.objects.filter(username="gotofritz").first()
    if existing is not None:
        return existing
    return DjangoUser.objects.create_user(username="gotofritz", password="x")


def write_yaml(tmp_path: Path, data: dict, filename: str = "recipe.yml") -> Path:
    """Write a dict to a YAML file and return the path."""
    p = tmp_path / filename
    with p.open("w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return p


@pytest.mark.django_db
def test_serves_4_sets_servings(gotofritz, tmp_path):
    """YAML with serves: 4 → Recipe.servings == 4."""
    write_yaml(tmp_path, make_yaml(title="Soup A", serves=4), "soup_a.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Soup A")
    assert recipe.servings == 4


@pytest.mark.django_db
@pytest.mark.parametrize("bad_serves", [0, -1, "abc", "0"])
def test_invalid_serves_raises_command_error(gotofritz, tmp_path, bad_serves):
    """serves: 0, negative, or non-numeric string → CommandError, nothing written to DB."""
    from django.core.management.base import CommandError

    data = make_yaml(title="Bad Serves")
    data["ingredients"]["serves"] = bad_serves
    write_yaml(tmp_path, data, "bad.yml")
    with pytest.raises(CommandError):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    assert not Recipe.objects.filter(recipe_name="Bad Serves").exists()


@pytest.mark.django_db
def test_serves_bool_true_is_rejected(gotofritz, tmp_path):
    """serves: true (YAML boolean) is rejected as invalid — int(True)==1 would silently pass."""
    from django.core.management.base import CommandError

    data = make_yaml(title="Bool Serves")
    data["ingredients"]["serves"] = True  # YAML bool, not int
    write_yaml(tmp_path, data, "bool_serves.yml")
    with pytest.raises(CommandError, match="bool"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")


@pytest.mark.django_db
def test_serves_1_sets_servings_1(gotofritz, tmp_path):
    """YAML with serves: 1 → Recipe.servings == 1."""
    write_yaml(tmp_path, make_yaml(title="Soup B", serves=1), "soup_b.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Soup B")
    assert recipe.servings == 1


@pytest.mark.django_db
def test_missing_serves_raises_command_error(gotofritz, tmp_path):
    """YAML missing serves key → CommandError; servings is mandatory, never guessed."""
    write_yaml(tmp_path, make_yaml(title="Soup C", serves=None), "soup_c.yml")
    with pytest.raises(CommandError, match="serves"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    assert not Recipe.objects.filter(recipe_name="Soup C").exists()


@pytest.mark.django_db
def test_null_serves_raises_command_error(gotofritz, tmp_path):
    """YAML with an explicit `serves:` but no value → CommandError, not a NULL row."""
    data = make_yaml(title="Soup D")
    data["ingredients"]["serves"] = None
    write_yaml(tmp_path, data, "soup_d.yml")
    with pytest.raises(CommandError, match="serves"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    assert not Recipe.objects.filter(recipe_name="Soup D").exists()


@pytest.mark.django_db
def test_dry_run_no_db_changes(gotofritz, tmp_path):
    """--dry-run writes nothing to DB, including cuisine rows."""
    from recipes.models import Cuisine

    data = make_yaml(title="Soup F", serves=4)
    data["cuisine"] = "italian"
    write_yaml(tmp_path, data, "soup_f.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)
    assert not Recipe.objects.filter(recipe_name="Soup F").exists()
    assert not Cuisine.objects.filter(cuisine="italian").exists()


@pytest.mark.django_db
def test_failed_import_does_not_corrupt_existing_recipe(gotofritz, tmp_path):
    """Exception mid-import leaves the original recipe intact (transaction rollback)."""
    good = make_yaml(title="Safe Recipe", serves=2)
    p = write_yaml(tmp_path, good, "safe.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    original = Recipe.objects.get(recipe_name="Safe Recipe")
    original_pk = original.pk

    # Corrupt YAML: quantity is not a valid decimal
    bad = make_yaml(title="Safe Recipe", serves=2)
    bad["ingredients"]["group"][0]["ingredient"][0]["quantity"] = "not-a-number"
    write_yaml(tmp_path, bad, "safe.yml")

    with pytest.raises(Exception):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")

    # Original must still exist with original pk
    assert Recipe.objects.filter(pk=original_pk).exists()
    assert Recipe.objects.get(pk=original_pk).recipe_name == "Safe Recipe"


@pytest.mark.django_db
def test_dry_run_does_not_write_recipes(tmp_path, user):
    """--dry-run must not persist any recipes to the database."""
    write_yaml(tmp_path, make_yaml(title="Ghost Soup"), "ghost.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)
    assert not Recipe.objects.filter(recipe_name="Ghost Soup").exists()


@pytest.mark.django_db
def test_unknown_user_raises_error(tmp_path):
    """--user with a non-existent username must raise CommandError before any DB writes."""
    from django.core.management.base import CommandError

    write_yaml(tmp_path, make_yaml(title="Ghost Soup"), "ghost.yml")
    with pytest.raises(CommandError, match="not found"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="nobody", dry_run=True)


@pytest.mark.django_db
def test_dry_run_catches_invalid_quantity(user, tmp_path):
    """--dry-run raises CommandError for invalid decimal quantity (full preflight)."""
    from django.core.management.base import CommandError

    bad = make_yaml(title="Bad Qty Soup")
    bad["ingredients"]["group"][0]["ingredient"][0]["quantity"] = "not-a-number"
    write_yaml(tmp_path, bad, "bad_qty.yml")

    with pytest.raises(CommandError, match="quantity"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)


@pytest.mark.django_db
def test_dry_run_catches_zero_denominator_quantity(user, tmp_path):
    """Fraction 1/0 must raise CommandError, not an unhandled DivisionByZero traceback."""
    from django.core.management.base import CommandError

    bad = make_yaml(title="Zero Denom Soup")
    bad["ingredients"]["group"][0]["ingredient"][0]["quantity"] = "1/0"
    write_yaml(tmp_path, bad, "zero_denom.yml")

    with pytest.raises(CommandError, match="quantity"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)


@pytest.mark.django_db
def test_dry_run_catches_mixed_zero_denominator(user, tmp_path):
    """Mixed fraction 1 1/0 must also raise CommandError."""
    from django.core.management.base import CommandError

    bad = make_yaml(title="Mixed Zero Denom Soup")
    bad["ingredients"]["group"][0]["ingredient"][0]["quantity"] = "1 1/0"
    write_yaml(tmp_path, bad, "mixed_zero_denom.yml")

    with pytest.raises(CommandError, match="quantity"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)


@pytest.mark.django_db
def test_dry_run_catches_invalid_serves(user, tmp_path):
    """--dry-run already raises CommandError for invalid serves values."""
    from django.core.management.base import CommandError

    bad = make_yaml(title="Bad Serves Soup", serves=0)
    write_yaml(tmp_path, bad, "bad_serves.yml")

    with pytest.raises(CommandError):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)


@pytest.mark.django_db
def test_import_records_source_filename(gotofritz, tmp_path):
    """Importing a YAML file stores its filename on the Recipe."""
    p = write_yaml(tmp_path, make_yaml(title="Filename Test"), "my_recipe_file.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Filename Test")
    assert recipe.yaml_filename == "my_recipe_file.yml"


@pytest.mark.django_db
def test_shared_tag_not_removed_from_first_recipe(gotofritz, tmp_path):
    """Importing a second recipe with a shared tag does not remove it from the first."""
    from recipes.models import Tag

    data_a = make_yaml(title="Recipe A")
    data_a["tags"] = ["vegetarian"]
    write_yaml(tmp_path, data_a, "a.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path / "a.yml"), user="gotofritz")

    data_b = make_yaml(title="Recipe B")
    data_b["tags"] = ["vegetarian"]
    write_yaml(tmp_path, data_b, "b.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path / "b.yml"), user="gotofritz")

    tag = Tag.objects.get(tag="vegetarian")
    tagged_names = set(tag.recipe.values_list("recipe_name", flat=True))  # ty: ignore[unresolved-attribute]
    assert "Recipe A" in tagged_names
    assert "Recipe B" in tagged_names


@pytest.mark.django_db
def test_import_reads_utf8_encoding(gotofritz, tmp_path):
    """Input files opened as UTF-8 so non-ASCII titles/descriptions survive import."""
    data = make_yaml(title="Soupe à l'oignon", description="Délicieuse recette française")
    p = tmp_path / "soupe.yml"
    # Write raw UTF-8 bytes to guarantee encoding
    import yaml as _yaml

    p.write_bytes(_yaml.dump(data, allow_unicode=True).encode("utf-8"))
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Soupe à l'oignon")
    assert recipe.short_description == "Délicieuse recette française"


@pytest.mark.django_db
def test_recipe_servings_zero_fails_validation(user):
    """servings=0 fails full_clean — must be None or >= 1."""
    from django.core.exceptions import ValidationError

    recipe = Recipe(recipe_name="Zero Serves", owner=user, servings=0)
    with pytest.raises(ValidationError):
        recipe.full_clean()


@pytest.mark.django_db
def test_serves_float_is_rejected(gotofritz, tmp_path):
    """serves: 1.5 must raise CommandError — not silently truncate to 1."""
    from django.core.management.base import CommandError

    data = make_yaml(title="Float Serves")
    data["ingredients"]["serves"] = 1.5
    p = write_yaml(tmp_path, data, "float_serves.yml")
    with pytest.raises(CommandError, match="serves"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    assert not Recipe.objects.filter(recipe_name="Float Serves").exists()


@pytest.mark.django_db
def test_import_always_inserts_never_updates(gotofritz, tmp_path):
    """batch_load is pure-insert: each file creates a new recipe, no dedup or update."""
    p1 = write_yaml(tmp_path, make_yaml(title="Insert Test A", serves=2), "a.yml")
    p2 = write_yaml(tmp_path, make_yaml(title="Insert Test B", serves=4), "b.yml")
    call_command("batch_load_yaml_recipes", str(p1), user="gotofritz")
    call_command("batch_load_yaml_recipes", str(p2), user="gotofritz")
    assert Recipe.objects.filter(recipe_name="Insert Test A").count() == 1
    assert Recipe.objects.filter(recipe_name="Insert Test B").count() == 1
    assert Recipe.objects.count() == 2


@pytest.mark.django_db
def test_import_sanitizes_stored_filename(gotofritz, tmp_path):
    """Reserved chars in source filename are stripped before storing yaml_filename."""
    p = write_yaml(tmp_path, make_yaml(title="Reserved Char Recipe"), "foo!bar.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Reserved Char Recipe")
    assert recipe.yaml_filename == "foobar.yml"


@pytest.mark.django_db
def test_missing_only_skips_when_sanitized_export_already_exists(gotofritz, tmp_path):
    """--missing-only skips recipe when sanitized export file already exists on disk."""
    # Import from filename with reserved char → stored as sanitized name
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    p = write_yaml(src_dir, make_yaml(title="Sanitize Skip Recipe"), "foo!bar.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Pre-populate sanitized export file (simulates a previous export run)
    existing = out_dir / "foobar.yml"
    existing.write_text("placeholder: true\n")

    call_command("export_recipes_to_yaml", str(out_dir), user="gotofritz", missing_only=True)

    # Must not have exported again — stored name is already sanitized, file exists
    assert existing.read_text() == "placeholder: true\n"


@pytest.mark.django_db
@pytest.mark.parametrize("ext", [".yaml", ".YAML", ".YML"])
def test_directory_import_picks_up_non_yml_extensions(gotofritz, tmp_path, ext):
    """Directory scan must include .yaml / .YAML / .YML, not just .yml."""
    title = f"Ext Test {ext}"
    data = make_yaml(title=title)
    p = tmp_path / f"recipe{ext}"
    with p.open("w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    # Add a non-YAML sibling that must be silently ignored
    (tmp_path / "README.md").write_text("# notes\n")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    assert Recipe.objects.filter(recipe_name=title).exists()


@pytest.mark.django_db
def test_directory_import_ignores_non_yaml_files(gotofritz, tmp_path):
    """Non-YAML files in directory (README.md, .gitkeep, etc.) must not crash the importer."""
    (tmp_path / "README.md").write_text("# notes\n")
    (tmp_path / ".gitkeep").write_text("")
    write_yaml(tmp_path, make_yaml(title="Clean Import"), "clean.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    assert Recipe.objects.filter(recipe_name="Clean Import").exists()


@pytest.mark.django_db
def test_dry_run_catches_duplicate_recipe_name(gotofritz, tmp_path):
    """--dry-run raises CommandError when recipe_name already exists in DB."""
    from django.core.management.base import CommandError

    p = write_yaml(tmp_path, make_yaml(title="Dup Name"), "dup.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")  # real insert

    with pytest.raises(CommandError, match="already exist"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz", dry_run=True)


@pytest.mark.django_db
def test_dry_run_catches_duplicate_title_within_batch(user, tmp_path):
    """--dry-run raises CommandError when two files in same invocation share a title."""
    from django.core.management.base import CommandError

    write_yaml(tmp_path, make_yaml(title="Same Name"), "a.yml")
    write_yaml(tmp_path, make_yaml(title="Same Name"), "b.yml")

    with pytest.raises(CommandError, match="Same Name"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz", dry_run=True)


@pytest.mark.django_db
def test_real_run_preflight_catches_duplicate_title_within_batch(gotofritz, tmp_path):
    """Batch with duplicate titles fails before any recipe is written to DB."""
    from django.core.management.base import CommandError

    write_yaml(tmp_path, make_yaml(title="Same Name"), "a.yml")
    write_yaml(tmp_path, make_yaml(title="Same Name"), "b.yml")

    with pytest.raises(CommandError, match="Same Name"):
        call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")

    assert Recipe.objects.filter(recipe_name="Same Name").count() == 0


@pytest.mark.django_db
def test_write_phase_is_atomic_across_batch(gotofritz, tmp_path):
    """Write failure on second file must roll back the entire batch, not just that file."""
    from unittest.mock import patch

    write_yaml(tmp_path, make_yaml(title="Batch Alpha"), "a.yml")
    write_yaml(tmp_path, make_yaml(title="Batch Beta"), "b.yml")

    original_create = Recipe.objects.create
    call_count = 0

    def fail_on_second(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Simulated DB error on second recipe")
        return original_create(**kwargs)

    with patch.object(Recipe.objects, "create", side_effect=fail_on_second):
        with pytest.raises(RuntimeError, match="Simulated DB error"):
            call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")

    # Whole batch must be absent — first recipe must not have been committed
    assert Recipe.objects.filter(recipe_name="Batch Alpha").count() == 0
    assert Recipe.objects.filter(recipe_name="Batch Beta").count() == 0


@pytest.mark.django_db
def test_directory_scan_skips_subdirectories_with_yaml_extension(gotofritz, tmp_path):
    """A subdirectory whose name ends in .yml must be skipped, not crash."""
    subdir = tmp_path / "subrecipes.yml"
    subdir.mkdir()
    write_yaml(tmp_path, make_yaml(title="Real Recipe"), "real.yml")
    call_command("batch_load_yaml_recipes", str(tmp_path), user="gotofritz")
    assert Recipe.objects.filter(recipe_name="Real Recipe").exists()


@pytest.mark.django_db
def test_import_raises_on_yaml_filename_collision_within_batch(gotofritz, tmp_path):
    """Two files with same sanitized basename (case-insensitive) → CommandError before any insert."""
    from django.core.management.base import CommandError

    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    write_yaml(dir_a, make_yaml(title="Recipe Alpha"), "soup.yml")
    write_yaml(dir_b, make_yaml(title="Recipe Beta"), "SOUP.yml")

    with pytest.raises(CommandError, match="[Ff]ilename"):
        call_command(
            "batch_load_yaml_recipes",
            str(dir_a / "soup.yml"),
            str(dir_b / "SOUP.yml"),
            user="gotofritz",
        )

    assert Recipe.objects.count() == 0


@pytest.mark.django_db
def test_import_raises_on_yaml_filename_collision_with_existing_recipe(gotofritz, tmp_path):
    """yaml_filename collision with existing recipe (case-insensitive) → CommandError."""
    from django.core.management.base import CommandError

    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    write_yaml(dir_a, make_yaml(title="Recipe Alpha"), "soup.yml")
    write_yaml(dir_b, make_yaml(title="Recipe Beta"), "SOUP.yml")

    call_command("batch_load_yaml_recipes", str(dir_a / "soup.yml"), user="gotofritz")

    with pytest.raises(CommandError, match="[Ff]ilename"):
        call_command("batch_load_yaml_recipes", str(dir_b / "SOUP.yml"), user="gotofritz")


@pytest.mark.django_db
def test_import_detects_collision_with_legacy_unsanitized_yaml_filename(gotofritz, tmp_path):
    """Unsanitized yaml_filename in DB (legacy/manual) is sanitized before collision check."""
    from django.contrib.auth.models import User as DjangoUser
    from django.core.management.base import CommandError

    user = DjangoUser.objects.get(username="gotofritz")
    # Create recipe then bypass save() to plant an unsanitized filename (simulates legacy row)
    recipe = Recipe.objects.create(recipe_name="Legacy Recipe", owner=user, yaml_filename="")
    Recipe.objects.filter(pk=recipe.pk).update(yaml_filename="foo!bar.yml")

    p = write_yaml(tmp_path, make_yaml(title="New Recipe"), "foobar.yml")
    with pytest.raises(CommandError, match="[Ff]ilename"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")


@pytest.mark.django_db
def test_import_detects_collision_with_blank_yaml_filename_recipe(gotofritz, tmp_path):
    """Recipe with blank yaml_filename uses safe_filename(recipe_name) for collision check."""
    from django.contrib.auth.models import User as DjangoUser
    from django.core.management.base import CommandError

    user = DjangoUser.objects.get(username="gotofritz")
    # "Soup" with blank yaml_filename → effective export path is safe_filename("Soup") = "Soup.yml"
    Recipe.objects.create(recipe_name="Soup", owner=user, yaml_filename="")

    # Importing "Soup.yml" → sanitized name "Soup.yml" → collides with effective filename
    p = write_yaml(tmp_path, make_yaml(title="New Soup"), "Soup.yml")
    with pytest.raises(CommandError, match="[Ff]ilename"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")


@pytest.mark.django_db
def test_blank_quantity_is_accepted(gotofritz, tmp_path):
    """quantity: '' in YAML must be treated as absent (None), not rejected as invalid decimal."""
    groups = [
        {
            "name": None,
            "ingredient": [
                {
                    "name": "olive oil",
                    "measurement": "tbsp",
                    "preparation": None,
                    "quantity": "",
                }
            ],
        }
    ]
    p = write_yaml(tmp_path, make_yaml(title="Blank Qty Recipe", groups=groups))
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    assert Recipe.objects.filter(recipe_name="Blank Qty Recipe").exists()


@pytest.mark.django_db
def test_quantity_too_many_total_digits_rejected(user, tmp_path):
    """quantity with more than 7 total digits must be rejected in preflight."""
    from django.core.management.base import CommandError

    groups = [
        {
            "name": None,
            "ingredient": [
                {"name": "flour", "measurement": "g", "preparation": None, "quantity": "123456.99"},
            ],
        }
    ]
    p = write_yaml(tmp_path, make_yaml(title="Overflow Qty", groups=groups))
    with pytest.raises(CommandError, match="quantity"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")


@pytest.mark.django_db
def test_quantity_too_many_decimal_places_rejected(user, tmp_path):
    """quantity with more than 2 decimal places must be rejected in preflight."""
    from django.core.management.base import CommandError

    groups = [
        {
            "name": None,
            "ingredient": [
                {"name": "flour", "measurement": "g", "preparation": None, "quantity": "1.999"},
            ],
        }
    ]
    p = write_yaml(tmp_path, make_yaml(title="Precision Qty", groups=groups))
    with pytest.raises(CommandError, match="quantity"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")


@pytest.mark.django_db
def test_quantity_max_valid_value_accepted(gotofritz, tmp_path):
    """quantity=99999.99 (exactly 7 digits, 2 dp) passes preflight."""
    groups = [
        {
            "name": None,
            "ingredient": [
                {"name": "flour", "measurement": "g", "preparation": None, "quantity": "99999.99"},
            ],
        }
    ]
    p = write_yaml(tmp_path, make_yaml(title="Max Qty", groups=groups))
    # Must not raise
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    assert Recipe.objects.filter(recipe_name="Max Qty").exists()


@pytest.mark.django_db
def test_serves_exceeds_small_int_max_rejected(user, tmp_path):
    """serves=32768 exceeds PositiveSmallIntegerField max (32767) and must be rejected."""
    from django.core.management.base import CommandError

    p = write_yaml(tmp_path, make_yaml(title="Overflow Serves", serves=32768))
    with pytest.raises(CommandError, match="serves"):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")


@pytest.mark.django_db
def test_serves_at_small_int_max_accepted(gotofritz, tmp_path):
    """serves=32767 is the PositiveSmallIntegerField max and must be accepted."""
    p = write_yaml(tmp_path, make_yaml(title="Max Serves", serves=32767))
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    assert Recipe.objects.get(recipe_name="Max Serves").servings == 32767


@pytest.mark.django_db
def test_long_title_imports_with_capped_yaml_filename(gotofritz, tmp_path):
    """Very long recipe title yields a yaml_filename under the column max_length."""
    long_title = "Long Title " + ("a" * 300)
    src = tmp_path / "src.yml"
    src.write_bytes(yaml.dump(make_yaml(title=long_title), allow_unicode=True).encode())
    call_command("batch_load_yaml_recipes", str(src), user="gotofritz")
    # Source filename ("src.yml") is short; assert recipe_name long values still fit
    # the model's CharField when re-saved with safe_filename(title) fallback path
    recipe = Recipe.objects.get(recipe_name=long_title)
    recipe.yaml_filename = ""  # force fallback path
    recipe.save(update_fields=["yaml_filename"])
    # Now simulate export path: would derive filename via safe_filename(title)
    from recipes.utils.filename import safe_filename

    derived = safe_filename(recipe.recipe_name)
    assert len(derived) <= 255
    assert derived.endswith(".yml")


@pytest.mark.django_db
def test_quantity_write_path_receives_decimal_not_float(gotofritz, tmp_path):
    """Write path must pass a Decimal (or None) to create(), never a raw float/str from YAML.

    Without normalization, validation runs `Decimal(str(qty))` but the create() call
    forwards `raw_qty` (a float for unquoted YAML numerics). Django's DecimalField
    converts floats via its own context, so validated and persisted values can diverge.
    This test pins the contract: create() must receive the same Decimal that was validated.
    """
    from decimal import Decimal
    from unittest.mock import patch

    from recipes.models import IngredientInRecipe

    # Write YAML with unquoted numeric quantity → safe_load returns float 1.5
    p = tmp_path / "float_qty.yml"
    p.write_text(
        "title: Float Qty Recipe\n"
        "description: x\n"
        "cuisine: null\n"
        "source: null\n"
        "tags: []\n"
        "directions:\n"
        "  step:\n"
        "    - Stir\n"
        "ingredients:\n"
        "  serves: 4\n"
        "  group:\n"
        "    - name: null\n"
        "      ingredient:\n"
        "        - name: flour\n"
        "          measurement: g\n"
        "          preparation: null\n"
        "          quantity: 1.5\n"
    )

    captured: list[object] = []
    original_create = IngredientInRecipe.objects.create

    def spy(**kwargs):
        captured.append(kwargs.get("quantity"))
        return original_create(**kwargs)

    with patch.object(IngredientInRecipe.objects, "create", side_effect=spy):
        call_command("batch_load_yaml_recipes", str(p), user="gotofritz")

    # create() must have received a Decimal, never a float or str
    assert len(captured) == 1
    received = captured[0]
    assert isinstance(received, Decimal), f"create() got {type(received).__name__}: {received!r}"
    assert received == Decimal("1.5")


@pytest.mark.django_db
def test_single_step_scalar_creates_one_step(gotofritz, tmp_path):
    """directions.step as a bare string must create exactly one Step, not one per character."""
    from recipes.models import Step

    data = make_yaml(title="Scalar Step Recipe")
    data["directions"]["step"] = "Boil everything"  # scalar, not list
    p = write_yaml(tmp_path, data, "scalar_step.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Scalar Step Recipe")
    steps = list(Step.objects.filter(recipe=recipe).order_by("index_in_sequence"))
    assert len(steps) == 1
    assert steps[0].step_text == "Boil everything"


@pytest.mark.django_db
def test_single_tag_scalar_creates_one_tag(gotofritz, tmp_path):
    """tags as a bare string must create exactly one Tag, not one per character."""
    data = make_yaml(title="Scalar Tag Recipe")
    data["tags"] = "vegetarian"  # scalar, not list
    p = write_yaml(tmp_path, data, "scalar_tag.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    recipe = Recipe.objects.get(recipe_name="Scalar Tag Recipe")
    tags = list(recipe.tag.all())  # ty: ignore[unresolved-attribute]
    assert len(tags) == 1
    assert tags[0].tag == "vegetarian"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("½", "0.5"),
        ("¼", "0.25"),
        ("¾", "0.75"),
        ("⅓", str(Decimal(1) / Decimal(3))),
        ("1½", "1.5"),
        ("2¾", "2.75"),
        ("1 1/2", "1.5"),
        ("3/4", "0.75"),
        ("1.5", "1.5"),
        ("2", "2"),
    ],
)
def test_normalize_quantity_unicode_fractions(raw, expected):
    assert _normalize_quantity(raw) == expected


@pytest.mark.django_db
def test_import_unicode_fraction_quantity(gotofritz, tmp_path):
    """Quantity written as '1½' in YAML must import as Decimal('1.5')."""
    groups = [
        {
            "name": None,
            "ingredient": [
                {
                    "name": "kashmiri chilli powder",
                    "measurement": "tsp",
                    "preparation": None,
                    "quantity": "1½",
                }
            ],
        }
    ]
    data = make_yaml(title="Swede Curry", groups=groups)
    p = write_yaml(tmp_path, data, "swede_curry.yml")
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    from recipes.models import IngredientInRecipe

    recipe = Recipe.objects.get(recipe_name="Swede Curry")
    iir = IngredientInRecipe.objects.get(
        ingredient_group__recipe=recipe,
        ingredient__ingredient_name="kashmiri chilli powder",
    )
    assert iir.quantity == Decimal("1.5")


@pytest.mark.django_db
def test_import_filename_collision_check_is_owner_scoped(gotofritz, tmp_path):
    """yaml_filename collision check must be scoped to the importing owner.
    Bob importing soup.yml must not be blocked by Alice's existing soup.yml."""
    alice = DjangoUser.objects.create_user(username="alice_fn", password="x")
    alice_recipe = Recipe.objects.create(recipe_name="Alice Soup", owner=alice, yaml_filename="")
    # Plant alice's effective filename so it matches "soup.yml"
    Recipe.objects.filter(pk=alice_recipe.pk).update(yaml_filename="soup.yml")

    p = write_yaml(tmp_path, make_yaml(title="Bob Soup"), "soup.yml")
    # Should succeed — different owner, same effective filename
    call_command("batch_load_yaml_recipes", str(p), user="gotofritz")
    assert Recipe.objects.filter(recipe_name="Bob Soup", owner=gotofritz).exists()
