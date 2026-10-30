"""One-off backfill for issue #20: lift headings out of step text into step_title.

Throwaway — delete once it has been run:

    uv run python scripts/backfill_step_titles.py --dry-run
    uv run python scripts/backfill_step_titles.py

The rule itself lives in `recipes/utils/step_title.py`, where it is tested.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from recipes.utils.step_title import sentence_case_heading, split_step_title  # noqa: E402


def backfill_database(*, dry_run: bool) -> int:
    """Split a heading off every untitled step in the database. Returns rows changed."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nutrisho.settings.dev")
    import django

    django.setup()

    from recipes.models import Step

    changed = 0
    for step in Step.objects.order_by("recipe_id", "index_in_sequence"):
        if step.step_title:
            # already split, by an earlier run of this script — only the shouting to fix
            title = sentence_case_heading(step.step_title)
            if title == step.step_title:
                continue
            print(f"  step {step.pk}: {step.step_title!r} -> {title!r}")
            if not dry_run:
                step.step_title = title
                step.save(update_fields=["step_title"])
            changed += 1
            continue
        title, remainder = split_step_title(step.step_text)
        if not title:
            continue
        title = sentence_case_heading(title)
        print(f"  step {step.pk}: {title!r} + {remainder[:60]!r}")
        if not dry_run:
            step.step_title = title
            step.step_text = remainder
            step.save(update_fields=["step_title", "step_text"])
        changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    changed = backfill_database(dry_run=args.dry_run)
    verb = "would change" if args.dry_run else "changed"
    print(f"{verb} {changed} step{'' if changed == 1 else 's'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
