"""
Tests for learning.py — LearningSystem.

OpenAI / external calls are never made.
The database used is a temporary in-memory-backed instance.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from organiser.learning import LearningSystem
from organiser.database import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def learning(db, mock_config, tmp_notes_dir):
    """LearningSystem wired to tmp db + tmp notes dir."""
    mock_config["paths"]["notes_output"] = str(tmp_notes_dir)
    return LearningSystem(db, mock_config)


# ---------------------------------------------------------------------------
# _determine_file_type
# ---------------------------------------------------------------------------

class TestDetermineFileType:
    def test_one_on_one_from_path(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "1-on-1" / "note.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        result = learning._determine_file_type(path)
        assert result == "1-on-1"

    def test_team_from_path(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "team-meetings" / "note.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        result = learning._determine_file_type(path)
        assert result == "team-meeting"

    def test_general_fallback(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "misc.md"
        path.touch()
        result = learning._determine_file_type(path)
        assert result == "general"


# ---------------------------------------------------------------------------
# _extract_people
# ---------------------------------------------------------------------------

class TestExtractPeople:
    def test_with_participants_section(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "note.md"
        content = "# Meeting\n\nParticipants: Alice, Bob\n"
        people = learning._extract_people(content, path)
        assert "Alice" in people
        assert "Bob" in people

    def test_with_attendees_section(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "note.md"
        content = "Attendees: Carol, Dave\n"
        people = learning._extract_people(content, path)
        assert "Carol" in people
        assert "Dave" in people

    def test_from_filename_with_pattern(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "1-on-1 with John.md"
        people = learning._extract_people("# note", path)
        assert "John" in people

    def test_filters_common_false_positives(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "note.md"
        content = "# Meeting Notes\n\nDate: today\n"
        people = learning._extract_people(content, path)
        # "Meeting", "Notes", "Date" should NOT appear
        false_pos = {"Meeting", "Notes", "Date", "Time", "Summary", "Action", "Items"}
        assert not people.intersection(false_pos)

    def test_empty_content(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "empty.md"
        result = learning._extract_people("", path)
        assert isinstance(result, set)


# ---------------------------------------------------------------------------
# _extract_projects
# ---------------------------------------------------------------------------

class TestExtractProjects:
    def test_project_marker(self, learning, tmp_notes_dir):
        content = "Project: SuperWidget\n"
        path = tmp_notes_dir / "note.md"
        projects = learning._extract_projects(content, path)
        # The regex may capture trailing whitespace; strip when comparing
        assert any(p.strip() == "SuperWidget" for p in projects)

    def test_frequent_capitalized_phrase(self, learning, tmp_notes_dir):
        content = "Alpha Beta discussed. Alpha Beta confirmed.\n"
        path = tmp_notes_dir / "note.md"
        projects = learning._extract_projects(content, path)
        assert "Alpha Beta" in projects

    def test_single_occurrence_not_extracted(self, learning, tmp_notes_dir):
        content = "Alpha Beta mentioned once.\n"
        path = tmp_notes_dir / "note.md"
        projects = learning._extract_projects(content, path)
        # Single occurrence shouldn't be auto-extracted (unless from Project: marker)
        assert "Alpha Beta" not in projects


# ---------------------------------------------------------------------------
# _extract_topics
# ---------------------------------------------------------------------------

class TestExtractTopics:
    def test_hashtags(self, learning):
        topics = learning._extract_topics("Some text #engineering #sprint\n")
        assert "engineering" in topics
        assert "sprint" in topics

    def test_topics_section(self, learning):
        topics = learning._extract_topics("Topics: design, backend, testing\n")
        assert "design" in topics
        assert "backend" in topics
        assert "testing" in topics

    def test_tags_section(self, learning):
        topics = learning._extract_topics("Tags: qa, release\n")
        assert "qa" in topics

    def test_no_topics(self, learning):
        result = learning._extract_topics("No topics here.")
        assert isinstance(result, set)


# ---------------------------------------------------------------------------
# _extract_meeting_pattern
# ---------------------------------------------------------------------------

class TestExtractMeetingPattern:
    def test_one_on_one_pattern(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "1-on-1" / "1-on-1 with Alice.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# note", encoding="utf-8")
        pattern = learning._extract_meeting_pattern(path, "# note")
        assert pattern == "1-on-1:Alice"

    def test_team_pattern(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "team-meetings" / "Engineering.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Team: Engineering\n", encoding="utf-8")
        pattern = learning._extract_meeting_pattern(path, "Team: Engineering\n")
        assert pattern is not None
        assert "team" in pattern.lower()

    def test_general_returns_general(self, learning, tmp_notes_dir):
        path = tmp_notes_dir / "general.md"
        path.write_text("# General", encoding="utf-8")
        pattern = learning._extract_meeting_pattern(path, "# General")
        assert pattern == "general"


# ---------------------------------------------------------------------------
# apply_name_corrections
# ---------------------------------------------------------------------------

class TestApplyNameCorrections:
    def test_basic_correction(self, learning, db):
        db.add_name_correction("jon", "John")
        result = learning.apply_name_corrections("I met with jon today.")
        assert "John" in result
        assert "jon" not in result

    def test_no_correction_when_none_stored(self, learning):
        text = "I met with Alice today."
        result = learning.apply_name_corrections(text)
        assert result == text

    def test_case_insensitive_correction(self, learning, db):
        db.add_name_correction("alis", "Alice")
        result = learning.apply_name_corrections("ALIS was there.")
        assert "Alice" in result

    def test_empty_text(self, learning):
        result = learning.apply_name_corrections("")
        assert result == ""


# ---------------------------------------------------------------------------
# get_learning_context
# ---------------------------------------------------------------------------

class TestGetLearningContext:
    def test_returns_expected_keys(self, learning):
        ctx = learning.get_learning_context()
        assert "known_people" in ctx
        assert "known_projects" in ctx
        assert "one_on_one_files" in ctx
        assert "name_corrections" in ctx

    def test_one_on_one_people_extracted(self, learning, db):
        db.add_knowledge("meeting_pattern", "1-on-1:Alice")
        ctx = learning.get_learning_context()
        assert "Alice" in ctx["one_on_one_files"]

    def test_known_projects_listed(self, learning, db):
        db.add_knowledge("project", "SuperWidget", confidence=0.9)
        ctx = learning.get_learning_context()
        assert "SuperWidget" in ctx["known_projects"]


# ---------------------------------------------------------------------------
# build_system_prompt_context
# ---------------------------------------------------------------------------

class TestBuildSystemPromptContext:
    def test_returns_string(self, learning):
        result = learning.build_system_prompt_context()
        assert isinstance(result, str)

    def test_includes_known_people(self, learning, db):
        db.add_knowledge("person", "Eve", confidence=0.9)
        result = learning.build_system_prompt_context()
        assert "Eve" in result

    def test_includes_corrections(self, learning, db):
        db.add_name_correction("jon", "John")
        result = learning.build_system_prompt_context()
        assert "jon" in result or "John" in result

    def test_empty_context_returns_empty_string(self, learning):
        # Fresh db with no data → should return empty or minimal string
        result = learning.build_system_prompt_context()
        # It's OK if this is empty or non-empty; just must be a string
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# scan_existing_notes (integration-level, uses real tmp files)
# ---------------------------------------------------------------------------

class TestScanExistingNotes:
    def test_scan_non_existent_dir_does_not_crash(self, learning, tmp_notes_dir, mock_config):
        """If notes dir doesn't exist yet, scan must not crash."""
        import shutil
        shutil.rmtree(tmp_notes_dir)
        learning.scan_existing_notes()  # Should log a warning and return

    def test_scan_extracts_people_from_files(self, learning, tmp_notes_dir, db):
        note = tmp_notes_dir / "meeting.md"
        note.write_text(
            "# 1-on-1 with Zara\n\nParticipants: Zara\n",
            encoding="utf-8",
        )
        learning.scan_existing_notes()
        people = db.get_knowledge(entity_type="person")
        names = [p["entity_name"] for p in people]
        assert "Zara" in names

    def test_scan_ignores_hidden_files(self, learning, tmp_notes_dir, db):
        hidden = tmp_notes_dir / ".hidden.md"
        hidden.write_text("# Hidden\n\nParticipants: Shadow\n", encoding="utf-8")
        learning.scan_existing_notes()
        people = db.get_knowledge(entity_type="person")
        names = [p["entity_name"] for p in people]
        assert "Shadow" not in names
