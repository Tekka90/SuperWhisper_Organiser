# SuperWhisper Organiser - Data Model Documentation

This document describes the complete database schema and data model used by SuperWhisper Organiser.

## Database Overview

**Database Type:** SQLite  
**Database File:** `processed_recordings.db`  
**Location:** Application root directory  

The database consists of 8 tables that track recordings, notes, knowledge, and processing status.

---

## Tables Overview

| Table | Purpose | Records |
|-------|---------|---------|
| `processed_recordings` | Track which recordings have been processed | One per recording |
| `processing_history` | Complete audit log of all processing events | One per processing attempt |
| `note_files` | Metadata for all note files | One per note file |
| `note_modifications` | Track manual edits to notes | One per modification |
| `knowledge_base` | Learned entities (people, projects, patterns) | One per entity |
| `name_corrections` | Transcript error corrections | One per correction pair |
| `processing_status` | Current real-time processing state | Singleton (1 row) |
| `note_detected_names` | AI-detected names in note files | One per name per file |

---

## Table Schemas

### 1. `processed_recordings`

Tracks which SuperWhisper recordings have been successfully processed.

```sql
CREATE TABLE processed_recordings (
    folder_name TEXT PRIMARY KEY,      -- Recording folder name (timestamp)
    processed_at TEXT NOT NULL,        -- ISO timestamp when processed
    note_file TEXT,                    -- Path to output note file
    meeting_type TEXT,                 -- e.g., "1-on-1", "team meeting"
    participants TEXT,                 -- Comma-separated names
    duration INTEGER,                  -- Meeting duration in milliseconds
    recording_date TEXT,               -- ISO timestamp of recording
    status TEXT DEFAULT 'completed'    -- 'completed' or 'failed'
)
```

**Usage:**
- Prevents duplicate processing
- Tracks output file location
- Stores basic meeting metadata

**Example:**
```
folder_name: "1738663480"
processed_at: "2025-02-04T10:15:30"
note_file: "1-to-1/1-to-1 with Fred.md"
meeting_type: "1-on-1"
participants: "Fred, Stephane"
duration: 1105383
recording_date: "2025-02-04T10:03:57"
status: "completed"
```

---

### 2. `processing_history`

Complete audit log of every processing event (success or failure).

```sql
CREATE TABLE processing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_name TEXT NOT NULL,         -- Recording folder name
    started_at TEXT NOT NULL,          -- When processing started
    completed_at TEXT,                 -- When processing finished (NULL if failed)
    status TEXT NOT NULL,              -- 'processing', 'completed', 'failed'
    note_file TEXT,                    -- Output note file path
    meeting_type TEXT,                 -- Detected meeting type
    participants TEXT,                 -- Detected participants
    error_message TEXT,                -- Error details if failed
    metadata TEXT                      -- JSON with additional context
)
```

**Usage:**
- Full processing history for audit trail
- Error tracking and debugging
- Processing analytics

**Example:**
```
id: 123
folder_name: "1738663480"
started_at: "2025-02-04T10:15:25"
completed_at: "2025-02-04T10:15:30"
status: "completed"
note_file: "1-to-1/1-to-1 with Fred.md"
meeting_type: "1-on-1"
participants: "Fred, Stephane"
error_message: NULL
metadata: "{\"ai_model\":\"gpt-4\",\"tokens\":1250}"
```

---

### 3. `note_files`

Metadata for all note files created/managed by the system.

```sql
CREATE TABLE note_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,    -- Relative path to note file
    created_at TEXT NOT NULL,          -- When file was created
    last_modified TEXT NOT NULL,       -- When file was last modified
    last_read TEXT,                    -- When file was last read by system
    file_type TEXT,                    -- e.g., "1-on-1", "team-meeting"
    associated_recordings INTEGER DEFAULT 0,  -- Count of recordings in file
    metadata TEXT                      -- JSON with additional details
)
```

**Usage:**
- Track note file lifecycle
- Manage file organization
- Count recordings per file
- Support knowledge extraction

**Example:**
```
id: 45
file_path: "1-to-1/1-to-1 with Fred.md"
created_at: "2025-01-15T09:00:00"
last_modified: "2025-02-04T10:15:30"
last_read: "2025-02-04T10:15:25"
file_type: "1-on-1"
associated_recordings: 7
metadata: "{\"person\":\"Fred\"}"
```

---

### 4. `note_modifications`

Tracks manual edits made to note files (for learning from user corrections).

```sql
CREATE TABLE note_modifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,           -- Which file was modified
    modified_at TEXT NOT NULL,         -- When modification occurred
    change_type TEXT,                  -- e.g., "name_correction", "content_edit"
    old_content TEXT,                  -- Content before (first 200 chars)
    new_content TEXT,                  -- Content after (first 200 chars)
    diff_summary TEXT                  -- Description of changes
)
```

**Usage:**
- Learn from user corrections
- Detect name corrections (transcript errors)
- Track manual improvements
- Improve future AI suggestions

