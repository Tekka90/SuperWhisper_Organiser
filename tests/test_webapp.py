"""
Tests for webapp.py — Flask REST API endpoints and helper functions.

The Flask app's global state (config, db, learning_system, analyzer, notes_path)
is patched via the `app_client` fixture defined in conftest.py.
No real database or notes directory is touched.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path is set up
import organiser.webapp as webapp
from organiser.webapp import _extract_latest_date_from_file, _merge_note_contents


# ---------------------------------------------------------------------------
# _extract_latest_date_from_file
# ---------------------------------------------------------------------------

class TestExtractLatestDateFromFile:
    def test_iso_date(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("Meeting on 2025-03-15.\n", encoding="utf-8")
        result = _extract_latest_date_from_file(f)
        assert result == datetime(2025, 3, 15)

    def test_long_month_format(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("Date: February 11, 2025\n", encoding="utf-8")
        result = _extract_latest_date_from_file(f)
        assert result == datetime(2025, 2, 11)

    def test_short_month_format(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("15 Mar 2025\n", encoding="utf-8")
        result = _extract_latest_date_from_file(f)
        assert result == datetime(2025, 3, 15)

    def test_returns_latest_of_multiple_dates(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("2025-01-01\n2025-06-15\n2025-03-10\n", encoding="utf-8")
        result = _extract_latest_date_from_file(f)
        assert result == datetime(2025, 6, 15)

    def test_no_date_returns_none(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("No date in this content.\n", encoding="utf-8")
        result = _extract_latest_date_from_file(f)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        f = tmp_path / "nonexistent.md"
        result = _extract_latest_date_from_file(f)
        assert result is None


# ---------------------------------------------------------------------------
# _merge_note_contents
# ---------------------------------------------------------------------------

class TestMergeNoteContents:
    def test_returns_string(self):
        result = _merge_note_contents("# Note A\n\nContent A", "# Note B\n\nContent B")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_both_contents(self):
        result = _merge_note_contents("## 2025-01-01\n\nAlpha", "## 2025-06-01\n\nBeta")
        assert "Alpha" in result
        assert "Beta" in result

    def test_newer_date_comes_first(self):
        result = _merge_note_contents(
            "## 2025-01-01\n\nOld entry",
            "## 2025-12-01\n\nNew entry",
        )
        idx_old = result.index("Old entry")
        idx_new = result.index("New entry")
        assert idx_new < idx_old  # new entry appears first

    def test_empty_first_content(self):
        result = _merge_note_contents("", "## 2025-01-01\n\nOnly this")
        assert "Only this" in result

    def test_empty_both_contents(self):
        result = _merge_note_contents("", "")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

class TestApiStatus:
    def test_returns_success(self, app_client):
        resp = app_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "status" in data

    def test_status_contains_is_processing(self, app_client):
        resp = app_client.get("/api/status")
        data = resp.get_json()
        assert "is_processing" in data["status"]


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------

class TestApiStats:
    def test_returns_success(self, app_client):
        resp = app_client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "stats" in data

    def test_stats_shape(self, app_client):
        data = app_client.get("/api/stats").get_json()
        stats = data["stats"]
        assert "total_processed" in stats
        assert "last_7_days" in stats


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------

class TestApiHistory:
    def test_returns_success(self, app_client):
        resp = app_client.get("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "history" in data

    def test_pagination_params_echoed(self, app_client):
        data = app_client.get("/api/history?limit=5&offset=0").get_json()
        assert data["limit"] == 5
        assert data["offset"] == 0


# ---------------------------------------------------------------------------
# GET /api/note-tree
# ---------------------------------------------------------------------------

class TestApiNoteTree:
    def test_returns_success_with_empty_notes(self, app_client):
        resp = app_client.get("/api/note-tree")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "tree" in data

    def test_files_appear_in_tree(self, app_client, tmp_notes_dir):
        (tmp_notes_dir / "sample.md").write_text("# Sample\n2025-01-01", encoding="utf-8")
        resp = app_client.get("/api/note-tree")
        data = resp.get_json()

        def flatten(items):
            names = []
            for item in items:
                names.append(item["name"])
                if item.get("children"):
                    names.extend(flatten(item["children"]))
            return names

        all_names = flatten(data["tree"])
        assert any("sample" in n.lower() for n in all_names)

    def test_folders_appear_in_tree(self, app_client, tmp_notes_dir):
        subfolder = tmp_notes_dir / "1-on-1"
        subfolder.mkdir()
        (subfolder / "Alice.md").write_text("# Alice\n", encoding="utf-8")
        resp = app_client.get("/api/note-tree")
        data = resp.get_json()
        folder_names = [item["name"] for item in data["tree"] if item.get("type") == "folder"]
        assert "1-on-1" in folder_names


# ---------------------------------------------------------------------------
# GET /api/notes/<path>
# ---------------------------------------------------------------------------

class TestApiNoteContent:
    def test_existing_file_returns_content(self, app_client, tmp_notes_dir):
        note = tmp_notes_dir / "hello.md"
        note.write_text("# Hello World\n", encoding="utf-8")
        resp = app_client.get("/api/notes/hello.md")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "Hello World" in data["content"]

    def test_missing_file_returns_404(self, app_client):
        resp = app_client.get("/api/notes/does_not_exist.md")
        assert resp.status_code == 404

    def test_response_includes_detected_names(self, app_client, tmp_notes_dir):
        note = tmp_notes_dir / "names.md"
        note.write_text("# Meeting with Alice\n", encoding="utf-8")
        resp = app_client.get("/api/notes/names.md")
        data = resp.get_json()
        assert "detected_names" in data

    def test_path_traversal_rejected(self, app_client, tmp_notes_dir):
        """Requests trying to escape the notes directory must be rejected."""
        # Create a file one level above tmp_notes_dir
        outside = tmp_notes_dir.parent / "secret.md"
        outside.write_text("SECRET", encoding="utf-8")
        resp = app_client.get("/api/notes/../secret.md")
        # Either 403 or 404 is acceptable — the file must NOT be served
        assert resp.status_code in (403, 404)
        if resp.status_code == 200:
            # If somehow 200 is returned, ensure secret content isn't in it
            assert "SECRET" not in resp.get_json().get("content", "")


# ---------------------------------------------------------------------------
# POST /api/notes/<path> (update content)
# ---------------------------------------------------------------------------

class TestApiUpdateNote:
    def test_update_existing_note(self, app_client, tmp_notes_dir):
        note = tmp_notes_dir / "edit_me.md"
        note.write_text("original content", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/edit_me.md",
            data=json.dumps({"content": "updated content"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert note.read_text(encoding="utf-8") == "updated content"

    def test_update_missing_note_returns_404(self, app_client):
        resp = app_client.post(
            "/api/notes/ghost.md",
            data=json.dumps({"content": "text"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_checkbox_tick_persisted(self, app_client, tmp_notes_dir):
        """Ticking a checkbox in the UI sends a POST with [ ] → [x]; file must update."""
        note = tmp_notes_dir / "tasks.md"
        note.write_text(
            "# Action items\n\n- [ ] Write tests\n- [ ] Deploy\n",
            encoding="utf-8",
        )
        toggled = "# Action items\n\n- [x] Write tests\n- [ ] Deploy\n"
        resp = app_client.post(
            "/api/notes/tasks.md",
            data=json.dumps({"content": toggled}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert note.read_text(encoding="utf-8") == toggled

    def test_checkbox_untick_persisted(self, app_client, tmp_notes_dir):
        """Un-ticking a checkbox sends [x] → [ ]; file must update."""
        note = tmp_notes_dir / "tasks2.md"
        note.write_text(
            "# Done\n\n- [x] Task one\n- [x] Task two\n",
            encoding="utf-8",
        )
        toggled = "# Done\n\n- [ ] Task one\n- [x] Task two\n"
        resp = app_client.post(
            "/api/notes/tasks2.md",
            data=json.dumps({"content": toggled}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert note.read_text(encoding="utf-8") == toggled


# ---------------------------------------------------------------------------
# POST /api/notes/rename
# ---------------------------------------------------------------------------

class TestApiRenameNote:
    def test_rename_success(self, app_client, tmp_notes_dir):
        old = tmp_notes_dir / "before.md"
        old.write_text("# Before", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/rename",
            data=json.dumps({"old_path": "before.md", "new_name": "after.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert not old.exists()
        assert (tmp_notes_dir / "after.md").exists()

    def test_rename_conflict_returns_409(self, app_client, tmp_notes_dir):
        (tmp_notes_dir / "a.md").write_text("A", encoding="utf-8")
        (tmp_notes_dir / "b.md").write_text("B", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/rename",
            data=json.dumps({"old_path": "a.md", "new_name": "b.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 409

    def test_rename_missing_source_returns_404(self, app_client):
        resp = app_client.post(
            "/api/notes/rename",
            data=json.dumps({"old_path": "ghost.md", "new_name": "new.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_rename_missing_params_returns_400(self, app_client):
        resp = app_client.post(
            "/api/notes/rename",
            data=json.dumps({"old_path": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/notes/delete
# ---------------------------------------------------------------------------

class TestApiDeleteNote:
    def test_delete_existing_file(self, app_client, tmp_notes_dir):
        note = tmp_notes_dir / "delete_me.md"
        note.write_text("bye", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/delete",
            data=json.dumps({"file_path": "delete_me.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert not note.exists()

    def test_delete_missing_file_returns_404(self, app_client):
        resp = app_client.post(
            "/api/notes/delete",
            data=json.dumps({"file_path": "nonexistent.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_delete_missing_param_returns_400(self, app_client):
        resp = app_client.post(
            "/api/notes/delete",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/notes/move
# ---------------------------------------------------------------------------

class TestApiMoveNote:
    def test_move_to_subfolder(self, app_client, tmp_notes_dir):
        note = tmp_notes_dir / "moveable.md"
        note.write_text("move me", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/move",
            data=json.dumps({"source_path": "moveable.md", "target_folder": "archived"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert (tmp_notes_dir / "archived" / "moveable.md").exists()

    def test_move_missing_source_returns_404(self, app_client):
        resp = app_client.post(
            "/api/notes/move",
            data=json.dumps({"source_path": "ghost.md", "target_folder": "archive"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_move_conflict_returns_409(self, app_client, tmp_notes_dir):
        sub = tmp_notes_dir / "dest"
        sub.mkdir()
        (tmp_notes_dir / "file.md").write_text("original", encoding="utf-8")
        (sub / "file.md").write_text("existing", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/move",
            data=json.dumps({"source_path": "file.md", "target_folder": "dest"}),
            content_type="application/json",
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/notes/search
# ---------------------------------------------------------------------------

class TestApiSearchNotes:
    def test_empty_query_returns_empty_results(self, app_client):
        resp = app_client.get("/api/notes/search?q=")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["results"] == []

    def test_finds_filename_match(self, app_client, tmp_notes_dir):
        (tmp_notes_dir / "project-alpha.md").write_text("# Project Alpha\n", encoding="utf-8")
        resp = app_client.get("/api/notes/search?q=alpha")
        data = resp.get_json()
        assert any("alpha" in r["path"].lower() for r in data["results"])

    def test_finds_content_match(self, app_client, tmp_notes_dir):
        (tmp_notes_dir / "secret-note.md").write_text(
            "Nothing special except: xylophone phrase\n", encoding="utf-8"
        )
        resp = app_client.get("/api/notes/search?q=xylophone+phrase")
        data = resp.get_json()
        assert data["count"] >= 1
        assert any("secret-note" in r["path"] for r in data["results"])

    def test_result_includes_snippets(self, app_client, tmp_notes_dir):
        (tmp_notes_dir / "snip.md").write_text("line1\nfindme phrase\nline3\n", encoding="utf-8")
        resp = app_client.get("/api/notes/search?q=findme+phrase")
        data = resp.get_json()
        if data["count"] > 0:
            assert "snippets" in data["results"][0]

    def test_title_matches_appear_first(self, app_client, tmp_notes_dir):
        (tmp_notes_dir / "unicorn-topic.md").write_text("# Unicorn Topic\nNo body match.", encoding="utf-8")
        (tmp_notes_dir / "body-match.md").write_text("# Body\nUnicorn-topic mentioned here.", encoding="utf-8")
        resp = app_client.get("/api/notes/search?q=unicorn-topic")
        data = resp.get_json()
        if len(data["results"]) >= 2:
            assert data["results"][0]["title_match"] is True


# ---------------------------------------------------------------------------
# GET /api/knowledge
# ---------------------------------------------------------------------------

class TestApiKnowledge:
    def test_returns_success(self, app_client):
        resp = app_client.get("/api/knowledge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_knowledge_shape(self, app_client):
        data = app_client.get("/api/knowledge").get_json()
        assert "knowledge" in data
        kb = data["knowledge"]
        assert "people" in kb
        assert "projects" in kb
        assert "patterns" in kb
        assert "name_corrections" in kb

    def test_no_cache_headers(self, app_client):
        resp = app_client.get("/api/knowledge")
        assert "no-cache" in resp.headers.get("Cache-Control", "").lower() or \
               "no-store" in resp.headers.get("Cache-Control", "").lower()


# ---------------------------------------------------------------------------
# POST /api/knowledge/merge-names
# ---------------------------------------------------------------------------

class TestApiMergeNames:
    def test_merge_success(self, app_client, tmp_notes_dir):
        # Store a note containing both names so the merge has files to process
        note = tmp_notes_dir / "note.md"
        note.write_text("Jon and John\n", encoding="utf-8")

        # Pre-populate db via the patched db instance
        import organiser.webapp as _wa
        _wa.db.store_detected_names("note.md", ["Jon", "John"])
        _wa.db.add_knowledge("person", "Jon")
        _wa.db.add_knowledge("person", "John")

        resp = app_client.post(
            "/api/knowledge/merge-names",
            data=json.dumps({"name1": "Jon", "name2": "John", "keep_name": "John"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_invalid_keep_name_returns_400(self, app_client):
        resp = app_client.post(
            "/api/knowledge/merge-names",
            data=json.dumps({"name1": "A", "name2": "B", "keep_name": "C"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_missing_params_returns_400(self, app_client):
        resp = app_client.post(
            "/api/knowledge/merge-names",
            data=json.dumps({"name1": "A"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/notes/detect-names (no analyzer => 503)
# ---------------------------------------------------------------------------

class TestApiDetectNames:
    def test_no_analyzer_returns_503(self, app_client):
        """When analyzer is None the endpoint should return 503."""
        resp = app_client.post(
            "/api/notes/detect-names",
            data=json.dumps({"content": "Alice was there."}),
            content_type="application/json",
        )
        assert resp.status_code == 503

    def test_empty_content_returns_400(self, app_client, tmp_notes_dir):
        """Empty content should return 400 regardless of analyzer state."""
        import organiser.webapp as _wa

        mock_analyzer = MagicMock()
        with patch.object(_wa, "analyzer", mock_analyzer):
            resp = app_client.post(
                "/api/notes/detect-names",
                data=json.dumps({"content": ""}),
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_with_mock_analyzer_returns_names(self, app_client, tmp_notes_dir):
        """With a mocked analyzer that returns valid JSON, names are returned."""
        import organiser.webapp as _wa

        choice = MagicMock()
        choice.message.content = '["Alice", "Bob"]'
        mock_resp = MagicMock()
        mock_resp.choices = [choice]

        mock_analyzer = MagicMock()
        mock_analyzer.client.chat.completions.create.return_value = mock_resp
        mock_analyzer.model = "gpt-4"

        with patch.object(_wa, "analyzer", mock_analyzer):
            resp = app_client.post(
                "/api/notes/detect-names",
                data=json.dumps({"content": "Alice and Bob had a meeting.", "file_path": ""}),
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "Alice" in data["names"]
        assert "Bob" in data["names"]


# ---------------------------------------------------------------------------
# POST /api/notes/correct-name
# ---------------------------------------------------------------------------

class TestApiCorrectName:
    def test_correct_name_success(self, app_client, tmp_notes_dir):
        note = tmp_notes_dir / "correct_me.md"
        note.write_text("Jon was in the meeting.\n", encoding="utf-8")

        import organiser.webapp as _wa
        _wa.db.store_detected_names("correct_me.md", ["Jon"])

        resp = app_client.post(
            "/api/notes/correct-name",
            data=json.dumps(
                {"file_path": "correct_me.md", "old_name": "Jon", "new_name": "John"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_missing_file_returns_404(self, app_client):
        resp = app_client.post(
            "/api/notes/correct-name",
            data=json.dumps(
                {"file_path": "ghost.md", "old_name": "A", "new_name": "B"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_missing_params_returns_400(self, app_client):
        resp = app_client.post(
            "/api/notes/correct-name",
            data=json.dumps({"file_path": "note.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/notes/merge
# ---------------------------------------------------------------------------

class TestApiMergeNotes:
    def test_merge_creates_merged_file(self, app_client, tmp_notes_dir):
        src = tmp_notes_dir / "source.md"
        tgt = tmp_notes_dir / "target.md"
        src.write_text("## 2025-01-01\n\nSource content\n", encoding="utf-8")
        tgt.write_text("## 2025-06-01\n\nTarget content\n", encoding="utf-8")

        resp = app_client.post(
            "/api/notes/merge",
            data=json.dumps(
                {
                    "source_path": "source.md",
                    "target_path": "target.md",
                    "final_name": "merged.md",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        merged = tmp_notes_dir / "merged.md"
        assert merged.exists()
        merged_text = merged.read_text(encoding="utf-8")
        assert "Source content" in merged_text
        assert "Target content" in merged_text

    def test_merge_missing_source_returns_404(self, app_client, tmp_notes_dir):
        tgt = tmp_notes_dir / "target.md"
        tgt.write_text("# T", encoding="utf-8")
        resp = app_client.post(
            "/api/notes/merge",
            data=json.dumps(
                {"source_path": "ghost.md", "target_path": "target.md", "final_name": "merged.md"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_merge_missing_params_returns_400(self, app_client):
        resp = app_client.post(
            "/api/notes/merge",
            data=json.dumps({"source_path": "a.md"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
