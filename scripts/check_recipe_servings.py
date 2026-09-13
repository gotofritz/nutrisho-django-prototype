#!/usr/bin/env python
"""Throwaway check (issue #21): every recipe must carry a serving count.

Run before applying migration 0012, which makes ``Recipe.servings`` NOT NULL and
aborts rather than inventing a serving count for rows that lack one.

    DJANGO_SETTINGS_MODULE=nutrisho.settings.dev uv run python scripts/check_recipe_servings.py

Checks the database, and the YAML sources in ``recipes_yaml/`` when that directory
exists (``batch_load_yaml_recipes`` now rejects a file without ``ingredients.serves``).
Exits 1 if anything is missing a serving count.
"""

import os
import sys
from pathlib import Path

import django
import yaml

ROOT = Path(__file__).resolve().parent.parent
YAML_DIR = ROOT / "recipes_yaml"

sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nutrisho.settings.dev")
django.setup()

from recipes.models import Recipe  # noqa: E402  # needs django.setup() first


def check_db() -> int:
    """Report recipes whose servings is NULL or below 1. Returns the offender count."""
    rows = list(
        Recipe.objects.filter(servings__isnull=True).values_list("pk", "recipe_name")
    ) + list(Recipe.objects.filter(servings__lt=1).values_list("pk", "recipe_name"))
    total = Recipe.objects.count()
    if rows:
        print(f"DB: {len(rows)} of {total} recipes have no usable serving count:")
        for pk, name in rows:
            print(f"  #{pk} {name!r}")
    else:
        print(f"DB: all {total} recipes have a serving count.")
    return len(rows)


def check_yaml() -> int:
    """Report YAML sources with no usable ingredients.serves. Returns the offender count."""
    if not YAML_DIR.is_dir():
        print(f"YAML: {YAML_DIR} not found, skipping.")
        return 0

    files = sorted(p for p in YAML_DIR.iterdir() if p.suffix.lower() in {".yml", ".yaml"})
    offenders: list[tuple[Path, object]] = []
    for path in files:
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        serves = (data.get("ingredients") or {}).get("serves")
        if not isinstance(serves, int) or isinstance(serves, bool) or serves < 1:
            offenders.append((path, serves))

    if offenders:
        print(f"YAML: {len(offenders)} of {len(files)} files have no usable 'serves':")
        for path, serves in offenders:
            print(f"  {path.name}: serves={serves!r}")
    else:
        print(f"YAML: all {len(files)} files have a serving count.")
    return len(offenders)


if __name__ == "__main__":
    bad = check_db() + check_yaml()
    sys.exit(1 if bad else 0)
