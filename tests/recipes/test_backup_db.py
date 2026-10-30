"""Tests for the backup_db management command."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from recipes.models import Recipe


def _backup(tmp_path, *args: str) -> tuple[str, str]:
    """Run backup_db into tmp_path; return (schema, dump) text, dump empty if not written."""
    schema = tmp_path / "schema.sql"
    dump = tmp_path / "dump.sql"
    call_command(
        "backup_db", "--schema", str(schema), "--dump", str(dump), *args, stdout=StringIO()
    )
    return (
        schema.read_text(encoding="utf-8"),
        dump.read_text(encoding="utf-8") if dump.exists() else "",
    )


@pytest.mark.django_db
def test_schema_has_every_app_table(tmp_path):
    """The schema file creates the recipe tables."""
    schema, _ = _backup(tmp_path)
    assert 'CREATE TABLE "recipes_recipe"' in schema
    assert 'CREATE TABLE "recipes_step"' in schema


@pytest.mark.django_db
def test_schema_has_no_yaml_filename(tmp_path):
    """The YAML source filename column is gone from Recipe."""
    schema, _ = _backup(tmp_path)
    assert "yaml_filename" not in schema


@pytest.mark.django_db
def test_schema_holds_no_data(user, tmp_path):
    """The committed schema never carries rows, so it is safe to check in."""
    Recipe.objects.create(recipe_name="Secret Soup", owner=user)
    schema, _ = _backup(tmp_path)
    assert "INSERT" not in schema
    assert "Secret Soup" not in schema


@pytest.mark.django_db
def test_schema_is_stable_across_runs(user, tmp_path):
    """Two runs over the same schema produce identical files, so git diffs stay quiet."""
    first, _ = _backup(tmp_path)
    Recipe.objects.create(recipe_name="Soup", owner=user)
    second, _ = _backup(tmp_path)
    assert first == second


@pytest.mark.django_db
def test_dump_holds_the_data(user, tmp_path):
    """The dump carries the rows, so the database can be rebuilt from it."""
    Recipe.objects.create(recipe_name="Secret Soup", owner=user)
    _, dump = _backup(tmp_path)
    assert 'CREATE TABLE "recipes_recipe"' in dump
    assert "Secret Soup" in dump


@pytest.mark.django_db
def test_schema_only_skips_the_dump(tmp_path):
    """--schema-only writes the schema and nothing else."""
    schema, dump = _backup(tmp_path, "--schema-only")
    assert schema
    assert not (tmp_path / "dump.sql").exists()
    assert dump == ""


@pytest.mark.django_db
def test_creates_missing_parent_directories(tmp_path):
    """Output paths in a directory that does not exist yet still get written."""
    schema = tmp_path / "nested" / "schema.sql"
    call_command("backup_db", "--schema", str(schema), "--schema-only", stdout=StringIO())
    assert schema.exists()


@pytest.mark.django_db
def test_reports_what_it_wrote(tmp_path):
    """The output names both files."""
    out = StringIO()
    schema = tmp_path / "schema.sql"
    dump = tmp_path / "dump.sql"
    call_command("backup_db", "--schema", str(schema), "--dump", str(dump), stdout=out)
    assert str(schema) in out.getvalue()
    assert str(dump) in out.getvalue()


@pytest.mark.django_db
def test_default_dump_name_is_timestamped(tmp_path, settings):
    """Without --dump the dump lands in docs/ as dump-<timestamp>.sql, which git ignores."""
    settings.BASE_DIR = tmp_path
    call_command("backup_db", stdout=StringIO())
    assert (tmp_path / "docs" / "schema.sql").exists()
    dumps = list((tmp_path / "docs").glob("dump-*.sql"))
    assert len(dumps) == 1


@pytest.mark.django_db
def test_refuses_a_non_sqlite_database(tmp_path, monkeypatch):
    """The dump relies on SQLite; another backend fails loudly rather than writing junk."""
    monkeypatch.setattr(connection, "vendor", "postgresql")
    with pytest.raises(CommandError, match="SQLite"):
        _backup(tmp_path)
