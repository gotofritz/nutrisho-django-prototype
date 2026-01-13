"""Pytest configuration for Anki skill tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock anki imports before any test imports the main module
sys.modules["anki"] = MagicMock()
sys.modules["anki.collection"] = MagicMock()
sys.modules["anki.errors"] = MagicMock()

# Add skill directory to path so tests can import main
sys.path.insert(0, str(Path(__file__).parent))
