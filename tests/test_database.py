"""
Tests for database.py — Database class.

All tests use an in-memory / tmp-path database; the production
database (processed_recordings.db / superwhisper.db) is never touched.
"""

import pytest
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

class TestInitSchema:
    def test_all_tables_created(self, db):
        """All 8 expected tables should exist after init."""
        import sqlite3

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "processed_recordings",
            "processing_history",
            "note_files",
            "note_modifications",
            "knowledge_base",
            "name_corrections",
            "processing_status",
            "note_detected_names",
        }
        assert expected.issubset(tables)

    def test_processing_status_singleton_initialised(self, db):
        """The singleton row (id=1) in processing_status must exist."""
        status = db.get_processing_status()
        assert status["id"] == 1
        assert status["is_processing"] == 0


# ---------------------------------------------------------------------------
# Processing status
# ---------------------------------------------------------------------------

class TestProcessingStatus:
    def test_set_and_get_idle(self, db):
        db.set_processing_status(False)
        status = db.get_processing_status()
        assert status["is_processing"] == 0
        assert status["current_folder"] is None

    def test_set_and_get_processing(self, db):
        db.set_processing_status(True, folder_name="folder123", progress=42, message="Running")
        status = db.get_processing_status()
        assert status["is_processing"] == 1
        assert status["current_folder"] == "folder123"
        assert status["progress_percent"] == 42
        assert status["status_message"] == "Running"

    def test_started_at_set_when_processing(self, db):
        before = datetime.now().isoformat()
        db.set_processing_status(True, folder_name="x")
        status = db.get_processing_status()
        # started_at should be a valid ISO timestamp ≥ before
        assert status["started_at"] >= before

    def test_reset_to_idle_preserves_history(self, db):
        db.set_processing_status(True, folder_name="y")
        db.set_processing_status(False)
        status = db.get_processing_status()
        assert status["is_processing"] == 0


# ---------------------------------------------------------------------------
# Processing lifecycle (start / complete / fail)
# ---------------------------------------------------------------------------

class TestProcessingLifecycle:
    def test_start_processing_returns_id(self, db):
        history_id = db.start_processing("folder_abc")
        assert isinstance(history_id, int)
        assert history_id > 0

    def test_start_processing_sets_status(self, db):
        db.start_processing("folder_abc")
        status = db.get_processing_status()
        assert status["is_processing"] == 1
        assert status["current_folder"] == "folder_abc"

    def test_complete_processing(self, db):
        hid = db.start_processing("folder_x")
        db.complete_processing(
            hid,
            note_file="notes/meeting.md",
            meeting_type="one_on_one",
            participants=["Alice", "Bob"],
            metadata={"key": "val"},
        )
        history = db.get_processing_history(limit=1)
        assert history[0]["status"] == "completed"
        assert history[0]["note_file"] == "notes/meeting.md"
        assert history[0]["meeting_type"] == "one_on_one"
        assert "Alice" in history[0]["participants"]

    def test_complete_processing_resets_status(self, db):
        hid = db.start_processing("folder_x")
        db.complete_processing(hid, "f.md", "general", [])
        assert db.get_processing_status()["is_processing"] == 0

    def test_fail_processing(self, db):
        hid = db.start_processing("folder_y")
        db.fail_processing(hid, "Something went wrong")
        history = db.get_processing_history(limit=1)
        assert history[0]["status"] == "failed"
        assert "Something went wrong" in history[0]["error_message"]

    def test_fail_processing_resets_status(self, db):
        hid = db.start_processing("folder_y")
        db.fail_processing(hid, "error")
        assert db.get_processing_status()["is_processing"] == 0


# ---------------------------------------------------------------------------
# Processing history
# ---------------------------------------------------------------------------

