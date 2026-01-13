---
name: anki
description: Read cards from and write new cards to a local Anki installation
allowed-tools: Bash
---

# Anki Skill

Read and query existing Anki cards, or add new cards directly to your local Anki collection.

## Prerequisites

**For Write Operations:**
- Anki must be closed before adding cards
- Collection database will be locked if Anki is running

**Optional Configuration:**
```bash
# Custom collection path (auto-detected if not set)
export ANKI_COLLECTION_PATH="/path/to/collection.anki2"
```

## Available Commands

### read-cards
Query and export cards from your Anki collection using Anki search syntax.

```bash
# Export all cards with tag "german" as JSON
skill: anki read-cards --query "tag:german" --format json --output cards.json

# Export due cards as CSV
skill: anki read-cards --query "is:due" --format csv --output due.csv

# Show cards from a specific deck as markdown
skill: anki read-cards --query "deck:Vocabulary" --format markdown

# Query all cards (returns as text summary)
skill: anki read-cards --query ""
```

**Formats:**
- `json` - Structured data with all fields and metadata
- `csv` - Tabular format (Front, Back, Tags, Deck)
- `markdown` - Human-readable formatted list
- `text` - Simple text summary (default)

### list-decks
List all decks in your collection with card counts.

```bash
skill: anki list-decks
```

### describe-deck
Show detailed information about a specific deck.

```bash
skill: anki describe-deck --deck "German Vocabulary"
```

### list-note-types
List all note types in your collection with their field structures.

```bash
skill: anki list-note-types
```

**Output shows:**
- Note type name
- Type (Standard or Cloze)
- Field names

**Example output:**

```text
Found 3 note type(s):

  Basic (Standard)
    Fields: Front, Back

  Cloze (Cloze)
    Fields: Text, Extra

  FSI German Drills (Standard)
    Fields: Prompt1, Prompt2, Answer
```

### describe-deck-note-types
Show which note types are used in a specific deck with sample card data.

```bash
skill: anki describe-deck-note-types --deck "DEU FSI German Basic Course Drills"
```

**Output shows:**
- Note types present in the deck
- Field structure for each type
- Up to 3 sample cards with field values

**Use cases:**
- Discover note type names before creating cards
- Inspect field structure of custom note types
- Validate deck contents and structure

### add-cards
Add new cards to your Anki collection. **Requires Anki to be closed.**

Supports multiple note types: Basic, Cloze, and custom note types.

**Basic Examples:**

```bash
# Add Basic cards from CSV file (default note type)
skill: anki add-cards --input cards.csv --deck "Vocabulary"

# Add Basic cards from JSON file
skill: anki add-cards --input cards.json --deck "German"

# Add a single Basic card via arguments
skill: anki add-cards --deck "Quick" --front "Hello" --back "Hallo" --tags "german,greetings"
```

**Cloze Card Examples:**

```bash
# Add Cloze cards from JSON
skill: anki add-cards --input cloze.json --deck "Geography" --note-type "Cloze"
```

**Cloze JSON Format:**
```json
[
  {
    "fields": {
      "Text": "{{c1::Berlin}} is the capital of {{c2::Germany}}",
      "Extra": "European capitals"
    },
    "tags": ["geography", "europe"]
  }
]
```

**Cloze CSV Format:**
```csv
Text,Extra,Tags
"{{c1::Tokyo}} is the capital of Japan","Asian capitals","geography,asia"
"{{c1::Paris}} is in {{c2::France}}","European cities","geography,europe"
```

**Custom Note Type Examples (e.g., FSI German Drills):**

```bash
# Add cards with custom 3-field note type
skill: anki add-cards --input fsi.json --deck "DEU FSI" --note-type "FSI German Drills"
```

**Custom Note Type JSON Format:**
```json
[
  {
    "fields": {
      "Prompt1": "_____ ist dort.",
      "Prompt2": "D- Flughafen",
      "Answer": "Der Flughafen ist dort."
    },
    "tags": ["fsi", "drill"]
  }
]
```

