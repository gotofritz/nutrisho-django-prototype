"""Tests for Anki skill."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from main import (
    add_cards,
    describe_deck,
    describe_deck_note_types,
    format_card_markdown,
    format_card_text,
    get_collection,
    get_collection_path,
    list_decks,
    list_note_types,
    read_cards,
)


def test_get_collection_path_from_env(monkeypatch, tmp_path):
    """Test collection path detection from environment variable."""

    # Create a temporary collection file
    collection_file = tmp_path / "collection.anki2"
    collection_file.touch()

    monkeypatch.setenv("ANKI_COLLECTION_PATH", str(collection_file))

    result = get_collection_path()
    assert result == collection_file


def test_get_collection_path_auto_detect_macos(monkeypatch):
    """Test collection path auto-detection on macOS."""
    # Clear environment variable
    monkeypatch.delenv("ANKI_COLLECTION_PATH", raising=False)

    # Mock Path.home() and make macOS path exist
    mock_home = Path("/Users/testuser")
    expected_path = mock_home / "Library" / "Application Support" / "Anki2" / "User 1" / "collection.anki2"

    with patch("main.Path.home", return_value=mock_home):
        # Mock exists to return True only for expected path

        def mock_exists(self):
            if self == expected_path:
                return True
            return False

        with patch.object(Path, "exists", mock_exists):
            result = get_collection_path()
            assert result == expected_path


def test_format_card_text():
    """Test card text formatting."""
    note = {
        "fields": {"Front": "Hello", "Back": "Hallo"},
        "tags": ["german", "greetings"],
    }

    result = format_card_text(note=note, deck_name="Test Deck")

    assert "Test Deck" in result
    assert "Hello" in result
    assert "Hallo" in result
    assert "german" in result
    assert "greetings" in result


def test_format_card_markdown():
    """Test card markdown formatting."""
    note = {
        "fields": {"Front": "Word", "Back": "Translation"},
        "tags": ["vocabulary"],
    }

    result = format_card_markdown(note=note, deck_name="Vocab")

    assert "**Word**" in result
    assert "Translation" in result
    assert "Vocab" in result
    assert "vocabulary" in result
    assert result.startswith("- ")


def test_format_card_text_cloze():
    """Test text formatting for Cloze note type."""
    note = {
        "fields": {"Text": "{{c1::Berlin}} is the capital", "Extra": "Geography"},
        "tags": ["german", "geography"],
    }

    result = format_card_text(note=note, deck_name="German")

    assert "German" in result
    assert "{{c1::Berlin}} is the capital" in result
    assert "Geography" in result
    assert "german" in result


def test_format_card_markdown_cloze():
    """Test markdown formatting for Cloze note type."""
    note = {
        "fields": {"Text": "{{c1::Tokyo}} is capital of Japan"},
        "tags": ["geography"],
    }

    result = format_card_markdown(note=note, deck_name="Geography")

    assert "**{{c1::Tokyo}} is capital of Japan**" in result
    assert "Geography" in result
    assert "geography" in result


def test_format_card_text_custom_fields():
    """Test text formatting for custom note type with multiple fields."""
    note = {
        "fields": {
            "Prompt1": "_____ ist dort",
            "Prompt2": "D- Flughafen",
            "Answer": "Der Flughafen ist dort",
        },
        "tags": ["fsi", "drill"],
    }

    result = format_card_text(note=note, deck_name="DEU FSI")

    assert "DEU FSI" in result
    assert "Prompt1:" in result or "_____ ist dort" in result
    assert "fsi" in result


def test_format_card_markdown_custom_fields():
    """Test markdown formatting for custom note type."""
    note = {
        "fields": {
            "Field1": "Value 1",
            "Field2": "Value 2",
        },
        "tags": ["custom"],
    }

    result = format_card_markdown(note=note, deck_name="Custom Deck")

    assert "Field1" in result
    assert "Value 1" in result
    assert "Field2" in result
    assert "Value 2" in result
    assert "Custom Deck" in result


def test_get_collection_nonexistent_env_path(monkeypatch):
    """Test error handling for non-existent env path."""
    monkeypatch.setenv("ANKI_COLLECTION_PATH", "/nonexistent/path.anki2")

    with pytest.raises(click.ClickException, match="points to non-existent file"):
        get_collection_path()


def test_get_collection_path_not_found(monkeypatch):
    """Test error when no collection path can be found."""
    # Clear env var and mock all paths to not exist
    monkeypatch.delenv("ANKI_COLLECTION_PATH", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    with patch("main.Path.home", return_value=Path("/tmp/testuser")):
        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(click.ClickException, match="Could not locate Anki collection"):
                get_collection_path()


def test_format_output_json():
    """Test JSON output formatting for cards."""
    cards_data = [
        {
            "fields": {"Front": "Hello", "Back": "Hallo"},
            "tags": ["german", "greetings"],
            "deck": "German",
        },
        {
            "fields": {"Front": "Goodbye", "Back": "Auf Wiedersehen"},
            "tags": ["german"],
            "deck": "German",
        },
    ]

    output = json.dumps(cards_data, indent=2, ensure_ascii=False)
    parsed = json.loads(output)

    assert len(parsed) == 2
    assert parsed[0]["fields"]["Front"] == "Hello"
    assert parsed[0]["deck"] == "German"
    assert "german" in parsed[0]["tags"]


def test_format_output_csv():
    """Test CSV output formatting for cards."""
    cards_data = [
        {
            "fields": {"Front": "Hello", "Back": "Hallo"},
            "tags": ["german", "greetings"],
            "deck": "German",
        },
    ]

    output_lines = ["Front,Back,Tags,Deck"]
    for card in cards_data:
        front = card["fields"].get("Front", "")
        back = card["fields"].get("Back", "")
        tags = ",".join(card["tags"])
        deck = card["deck"]
        output_lines.append(f'"{front}","{back}","{tags}","{deck}"')

    csv_output = "\n".join(output_lines)

    assert "Front,Back,Tags,Deck" in csv_output
    assert '"Hello"' in csv_output
    assert '"Hallo"' in csv_output
    assert '"german,greetings"' in csv_output
    assert '"German"' in csv_output


def test_get_collection_with_lock_error():
    """Test handling of locked collection (Anki running)."""
    # Create a custom exception class that looks like DBError
    class DBError(Exception):
        pass

    mock_error = DBError("database is locked")

    # Patch both Collection and DBError so the except clause can catch it
    with patch("main.Collection", side_effect=mock_error), patch("main.DBError", DBError):
        with pytest.raises(click.ClickException, match="Collection is locked"):
            get_collection()


def test_read_cards_with_mock_collection(tmp_path):
    """Test read_cards command with mocked Collection."""
    # Create mock collection
    mock_col = MagicMock()
    mock_note = MagicMock()
    mock_note.__getitem__ = lambda self, key: {"Front": "Test", "Back": "Answer"}[key]
    mock_note.keys.return_value = ["Front", "Back"]
    mock_note.tags = ["test-tag"]

    mock_card = MagicMock()
    mock_card.did = 1

    mock_deck = {"name": "Test Deck"}

    mock_col.find_notes.return_value = [1001]
    mock_col.get_note.return_value = mock_note
    mock_col.find_cards.return_value = [2001]
    mock_col.get_card.return_value = mock_card
    mock_col.decks.get.return_value = mock_deck

    output_file = tmp_path / "output.json"

    with patch("main.get_collection", return_value=mock_col):
        read_cards.callback(
            query="tag:test",
            output=str(output_file),
            format="json",
            collection=None,
        )

    # Verify file was created
    assert output_file.exists()

    # Verify content
    with open(output_file) as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["fields"]["Front"] == "Test"
        assert data[0]["deck"] == "Test Deck"
        assert "test-tag" in data[0]["tags"]

    # Verify collection was closed
    mock_col.close.assert_called_once()


def test_read_cards_empty_results():
    """Test read_cards with no matching cards."""
    mock_col = MagicMock()
    mock_col.find_notes.return_value = []

    with patch("main.get_collection", return_value=mock_col):
        # This will exit early with "No cards found" message
        read_cards.callback(query="nonexistent:tag", output=None, format="text", collection=None)

    mock_col.close.assert_called_once()


def test_add_cards_from_json(tmp_path):
    """Test adding cards from JSON file."""
    # Create test JSON file
    test_data = [
        {"front": "Hello", "back": "Hallo", "tags": ["german"]},
        {"front": "Goodbye", "back": "Tschüss", "tags": ["german", "informal"]},
    ]

    json_file = tmp_path / "cards.json"
    json_file.write_text(json.dumps(test_data), encoding="utf-8")

    # Mock collection and deck
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 1,
        "name": "Basic",
        "flds": [
            {"name": "Front"},
            {"name": "Back"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    mock_note = MagicMock()
    mock_note.__setitem__ = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="Test Deck",
            note_type="Basic",
            input_file=str(json_file),
            front=None,
            back=None,
            cloze_text=None,
            cloze_extra=None,
            tags=None,
            collection=None,
        )

    # Verify add_note was called twice
    assert mock_col.add_note.call_count == 2
    mock_col.save.assert_called_once()
    mock_col.close.assert_called_once()


def test_add_cards_from_csv(tmp_path):
    """Test adding cards from CSV file."""
    # Create test CSV file
    csv_file = tmp_path / "cards.csv"
    csv_file.write_text(
        'Front,Back,Tags\n"Word","Wort","german,vocabulary"\n"House","Haus","german"',
        encoding="utf-8",
    )

    # Mock collection
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck
    mock_model = {
        "id": 1,
        "flds": [
            {"name": "Front"},
            {"name": "Back"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model
    mock_note = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="Test Deck",
            note_type="Basic",
            input_file=str(csv_file),
            front=None,
            back=None,
            cloze_text=None,
            cloze_extra=None,
            tags=None,
            collection=None,
        )

    # Verify two cards were added
    assert mock_col.add_note.call_count == 2
    mock_col.save.assert_called_once()


def test_add_cards_single_via_args():
    """Test adding a single card via command line arguments."""
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck
    mock_model = {
        "id": 1,
        "flds": [
            {"name": "Front"},
            {"name": "Back"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model
    mock_note = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="Quick Deck",
            note_type="Basic",
            input_file=None,
            front="Question",
            back="Answer",
            cloze_text=None,
            cloze_extra=None,
            tags="quick,test",
            collection=None,
        )

    # Verify one card was added
    mock_col.add_note.assert_called_once()
    mock_col.save.assert_called_once()


def test_add_cards_deck_not_found():
    """Test error when target deck doesn't exist."""
    mock_col = MagicMock()
    mock_col.decks.by_name.return_value = None

    with patch("main.get_collection", return_value=mock_col):
        with pytest.raises(click.ClickException, match="Deck not found"):
            add_cards.callback(
                deck="Nonexistent Deck",
                note_type="Basic",
                input_file=None,
                front="Test",
                back="Test",
                cloze_text=None,
                cloze_extra=None,
                tags=None,
                collection=None,
            )

    mock_col.close.assert_called_once()


