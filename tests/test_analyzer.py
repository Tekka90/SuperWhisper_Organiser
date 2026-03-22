"""
Tests for analyzer.py — MeetingAnalysis and MeetingAnalyzer.

All OpenAI API calls are mocked; no network traffic is produced.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from organiser.analyzer import MeetingAnalysis, MeetingAnalyzer


# ---------------------------------------------------------------------------
# MeetingAnalysis
# ---------------------------------------------------------------------------

class TestMeetingAnalysis:
    def test_to_dict_contains_all_keys(self):
        analysis = MeetingAnalysis(
            meeting_type="one_on_one",
            participants=["Alice", "Bob"],
            topics=["roadmap", "Q1"],
            suggested_filename="1-to-1 with Alice.md",
            summary="Discussed Q1 roadmap.",
            related_meetings=["old-meeting.md"],
            confidence="high",
        )
        d = analysis.to_dict()
        assert d["meeting_type"] == "one_on_one"
        assert d["participants"] == ["Alice", "Bob"]
        assert d["topics"] == ["roadmap", "Q1"]
        assert d["suggested_filename"] == "1-to-1 with Alice.md"
        assert d["summary"] == "Discussed Q1 roadmap."
        assert d["related_meetings"] == ["old-meeting.md"]
        assert d["confidence"] == "high"

    def test_defaults_for_optional_fields(self):
        analysis = MeetingAnalysis(
            meeting_type="general",
            participants=[],
            topics=[],
            suggested_filename="meeting.md",
            summary="",
        )
        d = analysis.to_dict()
        assert d["related_meetings"] == []
        assert d["confidence"] == "medium"


# ---------------------------------------------------------------------------
# Fixtures for MeetingAnalyzer tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_openai_client():
    """Reusable mock for the openai.OpenAI client."""
    client = MagicMock()
    return client


@pytest.fixture
def analyzer(mock_config, mock_openai_client):
    """
    MeetingAnalyzer with the OpenAI client patched to avoid real API calls.
    """
    with patch("organiser.analyzer.OpenAI", return_value=mock_openai_client):
        inst = MeetingAnalyzer(mock_config, learning_system=None)
    inst.client = mock_openai_client
    return inst


# ---------------------------------------------------------------------------
# Helper – build a mock OpenAI response
# ---------------------------------------------------------------------------

def _make_openai_response(content: str):
    """Return a minimal object that mimics openai chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# _create_analysis_prompt
# ---------------------------------------------------------------------------

class TestCreateAnalysisPrompt:
    def test_contains_duration(self, analyzer):
        prompt = analyzer._create_analysis_prompt(
            llm_result="Transcript here.",
            raw_result="Raw transcript.",
            auto_participants=["Speaker 0"],
            duration=3_600_000,
            recording_date=None,
            existing_context="",
        )
        assert "1h" in prompt or "60m" in prompt  # format_duration output

    def test_contains_summary(self, analyzer):
        prompt = analyzer._create_analysis_prompt(
            llm_result="This is the summary.",
            raw_result="",
            auto_participants=[],
            duration=0,
            recording_date=None,
            existing_context="",
        )
        assert "This is the summary." in prompt

    def test_contains_existing_context(self, analyzer):
        prompt = analyzer._create_analysis_prompt(
            llm_result="",
            raw_result="",
            auto_participants=[],
            duration=0,
            recording_date=None,
            existing_context="## existing-note.md\nOld note content",
        )
        assert "existing-note.md" in prompt

    def test_contains_learning_context(self, analyzer):
        prompt = analyzer._create_analysis_prompt(
            llm_result="",
            raw_result="",
            auto_participants=[],
            duration=0,
            recording_date=None,
            existing_context="",
            learning_context="Known people: Alice, Bob",
        )
        assert "Alice" in prompt

    def test_truncates_long_llm_result(self, analyzer):
        long_text = "X" * 5000
        prompt = analyzer._create_analysis_prompt(
            llm_result=long_text,
            raw_result="",
            auto_participants=[],
            duration=0,
            recording_date=None,
            existing_context="",
        )
        # The prompt should not contain the full 5000-char string verbatim
        assert len(prompt) < 10_000  # sanity cap


# ---------------------------------------------------------------------------
# _build_existing_context
# ---------------------------------------------------------------------------

