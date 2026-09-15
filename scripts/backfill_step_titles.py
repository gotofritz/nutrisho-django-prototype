"""One-off backfill for issue #20: lift headings out of step text into step_title.

Throwaway — delete once it has been run. Two modes:

    uv run python scripts/backfill_step_titles.py --dry-run
    uv run python scripts/backfill_step_titles.py
    uv run python scripts/backfill_step_titles.py --yaml recipes_yaml/ --dry-run
    uv run python scripts/backfill_step_titles.py --yaml recipes_yaml/

The YAML mode is not optional housekeeping: `task filldb` rebuilds the database
from recipes_yaml/, so leaving the seed files alone would undo the database
backfill on the next reset.

The rule itself lives in `recipes/utils/step_title.py`, where it is tested.
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

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


def backfill_yaml(directory: Path, *, dry_run: bool) -> int:
    """Rewrite titled steps in every YAML file under `directory`. Returns files changed."""
    changed = 0
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".yml", ".yaml"} or not path.is_file():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        steps = (data or {}).get("directions", {}).get("step")
        if steps is None:
            continue
        if not isinstance(steps, list):
            steps = [steps]
        rewritten = []
        touched = False
        for step in steps:
            if isinstance(step, dict):
                # already split, by an earlier run — only the shouting to fix
                current = step.get("title") or ""
                title = sentence_case_heading(current)
                if title == current:
                    rewritten.append(step)
                    continue
                print(f"  {path.name}: {current!r} -> {title!r}")
                rewritten.append({**step, "title": title})
                touched = True
                continue
            if not isinstance(step, str):
                rewritten.append(step)
                continue
            title, remainder = split_step_title(step)
            if not title:
                rewritten.append(step)
                continue
            title = sentence_case_heading(title)
            print(f"  {path.name}: {title!r} + {remainder[:60]!r}")
            rewritten.append({"title": title, "text": remainder})
            touched = True
        if not touched:
            continue
        changed += 1
        if dry_run:
            continue
        data["directions"]["step"] = rewritten
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=True, default_flow_style=False)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yaml",
        type=Path,
        metavar="DIR",
        help="Rewrite the YAML files in DIR instead of the database",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    if args.yaml is not None:
        if not args.yaml.is_dir():
            parser.error(f"{args.yaml} is not a directory")
        changed = backfill_yaml(args.yaml, dry_run=args.dry_run)
        noun = "file"
    else:
        changed = backfill_database(dry_run=args.dry_run)
        noun = "step"

    verb = "would change" if args.dry_run else "changed"
    print(f"{verb} {changed} {noun}{'' if changed == 1 else 's'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