def test_add_cards_missing_input():
    """Test error when neither file nor args provided."""
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    with patch("main.get_collection", return_value=mock_col):
        with pytest.raises(click.ClickException, match="Must provide either"):
            add_cards.callback(
                deck="Test Deck",
                note_type="Basic",
                input_file=None,
                front=None,
                back=None,
                cloze_text=None,
                cloze_extra=None,
                tags=None,
                collection=None,
            )


def test_add_cards_invalid_note_type():
    """Test error when note type doesn't exist."""
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck
    mock_col.models.by_name.return_value = None  # Note type not found
    mock_col.models.all.return_value = [
        {"name": "Basic"},
        {"name": "Cloze"},
        {"name": "Custom"},
    ]

    with patch("main.get_collection", return_value=mock_col):
        with pytest.raises(click.ClickException, match="Note type 'InvalidType' not found"):
            add_cards.callback(
                deck="Test Deck",
                note_type="InvalidType",
                input_file=None,
                front="Test",
                back="Test",
                cloze_text=None,
                cloze_extra=None,
                tags=None,
                collection=None,
            )

    mock_col.close.assert_called_once()


def test_list_decks():
    """Test listing all decks."""
    mock_col = MagicMock()
    mock_col.decks.all.return_value = [
        {"id": 1, "name": "German"},
        {"id": 2, "name": "Spanish"},
        {"id": 3, "name": "French"},
    ]
    mock_col.find_cards.side_effect = lambda query: [1, 2, 3] if "did:1" in query else [4, 5]

    with patch("main.get_collection", return_value=mock_col):
        # Just verify it doesn't crash - output goes to stdout
        list_decks.callback(collection=None)

    mock_col.close.assert_called_once()