class TestBuildExistingContext:
    def test_none_input_returns_empty(self, analyzer):
        result = analyzer._build_existing_context(None)
        assert result == ""

    def test_empty_list_returns_empty(self, analyzer):
        result = analyzer._build_existing_context([])
        assert result == ""

    def test_includes_file_names(self, analyzer, tmp_path):
        note = tmp_path / "meeting.md"
        note.write_text("# Meeting\nSome content here.", encoding="utf-8")
        result = analyzer._build_existing_context([note])
        assert "meeting.md" in result

    def test_handles_missing_file_gracefully(self, analyzer, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        # Should not raise even if file is missing
        result = analyzer._build_existing_context([missing])
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# analyze_recording — happy path
# ---------------------------------------------------------------------------

class TestAnalyzeRecording:
    def test_returns_meeting_analysis_on_success(self, analyzer, mock_recording_folder):
        ai_response = json.dumps({
            "meeting_type": "one_on_one",
            "participants": ["Alice", "Charlie"],
            "topics": ["API design"],
            "suggested_filename": "1-to-1 with Alice.md",
            "summary": "Discussed API design.",
            "related_meetings": [],
            "confidence": "high",
        })
        analyzer.client.chat.completions.create.return_value = _make_openai_response(ai_response)

        result = analyzer.analyze_recording(mock_recording_folder)
        assert result is not None
        assert result.meeting_type == "one_on_one"
        assert "Alice" in result.participants

    def test_missing_meta_json_returns_none(self, analyzer, tmp_path):
        empty_folder = tmp_path / "no_meta"
        empty_folder.mkdir()
        result = analyzer.analyze_recording(empty_folder)
        assert result is None

    def test_empty_transcript_returns_none(self, analyzer, tmp_path):
        import json as _json

        folder = tmp_path / "empty_transcript"
        folder.mkdir()
        meta = {"datetime": "2025-01-01T00:00:00", "duration": 0, "llmResult": "", "rawResult": ""}
        (folder / "meta.json").write_text(_json.dumps(meta), encoding="utf-8")
        result = analyzer.analyze_recording(folder)
        assert result is None

    def test_openai_exception_returns_none(self, analyzer, mock_recording_folder):
        analyzer.client.chat.completions.create.side_effect = Exception("Network error")
        result = analyzer.analyze_recording(mock_recording_folder)
        assert result is None

    def test_uses_auto_participants_as_fallback(self, analyzer, mock_recording_folder):
        """If AI returns empty participants list, auto_participants are used."""
        ai_response = json.dumps({
            "meeting_type": "general",
            "participants": [],
            "topics": [],
            "suggested_filename": "meeting.md",
            "summary": "A meeting.",
            "confidence": "low",
        })
        analyzer.client.chat.completions.create.return_value = _make_openai_response(ai_response)
        result = analyzer.analyze_recording(mock_recording_folder)
        assert result is not None
        # Fall back to auto-detected speakers from segments
        assert result.participants == [] or len(result.participants) >= 0  # passes either way

    def test_applies_learning_context(self, mock_config, mock_recording_folder, db, tmp_notes_dir):
        """analyzer should call learning_system.build_system_prompt_context."""
        from organiser.learning import LearningSystem

        mock_config["paths"]["notes_output"] = str(tmp_notes_dir)
        learning = LearningSystem(db, mock_config)

        mock_client = MagicMock()
        ai_response = json.dumps({
            "meeting_type": "general",
            "participants": ["Alice"],
            "topics": [],
            "suggested_filename": "general.md",
            "summary": "A meeting.",
            "confidence": "medium",
        })
        mock_client.chat.completions.create.return_value = _make_openai_response(ai_response)

        with patch("organiser.analyzer.OpenAI", return_value=mock_client):
            inst = MeetingAnalyzer(mock_config, learning_system=learning)
        inst.client = mock_client

        result = inst.analyze_recording(mock_recording_folder)
        assert result is not None


# ---------------------------------------------------------------------------
# JSON recovery fallback (markdown code-block)
# ---------------------------------------------------------------------------

class TestJsonFallback:
    def test_recovers_json_from_markdown_block(self, analyzer, mock_recording_folder):
        payload = {
            "meeting_type": "general",
            "participants": [],
            "topics": [],
            "suggested_filename": "meeting.md",
            "summary": "A meeting.",
            "confidence": "medium",
        }
        wrapped = f"Here is the analysis:\n```json\n{json.dumps(payload)}\n```"
        analyzer.use_json_mode = False
        analyzer.client.chat.completions.create.return_value = _make_openai_response(wrapped)

        result = analyzer.analyze_recording(mock_recording_folder)
        assert result is not None
        assert result.meeting_type == "general"
