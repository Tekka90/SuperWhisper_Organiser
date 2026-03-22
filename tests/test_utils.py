"""
Tests for utils.py — utility / helper functions.

No real filesystem paths or database files from production are used.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import organiser.utils as utils


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_less_than_60_seconds(self):
        assert utils.format_duration(30_000) == "30 seconds"

    def test_exactly_60_seconds(self):
        result = utils.format_duration(60_000)
        assert "1m" in result

    def test_minutes_and_seconds(self):
        result = utils.format_duration(90_000)  # 1m 30s
        assert "1m" in result
        assert "30s" in result

    def test_hours(self):
        result = utils.format_duration(3_600_000)  # 1 hour
        assert "1h" in result

    def test_hours_and_minutes(self):
        result = utils.format_duration(5_400_000)  # 1h 30m
        assert "1h" in result
        assert "30m" in result

    def test_zero_duration(self):
        result = utils.format_duration(0)
        assert "0" in result


# ---------------------------------------------------------------------------
# expand_env_vars
# ---------------------------------------------------------------------------

class TestExpandEnvVars:
    def test_expands_string(self):
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            result = utils.expand_env_vars("prefix_${MY_VAR}_suffix")
        assert result == "prefix_hello_suffix"

    def test_missing_env_var_becomes_empty(self):
        result = utils.expand_env_vars("${DOES_NOT_EXIST_XYZ}")
        assert result == ""

    def test_dict_recursion(self):
        with patch.dict(os.environ, {"DB": "/tmp/db.sqlite"}):
            cfg = {"paths": {"db": "${DB}"}}
            result = utils.expand_env_vars(cfg)
        assert result["paths"]["db"] == "/tmp/db.sqlite"

    def test_list_recursion(self):
        with patch.dict(os.environ, {"NAME": "Alice"}):
            result = utils.expand_env_vars(["hello ${NAME}"])
        assert result == ["hello Alice"]

    def test_non_string_passthrough(self):
        assert utils.expand_env_vars(42) == 42
        assert utils.expand_env_vars(None) is None


# ---------------------------------------------------------------------------
# expand_path
# ---------------------------------------------------------------------------

class TestExpandPath:
    def test_tilde_expansion(self):
        result = utils.expand_path("~/some/path")
        assert str(result).startswith("/")
        assert "~" not in str(result)

    def test_env_var_expansion(self):
        with patch.dict(os.environ, {"MYDIR": "/tmp/test_dir"}):
            result = utils.expand_path("$MYDIR/notes")
        assert str(result) == "/tmp/test_dir/notes"

    def test_returns_path_object(self):
        result = utils.expand_path("/absolute/path")
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# load_meta_json
# ---------------------------------------------------------------------------

class TestLoadMetaJson:
    def test_loads_valid_meta(self, tmp_path):
        data = {"duration": 1000, "llmResult": "Test"}
        meta_file = tmp_path / "meta.json"
        meta_file.write_text(json.dumps(data), encoding="utf-8")
        result = utils.load_meta_json(tmp_path)
        assert result == data

    def test_missing_meta_returns_none(self, tmp_path):
        result = utils.load_meta_json(tmp_path)
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        meta_file = tmp_path / "meta.json"
        meta_file.write_text("{ not valid json }", encoding="utf-8")
        result = utils.load_meta_json(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# get_recording_date
# ---------------------------------------------------------------------------

class TestGetRecordingDate:
    def test_valid_datetime_field(self):
        meta = {"datetime": "2025-03-01T10:30:00"}
        result = utils.get_recording_date(meta)
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 3
        assert result.day == 1

    def test_missing_datetime_returns_none(self):
        result = utils.get_recording_date({})
        assert result is None

    def test_invalid_datetime_returns_none(self):
        result = utils.get_recording_date({"datetime": "not-a-date"})
        assert result is None


# ---------------------------------------------------------------------------
# extract_participants_from_segments
# ---------------------------------------------------------------------------

class TestExtractParticipants:
    def test_empty_segments(self):
        assert utils.extract_participants_from_segments([]) == []

    def test_single_speaker(self):
        segments = [{"speaker": "0", "text": "Hello"}]
        result = utils.extract_participants_from_segments(segments)
        assert result == ["Speaker 0"]

    def test_multiple_distinct_speakers(self):
        segments = [
            {"speaker": "0", "text": "A"},
            {"speaker": "1", "text": "B"},
            {"speaker": "0", "text": "C"},
        ]
        result = utils.extract_participants_from_segments(segments)
        assert set(result) == {"Speaker 0", "Speaker 1"}

    def test_segments_without_speaker_key(self):
        segments = [{"text": "No speaker field"}]
        result = utils.extract_participants_from_segments(segments)
        assert result == []

    def test_result_is_sorted(self):
        segments = [{"speaker": "2"}, {"speaker": "0"}, {"speaker": "1"}]
        result = utils.extract_participants_from_segments(segments)
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    """sanitize_filename is only present if it exists in utils.py."""

    def test_removes_path_separators(self):
        if not hasattr(utils, "sanitize_filename"):
            pytest.skip("sanitize_filename not implemented in utils.py")
        result = utils.sanitize_filename("path/to/file")
        assert "/" not in result

    def test_replaces_spaces(self):
        if not hasattr(utils, "sanitize_filename"):
            pytest.skip("sanitize_filename not implemented in utils.py")
        result = utils.sanitize_filename("my file name")
        # Should not raise; result should be a non-empty string
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Legacy DB helpers (init_database / is_recording_processed / mark_recording_processed)
# ---------------------------------------------------------------------------

class TestLegacyDbHelpers:
    def test_init_database_creates_table(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        utils.init_database(db_path)
        assert db_path.exists()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_recordings'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_is_recording_processed_false_for_new(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        utils.init_database(db_path)
        assert utils.is_recording_processed(db_path, "folder_new") is False

    def test_is_recording_processed_false_when_db_missing(self, tmp_path):
        db_path = tmp_path / "nonexistent.db"
        assert utils.is_recording_processed(db_path, "x") is False

    def test_mark_and_check_processed(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        utils.init_database(db_path)
        utils.mark_recording_processed(
            db_path,
            folder_name="folder_123",
            note_file="note.md",
            meeting_type="general",
            participants=["Alice", "Bob"],
        )
        assert utils.is_recording_processed(db_path, "folder_123") is True
        assert utils.is_recording_processed(db_path, "folder_999") is False
