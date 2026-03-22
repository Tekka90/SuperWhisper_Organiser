"""
Shared fixtures for SuperWhisper Organiser unit tests.
All tests use in-memory / temp-dir databases — never the real database.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on sys.path so we can import modules directly
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from organiser.database import Database


# ---------------------------------------------------------------------------
# Minimal config that mirrors config.yaml structure without real paths
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_notes_dir(tmp_path):
    """Temporary directory that acts as the notes output folder."""
    notes = tmp_path / "notes"
    notes.mkdir()
    return notes


@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to a fresh temporary SQLite database file."""
    return tmp_path / "test.db"


@pytest.fixture
def db(tmp_db_path):
    """Initialised Database instance backed by a temporary file."""
    return Database(tmp_db_path)


@pytest.fixture
def mock_config(tmp_path, tmp_notes_dir):
    """Minimal config dict wired to temp directories."""
    db_path = tmp_path / "test.db"
    return {
        "paths": {
            "recordings": str(tmp_path / "recordings"),
            "notes_output": str(tmp_notes_dir),
            "database": str(db_path),
        },
        "openai": {
            "api_key": "test-key-not-real",
            "model": "gpt-4",
            "temperature": 0.3,
            "max_tokens": 500,
            "base_url": None,
            "use_json_mode": True,
        },
        "analysis": {
            "system_prompt": "You are a helpful assistant.",
        },
        "logging": {
            "level": "WARNING",
            "file": str(tmp_path / "test.log"),
            "timestamps": False,
        },
        "processing": {
            "modes": ["default"],
        },
    }


@pytest.fixture
def mock_notes(tmp_notes_dir):
    """
    Creates a set of mock markdown files inside tmp_notes_dir and returns
    a dict mapping logical name → Path.
    """
    files = {}

    # 1-on-1 subfolder
    one_on_one = tmp_notes_dir / "1-on-1"
    one_on_one.mkdir()

    alice = one_on_one / "1-on-1 with Alice.md"
    alice.write_text(
        "# 1-on-1 with Alice\n\n"
        "## January 15, 2025\n\n"
        "Discussed Q1 roadmap with Alice.\n\n"
        "Participants: Alice, Bob\n",
        encoding="utf-8",
    )
    files["alice"] = alice

    bob = one_on_one / "1-on-1 with Bob.md"
    bob.write_text(
        "# 1-on-1 with Bob\n\n"
        "## 2025-01-20\n\n"
        "Reviewed Bob's performance.\n",
        encoding="utf-8",
    )
    files["bob"] = bob

    # Team subfolder
    team = tmp_notes_dir / "team"
    team.mkdir()

    team_meeting = team / "Engineering Team Meeting.md"
    team_meeting.write_text(
        "# Engineering Team Meeting\n\n"
        "## 15 Mar 2025\n\n"
        "Project: SuperWidget update discussed.\n"
        "SuperWidget mentioned again for emphasis.\n"
        "Tags: engineering, sprint, planning\n",
        encoding="utf-8",
    )
    files["team_meeting"] = team_meeting

    # Root-level general note
    general = tmp_notes_dir / "General Notes.md"
    general.write_text(
        "# General Notes\n\n"
        "## February 3, 2025\n\n"
        "Miscellaneous note without a date somewhere.\n"
        "#ideas #backlog\n",
        encoding="utf-8",
    )
    files["general"] = general

    return files


# ---------------------------------------------------------------------------
# Mock recording folder with meta.json
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_recording_folder(tmp_path):
    """A fake SuperWhisper recording folder with a meta.json."""
    folder = tmp_path / "1700000000"
    folder.mkdir()

    meta = {
        "datetime": "2025-03-01T10:00:00",
        "duration": 3600000,  # 1 hour in ms
        "llmResult": (
            "Meeting with Alice and Charlie about the SuperWidget project. "
            "Alice proposed a new API design. Charlie agreed to review by Friday."
        ),
        "rawResult": (
            "Alice: So let's talk about the SuperWidget API.\n"
            "Charlie: Sure, I can review your proposal.\n"
            "Alice: Great, thanks Charlie!"
        ),
        "segments": [
            {"speaker": "0", "text": "Alice: So let's talk about the SuperWidget API."},
            {"speaker": "1", "text": "Charlie: Sure, I can review your proposal."},
        ],
        "mode": "default",
    }
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


# ---------------------------------------------------------------------------
# Flask test client with injected mocks (no real config file needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(mock_config, tmp_notes_dir, tmp_db_path):
    """
    Flask test client with global state patched to use temp directories.
    No OpenAI key is touched; the analyzer global is set to None.
    """
    import organiser.webapp as webapp

    real_db = Database(tmp_db_path)
    from organiser.learning import LearningSystem

    real_learning = LearningSystem(real_db, mock_config)

    # Patch the module-level globals without starting a real server
    with (
        patch.object(webapp, "config", mock_config),
        patch.object(webapp, "db", real_db),
        patch.object(webapp, "learning_system", real_learning),
        patch.object(webapp, "analyzer", None),
        patch.object(webapp, "notes_path", tmp_notes_dir),
    ):
        webapp.app.config["TESTING"] = True
        with webapp.app.test_client() as client:
            yield client