**Flexible Format (case-insensitive field matching):**
```json
[
  {
    "prompt1": "_____ ist dort.",
    "prompt2": "D- Flughafen",
    "answer": "Der Flughafen ist dort.",
    "tags": ["fsi", "drill"]
  }
]
```

**Legacy Basic Format (backward compatible):**
```json
[
  {
    "front": "Word",
    "back": "Translation",
    "tags": ["tag1", "tag2"]
  }
]
```

**CSV Format (Basic):**
```csv
Front,Back,Tags
"Word","Translation","tag1,tag2"
```

## Supported Note Types

The skill supports any note type in your collection:

### Built-in Note Types

**Basic (default)**
- Fields: Front, Back
- Format: `{"front": "...", "back": "..."}` or `{"fields": {"Front": "...", "Back": "..."}}`
- Use: Standard flashcards

**Cloze**
- Fields: Text, Extra
- Format: `{"fields": {"Text": "{{c1::word}}", "Extra": "hint"}}`
- Use: Fill-in-the-blank cards with cloze deletions

### Custom Note Types

Any custom note type in your collection is supported. Use discovery commands to find them:

```bash
# List all note types with their fields
skill: anki list-note-types

# See which note types are used in a specific deck
skill: anki describe-deck-note-types --deck "Your Deck"
```

### Input Format Options

**1. Explicit Fields (recommended for non-Basic types):**
```json
{"fields": {"Field1": "value", "Field2": "value"}, "tags": [...]}
```

**2. Legacy Front/Back (Basic only):**
```json
{"front": "value", "back": "value", "tags": [...]}
```

**3. Case-Insensitive Matching:**
```json
{"field1": "value", "field2": "value", "tags": [...]}
```
Field names are matched case-insensitively to note type fields.

## Usage Notes

- Dependencies auto-installed via PEP 723 inline metadata (`anki>=25.9.2`)
- Collection path auto-detected: `~/Library/Application Support/Anki2/User 1/collection.anki2` (macOS)
- Override with `--collection` argument or `ANKI_COLLECTION_PATH` environment variable
- All write operations use high-level Anki API (no direct database writes)
- Collection is properly closed after each operation
- Default note type is "Basic" - specify `--note-type` for other types

## Error Handling

**Common Errors:**

- `Collection is locked` - Anki is currently running. Close it and try again.
- `Deck not found` - Specified deck doesn't exist. Use `list-decks` to see available decks.
- `Collection not found` - Cannot locate Anki collection. Specify path with `--collection`.
- `Note type 'X' not found` - Specified note type doesn't exist. Use `list-note-types` to see available types.

## Troubleshooting

### Field Mapping Issues

**Problem:** `Field 'X' not found in note type`

**Solution:**
- Use `list-note-types` to see exact field names (case-sensitive for explicit format)
- Or use `describe-deck-note-types --deck "Your Deck"` to see fields with examples
- Field names must match exactly when using explicit `fields` format

**Problem:** `Could not map any input fields`

**Solution:**
- Check field names match note type fields (case-insensitive matching)
- For custom note types, use explicit `fields` format:
  ```json
  {"fields": {"ExactFieldName": "value"}, "tags": [...]}
  ```

**Problem:** `Note type does not have Front/Back fields`

**Solution:**
- Using `{"front": "...", "back": "..."}` only works with Basic note type
- For other note types, use explicit fields or case-insensitive matching:
  ```json
  {"fields": {"Text": "...", "Extra": "..."}, "tags": [...]}
  ```

### Cloze Card Issues

**Problem:** Cloze cards not working

**Solution:**
- Ensure note type is "Cloze": `--note-type "Cloze"`
- Use proper cloze deletion syntax: `{{c1::text}}`, `{{c2::text}}`, etc.
- Text field must contain at least one cloze deletion
- Example: `{"fields": {"Text": "{{c1::Berlin}} is capital", "Extra": "Geography"}}`

## Security Considerations

- **Safe API Usage**: Only uses high-level Anki API methods (`col.add_note`, `col.find_notes`)
- **No Direct SQL**: Never writes directly to database to prevent corruption
- **Resource Cleanup**: Collection always closed properly, even on errors
- **Input Validation**: Card data validated before writing to collection