def test_describe_deck():
    """Test describing a specific deck."""
    mock_col = MagicMock()
    mock_deck = {"id": 1, "name": "Test Deck"}
    mock_col.decks.by_name.return_value = mock_deck

    # Mock card counts for different queries
    def find_cards_side_effect(query):
        if "is:new" in query:
            return [1, 2, 3]
        elif "is:due" in query:
            return [4, 5]
        elif "is:suspended" in query:
            return [6]
        else:
            return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    mock_col.find_cards.side_effect = find_cards_side_effect

    mock_note = MagicMock()
    mock_note.tags = ["vocabulary", "basics"]
    mock_col.find_notes.return_value = [101, 102]
    mock_col.get_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        describe_deck.callback(deck="Test Deck", collection=None)

    mock_col.close.assert_called_once()


def test_describe_deck_not_found():
    """Test error when describing non-existent deck."""
    mock_col = MagicMock()
    mock_col.decks.by_name.return_value = None

    with patch("main.get_collection", return_value=mock_col):
        with pytest.raises(click.ClickException, match="Deck not found"):
            describe_deck.callback(deck="Nonexistent", collection=None)


def test_list_note_types():
    """Test listing all note types in the collection."""
    mock_col = MagicMock()
    mock_col.models.all.return_value = [
        {
            "name": "Basic",
            "type": 0,
            "flds": [
                {"name": "Front"},
                {"name": "Back"},
            ],
        },
        {
            "name": "Cloze",
            "type": 1,
            "flds": [
                {"name": "Text"},
                {"name": "Extra"},
            ],
        },
        {
            "name": "FSI German Drills",
            "type": 0,
            "flds": [
                {"name": "Prompt1"},
                {"name": "Prompt2"},
                {"name": "Answer"},
            ],
        },
    ]

    with patch("main.get_collection", return_value=mock_col):
        list_note_types.callback(collection=None)

    mock_col.close.assert_called_once()