**Example:**
```
id: 89
file_path: "1-to-1/1-to-1 with Fred.md"
modified_at: "2025-02-04T14:30:00"
change_type: "name_correction"
old_content: "Meeting with Red about..."
new_content: "Meeting with Fred about..."
diff_summary: "Corrected 'Red' to 'Fred'"
```

---

### 5. `knowledge_base`

Learned entities extracted from notes (people, projects, meeting patterns).

```sql
CREATE TABLE knowledge_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,         -- 'person', 'project', 'meeting_pattern'
    entity_name TEXT NOT NULL,         -- Name of entity
    context TEXT,                      -- Additional context (e.g., "team member")
    source_file TEXT,                  -- Most recent file this was seen in
    confidence REAL DEFAULT 1.0,       -- Confidence score (0.0-1.0)
    created_at TEXT NOT NULL,          -- First time learned
    usage_count INTEGER DEFAULT 1,     -- How many times mentioned
    last_seen TEXT NOT NULL,           -- Most recent mention timestamp
    UNIQUE(entity_type, entity_name)
)
```

**Usage:**
- Build knowledge graph from notes
- Track people, projects, topics
- Provide context to AI analyzer
- Support intelligent suggestions

**Entity Types:**
- **person**: Individual people (Fred, Stephane, etc.)
- **project**: Project names (Project Phoenix, etc.)
- **meeting_pattern**: Recurring meeting types
  - Format: `"1-on-1:Fred"` or `"team:Engineering"`

**Example:**
```
id: 12
entity_type: "person"
entity_name: "Fred"
context: "team member"
source_file: "1-to-1/1-to-1 with Fred.md"
confidence: 0.95
created_at: "2025-01-15T09:00:00"
usage_count: 23
last_seen: "2025-02-04T10:15:30"
```

---

### 6. `name_corrections`

Tracks corrections for transcript errors (learns to fix common mistakes).

```sql
CREATE TABLE name_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incorrect_name TEXT NOT NULL,      -- Name as transcribed (wrong)
    correct_name TEXT NOT NULL,        -- Correct name
    context TEXT,                      -- Where/how correction was found
    source_file TEXT,                  -- File where correction was detected
    created_at TEXT NOT NULL,          -- When correction was learned
    applied_count INTEGER DEFAULT 0,   -- How many times applied
    UNIQUE(incorrect_name, correct_name)
)
```

**Usage:**
- Learn from user corrections
- Auto-fix transcript errors in future recordings
- Improve accuracy over time

**Example:**
```
id: 5
incorrect_name: "red"
correct_name: "Fred"
context: "1-on-1 meeting notes"
source_file: "1-to-1/1-to-1 with Fred.md"
created_at: "2025-01-20T11:30:00"
applied_count: 8
```

**How it works:**
1. User edits note to fix transcription error
2. System detects the change in `note_modifications`
3. Extracts the correction pattern
4. Adds to `name_corrections`
5. Future transcripts automatically apply correction

---

### 7. `processing_status`

Real-time status of current processing (singleton table - only 1 row).

```sql
CREATE TABLE processing_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Always 1 (singleton)
    is_processing INTEGER DEFAULT 0,         -- 1 if currently processing
    current_folder TEXT,                     -- Folder being processed now
    started_at TEXT,                         -- When current processing started
    progress_percent INTEGER DEFAULT 0,      -- Progress percentage (0-100)
    status_message TEXT                      -- Human-readable status
)
```

**Usage:**
- Show real-time processing status in web UI
- Prevent concurrent processing
- Display progress to user

**Example (idle):**
```
id: 1
is_processing: 0
current_folder: NULL
started_at: NULL
progress_percent: 0
status_message: "Idle"
```

**Example (processing):**
```
id: 1
is_processing: 1
current_folder: "1738663480"
started_at: "2025-02-04T10:15:25"
progress_percent: 45
status_message: "Analyzing meeting with AI..."
```

---

### 8. `note_detected_names`

Stores names detected in note files by AI (for knowledge management).

```sql
CREATE TABLE note_detected_names (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,           -- Note file path
    name TEXT NOT NULL,                -- Detected person name
    detected_at TEXT NOT NULL,         -- When detection occurred
    detection_method TEXT DEFAULT 'ai', -- 'ai', 'manual', 'pattern'
    UNIQUE(file_path, name)
)
```

**Usage:**
- Track which names appear in which files
- Support name detection feature in web UI
- Enable name highlighting in notes
- Allow name merging for duplicates
- Count files per person in Knowledge Base

**Example:**
```
id: 156
file_path: "1-to-1/1-to-1 with Fred.md"
name: "Fred"
detected_at: "2025-02-04T10:16:00"
detection_method: "ai"
```

**Features using this table:**
- **Name Detection**: AI scans notes and populates this table
- **Name Highlighting**: Shows detected names in yellow in web UI
- **Name Correction**: Click name to fix with AI help
- **Name Merging**: Drag one name onto another to merge (updates all entries)
- **Knowledge Base**: Shows "In X files" count per person
- **File Cleanup**: Deletes orphaned knowledge_base entries with 0 files

