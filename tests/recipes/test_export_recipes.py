"""Tests for export_recipes_to_yaml management command."""

from decimal import Decimal

import pytest
import yaml
from django.core.management import call_command

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Step,
)


def build_recipe(user, name="Test Recipe", servings=4, cuisine_name=None, source_instance=""):
    """Helper to build a recipe with one group and one ingredient."""
    cuisine = None
    if cuisine_name:
        cuisine, _ = Cuisine.objects.get_or_create(cuisine=cuisine_name)
    recipe = Recipe.objects.create(
        recipe_name=name,
        short_description="A tasty dish",
        owner=user,
        source_instance=source_instance,
        cuisine=cuisine,
        servings=servings,
    )
    Step.objects.create(recipe=recipe, step_text="Chop everything", index_in_sequence=1)
    group = IngredientGroup.objects.create(recipe=recipe, group_name=None, index_in_sequence=1)
    ing, _ = Ingredient.objects.get_or_create(ingredient_name="salt")
    IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=1,
        quantity=Decimal("1.50"),
        unit="tsp",
        preparation="fine",
    )
    return recipe


@pytest.mark.django_db
def test_empty_db_writes_no_files(user, tmp_path):
    """With no recipes in DB, no YAML files are written."""
    call_command("export_recipes_to_yaml", str(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.django_db
def test_single_recipe_produces_expected_yaml(user, tmp_path):
    """A single recipe with one group/ingredient produces correct YAML schema."""
    build_recipe(user, name="Ajo Blanco", servings=2, cuisine_name=".spain.andalusia")
    call_command("export_recipes_to_yaml", str(tmp_path))

    out_file = tmp_path / "Ajo Blanco.yml"
    assert out_file.exists()

    with out_file.open() as f:
        data = yaml.safe_load(f)

    assert "id" not in data
    assert data["title"] == "Ajo Blanco"
    assert data["description"] == "A tasty dish"
    assert data["cuisine"] == ".spain.andalusia"
    assert data["source"] == ""
    assert isinstance(data["tags"], list)
    assert isinstance(data["directions"]["step"], list)
    assert data["directions"]["step"][0] == "Chop everything"
    assert data["ingredients"]["serves"] == 2
    assert isinstance(data["ingredients"]["group"], list)
    group = data["ingredients"]["group"][0]
    assert group["name"] is None
    assert isinstance(group["ingredient"], list)
    ing = group["ingredient"][0]
    assert ing["name"] == "salt"
    assert ing["measurement"] == "tsp"
    assert ing["preparation"] == "fine"
    assert Decimal(ing["quantity"]) == Decimal("1.50")


@pytest.mark.django_db
def test_id_flag_exports_only_that_recipe(user, tmp_path):
    """--id flag exports only the specified recipe."""
    r1 = build_recipe(user, name="Recipe One")
    build_recipe(user, name="Recipe Two")
    call_command("export_recipes_to_yaml", str(tmp_path), id=r1.pk)

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "Recipe One.yml"


@pytest.mark.django_db
def test_missing_only_skips_existing_files(user, tmp_path):
    """--missing-only skips recipes that already have a YAML file on disk."""
    build_recipe(user, name="Already Exported")
    build_recipe(user, name="New Recipe")

    # pre-create the file for the first recipe
    existing = tmp_path / "Already Exported.yml"
    existing.write_text("placeholder: true\n")

    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)

    # existing file should be untouched
    with existing.open() as f:
        data = yaml.safe_load(f)
    assert data == {"placeholder": True}

    # new recipe should be written
    assert (tmp_path / "New Recipe.yml").exists()


@pytest.mark.django_db
def test_special_chars_in_name_produce_safe_filename(user, tmp_path):
    """Recipe names with / : \\ produce safe filenames with _ substitution."""
    build_recipe(user, name="Soupe/Gratinée: A Classic")
    call_command("export_recipes_to_yaml", str(tmp_path))

    expected = tmp_path / "SoupeGratinée A Classic.yml"
    assert expected.exists()


@pytest.mark.django_db
def test_round_trip_export_then_import(user, tmp_path):
    """Export then re-import produces identical DB state."""
    recipe = build_recipe(user, name="Round Trip Dish", servings=3)
    original_id = recipe.pk

    # Export
    call_command("export_recipes_to_yaml", str(tmp_path))

    # Delete from DB
    Recipe.objects.filter(pk=original_id).delete()
    assert not Recipe.objects.filter(recipe_name="Round Trip Dish").exists()

    # Re-import — batch_load_yaml_recipes expects a user named 'gotofritz'
    from django.contrib.auth.models import User as DjangoUser

    DjangoUser.objects.get_or_create(username="gotofritz", defaults={"password": "x"})

    call_command("batch_load_yaml_recipes", str(tmp_path))

    reimported = Recipe.objects.get(recipe_name="Round Trip Dish")
    assert reimported.servings == 3
    assert reimported.step.count() == 1
    assert reimported.step.first().step_text == "Chop everything"
    group = reimported.ingredients_group.first()
    assert group is not None
    iir = group.ingredient.first()
    assert iir.ingredient.ingredient_name == "salt"
    assert iir.quantity == Decimal("1.50")


@pytest.mark.django_db
def test_filename_collision_raises_error(user, tmp_path):
    """Two recipe names mapping to the same safe filename raise CommandError."""
    from django.core.management.base import CommandError

    build_recipe(user, name="A/B")
    build_recipe(user, name="A:B")

    with pytest.raises(CommandError, match="collision"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_missing_only_skips_collision_for_already_exported(user, tmp_path):
    """--missing-only skips collision check for files that already exist on disk."""
    build_recipe(user, name="A/B")
    build_recipe(user, name="A:B")

    # Pre-create the colliding filename so both recipes would be skipped
    (tmp_path / "AB.yml").write_text("placeholder: true\n")

    # Should NOT raise — both recipes are skipped before collision check
    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)
    assert (tmp_path / "AB.yml").read_text() == "placeholder: true\n"


@pytest.mark.django_db
def test_export_uses_stored_yaml_filename(user, tmp_path):
    """Export uses yaml_filename when set rather than deriving from recipe name."""
    recipe = build_recipe(user, name="Easy Baba Ganoush Recipe")
    recipe.yaml_filename = "baba_ganoush.yml"
    recipe.save(update_fields=["yaml_filename"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "baba_ganoush.yml").exists()
    assert not (tmp_path / "Easy Baba Ganoush Recipe.yml").exists()


@pytest.mark.django_db
def test_missing_only_skips_stored_filename(user, tmp_path):
    """--missing-only skips recipes whose stored yaml_filename already exists on disk."""
    recipe = build_recipe(user, name="Easy Baba Ganoush Recipe")
    recipe.yaml_filename = "baba_ganoush.yml"
    recipe.save(update_fields=["yaml_filename"])

    existing = tmp_path / "baba_ganoush.yml"
    existing.write_text("placeholder: true\n")

    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)

    assert existing.read_text() == "placeholder: true\n"


@pytest.mark.django_db
def test_export_falls_back_to_safe_filename_when_no_stored_name(user, tmp_path):
    """Export falls back to safe_filename(recipe_name) when yaml_filename is unset."""
    build_recipe(user, name="My New Soup")

    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "My New Soup.yml").exists()


