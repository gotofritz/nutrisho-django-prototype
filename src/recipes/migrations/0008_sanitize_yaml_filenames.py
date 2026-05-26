"""Sanitize all existing yaml_filename values so the DB invariant holds."""

import re
import unicodedata

from django.db import migrations
from django.db.models import Q

# Logic frozen from recipes/utils/filename.py at migration creation time.
# Do NOT replace with an import — migrations must be deterministic across
# code changes and renames.
_WINDOWS_RESERVED_MIG = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", re.IGNORECASE)
_MAX_BASENAME_MIG = 255


def _sanitize_stem_mig(stem: str) -> str:
    stem = stem.rstrip(". ")
    prefix = stem[: stem.index(".")] if "." in stem else stem
    if _WINDOWS_RESERVED_MIG.match(prefix):
        stem = "_" + stem
    return stem


def _cap_stem_mig(stem: str, ext: str, fallback: str) -> str:
    ext_bytes = len(ext.encode("utf-8"))
    budget = _MAX_BASENAME_MIG - ext_bytes
    if budget <= 0:
        return fallback
    stem_bytes = stem.encode("utf-8")
    if len(stem_bytes) <= budget:
        return stem
    truncated = stem_bytes[:budget].decode("utf-8", errors="ignore").rstrip(". ")
    return truncated or fallback


def _safe_filename_mig(name: str, fallback: str = "recipe") -> str:
    normalized = unicodedata.normalize("NFKC", name)
    normalized = re.sub(r"\s+", " ", normalized)
    clean = re.sub(r"[^\w -]", "", normalized)
    stem = _sanitize_stem_mig(clean) or fallback
    stem = _cap_stem_mig(stem, ".yml", fallback)
    return stem + ".yml"


def _sanitize_stored_filename_mig(stored: str, fallback: str = "recipe") -> str:
    parts = [p for p in re.split(r"[/\\]", stored) if p]
    basename = parts[-1] if parts else "recipe"
    lower = basename.lower()
    if lower.endswith(".yaml"):
        stem = basename[:-5]
        ext = basename[-5:]
    elif lower.endswith(".yml"):
        stem = basename[:-4]
        ext = basename[-4:]
    else:
        stem = basename
        ext = ".yml"
    normalized = unicodedata.normalize("NFKC", stem)
    normalized = re.sub(r"\s+", " ", normalized)
    clean_stem = re.sub(r"[^\w .\-]", "", normalized)
    final_stem = _sanitize_stem_mig(clean_stem) or fallback
    final_stem = _cap_stem_mig(final_stem, ext, fallback)
    return final_stem + ext


def _sanitize_yaml_filenames(apps, schema_editor):
    Recipe = apps.get_model("recipes", "Recipe")
    rows = list(
        Recipe.objects.exclude(yaml_filename="")
        .exclude(yaml_filename__isnull=True)
        .values("pk", "yaml_filename")
    )
    blank_rows = list(
        Recipe.objects.filter(Q(yaml_filename="") | Q(yaml_filename__isnull=True))
        .values("pk", "recipe_name")
    )

    # Detect collisions before any writes; include blank rows using safe_filename fallback
    seen: dict[str, int] = {}  # casefold(effective_filename) -> pk
    for row in blank_rows:
        pk_fallback = f"recipe-{row['pk']}"
        effective = _safe_filename_mig(str(row["recipe_name"] or ""), fallback=pk_fallback)
        key = effective.casefold()
        if key in seen:
            raise RuntimeError(
                f"Migration 0008 aborted: two recipes would both map to '{effective}' "
                f"(PKs {seen[key]} and {row['pk']}). "
                f"Rename or delete one recipe before running this migration."
            )
        seen[key] = row["pk"]

    for row in rows:
        sanitized = _sanitize_stored_filename_mig(row["yaml_filename"])
        key = sanitized.casefold()
        if key in seen:
            raise RuntimeError(
                f"Migration 0008 aborted: two recipes would both sanitize to '{sanitized}' "
                f"(PKs {seen[key]} and {row['pk']}). "
                f"Rename or delete one recipe (yaml_filename) before running this migration."
            )
        seen[key] = row["pk"]

    for row in rows:
        sanitized = _sanitize_stored_filename_mig(row["yaml_filename"])
        if sanitized != row["yaml_filename"]:
            Recipe.objects.filter(pk=row["pk"]).update(yaml_filename=sanitized)


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0007_unique_sequence_constraints"),
    ]

    operations = [
        migrations.RunPython(_sanitize_yaml_filenames, migrations.RunPython.noop),
    ]