---

## Data Relationships

### Recording → Note File → Knowledge

```
SuperWhisper Recording (folder_name)
    ↓
processed_recordings (tracks processing)
    ↓
processing_history (logs event)
    ↓
note_files (registers output file)
    ↓
note_detected_names (names in file)
    ↓
knowledge_base (learned entities)
```

### User Edit → Learning Cycle

```
User edits note file
    ↓
note_modifications (logs change)
    ↓
System detects name correction
    ↓
name_corrections (stores pattern)
    ↓
Future transcripts auto-corrected
```

### Knowledge Base Population

```
Scan existing notes
    ↓
Extract people from filenames
    ↓
Extract projects from content
    ↓
Identify meeting patterns
    ↓
Store in knowledge_base
    ↓
Provide context to AI analyzer
```

---

## Database Operations

### Common Queries

**Get all processed recordings:**
```python
db.get_all_processed()
```

**Mark recording as processed:**
```python
db.mark_processed(folder_name, note_file, meeting_type, participants)
```

**Get processing history:**
```python
db.get_processing_history(limit=50, status_filter='completed')
```

**Add to knowledge base:**
```python
db.add_knowledge('person', 'Fred', source_file='1-to-1/1-to-1 with Fred.md')
```

**Get all people:**
```python
people = db.get_knowledge(entity_type='person', min_confidence=0.5)
```

**Store detected names:**
```python
db.store_detected_names('path/to/note.md', ['Fred', 'Stephane'], method='ai')
```

**Merge person names:**
```python
db.merge_person_names('Stefan', 'Stephane', keep_name='Stephane')
```

**Clean up orphaned entries:**
```python
deleted_count = db.cleanup_orphaned_people()
```

---

## Indexes and Performance

**Primary Keys:**
- All tables have either `id` (autoincrement) or natural key (e.g., `folder_name`)

**Unique Constraints:**
- `note_files.file_path`: Each file path appears once
- `knowledge_base(entity_type, entity_name)`: Each entity unique per type
- `name_corrections(incorrect_name, correct_name)`: Each correction pair unique
- `note_detected_names(file_path, name)`: Each name unique per file

**Foreign Key Relationships:**
- Not enforced by foreign keys (SQLite limitation)
- Referential integrity maintained by application logic
- Cascading deletes handled in Python code

---

## Database Maintenance

### Automatic Cleanup

**Orphaned People Cleanup:**
- Runs on Knowledge Base page load
- Removes people from `knowledge_base` with 0 files in `note_detected_names`
- Keeps database clean after name deletions/merges

**Stale Status Cleanup:**
- Processing status auto-resets if stale (no update in 10 minutes)
- Prevents stuck "processing" state

### Manual Maintenance

**Rebuild Knowledge Base:**
```bash
python sworganiser.py scan-notes
```

**View Database Statistics:**
```bash
sqlite3 processed_recordings.db "SELECT COUNT(*) FROM processed_recordings"
sqlite3 processed_recordings.db "SELECT COUNT(*) FROM knowledge_base WHERE entity_type='person'"
```

---

## Database Evolution

### Schema Evolution

**Current Version:** 1.0

Database includes complete feature set:
- Core tracking: `processed_recordings`, `processing_history`
- File management: `note_files`, `note_modifications`
- Learning system: `knowledge_base`, `name_corrections`
- Real-time status: `processing_status`
- Name detection: `note_detected_names`

All tables created automatically on first run with `CREATE TABLE IF NOT EXISTS`.

### Migration Strategy

- Database schema auto-initializes on first run
- New tables added with `CREATE TABLE IF NOT EXISTS`
- Existing data preserved during upgrades
- No destructive migrations

---

## Best Practices

### For Developers

1. **Use Database Methods:** Always use `Database` class methods, never raw SQL
2. **Transaction Safety:** Database methods handle commits/rollbacks
3. **Connection Management:** Connections auto-closed by methods
4. **Error Handling:** Wrap database calls in try/except blocks
5. **Logging:** Database operations are logged for debugging

### For Users

1. **Backup Regularly:** Copy `processed_recordings.db` to backup location
2. **Don't Edit Directly:** Use web interface or API, not SQLite directly
3. **Sync Considerations:** If syncing folder, exclude `.db` files
4. **Database Size:** Grows slowly; 1000 recordings ≈ 1-2 MB

---

## Troubleshooting

**Database locked:**
- Another process is accessing the database
- Wait or restart application

**Corrupted database:**
- Restore from backup
- Delete `.db` file to rebuild (loses history)

**Missing tables:**
- Run application once to initialize schema
- Check file permissions on database file

**Slow queries:**
- Database is optimized for current workload
- Indexes on primary keys and unique constraints
- No performance issues expected with < 100k recordings

---

## See Also

- [README.md](README.md) - General documentation
- [WEB_INTERFACE_GUIDE.md](WEB_INTERFACE_GUIDE.md) - Web UI features
- [copilot-instructions.md](copilot-instructions.md) - Development context
- [database.py](database.py) - Database implementation