def test_describe_deck_note_types():
    """Test describing note types used in a specific deck."""
    mock_col = MagicMock()
    mock_deck = {"id": 1, "name": "Test Deck"}
    mock_col.decks.by_name.return_value = mock_deck
    mock_col.find_notes.return_value = [1001, 1002, 1003]

    # Mock three notes with different note types
    mock_note_basic = MagicMock()
    mock_note_basic.mid = 100
    mock_note_basic.keys.return_value = ["Front", "Back"]
    mock_note_basic.__getitem__ = lambda self, key: {"Front": "Hello", "Back": "Hallo"}[key]

    mock_note_cloze = MagicMock()
    mock_note_cloze.mid = 200
    mock_note_cloze.keys.return_value = ["Text", "Extra"]
    mock_note_cloze.__getitem__ = lambda self, key: {"Text": "{{c1::Berlin}} is the capital", "Extra": "Geography"}[key]

    mock_note_fsi = MagicMock()
    mock_note_fsi.mid = 300
    mock_note_fsi.keys.return_value = ["Prompt1", "Prompt2", "Answer"]
    mock_note_fsi.__getitem__ = lambda self, key: {"Prompt1": "_____ ist dort.", "Prompt2": "D- Flughafen", "Answer": "Der Flughafen ist dort."}[key]

    mock_col.get_note.side_effect = [mock_note_basic, mock_note_cloze, mock_note_fsi]

    # Mock models
    mock_model_basic = {
        "name": "Basic",
        "type": 0,
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    mock_model_cloze = {
        "name": "Cloze",
        "type": 1,
        "flds": [{"name": "Text"}, {"name": "Extra"}],
    }
    mock_model_fsi = {
        "name": "FSI German Drills",
        "type": 0,
        "flds": [{"name": "Prompt1"}, {"name": "Prompt2"}, {"name": "Answer"}],
    }

    def get_model_side_effect(mid):
        if mid == 100:
            return mock_model_basic
        elif mid == 200:
            return mock_model_cloze
        elif mid == 300:
            return mock_model_fsi
        return None

    mock_col.models.get.side_effect = get_model_side_effect

    with patch("main.get_collection", return_value=mock_col):
        describe_deck_note_types.callback(deck="Test Deck", collection=None)

    mock_col.close.assert_called_once()


def test_describe_deck_note_types_not_found():
    """Test error when describing note types for non-existent deck."""
    mock_col = MagicMock()
    mock_col.decks.by_name.return_value = None

    with patch("main.get_collection", return_value=mock_col):
        with pytest.raises(click.ClickException, match="Deck not found"):
            describe_deck_note_types.callback(deck="Nonexistent", collection=None)


def test_describe_deck_note_types_empty_deck():
    """Test describing note types for a deck with no cards."""
    mock_col = MagicMock()
    mock_deck = {"id": 1, "name": "Empty Deck"}
    mock_col.decks.by_name.return_value = mock_deck
    mock_col.find_notes.return_value = []

    with patch("main.get_collection", return_value=mock_col):
        describe_deck_note_types.callback(deck="Empty Deck", collection=None)

    mock_col.close.assert_called_once()


def test_add_cards_cloze_explicit_fields(tmp_path):
    """Test adding Cloze cards with explicit fields format."""
    # Create test JSON with explicit fields
    test_data = [
        {
            "fields": {
                "Text": "{{c1::Berlin}} is the capital of Germany",
                "Extra": "Geography",
            },
            "tags": ["german", "geography"],
        },
    ]

    json_file = tmp_path / "cloze_cards.json"
    json_file.write_text(json.dumps(test_data), encoding="utf-8")

    # Mock collection with Cloze note type
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 2,
        "name": "Cloze",
        "flds": [
            {"name": "Text"},
            {"name": "Extra"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    mock_note = MagicMock()
    mock_note.__setitem__ = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="German",
            note_type="Cloze",
            input_file=str(json_file),
            front=None,
            back=None,
            cloze_text=None,
            cloze_extra=None,
            tags=None,
            collection=None,
        )

    # Verify note fields were set correctly
    mock_note.__setitem__.assert_any_call("Text", "{{c1::Berlin}} is the capital of Germany")
    mock_note.__setitem__.assert_any_call("Extra", "Geography")
    mock_col.add_note.assert_called_once()
    mock_col.save.assert_called_once()


def test_add_cards_custom_note_type_flexible(tmp_path):
    """Test adding cards with custom note type using flexible field matching."""
    # Create test JSON with lowercase field names (case-insensitive matching)
    test_data = [
        {
            "prompt1": "_____ ist dort.",
            "prompt2": "D- Flughafen",
            "answer": "Der Flughafen ist dort.",
            "tags": ["fsi", "drill"],
        },
    ]

    json_file = tmp_path / "fsi_cards.json"
    json_file.write_text(json.dumps(test_data), encoding="utf-8")

    # Mock collection with custom FSI note type
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 3,
        "name": "FSI German Drills",
        "flds": [
            {"name": "Prompt1"},
            {"name": "Prompt2"},
            {"name": "Answer"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    mock_note = MagicMock()
    mock_note.__setitem__ = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="DEU FSI",
            note_type="FSI German Drills",
            input_file=str(json_file),
            front=None,
            back=None,
            cloze_text=None,
            cloze_extra=None,
            tags=None,
            collection=None,
        )

    # Verify case-insensitive field mapping worked
    mock_note.__setitem__.assert_any_call("Prompt1", "_____ ist dort.")
    mock_note.__setitem__.assert_any_call("Prompt2", "D- Flughafen")
    mock_note.__setitem__.assert_any_call("Answer", "Der Flughafen ist dort.")
    mock_col.add_note.assert_called_once()


def test_add_cards_csv_flexible_columns(tmp_path):
    """Test adding cards from CSV with flexible column names."""
    # Create CSV with custom columns
    csv_file = tmp_path / "custom_cards.csv"
    csv_file.write_text(
        'Text,Extra,Tags\n"{{c1::Tokyo}} is the capital","Asian capitals","geography"\n',
        encoding="utf-8",
    )

    # Mock collection with Cloze note type
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 2,
        "name": "Cloze",
        "flds": [
            {"name": "Text"},
            {"name": "Extra"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    mock_note = MagicMock()
    mock_note.__setitem__ = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="Geography",
            note_type="Cloze",
            input_file=str(csv_file),
            front=None,
            back=None,
            cloze_text=None,
            cloze_extra=None,
            tags=None,
            collection=None,
        )

    # Verify fields were mapped correctly
    mock_note.__setitem__.assert_any_call("Text", "{{c1::Tokyo}} is the capital")
    mock_note.__setitem__.assert_any_call("Extra", "Asian capitals")
    mock_col.add_note.assert_called_once()


def test_add_cards_invalid_field_name():
    """Test error when providing invalid field name in explicit fields format."""
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 2,
        "name": "Cloze",
        "flds": [
            {"name": "Text"},
            {"name": "Extra"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    # Card data with invalid field name
    from main import map_input_to_note_fields

    card_data = {
        "fields": {
            "InvalidField": "Some text",
            "Extra": "Extra info",
        },
        "tags": [],
    }

    with pytest.raises(click.ClickException, match="Field 'InvalidField' not found"):
        map_input_to_note_fields(card_data=card_data, model=mock_model)


def test_add_cards_front_back_with_wrong_note_type():
    """Test error when using front/back with non-Basic note type."""
    mock_model = {
        "id": 2,
        "name": "Cloze",
        "flds": [
            {"name": "Text"},
            {"name": "Extra"},
        ],
    }

    from main import map_input_to_note_fields

    card_data = {
        "front": "Question",
        "back": "Answer",
        "tags": [],
    }

    with pytest.raises(click.ClickException, match="Note type does not have Front/Back fields"):
        map_input_to_note_fields(card_data=card_data, model=mock_model)


def test_add_cards_no_matching_fields():
    """Test error when no fields can be mapped."""
    mock_model = {
        "id": 2,
        "name": "Custom",
        "flds": [
            {"name": "Field1"},
            {"name": "Field2"},
        ],
    }

    from main import map_input_to_note_fields

    card_data = {
        "wrongfield": "value",
        "anotherfield": "value",
        "tags": [],
    }

    with pytest.raises(click.ClickException, match="Could not map any input fields"):
        map_input_to_note_fields(card_data=card_data, model=mock_model)


def test_add_cards_cloze_via_cli_shortcut():
    """Test adding a single Cloze card via --cloze-text shortcut."""
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 2,
        "name": "Cloze",
        "type": 1,  # Cloze type
        "flds": [
            {"name": "Text"},
            {"name": "Extra"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    mock_note = MagicMock()
    mock_note.__setitem__ = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="Quick Cloze",
            note_type="Cloze",
            input_file=None,
            front=None,
            back=None,
            cloze_text="{{c1::Berlin}} is the capital of {{c2::Germany}}",
            cloze_extra="Geography",
            tags="europe,capitals",
            collection=None,
        )

    # Verify fields were set correctly
    mock_note.__setitem__.assert_any_call("Text", "{{c1::Berlin}} is the capital of {{c2::Germany}}")
    mock_note.__setitem__.assert_any_call("Extra", "Geography")
    mock_col.add_note.assert_called_once()
    mock_col.save.assert_called_once()


def test_add_cards_cloze_invalid_syntax():
    """Test error when cloze-text doesn't have cloze deletion syntax."""
    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    with patch("main.get_collection", return_value=mock_col):
        with pytest.raises(click.ClickException, match="must contain at least one cloze deletion"):
            add_cards.callback(
                deck="Quick Cloze",
                note_type="Cloze",
                input_file=None,
                front=None,
                back=None,
                cloze_text="Berlin is the capital of Germany",  # Missing {{c1::...}} syntax
                cloze_extra=None,
                tags=None,
                collection=None,
            )


def test_has_cloze_deletion():
    """Test the _has_cloze_deletion validation function."""
    from main import _has_cloze_deletion

    # Valid cloze deletions
    assert _has_cloze_deletion("{{c1::Berlin}} is the capital")
    assert _has_cloze_deletion("The capital is {{c2::Berlin}}")
    assert _has_cloze_deletion("{{c1::Berlin::hint}} is a city")
    assert _has_cloze_deletion("{{c1::A}} and {{c2::B}}")

    # Invalid (no cloze deletion)
    assert not _has_cloze_deletion("Berlin is the capital")
    assert not _has_cloze_deletion("{{Berlin}}")  # Missing c1::
    assert not _has_cloze_deletion("{c1::Berlin}")  # Single braces
    assert not _has_cloze_deletion("")


def test_add_cards_batch_cloze_with_invalid_skips(tmp_path):
    """Test that batch Cloze import skips cards without cloze deletions."""
    # Create JSON with mix of valid and invalid Cloze cards
    json_file = tmp_path / "mixed_cloze.json"
    json_file.write_text(
        json.dumps([
            {
                "fields": {
                    "Text": "{{c1::Valid}} cloze card",
                    "Extra": "Good"
                },
                "tags": ["test"]
            },
            {
                "fields": {
                    "Text": "Invalid - no cloze deletion",
                    "Extra": "Bad"
                },
                "tags": ["test"]
            },
            {
                "fields": {
                    "Text": "Another {{c1::valid}} one",
                    "Extra": "Good"
                },
                "tags": ["test"]
            },
        ])
    )

    mock_col = MagicMock()
    mock_deck = {"id": 1}
    mock_col.decks.by_name.return_value = mock_deck

    mock_model = {
        "id": 2,
        "name": "Cloze",
        "type": 1,  # Cloze type
        "flds": [
            {"name": "Text"},
            {"name": "Extra"},
        ],
    }
    mock_col.models.by_name.return_value = mock_model

    mock_note = MagicMock()
    mock_note.__setitem__ = MagicMock()
    mock_col.new_note.return_value = mock_note

    with patch("main.get_collection", return_value=mock_col):
        add_cards.callback(
            deck="Test Cloze",
            note_type="Cloze",
            input_file=str(json_file),
            front=None,
            back=None,
            cloze_text=None,
            cloze_extra=None,
            tags=None,
            collection=None,
        )

    # Should have added only 2 cards (skipped the invalid one)
    assert mock_col.add_note.call_count == 2
    mock_col.save.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
