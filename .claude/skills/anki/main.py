#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "anki>=25.9.2",
#     "click>=8.1.0",
# ]
# ///
"""Anki skill for reading and writing cards to local Anki collections.

This skill provides safe read/write access to Anki collections using the
official Anki Python API. It supports querying cards, listing decks, and
adding new cards without direct database writes.
"""

import csv
import json
import os
import re
from io import StringIO
from pathlib import Path

import click
from anki.collection import Collection
from anki.errors import DBError


def get_collection_path() -> Path:
    """Get Anki collection path from environment or auto-detect.

    Returns:
        Path to collection.anki2 file

    Raises:
        click.ClickException: If collection cannot be found
    """
    # Check environment variable
    env_path = os.environ.get("ANKI_COLLECTION_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
        raise click.ClickException(f"ANKI_COLLECTION_PATH points to non-existent file: {env_path}")

    # Auto-detect based on platform
    home = Path.home()
    candidates = [
        home / "Library" / "Application Support" / "Anki2" / "User 1" / "collection.anki2",  # macOS
        home / ".local" / "share" / "Anki2" / "User 1" / "collection.anki2",  # Linux
        home / ".var" / "app" / "net.ankiweb.Anki" / "data" / "Anki2" / "User 1" / "collection.anki2",  # Linux Flatpak
    ]

    # Windows path
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Anki2" / "User 1" / "collection.anki2")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise click.ClickException("Could not locate Anki collection. Use --collection to specify path or set ANKI_COLLECTION_PATH.")


def get_collection(*, collection_path: Path | None = None) -> Collection:
    """Open Anki collection with error handling.

    Args:
        collection_path: Optional path to collection file

    Returns:
        Open Collection object

    Raises:
        click.ClickException: If collection cannot be opened
    """
    path = collection_path or get_collection_path()

    try:
        return Collection(str(path))
    except DBError as e:
        if "database is locked" in str(e).lower():
            raise click.ClickException("Collection is locked. Close Anki and try again.")
        raise click.ClickException(f"Failed to open collection: {e}")
    except Exception as e:
        raise click.ClickException(f"Failed to open collection: {e}")


def validate_cloze_syntax(*, text: str) -> None:
    """Validate cloze deletion syntax and provide helpful warnings.

    Args:
        text: Text field content to validate

    Raises:
        click.ClickException: If cloze syntax is invalid or missing
    """
    # Check if text contains any cloze deletions
    cloze_pattern = r"\{\{c\d+::[^}]+\}\}"
    if not re.search(cloze_pattern, text):
        raise click.ClickException(
            f"Cloze card Text field must contain at least one cloze deletion.\n"
            f"Expected format: {{{{c1::text}}}} or {{{{c1::text::hint}}}}\n"
            f"Example: '{{{{c1::Berlin}}}} is the capital of Germany'\n"
            f"Received: '{text[:100]}...'" if len(text) > 100 else f"Received: '{text}'"
        )


def _has_cloze_deletion(text: str) -> bool:
    """Check if text contains valid Cloze deletion syntax.

    Args:
        text: Text to check for cloze deletions

    Returns:
        True if text contains at least one cloze deletion ({{c1::...}}, etc.)
    """
    # Pattern matches {{c1::text}}, {{c2::text::hint}}, etc.
    pattern = r"\{\{c\d+::[^}]+\}\}"
    return bool(re.search(pattern, text))


def map_input_to_note_fields(*, card_data: dict, model: dict) -> dict[str, str]:
    """Map input card data to note type fields with flexible matching.

    Supports multiple input formats:
    - Explicit fields: {"fields": {"Text": "...", "Extra": "..."}}
    - Legacy front/back: {"front": "...", "back": "..."} → Front/Back
    - Flexible keys: case-insensitive matching to note type fields

    Args:
        card_data: Input card data dictionary
        model: Anki note type model dictionary

    Returns:
        Dictionary mapping field names to values

    Raises:
        click.ClickException: If required fields are missing or cannot be mapped
    """
    # Get expected field names from model
    model_fields = [field["name"] for field in model["flds"]]
    field_mapping = {}

    # Case 1: Explicit fields object
    if "fields" in card_data:
        fields_data = card_data["fields"]
        if not isinstance(fields_data, dict):
            raise click.ClickException("'fields' must be a dictionary")

        # Direct mapping (case-sensitive)
        for field_name, field_value in fields_data.items():
            if field_name not in model_fields:
                raise click.ClickException(
                    f"Field '{field_name}' not found in note type.\n"
                    f"Expected fields: {', '.join(model_fields)}"
                )
            field_mapping[field_name] = str(field_value)

        return field_mapping

    # Case 2: Legacy front/back format (for backward compatibility)
    if "front" in card_data and "back" in card_data:
        # Map to Front/Back fields (standard Basic note type)
        if "Front" not in model_fields or "Back" not in model_fields:
            raise click.ClickException(
                f"Note type does not have Front/Back fields.\n"
                f"Expected fields: {', '.join(model_fields)}\n"
                f"Use explicit 'fields' format: {{\"fields\": {{\"{model_fields[0]}\": \"...\"}}}}"
            )
        return {
            "Front": str(card_data["front"]),
            "Back": str(card_data["back"]),
        }

    # Case 3: Flexible case-insensitive matching
    # Create lowercase mapping of input keys
    input_keys_lower = {k.lower(): k for k in card_data.keys() if k != "tags"}

    # Try to match each model field (case-insensitive)
    for field_name in model_fields:
        field_lower = field_name.lower()
        if field_lower in input_keys_lower:
            original_key = input_keys_lower[field_lower]
            field_mapping[field_name] = str(card_data[original_key])

    # Validate that we have at least some fields mapped
    if not field_mapping:
        raise click.ClickException(
            f"Could not map any input fields to note type fields.\n"
            f"Expected fields: {', '.join(model_fields)}\n"
            f"Provided keys: {', '.join([k for k in card_data.keys() if k != 'tags'])}\n"
            f"Use explicit 'fields' format or provide fields with matching names."
        )

    return field_mapping


def format_card_text(*, note: dict, deck_name: str) -> str:
    """Format a single card as text with flexible field support.

    Tries multiple note type formats:
    - Basic: Front → Back
    - Cloze: Text
    - Custom: First 2-3 fields

    Args:
        note: Note dictionary with fields
        deck_name: Name of the deck

    Returns:
        Formatted text string
    """
    fields = note.get("fields", {})
    tags = ", ".join(note.get("tags", []))

    # Try Basic note type (Front/Back)
    if "Front" in fields and "Back" in fields:
        return f"[{deck_name}] {fields['Front']} → {fields['Back']} (tags: {tags})"

    # Try Cloze note type (Text/Extra)
    if "Text" in fields:
        text = fields["Text"]
        extra = fields.get("Extra", "")
        if extra:
            return f"[{deck_name}] {text} ({extra}) (tags: {tags})"
        return f"[{deck_name}] {text} (tags: {tags})"

    # Custom note type - display first few fields
    field_items = list(fields.items())
    if not field_items:
        return f"[{deck_name}] (empty note) (tags: {tags})"

    if len(field_items) == 1:
        field_name, field_value = field_items[0]
        return f"[{deck_name}] {field_name}: {field_value} (tags: {tags})"

    # Multiple fields - show first 2-3
    field_strs = [f"{name}: {value}" for name, value in field_items[:3]]
    field_display = " | ".join(field_strs)
    return f"[{deck_name}] {field_display} (tags: {tags})"


def format_card_markdown(*, note: dict, deck_name: str) -> str:
    """Format a single card as markdown with flexible field support.

    Tries multiple note type formats:
    - Basic: Front → Back
    - Cloze: Text (Extra)
    - Custom: All fields listed

    Args:
        note: Note dictionary with fields
        deck_name: Name of the deck

    Returns:
        Formatted markdown string
    """
    fields = note.get("fields", {})
    tags = ", ".join(note.get("tags", []))

    # Try Basic note type (Front/Back)
    if "Front" in fields and "Back" in fields:
        return f"- **{fields['Front']}** → {fields['Back']}\n  - Deck: {deck_name}\n  - Tags: {tags}"

    # Try Cloze note type (Text/Extra)
    if "Text" in fields:
        text = fields["Text"]
        extra = fields.get("Extra", "")
        if extra:
            return f"- **{text}** ({extra})\n  - Deck: {deck_name}\n  - Tags: {tags}"
        return f"- **{text}**\n  - Deck: {deck_name}\n  - Tags: {tags}"

    # Custom note type - list all fields
    field_items = list(fields.items())
    if not field_items:
        return f"- (empty note)\n  - Deck: {deck_name}\n  - Tags: {tags}"

    if len(field_items) == 1:
        field_name, field_value = field_items[0]
        return f"- **{field_name}:** {field_value}\n  - Deck: {deck_name}\n  - Tags: {tags}"

    # Multiple fields - list them
    field_lines = "\n  - ".join([f"**{name}:** {value}" for name, value in field_items])
    return f"- Card:\n  - {field_lines}\n  - Deck: {deck_name}\n  - Tags: {tags}"


@click.group()
def cli() -> None:
    """Anki skill for reading and writing cards."""
    pass


@cli.command(name="read-cards")
@click.option("--query", required=True, help='Anki search query (e.g., "tag:german", "is:due")')
@click.option("--output", help="Output file path (prints to stdout if not specified)")
@click.option(
    "--format",
    type=click.Choice(["json", "csv", "markdown", "text"]),
    default="text",
    help="Output format (default: text)",
)
@click.option("--collection", help="Path to collection.anki2 file (auto-detected if not specified)")
def read_cards(*, query: str, output: str | None, format: str, collection: str | None) -> None:
    """Query and export cards from Anki collection."""
    col = None
    try:
        collection_path = Path(collection) if collection else None
        col = get_collection(collection_path=collection_path)

        # Find notes matching query
        note_ids = col.find_notes(query)

        if not note_ids:
            click.echo(f"No cards found matching query: {query}")
            return

        # Collect card data
        cards_data = []
        for note_id in note_ids:
            note = col.get_note(note_id)

            # Get deck name from first card
            card_ids = col.find_cards(f"nid:{note_id}")
            deck_name = "Unknown"
            if card_ids:
                card = col.get_card(card_ids[0])
                deck = col.decks.get(card.did)
                deck_name = deck["name"] if deck else "Unknown"

            # Extract fields
            fields = {}
            for field_name in note.keys():
                fields[field_name] = note[field_name]

            cards_data.append({
                "fields": fields,
                "tags": note.tags,
                "deck": deck_name,
            })

        # Output based on format
        if format == "json":
            output_data = json.dumps(cards_data, indent=2, ensure_ascii=False)
            if output:
                Path(output).write_text(output_data, encoding="utf-8")
                click.echo(f"Exported {len(cards_data)} cards to {output}")
            else:
                click.echo(output_data)

        elif format == "csv":
            # Build CSV with flexible columns based on all fields present
            # Collect all unique field names across all cards
            all_field_names = set()
            for card in cards_data:
                all_field_names.update(card["fields"].keys())

            # Sort field names for consistent ordering
            field_names = sorted(all_field_names)

            # Build CSV output
            output_buffer = StringIO()
            csv_writer = csv.writer(output_buffer)

            # Write header
            csv_writer.writerow(field_names + ["Tags", "Deck"])

            # Write data rows
            for card in cards_data:
                row = []
                for field_name in field_names:
                    row.append(card["fields"].get(field_name, ""))
                row.append(",".join(card["tags"]))
                row.append(card["deck"])
                csv_writer.writerow(row)

            output_data = output_buffer.getvalue()
            if output:
                Path(output).write_text(output_data, encoding="utf-8")
                click.echo(f"Exported {len(cards_data)} cards to {output}")
            else:
                click.echo(output_data)

        elif format == "markdown":
            output_lines = [f"# Anki Cards ({len(cards_data)} cards)\n"]
            for card in cards_data:
                output_lines.append(format_card_markdown(note=card, deck_name=card["deck"]))

            output_data = "\n".join(output_lines)
            if output:
                Path(output).write_text(output_data, encoding="utf-8")
                click.echo(f"Exported {len(cards_data)} cards to {output}")
            else:
                click.echo(output_data)

        else:  # text format
            click.echo(f"Found {len(cards_data)} cards:\n")
            for card in cards_data:
                click.echo(format_card_text(note=card, deck_name=card["deck"]))

    finally:
        if col:
            col.close()


@cli.command(name="list-decks")
@click.option("--collection", help="Path to collection.anki2 file (auto-detected if not specified)")
def list_decks(*, collection: str | None) -> None:
    """List all decks in the collection."""
    col = None
    try:
        collection_path = Path(collection) if collection else None
        col = get_collection(collection_path=collection_path)

        decks = col.decks.all()

        click.echo(f"Found {len(decks)} decks:\n")
        for deck in sorted(decks, key=lambda d: d["name"]):
            deck_id = deck["id"]
            deck_name = deck["name"]

            # Count cards in deck
            card_count = len(col.find_cards(f"did:{deck_id}"))

            click.echo(f"  {deck_name}: {card_count} cards")

    finally:
        if col:
            col.close()


@cli.command(name="list-note-types")
@click.option("--collection", help="Path to collection.anki2 file (auto-detected if not specified)")
def list_note_types(*, collection: str | None) -> None:
    """List all note types in the collection with their fields."""
    col = None
    try:
        collection_path = Path(collection) if collection else None
        col = get_collection(collection_path=collection_path)

        models = col.models.all()

        click.echo(f"Found {len(models)} note type(s):\n")
        for model in sorted(models, key=lambda m: m["name"]):
            model_name = model["name"]
            model_type = "Cloze" if model["type"] == 1 else "Standard"
            fields = [field["name"] for field in model["flds"]]

            click.echo(f"  {model_name} ({model_type})")
            click.echo(f"    Fields: {', '.join(fields)}")

    finally:
        if col:
            col.close()


@cli.command(name="describe-deck-note-types")
@click.option("--deck", required=True, help="Deck name")
@click.option("--collection", help="Path to collection.anki2 file (auto-detected if not specified)")
def describe_deck_note_types(*, deck: str, collection: str | None) -> None:
    """Show note types used in a specific deck with sample data."""
    col = None
    try:
        collection_path = Path(collection) if collection else None
        col = get_collection(collection_path=collection_path)

        # Find deck by name
        deck_obj = col.decks.by_name(deck)
        if not deck_obj:
            raise click.ClickException(f"Deck not found: {deck}")

        # Find all notes in deck
        note_ids = col.find_notes(f"deck:{deck}")
        if not note_ids:
            click.echo(f"No cards found in deck: {deck}")
            return

        # Collect note types and sample cards
        note_type_data = {}
        for note_id in note_ids:
            note = col.get_note(note_id)
            model = col.models.get(note.mid)
            if not model:
                continue

            model_name = model["name"]
            if model_name not in note_type_data:
                model_type = "Cloze" if model["type"] == 1 else "Standard"
                fields = [field["name"] for field in model["flds"]]
                note_type_data[model_name] = {
                    "type": model_type,
                    "fields": fields,
                    "samples": [],
                }

            # Add sample if we have fewer than 3
            if len(note_type_data[model_name]["samples"]) < 3:
                sample_fields = {}
                for field_name in note.keys():
                    sample_fields[field_name] = note[field_name]
                note_type_data[model_name]["samples"].append(sample_fields)

        # Output
        click.echo(f"Deck: {deck}")
        click.echo(f"Found {len(note_type_data)} note type(s) in use:\n")

        for model_name in sorted(note_type_data.keys()):
            data = note_type_data[model_name]
            click.echo(f"  {model_name} ({data['type']})")
            click.echo(f"    Fields: {', '.join(data['fields'])}")
            click.echo("    Sample cards:")

            for i, sample in enumerate(data["samples"], 1):
                click.echo(f"      Sample {i}:")
                for field_name, field_value in sample.items():
                    # Truncate long values
                    display_value = field_value[:80] + "..." if len(field_value) > 80 else field_value
                    # Replace newlines with spaces for cleaner output
                    display_value = display_value.replace("\n", " ")
                    click.echo(f"        {field_name}: {display_value}")
            click.echo()

    finally:
        if col:
            col.close()


@cli.command(name="describe-deck")
@click.option("--deck", required=True, help="Deck name")
@click.option("--collection", help="Path to collection.anki2 file (auto-detected if not specified)")
def describe_deck(*, deck: str, collection: str | None) -> None:
    """Show detailed information about a specific deck."""
    col = None
    try:
        collection_path = Path(collection) if collection else None
        col = get_collection(collection_path=collection_path)

        # Find deck by name
        deck_obj = col.decks.by_name(deck)
        if not deck_obj:
            raise click.ClickException(f"Deck not found: {deck}")

        deck_id = deck_obj["id"]

        # Count cards
        total_cards = len(col.find_cards(f"did:{deck_id}"))
        new_cards = len(col.find_cards(f"did:{deck_id} is:new"))
        due_cards = len(col.find_cards(f"did:{deck_id} is:due"))
        suspended_cards = len(col.find_cards(f"did:{deck_id} is:suspended"))

        click.echo(f"Deck: {deck}")
        click.echo(f"  Total cards: {total_cards}")
        click.echo(f"  New: {new_cards}")
        click.echo(f"  Due: {due_cards}")
        click.echo(f"  Suspended: {suspended_cards}")

        # Get unique tags in deck
        note_ids = col.find_notes(f"deck:{deck}")
        all_tags = set()
        for note_id in note_ids:
            note = col.get_note(note_id)
            all_tags.update(note.tags)

        if all_tags:
            click.echo(f"  Tags: {', '.join(sorted(all_tags))}")

    finally:
        if col:
            col.close()


@cli.command(name="add-cards")
@click.option("--deck", required=True, help="Target deck name")
@click.option("--note-type", default="Basic", help="Note type name (default: Basic)")
@click.option("--input", "input_file", help="CSV or JSON file with card data")
@click.option("--front", help="Card front (for single card)")
@click.option("--back", help="Card back (for single card)")
@click.option("--cloze-text", help="Cloze Text field (convenience for single Cloze card)")
@click.option("--cloze-extra", help="Cloze Extra field (optional, for single Cloze card)")
@click.option("--tags", help="Comma-separated tags (for single card)")
@click.option("--collection", help="Path to collection.anki2 file (auto-detected if not specified)")
def add_cards(
    *,
    deck: str,
    note_type: str,
    input_file: str | None,
    front: str | None,
    back: str | None,
    cloze_text: str | None,
    cloze_extra: str | None,
    tags: str | None,
    collection: str | None,
) -> None:
    """Add new cards to Anki collection. Requires Anki to be closed."""
    col = None
    try:
        collection_path = Path(collection) if collection else None
        col = get_collection(collection_path=collection_path)

        # Find deck by name
        deck_obj = col.decks.by_name(deck)
        if not deck_obj:
            raise click.ClickException(f"Deck not found: {deck}. Use list-decks to see available decks.")

        deck_id = deck_obj["id"]

        # Determine input source
        cards_to_add = []

        if input_file:
            # Load from file
            input_path = Path(input_file)
            if not input_path.exists():
                raise click.ClickException(f"Input file not found: {input_file}")

            if input_path.suffix.lower() == ".json":
                # JSON format
                data = json.loads(input_path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    raise click.ClickException("JSON file must contain an array of card objects")

                for item in data:
                    if not isinstance(item, dict):
                        raise click.ClickException("Each card must be an object")

                    # Extract tags (common for all formats)
                    card_tags = item.get("tags", [])
                    if isinstance(card_tags, str):
                        card_tags = [t.strip() for t in card_tags.split(",")]

                    # Support multiple input formats:
                    # 1. Explicit fields: {"fields": {"Text": "...", "Extra": "..."}, "tags": [...]}
                    # 2. Legacy front/back: {"front": "...", "back": "...", "tags": [...]}
                    # 3. Flexible keys: {"text": "...", "extra": "...", "tags": [...]}

                    if "fields" in item:
                        # Explicit fields format
                        cards_to_add.append({
                            "fields": item["fields"],
                            "tags": card_tags,
                        })
                    elif "front" in item and "back" in item:
                        # Legacy front/back format (backward compatible)
                        cards_to_add.append({
                            "front": item["front"],
                            "back": item["back"],
                            "tags": card_tags,
                        })
                    else:
                        # Flexible format - pass all fields through for case-insensitive matching
                        card_dict = {k: v for k, v in item.items() if k != "tags"}
                        card_dict["tags"] = card_tags
                        cards_to_add.append(card_dict)

            elif input_path.suffix.lower() == ".csv":
                # CSV format with flexible column mapping
                with input_path.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Extract tags if present
                        card_tags = []
                        if "Tags" in row and row["Tags"]:
                            card_tags = [t.strip() for t in row["Tags"].split(",")]

                        # Support flexible CSV formats:
                        # 1. Standard Front/Back columns (legacy)
                        # 2. Any columns matching note type field names (case-insensitive)

                        # Pass all non-Tags columns through for flexible matching
                        card_dict = {k: v for k, v in row.items() if k != "Tags" and v}  # Skip empty values
                        card_dict["tags"] = card_tags
                        cards_to_add.append(card_dict)
            else:
                raise click.ClickException("Input file must be .json or .csv")

        elif cloze_text:
            # Single Cloze card from arguments
            card_tags = []
            if tags:
                card_tags = [t.strip() for t in tags.split(",")]

            # Validate Cloze deletion syntax
            if not _has_cloze_deletion(cloze_text):
                raise click.ClickException(
                    "Cloze Text field must contain at least one cloze deletion.\n"
                    "Use syntax: {{c1::text}}, {{c2::text}}, etc.\n"
                    "Example: {{c1::Berlin}} is the capital of {{c2::Germany}}"
                )

            cards_to_add.append({
                "fields": {
                    "Text": cloze_text,
                    "Extra": cloze_extra or "",
                },
                "tags": card_tags,
            })
        elif front and back:
            # Single Basic card from arguments
            card_tags = []
            if tags:
                card_tags = [t.strip() for t in tags.split(",")]

            cards_to_add.append({
                "front": front,
                "back": back,
                "tags": card_tags,
            })
        else:
            raise click.ClickException(
                "Must provide either:\n"
                "  --input file, or\n"
                "  --front/--back arguments (for Basic cards), or\n"
                "  --cloze-text argument (for Cloze cards)"
            )

        # Get the specified note type
        model = col.models.by_name(note_type)
        if not model:
            # List available note types to help user
            available_models = col.models.all()
            model_names = [m["name"] for m in available_models]
            model_list = "\n  - ".join(sorted(model_names))
            raise click.ClickException(
                f"Note type '{note_type}' not found in collection.\n\n"
                f"Available note types:\n  - {model_list}\n\n"
                f"Use 'list-note-types' command to see field structures."
            )

        # Add cards using high-level API
        added_count = 0
        is_cloze_model = model.get("type") == 1  # 1 = Cloze note type

        for card_data in cards_to_add:
            # Create new note
            note = col.new_note(model)

            # Map input fields to note type fields
            field_mapping = map_input_to_note_fields(card_data=card_data, model=model)

            # Validate Cloze cards have proper syntax
            if is_cloze_model and "Text" in field_mapping:
                text_value = field_mapping["Text"]
                if not _has_cloze_deletion(text_value):
                    click.echo(
                        f"Warning: Skipping Cloze card without cloze deletion syntax: "
                        f"'{text_value[:50]}...'" if len(text_value) > 50 else f"'{text_value}'"
                    )
                    continue

            # Set fields
            for field_name, field_value in field_mapping.items():
                note[field_name] = field_value

            # Set tags
            if card_data["tags"]:
                note.tags = card_data["tags"]

            # Add to collection (high-level API, no direct SQL)
            col.add_note(note, deck_id)
            added_count += 1

        # Save changes
        col.save()

        click.echo(f"Successfully added {added_count} card(s) to deck '{deck}'")

    finally:
        if col:
            col.close()


if __name__ == "__main__":
    cli()
