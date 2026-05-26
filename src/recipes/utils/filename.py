"""Filename sanitization utilities shared by models and management commands."""

import re
import unicodedata

# Windows reserved device names (case-insensitive); cannot be filenames on Windows.
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", re.IGNORECASE)

# Cap basename length. 255 is the de-facto NAME_MAX on most filesystems (ext4, APFS,
# NTFS) and also fits within Recipe.yaml_filename's max_length=260 column.
_MAX_BASENAME = 255


def _cap_stem(stem: str, ext: str, fallback: str) -> str:
    """Truncate stem so stem+ext fits in _MAX_BASENAME; fall back if nothing remains."""
    budget = _MAX_BASENAME - len(ext)
    if budget <= 0:
        return fallback
    if len(stem) <= budget:
        return stem
    return stem[:budget].rstrip(". ") or fallback


def _sanitize_stem(stem: str) -> str:
    """Trim trailing dots/spaces and prefix Windows-reserved names."""
    stem = stem.rstrip(". ")
    # Windows rejects reserved device names even with dotted suffixes (CON.v2, NUL.backup)
    prefix = stem[: stem.index(".")] if "." in stem else stem
    if _WINDOWS_RESERVED.match(prefix):
        stem = "_" + stem
    return stem


def safe_filename(name: str, fallback: str = "recipe") -> str:
    """Normalize to NFKC, strip reserved chars, fix Windows hazards, then append .yml."""
    normalized = unicodedata.normalize("NFKC", name)
    normalized = re.sub(r"\s+", " ", normalized)
    clean = re.sub(r"[^\w -]", "", normalized)
    stem = _sanitize_stem(clean) or fallback
    stem = _cap_stem(stem, ".yml", fallback)
    return stem + ".yml"


def sanitize_stored_filename(stored: str, fallback: str = "recipe") -> str:
    """Return a safe, bare filename from a stored yaml_filename value.

    Handles Unix paths, Windows paths (C:\\tmp\\foo.yml), backslash traversal
    (..\\ evil.yml), and reserved characters so the result is always a safe
    basename regardless of the platform that last wrote the field.

    The original extension (.yml or .yaml) is preserved so --missing-only can
    match against the file that was originally imported. Interior dots in the
    stem are also preserved (e.g. grandma.v2.yml stays grandma.v2.yml).
    If all stem characters are stripped, fallback is used instead.
    """
    # Split on both slash styles; take the last non-empty component
    parts = [p for p in re.split(r"[/\\]", stored) if p]
    basename = parts[-1] if parts else "recipe"
    # Separate stem and extension; preserve original extension casing (.YAML, .YML, etc.)
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
    # Normalize to NFKC; collapse whitespace; strip reserved chars; keep interior dots
    normalized = unicodedata.normalize("NFKC", stem)
    normalized = re.sub(r"\s+", " ", normalized)
    clean_stem = re.sub(r"[^\w .\-]", "", normalized)
    final_stem = _sanitize_stem(clean_stem) or fallback
    final_stem = _cap_stem(final_stem, ext, fallback)
    return final_stem + ext
