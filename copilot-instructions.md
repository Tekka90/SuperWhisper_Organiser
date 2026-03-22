# SuperWhisper Organiser - GitHub Copilot Context

> **Purpose:** AI-powered meeting note organizer that processes SuperWhisper recordings into intelligent markdown files with name detection, correction, and knowledge management.

## Development Workflow (ALWAYS follow these rules)

> These rules apply to **every** code change, no matter how small.

### 1. Tests — mandatory after every change
- **Run the full suite** before and after any modification: `python -m pytest tests/`
- **All 185 tests must stay green.** Never leave a failing test unresolved.
- **Write new tests** for every new feature, endpoint, DB method, or utility function added.
  - New DB method → add a test class in `tests/test_database.py`
  - New API endpoint → add a test class in `tests/test_webapp.py`
  - New utility function → add tests in the relevant `tests/test_*.py` file
- **Update existing tests** if behaviour changes (don't just delete the failing test).
- Tests must use `tmp_path` / `mock_config` fixtures — **never touch the production database or notes folder**.

### 2. Documentation — mandatory after every change
- **`copilot-instructions.md`**: update the Component Map line counts, Critical Patterns, API table, or Quick Reference if anything changes.
- **`README.md`**: update if user-facing behaviour, install steps, or commands change.
- **`docs/DATA_MODEL.md`**: update if the database schema changes (new table, new column, new constraint).
- **`CHANGELOG.md`**: add an entry summarising what changed and why.
- Keep the `**Version:**` / `**Updated:**` line at the bottom of this file current.

### 3. Order of operations for a typical feature
1. Write / update the test(s) first (TDD preferred, or at minimum alongside the code).
2. Implement the feature.
3. Run `python -m pytest tests/` — fix until green.
4. Update all relevant documentation files listed above.

## Tech Stack

- **Backend:** Python 3.8+, Flask 3.0.0, SQLite (8 tables)
- **AI:** OpenAI API (GPT-4 or local models)
- **Frontend:** Vanilla JavaScript, marked.js, custom CSS
- **Key Libraries:** watchdog (monitoring), click (CLI), rich (terminal UI)

## Component Map

### Backend (Python)
| File | Lines | Purpose |
|------|-------|---------|
| `sworganiser.py` | ~300 | CLI entry point (click commands), web server launcher |
| `webapp.py` | ~1490 | Flask REST API, all endpoints, serves HTML/static files |
| `database.py` | ~795 | SQLite operations, 8 tables, CRUD methods |
| `analyzer.py` | ~500 | OpenAI integration, name detection/replacement |
| `organizer.py` | ~600 | Note file creation/management, folder structure |
| `watcher.py` | ~244 | File system monitoring (watchdog), detects new recordings |
| `learning.py` | ~416 | Knowledge extraction, builds context for AI |
| `utils.py` | ~200 | Config loading, logging, path utilities |

### Frontend (JavaScript + HTML)
| File | Lines | Purpose |
|------|-------|---------|
| `static/js/notes.js` | ~900 | Note viewer, name detection UI, file tree |
| `static/js/knowledge.js` | ~480 | Knowledge base, drag-and-drop name merging |
| `static/css/style.css` | ~890 | All styling, animations, responsive layout |
| `templates/notes.html` | - | Note viewer/editor page |
| `templates/knowledge.html` | - | Knowledge base page (people, projects) |
| `templates/index.html` | - | Dashboard with processing status |

### Database (SQLite)
8 tables - see [DATA_MODEL.md](docs/DATA_MODEL.md) for schema details:
- `processed_recordings` - Processed meeting tracking
- `note_files` - Note file metadata
- `note_detected_names` - AI-detected names per file **(UNIQUE: file_path, name)**
- `knowledge_base` - People, projects, patterns **(UNIQUE: entity_type, entity_name)**
- `name_corrections` - Auto-correction rules
- `processing_status` - Real-time progress (singleton table, id=1)
- `processing_history` - Complete audit log
- `note_modifications` - Manual edit tracking

## Critical Implementation Patterns

### 1. UNIQUE Constraint Handling (Important!)
**Problem:** `note_detected_names(file_path, name)` has UNIQUE constraint. When merging names that both exist in the same file, UPDATE would violate this.

**Solution (in `database.py`):**
```python
# ALWAYS delete duplicates BEFORE updating
cursor.execute("""
    DELETE FROM note_detected_names 
    WHERE file_path IN (...) AND name = ?
""", (name_to_remove,))
conn.commit()

# THEN update remaining entries
cursor.execute("""
    UPDATE note_detected_names 
    SET name = ? WHERE name = ?
""", (keep_name, name_to_remove))
```

### 2. Name Detection & Highlighting
- Store detected names in `note_detected_names` table
- Auto-highlight on page load using regex word boundaries: `\b${name}\b`
- CSS class: `.detected-name` (yellow-orange gradient background)
- JavaScript: `highlightNamesInViewer()` wraps matches in `<span>`

### 3. AI Name Replacement (Context-Aware)
- Don't use simple find/replace - AI understands grammar
- Handles: possessives ("John" → "John's"), case sensitivity, context
- Endpoint: `POST /api/notes/correct-name`
- Method: `analyzer.replace_name_with_ai(content, old_name, new_name)`

### 4. Processing Status (Singleton Pattern)
- `processing_status` table has exactly 1 row (id=1)
- Track: `is_processing`, `current_folder`, `progress_message`, `last_updated`
- Auto-reset if `last_updated` > 10 minutes old
- Frontend polls: `GET /api/processing-status` every 2 seconds

### 5. Orphaned Entry Cleanup
- Runs automatically in `knowledge.html` on page load
- Deletes people from `knowledge_base` with 0 files
- SQL: `WHERE entity_type='person' AND NOT EXISTS (SELECT 1 FROM note_detected_names WHERE name = entity_name)`

### 6. File Sorting by Date
- Extract dates from file content with regex: `(January|February|...) \d{1,2}, \d{4}`
- Include `latest_date` in `/api/note-tree` response
- Frontend sorts by `latest_date` DESC (newest first)
- Helper: `_extract_latest_date_from_file()` in `webapp.py`

### 7. Drag-and-Drop Merging
- HTML5 drag-drop API: `dragstart`, `dragover`, `drop` events
- Visual feedback with CSS classes: `.dragging`, `.drag-over`
- Modal confirmation before merging
- Updates ALL files containing either name (can be 10+ files)

### 8. Path Security Validation
- All note file paths are validated with `_check_path_security(*files)` in `webapp.py`
- Returns `(Response, 403)` tuple on traversal attempt, `None` on success
- Call pattern: `err = _check_path_security(file); if err: return err`
- Never inline the `resolve().relative_to()` block — always use this helper

### 9. Bulk Name Replacement in Files
- Use `_replace_name_in_files(files, old_name, new_name, change_type)` in `webapp.py`
- Handles read → regex sub → write → `track_note_modification` in one place
- Used by both name-merge and global correction endpoints
- Returns count of files modified

## API Patterns

### Standard Response Format
```python
# Success
return jsonify({'success': True, 'data': {...}})

# Error  
return jsonify({'success': False, 'error': 'Message'}), 400
```

### Key Endpoints
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/note-tree` | File tree with latest dates |
| GET | `/api/note/<path>` | Read note content |
| POST | `/api/notes/detect-names` | AI name detection |
| POST | `/api/notes/correct-name` | AI name replacement |
| POST | `/api/knowledge/merge-names` | Merge two names |
| DELETE | `/api/knowledge/person/<name>` | Delete person |
| GET | `/api/processing-status` | Real-time progress |
| GET | `/api/knowledge` | All KB entries |

## Common Gotchas & Solutions

| Issue | Solution |
|-------|----------|
| UNIQUE constraint error on merge | DELETE duplicates BEFORE UPDATE (see pattern #1) |
| Names not auto-highlighted | Check `note_detected_names` has entries for file |
| Stale Knowledge Base data | Use cache-busting: `?_=${Date.now()}` |
| File links broken | Route is `/notes-viewer?file=X` not `/notes?file=X` |
| Progress stuck "Processing..." | Refresh page, check `processing_status.last_updated` |
| Database locked | Kill zombie Python processes: `pkill -f "python.*sworganiser.py"` |
| Port 5000 in use | `lsof -ti:5000 \| xargs kill -9` |
| Names showing "In 0 files" | Auto-cleanup runs on KB page load |

## Code Conventions

**Python:**
- Type hints where helpful
- Docstrings for public methods
- `logger.info()` for events, `logger.error()` for errors
- Private methods: prefix `_` (e.g., `_extract_latest_date()`)
- Never bare `except:` - catch specific exceptions

**JavaScript:**
- `async/await` not `.then()` chains
- `function name()` for top-level, `const name = ()` for callbacks
- camelCase: `loadKnowledge()`, `detectNames()`
- Always show loading states and error handling

**CSS:**
- kebab-case: `.detected-name`, `.drag-over`
- Animations in `@keyframes` blocks
- Group related styles together

**Database:**
- All SQL in `database.py`, never in `webapp.py`
- Use `row_factory = sqlite3.Row` for dict-like access
- Always `conn.commit()` after writes
- Return `dict(row)` for JSON serialization

## Quick Reference

### Start Server
```bash
cd ~/Documents/superwhisper/SuperWhisper\ Organiser
source venv/bin/activate
python sworganiser.py web
# Open http://127.0.0.1:5000
```

### Run Unit Tests
```bash
cd ~/Documents/superwhisper/SuperWhisper\ Organiser
source venv/bin/activate
scripts/run_tests.sh                   # all 185 tests
scripts/run_tests.sh --cov             # with coverage report
python -m pytest tests/ -k db    # filter by name

# Individual modules
python -m pytest tests/test_database.py   # 68 tests — DB layer
python -m pytest tests/test_utils.py      # 31 tests — utility helpers
python -m pytest tests/test_learning.py   # 32 tests — LearningSystem
python -m pytest tests/test_analyzer.py   # 18 tests — OpenAI (mocked)
python -m pytest tests/test_webapp.py     # 51 tests — REST API
```

> **Safety**: Tests always use `tmp_path` fixtures. The production database
> and notes folder are **never** accessed.

## Test Infrastructure

| File | Purpose |
|------|---------|
| `pytest.ini` | Pytest config — `testpaths = tests`, short TB, strict markers |
| `scripts/run_tests.sh` | Shell helper: activates venv, installs pytest, optional `--cov` flag |
| `tests/conftest.py` | Shared fixtures: `db`, `tmp_notes_dir`, `mock_config`, `app_client` |
| `tests/test_database.py` | `Database` class — schema, lifecycle, knowledge base, merge, cleanup |
| `tests/test_utils.py` | `format_duration`, `expand_env_vars`, `load_meta_json`, legacy DB helpers |
| `tests/test_learning.py` | `LearningSystem` — extraction, corrections, prompt context, scan |
| `tests/test_analyzer.py` | `MeetingAnalyzer` — prompt building, OpenAI mock, JSON fallback |
| `tests/test_webapp.py` | All Flask endpoints + `_extract_latest_date_from_file`, `_merge_note_contents` |

## Dependencies

**Backend:** `openai>=1.0.0`, `watchdog>=3.0.0`, `click>=8.0.0`, `rich>=13.0.0`, `PyYAML>=6.0`, `python-dateutil>=2.8.0`, `Flask>=3.0.0`, `flask-cors>=4.0.0`

**Frontend:** `marked.js` (CDN), vanilla JavaScript, modern CSS

## Documentation

- [DATA_MODEL.md](docs/DATA_MODEL.md) - Complete database schema
- [WEB_INTERFACE_GUIDE.md](docs/WEB_INTERFACE_GUIDE.md) - User guide
- [README.md](README.md) - Project overview

---
**Version:** 1.2 | **Updated:** March 22, 2026