@pytest.mark.django_db
def test_case_only_name_difference_raises_collision(user, tmp_path):
    """Recipe names differing only in case map to the same file on case-insensitive FSes."""
    from django.core.management.base import CommandError

    build_recipe(user, name="Soup")
    build_recipe(user, name="soup")

    with pytest.raises(CommandError, match="collision"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_traversal_in_stored_filename_is_contained(user, tmp_path):
    """yaml_filename with path traversal segments writes to output_dir, not escaped path."""
    recipe = build_recipe(user, name="Traversal Test")
    recipe.yaml_filename = "../evil.yml"
    recipe.save(update_fields=["yaml_filename"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    # File must be inside tmp_path, not one level up
    assert (tmp_path / "evil.yml").exists()
    assert not (tmp_path.parent / "evil.yml").exists()


@pytest.mark.django_db
def test_absolute_stored_filename_is_contained(user, tmp_path):
    """yaml_filename with absolute path writes basename inside output_dir."""
    recipe = build_recipe(user, name="Absolute Test")
    recipe.yaml_filename = "/etc/passwd.yml"
    recipe.save(update_fields=["yaml_filename"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "passwd.yml").exists()


def test_safe_filename_strips_reserved_chars():
    """safe_filename strips reserved filename characters (NFKC normalize then remove)."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    assert safe_filename("A?B") == "AB.yml"
    assert safe_filename("A*B") == "AB.yml"
    assert safe_filename("A<B") == "AB.yml"
    assert safe_filename("A>B") == "AB.yml"
    assert safe_filename("A|B") == "AB.yml"
    assert safe_filename('A"B') == "AB.yml"
    assert safe_filename("A/B:C\\D") == "ABCD.yml"
    assert safe_filename("Gratinée") == "Gratinée.yml"  # accented word chars preserved


def test_safe_filename_windows_reserved_names_are_renamed():
    """safe_filename prefixes Windows reserved device names so the file is writable on Windows."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    assert safe_filename("CON") == "_CON.yml"
    assert safe_filename("con") == "_con.yml"
    assert safe_filename("PRN") == "_PRN.yml"
    assert safe_filename("NUL") == "_NUL.yml"
    assert safe_filename("COM1") == "_COM1.yml"
    assert safe_filename("LPT9") == "_LPT9.yml"
    # Non-reserved names unaffected
    assert safe_filename("CONSOLE") == "CONSOLE.yml"


def test_safe_filename_trims_trailing_dots_and_spaces():
    """safe_filename trims trailing dots and spaces from stem (illegal on Windows)."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    assert safe_filename("foo ") == "foo.yml"
    assert safe_filename("foo.") == "foo.yml"
    assert safe_filename("foo...") == "foo.yml"


def test_safe_filename_strips_control_whitespace():
    """safe_filename strips tabs, newlines, and other non-space whitespace from titles."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    assert safe_filename("foo\tbar") == "foo bar.yml"
    assert safe_filename("foo\nbar") == "foo bar.yml"
    assert safe_filename("foo\r\nbar") == "foo bar.yml"
    assert safe_filename("foo\x0cbar") == "foo bar.yml"  # form feed


def test_sanitize_stored_filename_strips_control_whitespace():
    """sanitize_stored_filename strips tabs and newlines from stem."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("foo\tbar.yml") == "foo bar.yml"
    assert sanitize_stored_filename("foo\nbar.yml") == "foo bar.yml"


def test_safe_filename_caps_basename_length():
    """Very long titles are truncated so basename fits in NAME_MAX (255 bytes)."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    long_title = "a" * 500
    result = safe_filename(long_title)
    assert len(result) <= 255
    assert result.endswith(".yml")
    # Must not be all-fallback when stem has plenty of valid chars
    assert result.startswith("a")


def test_sanitize_stored_filename_caps_basename_length():
    """Very long stored filenames truncate the stem while preserving the extension."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    long_stored = "a" * 500 + ".yaml"
    result = sanitize_stored_filename(long_stored)
    assert len(result) <= 255
    assert result.endswith(".yaml")
    assert result.startswith("a")

    # .yml extension also preserved
    long_yml = "b" * 500 + ".yml"
    result_yml = sanitize_stored_filename(long_yml)
    assert len(result_yml) <= 255
    assert result_yml.endswith(".yml")


def test_sanitize_stored_filename_fits_model_max_length():
    """Result of sanitize_stored_filename always fits Recipe.yaml_filename max_length=260."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    for n in (200, 260, 300, 500, 1000):
        result = sanitize_stored_filename("x" * n + ".yml")
        assert len(result) <= 260, f"len={len(result)} for input length {n}"


def test_safe_filename_multibyte_chars_capped_by_bytes():
    """Multibyte chars (é=2 B, CJK=3 B) are truncated by byte count, not char count."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    # 200 × 'é' = 200 chars but 400 bytes — must not exceed 255 bytes in output
    result_e = safe_filename("é" * 200)
    assert result_e.endswith(".yml")
    assert len(result_e.encode("utf-8")) <= 255

    # CJK: each char = 3 bytes
    result_cjk = safe_filename("中" * 200)
    assert result_cjk.endswith(".yml")
    assert len(result_cjk.encode("utf-8")) <= 255


def test_sanitize_stored_filename_multibyte_chars_capped_by_bytes():
    """Multibyte chars in stored filenames are truncated by byte count, not char count."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    long_stored = "é" * 200 + ".yml"
    result = sanitize_stored_filename(long_stored)
    assert result.endswith(".yml")
    assert len(result.encode("utf-8")) <= 255

    cjk_stored = "中" * 200 + ".yaml"
    result_cjk = sanitize_stored_filename(cjk_stored)
    assert result_cjk.endswith(".yaml")
    assert len(result_cjk.encode("utf-8")) <= 255


@pytest.mark.django_db
def test_blank_yaml_filename_backfilled_on_first_export(user, tmp_path):
    """Export saves yaml_filename to DB when row has blank; subsequent export uses stored value."""
    recipe = build_recipe(user, name="Backfill Me")
    assert recipe.yaml_filename == ""

    call_command("export_recipes_to_yaml", str(tmp_path))

    recipe.refresh_from_db()
    assert recipe.yaml_filename != ""
    assert recipe.yaml_filename.endswith(".yml")


@pytest.mark.django_db
def test_missing_only_uses_stable_filename_after_recipe_rename(user, tmp_path):
    """After rename, --missing-only still skips the original exported file (stored yaml_filename).

    Without backfill: rename causes export to derive new filename from new recipe_name,
    writing a second YAML file alongside the already-exported one.
    With backfill: first export stores the filename; rename does not change stored filename;
    --missing-only skips correctly because it matches on stored yaml_filename.
    """
    recipe = build_recipe(user, name="Original Name")

    # First export — this should store the filename on the recipe
    call_command("export_recipes_to_yaml", str(tmp_path))
    recipe.refresh_from_db()
    original_file = tmp_path / recipe.yaml_filename

    # Simulate rename (not via yaml_filename field — the recipe_name changes)
    recipe.recipe_name = "New Name After Rename"
    recipe.save(update_fields=["recipe_name"])

    # Second export with --missing-only: must NOT write a new "New Name After Rename.yml"
    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)

    # Original file still present (exported first time)
    assert original_file.exists()
    # New-name file must NOT exist (recipe was skipped because yaml_filename is stable)
    assert not (tmp_path / "New Name After Rename.yml").exists()


def test_sanitize_stored_filename_windows_reserved_is_renamed():
    """sanitize_stored_filename prefixes Windows reserved names."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("CON.yml") == "_CON.yml"
    assert sanitize_stored_filename("NUL.yaml") == "_NUL.yaml"


def test_sanitize_stored_filename_trims_trailing_dots_and_spaces():
    """sanitize_stored_filename trims trailing dots/spaces from stem."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("foo .yml") == "foo.yml"
    assert sanitize_stored_filename("foo..yml") == "foo.yml"


@pytest.mark.django_db
def test_windows_path_in_stored_filename_is_sanitized(user, tmp_path):
    """yaml_filename with Windows drive+backslash path writes safe basename inside output_dir."""
    recipe = build_recipe(user, name="Windows Path Test")
    recipe.yaml_filename = r"C:\tmp\foo:bar.yml"
    recipe.save(update_fields=["yaml_filename"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "foobar.yml").exists()


@pytest.mark.django_db
def test_backslash_traversal_in_stored_filename_is_contained(user, tmp_path):
    """yaml_filename with backslash traversal writes inside output_dir."""
    recipe = build_recipe(user, name="Backslash Traversal")
    recipe.yaml_filename = r"..\evil.yml"
    recipe.save(update_fields=["yaml_filename"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "evil.yml").exists()
    assert not (tmp_path.parent / "evil.yml").exists()


def test_sanitize_stored_filename_preserves_yaml_extension():
    """sanitize_stored_filename preserves .yaml vs .yml so --missing-only finds the right file."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("foo.yaml") == "foo.yaml"
    assert sanitize_stored_filename("foo.yml") == "foo.yml"
    assert sanitize_stored_filename("foo.YAML") == "foo.YAML"  # original casing preserved


def test_sanitize_stored_filename_preserves_interior_dots():
    """Interior dots in stored basenames survive round-trip so --missing-only stays stable."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("grandma.v2.yml") == "grandma.v2.yml"
    assert sanitize_stored_filename("recipe.final.yml") == "recipe.final.yml"
    assert sanitize_stored_filename("my.recipe.yaml") == "my.recipe.yaml"


@pytest.mark.django_db
def test_recipe_with_dot_yaml_stored_filename_exports_correctly(user, tmp_path):
    """yaml_filename ending in .yaml exports to .yaml (extension preserved, no double suffix)."""
    recipe = build_recipe(user, name="Yaml Extension Test")
    recipe.yaml_filename = "my_recipe.yaml"
    recipe.save(update_fields=["yaml_filename"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "my_recipe.yaml").exists()
    assert not (tmp_path / "my_recipe.yaml.yml").exists()
    assert not (tmp_path / "my_recipe.yml").exists()


@pytest.mark.django_db
def test_export_encodes_unicode_correctly(user, tmp_path):
    """Export writes UTF-8 so non-ASCII recipe data survives round-trip."""
    build_recipe(user, name="Sauté d'Agneau", cuisine_name="française")
    call_command("export_recipes_to_yaml", str(tmp_path))

    out_file = tmp_path / "Sauté dAgneau.yml"
    assert out_file.exists()
    raw = out_file.read_bytes()
    text = raw.decode("utf-8")
    assert "Sauté" in text
    assert "française" in text


@pytest.mark.django_db
def test_null_servings_omitted_from_export_yaml(user, tmp_path):
    """Recipe with servings=None exports without a 'serves' key (not 'serves: null')."""
    build_recipe(user, name="Unknown Serves Dish", servings=None)
    call_command("export_recipes_to_yaml", str(tmp_path))

    out_file = tmp_path / "Unknown Serves Dish.yml"
    assert out_file.exists()
    with out_file.open() as f:
        data = yaml.safe_load(f)
    assert "serves" not in data["ingredients"]


@pytest.mark.django_db
def test_round_trip_null_servings_stays_null(user, tmp_path):
    """Export then re-import preserves servings=None; does not corrupt to 1."""
    from django.contrib.auth.models import User as DjangoUser

    recipe = build_recipe(user, name="Null Serves Round Trip", servings=None)
    original_id = recipe.pk

    call_command("export_recipes_to_yaml", str(tmp_path))
    Recipe.objects.filter(pk=original_id).delete()

    DjangoUser.objects.get_or_create(username="gotofritz", defaults={"password": "x"})
    call_command("batch_load_yaml_recipes", str(tmp_path))

    reimported = Recipe.objects.get(recipe_name="Null Serves Round Trip")
    assert reimported.servings is None


@pytest.mark.django_db
def test_tags_exported_in_sorted_order(user, tmp_path):
    """Tags written to YAML in sorted order for stable diffs."""
    recipe = build_recipe(user, name="Tagged Dish")
    from recipes.models import Tag

    for t in ["zucchini", "appetizer", "mediterranean"]:
        tag, _ = Tag.objects.get_or_create(tag=t)
        tag.recipe.add(recipe)  # ty: ignore[unresolved-attribute]

    call_command("export_recipes_to_yaml", str(tmp_path))

    out_file = tmp_path / "Tagged Dish.yml"
    with out_file.open() as f:
        data = yaml.safe_load(f)

    assert data["tags"] == sorted(data["tags"])
    assert data["tags"] == ["appetizer", "mediterranean", "zucchini"]


@pytest.mark.django_db
def test_null_description_exports_as_null_not_empty_string(user, tmp_path):
    """Recipe with short_description=None exports description as null, not ''."""
    recipe = build_recipe(user, name="No Desc Dish")
    recipe.short_description = None
    recipe.save(update_fields=["short_description"])

    call_command("export_recipes_to_yaml", str(tmp_path))

    out_file = tmp_path / "No Desc Dish.yml"
    with out_file.open() as f:
        data = yaml.safe_load(f)
    assert data["description"] is None


@pytest.mark.django_db
def test_round_trip_null_description_stays_null(user, tmp_path):
    """Export then re-import preserves short_description=None (not corrupted to '')."""
    from django.contrib.auth.models import User as DjangoUser

    recipe = build_recipe(user, name="Null Desc Dish")
    recipe.short_description = None
    recipe.save(update_fields=["short_description"])
    original_id = recipe.pk

    call_command("export_recipes_to_yaml", str(tmp_path))
    Recipe.objects.filter(pk=original_id).delete()

    DjangoUser.objects.get_or_create(username="gotofritz", defaults={"password": "x"})
    call_command("batch_load_yaml_recipes", str(tmp_path))

    reimported = Recipe.objects.get(recipe_name="Null Desc Dish")
    assert reimported.short_description is None


@pytest.mark.django_db
def test_missing_only_skips_dot_yaml_extension_file(user, tmp_path):
    """--missing-only skips recipe when stored yaml_filename with .yaml extension already exists."""
    recipe = build_recipe(user, name="Yaml Ext Recipe")
    recipe.yaml_filename = "yaml_ext.yaml"
    recipe.save(update_fields=["yaml_filename"])

    existing = tmp_path / "yaml_ext.yaml"
    existing.write_text("placeholder: true\n")

    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)

    # Original .yaml file untouched (skipped)
    assert existing.read_text() == "placeholder: true\n"
    # Must NOT have created a separate .yml file (extension mismatch = wrong skip logic)
    assert not (tmp_path / "yaml_ext.yml").exists()


def test_sanitize_stored_filename_preserves_uppercase_extension():
    """sanitize_stored_filename preserves original extension casing (.YAML / .YML)."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("soup.YAML") == "soup.YAML"
    assert sanitize_stored_filename("soup.YML") == "soup.YML"
    assert sanitize_stored_filename("soup.Yaml") == "soup.Yaml"


@pytest.mark.django_db
def test_missing_only_skips_uppercase_yaml_extension_file(user, tmp_path):
    """--missing-only skips recipe whose stored yaml_filename has uppercase .YAML extension."""
    recipe = build_recipe(user, name="Upper Ext Recipe")
    recipe.yaml_filename = "upper_ext.YAML"
    recipe.save(update_fields=["yaml_filename"])

    existing = tmp_path / "upper_ext.YAML"
    existing.write_text("placeholder: true\n")

    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)

    assert existing.read_text() == "placeholder: true\n"
    assert not (tmp_path / "upper_ext.yaml").exists()
    assert not (tmp_path / "upper_ext.yml").exists()


def test_safe_filename_empty_stem_fallback():
    """Title stripped to empty string produces 'recipe.yml', not '.yml'."""
    from recipes.management.commands.export_recipes_to_yaml import safe_filename

    assert safe_filename("!!!") == "recipe.yml"
    assert safe_filename("...") == "recipe.yml"
    assert safe_filename("   ") == "recipe.yml"


def test_sanitize_stored_filename_empty_stem_fallback():
    """Stored filename stripped to empty stem produces 'recipe.yml', not '.yml'."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("!!!.yml") == "recipe.yml"
    assert sanitize_stored_filename("....") == "recipe.yml"
    assert sanitize_stored_filename("!!!.yaml") == "recipe.yaml"


@pytest.mark.django_db
def test_all_stripped_title_uses_recipe_id_as_filename(user, tmp_path):
    """Recipe whose title strips to empty stem exports as 'recipe-<pk>.yml'."""
    recipe = build_recipe(user, name="!!!")
    call_command("export_recipes_to_yaml", str(tmp_path))
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == f"recipe-{recipe.pk}.yml"


@pytest.mark.django_db
def test_missing_only_skips_case_insensitive_filename_match(user, tmp_path):
    """--missing-only must skip when existing file matches by casefold, not just exact case."""
    recipe = build_recipe(user, name="Ajo Blanco Soup")
    # Stored filename uses uppercase; existing disk file is lowercase
    recipe.yaml_filename = "Ajo Blanco Soup.yml"
    recipe.save(update_fields=["yaml_filename"])

    existing = tmp_path / "ajo blanco soup.yml"
    existing.write_text("placeholder\n")

    call_command("export_recipes_to_yaml", str(tmp_path), missing_only=True)

    # File must be unchanged — recipe was skipped via casefold match
    assert existing.read_text() == "placeholder\n"
    assert not (tmp_path / "Ajo Blanco Soup.yml").exists()


@pytest.mark.django_db
def test_second_export_to_same_directory_refreshes_files(user, tmp_path):
    """Exporting twice to the same directory overwrites files; must not raise collision error."""
    build_recipe(user, name="Refresh Me", servings=2)
    call_command("export_recipes_to_yaml", str(tmp_path))
    # Second export must succeed (overwrite), not raise CommandError
    call_command("export_recipes_to_yaml", str(tmp_path))
    files = list(tmp_path.iterdir())
    assert len(files) == 1


@pytest.mark.django_db
def test_exported_yaml_has_no_id_field(user, tmp_path):
    """Exported YAML must not include 'id' — importer always inserts fresh rows."""
    build_recipe(user, name="No ID Recipe")
    call_command("export_recipes_to_yaml", str(tmp_path))
    with (tmp_path / "No ID Recipe.yml").open() as f:
        data = yaml.safe_load(f)
    assert "id" not in data


@pytest.mark.django_db
def test_output_dir_is_file_raises_command_error(user, tmp_path):
    """Passing a path that exists as a regular file raises CommandError, not FileExistsError."""
    from django.core.management.base import CommandError

    file_path = tmp_path / "not_a_dir.yml"
    file_path.write_text("data\n")

    with pytest.raises(CommandError, match="not a directory"):
        call_command("export_recipes_to_yaml", str(file_path))


@pytest.mark.django_db
def test_id_not_found_raises_command_error(user, tmp_path):
    """--id with nonexistent recipe ID raises CommandError."""
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="99999"):
        call_command("export_recipes_to_yaml", str(tmp_path), id=99999)


@pytest.mark.django_db
def test_case_rename_overwrites_existing_file_not_creates_duplicate(user, tmp_path):
    """Normal export with case-only rename overwrites existing file; no duplicate left on disk."""
    recipe = build_recipe(user, name="Soup")
    recipe.yaml_filename = "Soup.yml"
    recipe.save(update_fields=["yaml_filename"])

    # Pre-create the file under different case (simulates case-only rename on disk)
    old_file = tmp_path / "SOUP.yml"
    old_file.write_text("old: true\n")

    call_command("export_recipes_to_yaml", str(tmp_path))

    files = [f for f in tmp_path.iterdir() if f.is_file()]
    # Must not leave two files; only one YAML file in the dir
    assert len(files) == 1
    # The surviving file must contain the fresh export, not the old placeholder
    content = yaml.safe_load(files[0].read_text())
    assert content.get("title") == "Soup"


@pytest.mark.django_db
def test_target_path_is_directory_raises_command_error(user, tmp_path):
    """If a target output path is a directory (not a file), raises CommandError before any writes."""
    from django.core.management.base import CommandError

    recipe = build_recipe(user, name="Dir Collision Recipe")
    recipe.yaml_filename = "dir_collision.yml"
    recipe.save(update_fields=["yaml_filename"])

    # Create a directory with the same name as the expected output file
    (tmp_path / "dir_collision.yml").mkdir()

    with pytest.raises(CommandError, match="not a regular file"):
        call_command("export_recipes_to_yaml", str(tmp_path))


def test_sanitize_stored_filename_reserved_with_dotted_segments():
    """sanitize_stored_filename prefixes reserved names that appear before dotted segments."""
    from recipes.management.commands.export_recipes_to_yaml import sanitize_stored_filename

    assert sanitize_stored_filename("CON.v2.yml") == "_CON.v2.yml"
    assert sanitize_stored_filename("NUL.backup.yaml") == "_NUL.backup.yaml"
    assert sanitize_stored_filename("LPT1.old.yml") == "_LPT1.old.yml"
    # Non-reserved prefix not affected
    assert sanitize_stored_filename("my.CON.yml") == "my.CON.yml"


@pytest.mark.django_db
def test_existing_case_collision_in_output_dir_raises_command_error(user, tmp_path):
    """When output_dir already contains two files differing only in case, raises CommandError."""
    from django.core.management.base import CommandError

    (tmp_path / "soup.yml").write_text("old\n")
    (tmp_path / "SOUP.yml").write_text("old\n")
    build_recipe(user, name="Anything")

    with pytest.raises(CommandError, match="[Cc]ollide|[Aa]mbiguous|[Cc]ollision"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_non_yaml_files_differing_in_case_do_not_abort_export(user, tmp_path):
    """Non-YAML files that differ only in case (e.g. README / readme) must not abort export."""
    (tmp_path / "README").write_text("notes\n")
    (tmp_path / "readme").write_text("also notes\n")
    build_recipe(user, name="Fine Recipe")

    # Must not raise — the collision check must be limited to .yml/.yaml files
    call_command("export_recipes_to_yaml", str(tmp_path))

    assert (tmp_path / "Fine Recipe.yml").exists()


# --- Lossy round-trip detection -----------------------------------------------
#
# The YAML schema is a strict subset of the model: owner, source FK,
# Step.duration, Step.extra_info, IngredientInRecipe.substitute, and
# IngredientInRecipe.note are not represented. Without intervention,
# export → delete → re-import silently drops these. The exporter refuses
# by default and accepts --force to acknowledge the loss.


@pytest.mark.django_db
def test_export_refuses_recipe_with_non_gotofritz_owner(tmp_path):
    """owner != gotofritz is lossy (importer hardcodes gotofritz); export refuses."""
    from django.contrib.auth.models import User as DjangoUser
    from django.core.management.base import CommandError

    other = DjangoUser.objects.create_user(username="alice", password="x")
    build_recipe(other, name="Alice Recipe")

    with pytest.raises(CommandError, match="owner"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_export_refuses_recipe_with_source_fk(user, tmp_path):
    """Recipe with non-null source FK is lossy; export refuses."""
    from django.core.management.base import CommandError

    from recipes.models import Source

    src = Source.objects.create(source="A Book")
    recipe = build_recipe(user, name="Sourced Recipe")
    recipe.source = src
    recipe.save(update_fields=["source"])

    with pytest.raises(CommandError, match="source"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_export_refuses_step_with_duration(user, tmp_path):
    """Step with non-null duration is lossy; export refuses."""
    from datetime import timedelta

    from django.core.management.base import CommandError

    recipe = build_recipe(user, name="Timed Recipe")
    step = recipe.step.first()  # ty: ignore[unresolved-attribute]
    step.duration = timedelta(minutes=15)
    step.save(update_fields=["duration"])

    with pytest.raises(CommandError, match="duration"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_export_refuses_step_with_extra_info(user, tmp_path):
    """Step with non-empty extra_info is lossy; export refuses."""
    from django.core.management.base import CommandError

    recipe = build_recipe(user, name="Annotated Recipe")
    step = recipe.step.first()  # ty: ignore[unresolved-attribute]
    step.extra_info = "Use a wooden spoon"
    step.save(update_fields=["extra_info"])

    with pytest.raises(CommandError, match="extra_info"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_export_refuses_iir_with_substitute(user, tmp_path):
    """IngredientInRecipe with substitute FK is lossy; export refuses."""
    from django.core.management.base import CommandError

    recipe = build_recipe(user, name="Substitute Recipe")
    sub, _ = Ingredient.objects.get_or_create(ingredient_name="sea salt")
    iir = recipe.ingredients_group.first().ingredient.first()  # ty: ignore[unresolved-attribute]
    iir.substitute = sub
    iir.save(update_fields=["substitute"])

    with pytest.raises(CommandError, match="substitute"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_export_refuses_iir_with_note(user, tmp_path):
    """IngredientInRecipe with non-empty note is lossy; export refuses."""
    from django.core.management.base import CommandError

    recipe = build_recipe(user, name="Noted Recipe")
    iir = recipe.ingredients_group.first().ingredient.first()  # ty: ignore[unresolved-attribute]
    iir.note = "fresh ground"
    iir.save(update_fields=["note"])

    with pytest.raises(CommandError, match="note"):
        call_command("export_recipes_to_yaml", str(tmp_path))


@pytest.mark.django_db
def test_force_flag_allows_lossy_export(user, tmp_path, capsys):
    """--force exports lossy recipes after writing a stderr warning listing dropped fields."""
    recipe = build_recipe(user, name="Forced Recipe")
    step = recipe.step.first()  # ty: ignore[unresolved-attribute]
    step.extra_info = "ignore me"
    step.save(update_fields=["extra_info"])

    call_command("export_recipes_to_yaml", str(tmp_path), force=True)

    assert (tmp_path / "Forced Recipe.yml").exists()
    captured = capsys.readouterr()
    # Either stderr or stdout — Django writes warnings to stderr via self.stderr
    combined = captured.err + captured.out
    assert "Forced Recipe" in combined
    assert "extra_info" in combined


@pytest.mark.django_db
def test_recipe_with_default_owner_and_no_extras_exports_cleanly(user, tmp_path):
    """Non-lossy recipe (gotofritz owner, no source/duration/extras) exports without --force."""
    build_recipe(user, name="Clean Recipe")
    call_command("export_recipes_to_yaml", str(tmp_path))
    assert (tmp_path / "Clean Recipe.yml").exists()


# --- Schema-completeness invariant --------------------------------------------
#
# Each persisted field on Recipe/Step/IngredientInRecipe must be exactly one of:
#   - serialized by recipe_to_dict (round-trip preserved)
#   - flagged by lossy_fields (caught by export refusal)
#   - explicitly listed below as IGNORED (e.g. auto pk, auto_now_add timestamps)
#
# A new model field added to any of these models that fits none of the three
# categories will fail this test. This stops the review-fix-review circle: any
# silent drop becomes a build failure on the commit that introduces the field.

# Fields that are intentionally not exported and not lossy-flagged.
# Justify each entry — anything here must be either auto-managed or structural.
_IGNORED_FIELDS: dict[str, set[str]] = {
    "Recipe": {
        "id",  # AutoField, regenerated on insert
        "created_date",  # auto_now_add; always regenerated, not worth flagging
        "yaml_filename",  # filename routing, not recipe content
        "recipe_name",  # serialized as 'title'
        "short_description",  # serialized as 'description'
        "source_instance",  # serialized as 'source'
        "cuisine",  # serialized as 'cuisine' (FK → name)
        "servings",  # serialized as ingredients.serves
    },
    "Step": {
        "id",
        "recipe",  # FK, set on insert
        "index_in_sequence",  # set on insert from list order
        "step_text",  # serialized as directions.step[i]
    },
    "IngredientInRecipe": {
        "id",
        "ingredient",  # serialized as ingredient.name
        "ingredient_group",  # FK, set on insert
        "index_in_sequence",  # set on insert from list order
        "unit",  # serialized as 'measurement'
        "preparation",  # serialized as 'preparation'
        "quantity",  # serialized as 'quantity'
    },
}

# Fields that lossy_fields() must catch. Each entry is the model field name.
_EXPECTED_LOSSY: dict[str, set[str]] = {
    "Recipe": {"owner", "source"},
    "Step": {"duration", "extra_info"},
    "IngredientInRecipe": {"substitute", "note"},
}


def test_every_persisted_field_is_categorized():
    """Every concrete field on Recipe/Step/IIR is exported, lossy-flagged, or ignored.

    Forces anyone adding a new model field to decide whether it round-trips or is
    lossy. Prevents silent data loss from future schema changes.
    """
    from recipes.models import IngredientInRecipe, Recipe, Step

    models = {"Recipe": Recipe, "Step": Step, "IngredientInRecipe": IngredientInRecipe}

    for model_name, model_cls in models.items():
        # _meta is injected by Django's model metaclass; ty cannot see through it.
        # Introspecting fields here is deliberate — the whole point of the test is
        # to catch new model fields that nobody categorized, which a hardcoded list
        # would silently miss.
        field_names = {
            f.name
            for f in model_cls._meta.get_fields()  # ty: ignore[possibly-missing-attribute]
            if getattr(f, "concrete", False)
        }
        ignored = _IGNORED_FIELDS[model_name]
        lossy = _EXPECTED_LOSSY[model_name]
        categorized = ignored | lossy
        uncategorized = field_names - categorized
        assert not uncategorized, (
            f"{model_name} has fields not categorized as exported/lossy/ignored: "
            f"{sorted(uncategorized)}. Add each to recipe_to_dict (and the importer), "
            f"to lossy_fields(), or to _IGNORED_FIELDS with justification."
        )
        # Reverse check: nothing in our lists should reference a field that no longer exists
        stale = categorized - field_names
        assert not stale, f"{model_name} category lists reference removed fields: {sorted(stale)}"


@pytest.mark.django_db
def test_lossy_fields_function_catches_every_expected_lossy_field():
    """lossy_fields() returns a reason for each field listed in _EXPECTED_LOSSY.

    Pairs with the previous test: that one asserts the field SHOULD be lossy-flagged;
    this one asserts the function actually flags it. Together they pin the contract.
    """
    from datetime import timedelta

    from django.contrib.auth.models import User as DjangoUser

    from recipes.management.commands.export_recipes_to_yaml import lossy_fields
    from recipes.models import Source

    # Build a recipe touching every lossy field at once
    alice = DjangoUser.objects.create_user(username="alice", password="x")
    src = Source.objects.create(source="A Book")
    recipe = Recipe.objects.create(
        recipe_name="Lossy Witness",
        owner=alice,
        source=src,
    )
    step = Step.objects.create(
        recipe=recipe,
        step_text="x",
        index_in_sequence=1,
        duration=timedelta(minutes=1),
        extra_info="extra",
    )
    group = IngredientGroup.objects.create(recipe=recipe, group_name=None, index_in_sequence=1)
    ing, _ = Ingredient.objects.get_or_create(ingredient_name="x")
    sub, _ = Ingredient.objects.get_or_create(ingredient_name="y")
    IngredientInRecipe.objects.create(
        ingredient=ing,
        substitute=sub,
        ingredient_group=group,
        index_in_sequence=1,
        note="some note",
    )

    reasons_text = " ".join(lossy_fields(recipe))
    # Recipe-level
    assert "owner" in reasons_text
    assert "source" in reasons_text
    # Step-level
    assert "duration" in reasons_text
    assert "extra_info" in reasons_text
    # IIR-level
    assert "substitute" in reasons_text
    assert "note" in reasons_text
    # silence unused-warning for step (kept for clarity that all paths populated)
    del step