class TestProcessingHistory:
    def test_history_ordered_newest_first(self, db):
        hid1 = db.start_processing("old_folder")
        db.complete_processing(hid1, "a.md", "general", [])
        hid2 = db.start_processing("new_folder")
        db.complete_processing(hid2, "b.md", "general", [])

        history = db.get_processing_history()
        assert history[0]["folder_name"] == "new_folder"
        assert history[1]["folder_name"] == "old_folder"

    def test_history_pagination(self, db):
        for i in range(5):
            hid = db.start_processing(f"folder_{i}")
            db.complete_processing(hid, f"f{i}.md", "general", [])

        page1 = db.get_processing_history(limit=2, offset=0)
        page2 = db.get_processing_history(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # No overlap
        ids1 = {r["id"] for r in page1}
        ids2 = {r["id"] for r in page2}
        assert not ids1.intersection(ids2)


# ---------------------------------------------------------------------------
# Processing stats
# ---------------------------------------------------------------------------

class TestProcessingStats:
    def test_stats_empty_db(self, db):
        stats = db.get_processing_stats()
        assert stats["total_processed"] == 0
        assert stats["last_7_days"] == 0

    def test_stats_counts_history(self, db):
        hid = db.start_processing("f")
        db.complete_processing(hid, "n.md", "one_on_one", [])
        stats = db.get_processing_stats()
        # start + complete = 2 events in history
        assert stats["last_7_days"] >= 1
        assert "completed" in stats["by_status"]


# ---------------------------------------------------------------------------
# Note files
# ---------------------------------------------------------------------------

class TestNoteFiles:
    def test_register_creates_entry(self, db):
        db.register_note_file("folder/note.md", file_type="meeting")
        files = db.get_note_files()
        assert any(f["file_path"] == "folder/note.md" for f in files)

    def test_register_upserts_on_conflict(self, db):
        db.register_note_file("note.md", file_type="old_type")
        db.register_note_file("note.md", file_type="new_type")
        files = [f for f in db.get_note_files() if f["file_path"] == "note.md"]
        assert len(files) == 1  # only one row

    def test_mark_note_read(self, db):
        db.register_note_file("read_me.md")
        db.mark_note_read("read_me.md")
        files = [f for f in db.get_note_files() if f["file_path"] == "read_me.md"]
        assert files[0]["last_read"] is not None

    def test_increment_recording_count(self, db):
        db.register_note_file("counter.md")
        db.increment_note_recording_count("counter.md")
        db.increment_note_recording_count("counter.md")
        files = [f for f in db.get_note_files() if f["file_path"] == "counter.md"]
        assert files[0]["associated_recordings"] == 2

    def test_update_note_file_path(self, db):
        db.register_note_file("old/path.md")
        db.update_note_file_path("old/path.md", "new/path.md")
        files = db.get_note_files()
        paths = [f["file_path"] for f in files]
        assert "new/path.md" in paths
        assert "old/path.md" not in paths

    def test_note_files_pagination(self, db):
        for i in range(5):
            db.register_note_file(f"note_{i}.md")
        p1 = db.get_note_files(limit=2, offset=0)
        p2 = db.get_note_files(limit=2, offset=2)
        assert len(p1) == 2
        assert len(p2) == 2


# ---------------------------------------------------------------------------
# Note modifications
# ---------------------------------------------------------------------------

class TestNoteModifications:
    def test_track_modification_stored(self, db):
        db.track_note_modification("note.md", "old content", "new content", "manual_edit")
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM note_modifications WHERE file_path = 'note.md'")
        rows = cursor.fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["change_type"] == "manual_edit"

    def test_get_deleted_notes(self, db):
        db.track_note_modification("deleted.md", "", "", "deleted")
        deleted = db.get_deleted_notes()
        assert any(d["file_path"] == "deleted.md" for d in deleted)


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------

class TestKnowledgeBase:
    def test_add_knowledge_creates_entry(self, db):
        db.add_knowledge("person", "Alice", context="1-on-1", confidence=0.9)
        results = db.get_knowledge(entity_type="person")
        names = [r["entity_name"] for r in results]
        assert "Alice" in names

    def test_add_knowledge_increments_usage(self, db):
        db.add_knowledge("person", "Bob")
        db.add_knowledge("person", "Bob")
        results = db.get_knowledge(entity_type="person")
        bob = next(r for r in results if r["entity_name"] == "Bob")
        assert bob["usage_count"] == 2

    def test_add_knowledge_raises_max_confidence(self, db):
        db.add_knowledge("person", "Charlie", confidence=0.6)
        db.add_knowledge("person", "Charlie", confidence=0.9)
        results = db.get_knowledge(entity_type="person")
        charlie = next(r for r in results if r["entity_name"] == "Charlie")
        assert charlie["confidence"] == pytest.approx(0.9)

    def test_get_knowledge_filters_by_type(self, db):
        db.add_knowledge("person", "Dave")
        db.add_knowledge("project", "SuperWidget")
        people = db.get_knowledge(entity_type="person")
        projects = db.get_knowledge(entity_type="project")
        assert all(r["entity_type"] == "person" for r in people)
        assert all(r["entity_type"] == "project" for r in projects)

    def test_get_knowledge_filters_by_confidence(self, db):
        db.add_knowledge("person", "LowConf", confidence=0.3)
        db.add_knowledge("person", "HighConf", confidence=0.9)
        results = db.get_knowledge(entity_type="person", min_confidence=0.5)
        names = [r["entity_name"] for r in results]
        assert "HighConf" in names
        assert "LowConf" not in names

    def test_get_knowledge_all_types(self, db):
        db.add_knowledge("person", "Eve")
        db.add_knowledge("project", "Alpha")
        results = db.get_knowledge()
        types = {r["entity_type"] for r in results}
        assert "person" in types
        assert "project" in types


# ---------------------------------------------------------------------------
# Name corrections
# ---------------------------------------------------------------------------

class TestNameCorrections:
    def test_add_name_correction(self, db):
        db.add_name_correction("jon", "John", context="manual", source_file="note.md")
        corrections = db.get_name_corrections()
        assert any(c["incorrect_name"] == "jon" and c["correct_name"] == "John" for c in corrections)

    def test_add_correction_increments_on_conflict(self, db):
        db.add_name_correction("alis", "Alice")
        db.add_name_correction("alis", "Alice")
        corrections = db.get_name_corrections()
        entry = next(c for c in corrections if c["incorrect_name"] == "alis")
        # Second insert triggers ON CONFLICT → applied_count += 1
        assert entry["applied_count"] >= 1

    def test_corrections_stored_lowercase_incorrect(self, db):
        db.add_name_correction("FRANK", "Frank")
        corrections = db.get_name_corrections()
        entry = next(c for c in corrections if c["correct_name"] == "Frank")
        assert entry["incorrect_name"] == "frank"


# ---------------------------------------------------------------------------
# Detected names
# ---------------------------------------------------------------------------

class TestDetectedNames:
    def test_store_and_get_detected_names(self, db):
        db.store_detected_names("note.md", ["Alice", "Bob"])
        names = db.get_detected_names("note.md")
        assert set(names) == {"Alice", "Bob"}

    def test_store_detected_names_replaces_existing(self, db):
        db.store_detected_names("note.md", ["Alice", "Bob"])
        db.store_detected_names("note.md", ["Charlie"])
        names = db.get_detected_names("note.md")
        assert names == ["Charlie"]

    def test_store_detected_names_empty_list(self, db):
        db.store_detected_names("note.md", ["Alice"])
        db.store_detected_names("note.md", [])
        names = db.get_detected_names("note.md")
        assert names == []

    def test_update_detected_name(self, db):
        db.store_detected_names("note.md", ["Jon"])
        db.update_detected_name("note.md", "Jon", "John")
        names = db.get_detected_names("note.md")
        assert "John" in names
        assert "Jon" not in names

    def test_get_files_containing_names(self, db):
        db.store_detected_names("a.md", ["Alice"])
        db.store_detected_names("b.md", ["Bob"])
        db.store_detected_names("c.md", ["Alice", "Bob"])

        files = db.get_files_containing_names(["Alice"])
        file_set = set(files)
        assert "a.md" in file_set
        assert "c.md" in file_set
        assert "b.md" not in file_set

    def test_get_files_containing_names_multiple(self, db):
        db.store_detected_names("x.md", ["Alice"])
        db.store_detected_names("y.md", ["Bob"])
        files = db.get_files_containing_names(["Alice", "Bob"])
        assert set(files) == {"x.md", "y.md"}


# ---------------------------------------------------------------------------
# Merge person names
# ---------------------------------------------------------------------------

class TestMergePersonNames:
    def test_merge_updates_knowledge_base(self, db):
        db.add_knowledge("person", "Jon")
        db.add_knowledge("person", "John")
        db.merge_person_names("Jon", "John", keep_name="John")
        people = db.get_knowledge(entity_type="person")
        names = [p["entity_name"] for p in people]
        assert "John" in names
        assert "Jon" not in names

    def test_merge_combines_usage_counts(self, db):
        # Add Jon twice, John once
        db.add_knowledge("person", "Jon")
        db.add_knowledge("person", "Jon")
        db.add_knowledge("person", "John")
        db.merge_person_names("Jon", "John", keep_name="John")
        people = db.get_knowledge(entity_type="person")
        john = next(p for p in people if p["entity_name"] == "John")
        assert john["usage_count"] == 3

    def test_merge_handles_unique_constraint_in_detected_names(self, db):
        """Merging names that both appear in the same file must not raise."""
        db.store_detected_names("shared.md", ["Jon", "John"])
        db.add_knowledge("person", "Jon")
        db.add_knowledge("person", "John")
        # Should not raise despite UNIQUE(file_path, name)
        db.merge_person_names("Jon", "John", keep_name="John")
        names = db.get_detected_names("shared.md")
        assert "John" in names
        assert "Jon" not in names

    def test_merge_updates_detected_names_across_files(self, db):
        db.store_detected_names("a.md", ["Jon"])
        db.store_detected_names("b.md", ["Jon"])
        db.add_knowledge("person", "Jon")
        db.add_knowledge("person", "John")
        db.merge_person_names("Jon", "John", keep_name="John")
        assert "John" in db.get_detected_names("a.md")
        assert "John" in db.get_detected_names("b.md")

    def test_merge_with_nonexistent_entries(self, db):
        """merge_person_names must not crash if neither entry exists."""
        db.merge_person_names("Ghost", "NoOne", keep_name="NoOne")  # should not raise


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------

class TestCleanupHelpers:
    def test_cleanup_orphaned_people_removes_zero_file_entries(self, db):
        db.add_knowledge("person", "Ghost")  # never stored in note_detected_names
        count = db.cleanup_orphaned_people()
        assert count >= 1
        people = db.get_knowledge(entity_type="person")
        assert not any(p["entity_name"] == "Ghost" for p in people)

    def test_cleanup_orphaned_people_preserves_linked_people(self, db):
        db.add_knowledge("person", "Alice")
        db.store_detected_names("note.md", ["Alice"])
        db.cleanup_orphaned_people()
        people = db.get_knowledge(entity_type="person")
        assert any(p["entity_name"] == "Alice" for p in people)

    def test_cleanup_stale_knowledge_removes_missing_file_entries(self, db, tmp_notes_dir):
        # source_file points to a file that does *not* exist on disk
        db.add_knowledge("person", "Phantom", source_file="does_not_exist.md")
        count = db.cleanup_stale_knowledge(tmp_notes_dir)
        assert count >= 1

    def test_cleanup_stale_knowledge_keeps_existing_file_entries(self, db, tmp_notes_dir):
        existing = tmp_notes_dir / "real.md"
        existing.write_text("# Real Note", encoding="utf-8")
        # Store relative path as it appears in source_file
        db.add_knowledge("person", "Alive", source_file="real.md")
        db.cleanup_stale_knowledge(tmp_notes_dir)
        results = db.get_knowledge(entity_type="person")
        assert any(r["entity_name"] == "Alive" for r in results)
