# SuperWhisper Organiser - Web Interface & Learning System

## 🎉 Features

SuperWhisper Organiser has been significantly enhanced with:

### 1. **Web Application**
- Real-time processing status dashboard
- Complete processing history with search and filtering  
- Interactive note viewer and editor
- Knowledge base explorer

### 2. **Intelligent Learning System**
- Automatically learns from your existing notes
- Recognizes people, projects, and meeting patterns
- Tracks name corrections from transcript errors
- Improves future processing with learned context

### 3. **Enhanced Tracking**
- Full processing history with timestamps
- Success/failure tracking
- Note file metadata and statistics
- Processing status monitoring

---

## 🚀 Quick Start

### Installation

1. **Install new dependencies:**
```bash
pip install -r requirements.txt
```

The new requirements include:
- `flask` - Web framework
- `flask-cors` - CORS support

### Running the Web Interface

Start the web application:

```bash
python sworganiser.py web
```

Or specify custom host and port:

```bash
python sworganiser.py web --host 0.0.0.0 --port 8080
```

Then open your browser to: **http://127.0.0.1:5000**

---

## 📱 Web Interface Features

### Dashboard (`/`)
- **Current Status**: See if recordings are being processed right now
- **Statistics**: Total processed, recent activity, success rates
- **By Type Chart**: Visual breakdown of meeting types
- **Recent Activity**: Last 5 processing events
- **Quick Actions**: Scan notes, refresh data

### History (`/history`)
- **Complete History**: All processing events with details
- **Search**: Filter by folder name
- **Filter**: By status (completed, processing, failed)
- **Pagination**: Browse through large histories
- **Details**: View timestamps, participants, output files

### Notes Viewer (`/notes-viewer`)

The notes viewer is your central hub for managing meeting notes with AI-powered features.

#### File Management
- **File Browser**: Hierarchical view of all your notes
- **Smart Sorting**: Files sorted by latest date mentioned in content (newest first)
- **Folder Organization**: Clean structure (1-to-1, team-meetings, etc.)
- **Search**: Find notes quickly by filename
- **Select File**: Click to view, rendered Markdown preview

#### Viewing & Editing
- **Markdown Rendering**: Beautiful formatted view powered by marked.js
- **Edit Mode**: Click "Edit" to modify note content
- **Save/Cancel**: Save changes or cancel without saving
- **Auto-Save**: Changes immediately written to disk

#### AI-Powered Name Detection
- **Detect Names Button**: Click to analyze note and extract person names
- **Progress Indicators**: 3-stage progress display (Analyzing → Processing → Highlighting)
- **Auto-Highlighting**: Detected names highlighted in yellow-orange gradient
- **Persistent Storage**: Names stored in database, auto-highlight on future visits
- **Visual Feedback**: Highlighted names are clickable

#### AI-Powered Name Correction
- **Click to Correct**: Click any highlighted name to open correction dialog
- **AI Replacement**: AI intelligently replaces names preserving context
  - Handles possessives ("Fred's" → "Stephane's")
  - Respects grammar rules
  - Uses word boundaries (avoids partial matches)
- **One-Click Fix**: Apply correction instantly
- **Database Update**: Updates file, database, and knowledge base
- **Progress Display**: Shows 3 stages (Replacing → Saving → Updating)

#### File Operations
- **Rename**: Change filename while preserving content
- **Delete**: Remove note file (with confirmation)
- **Merge**: Combine multiple notes into one
- **Extract**: Split sections into separate files
- **Move**: Organize into different folders

### Knowledge Base (`/knowledge`)

The most powerful new feature - your intelligent knowledge management system.

#### People Tab
- **All Detected People**: Everyone AI has found in your notes
- **File Count**: Shows "In X files" for each person
- **Last Seen**: Which file they were most recently mentioned in
- **Clickable Links**: Click file link to open that note directly
- **Confidence Score**: AI confidence in detection (0-100%)
- **Mention Count**: How many times they appear across all notes

#### Drag-and-Drop Name Merging
- **Visual Merging**: Drag one name card onto another
- **Smart Modal**: Choose which spelling to keep
- **Bulk Update**: Updates ALL files containing the removed name
- **Database Sync**: Merges usage counts and contexts
- **Auto-Correction**: Adds correction rule for future recordings
- **Progress Feedback**: Shows how many files were updated

**How to merge names:**
1. Find two names that are duplicates (e.g., "Stefan" and "Stephane")
2. Drag "Stefan" card onto "Stephane" card
3. Modal appears: "Keep Stefan or Keep Stephane?"
4. Click "Keep Stephane"
5. System updates all files, merges database entries
6. Success message shows: "✓ Successfully merged names into 'Stephane'\n\nUpdated 3 note files."

#### Delete Non-Names
- **Cleanup Tool**: Small red "Delete" button on each person card
- **Remove Mistakes**: Delete entries that aren't actually people
  - Examples: "Meeting", "Discussion", "Project", etc.
- **Confirmation**: Shows warning dialog before deletion
- **Complete Removal**: Deletes from database and knowledge base
- **Auto-Refresh**: Knowledge Base updates automatically

#### Projects Tab
- **Detected Projects**: All project names found in notes
- **Usage Stats**: How often each project is mentioned
- **Context**: Additional context where available
- **Last Seen**: Most recent mention

#### Meeting Patterns Tab
- **1-on-1 Meetings**: Recurring 1-on-1s detected
- **Team Meetings**: Regular team meeting patterns
- **Other Patterns**: Additional recurring meeting types

#### Name Corrections Tab
- **Learning History**: All name corrections the system has learned
- **Applied Count**: How many times each correction was auto-applied
- **Source Tracking**: Which file the correction came from

#### Real-Time Updates
- **Refresh Button**: Manual refresh anytime
- **Cache Busting**: Never shows stale data
- **Auto-Cleanup**: Removes orphaned entries (people with 0 files)
- **Loading States**: Visual feedback during updates

### History (`/history`)
- **Complete Audit Log**: Every processing event recorded
- **Status Filtering**: View completed, failed, or all events
- **Search**: Find specific recording by folder name
- **Pagination**: Navigate through history efficiently
- **Event Details**: 
  - Folder name and timestamp
  - Processing duration
  - Output file location
  - Participants detected
  - Meeting type
  - Error messages (if failed)

---

## 🧠 Learning System

### How It Works

The learning system continuously improves by:

1. **Scanning Existing Notes**
   - Extracts person names from filenames and content
   - Identifies projects mentioned multiple times
   - Recognizes meeting patterns (1-on-1, team meetings)
   - Builds a knowledge graph

2. **Tracking Corrections**
   - Monitors edits you make to notes
   - Detects name corrections (e.g., "Red" → "Fred")
   - Applies corrections to future transcripts automatically

3. **Contextual Intelligence**
   - Suggests appending to existing 1-on-1 files
   - Recognizes recurring participants
   - Associates meetings with known projects
   - Provides context to the AI analyzer

4. **AI-Powered Name Detection**
   - Analyzes note content with AI
   - Extracts and highlights person names
   - Stores names persistently in database
   - Auto-highlights on every page load

5. **Intelligent Name Correction**
   - Click any highlighted name to correct
   - AI replaces name with context understanding
   - Handles grammar, possessives, capitalization
   - Updates everywhere: file, database, knowledge base

6. **Visual Name Merging**
   - Drag one name onto another to merge
   - System updates all files automatically
   - Merges database entries and usage counts
   - Creates auto-correction rule for future

### Manual Knowledge Scan

Trigger a full rescan of your notes:

```bash
python sworganiser.py scan-notes
```

Or click the "Scan Notes" button in the web interface dashboard.

This is automatically done on startup, but you can run it again after making many manual edits.

---

## 🎯 Example Use Cases

### Use Case 1: Recurring 1-on-1 Meetings

**Without intelligent organization:**
- Each 1-on-1 with Fred creates a new file
- You manually organize them

**With SuperWhisper Organiser:**
- First meeting with Fred creates: `1-to-1 with Fred.md`
- System learns about this file
- Future meetings with Fred automatically append to the same file
- All Fred's 1-on-1s in one place!

### Use Case 2: AI-Powered Name Detection

**Scenario:**
You have a team meeting note with multiple participants but names aren't highlighted.

**With Name Detection:**
1. Open the note in Notes Viewer
2. Click "Detect names" button
3. AI analyzes content: "Analyzing..."
4. Names extracted and stored: "Processing..."
5. Names highlighted in yellow: "Highlighting..."
6. All detected names now clickable
7. Future opens auto-highlight (stored in database)

**Benefits:**
- Quick identification of all participants
- Visual confirmation of who was present
- Enables name correction workflow
- Persistent - works forever after detection

### Use Case 3: Name Correction with AI

**Scenario:**
SuperWhisper transcribed "Lexman" but it should be "Lekshmanan"

**Before:**
- Find/replace manually (risky for partial matches)
- Update multiple files individually
- No context preservation

**With AI Correction:**
1. Click on highlighted "Lexman" in note
2. Modal appears with correction option
3. Click "Apply AI Correction"
4. AI intelligently replaces:
   - "Lexman is working" → "Lekshmanan is working"
   - "Lexman's project" → "Lekshmanan's project"
   - "I met with Lexman" → "I met with Lekshmanan"
5. File saved, database updated, knowledge base refreshed
6. Done in seconds!

**Benefits:**
- Context-aware replacement
- Handles grammar automatically
- Updates everywhere at once
- No manual editing needed

### Use Case 4: Drag-and-Drop Name Merging

**Scenario:**
You have duplicate name entries: "Stefan", "Stephane", and "Stephen" all referring to the same person.

**Before:**
- Edit each file manually
- Search and replace risky
- Database gets out of sync
- Knowledge base has duplicates

**With Drag-and-Drop Merging:**
1. Go to Knowledge Base → People tab
2. See three entries: Stefan (2 files), Stephane (5 files), Stephen (1 file)
3. Drag "Stefan" onto "Stephane"
4. Modal: "Keep Stefan or Keep Stephane?" → Click "Keep Stephane"
5. System updates 2 files automatically
6. Drag "Stephen" onto "Stephane"
7. System updates 1 more file
8. Result: One clean "Stephane" entry with 8 files

**Benefits:**
- Visual, intuitive interface
- Bulk updates all files at once
- Database stays synchronized
- Usage counts combined correctly
- Auto-correction rule created for future

### Use Case 5: Knowledge Base Cleanup

**Scenario:**
Name detection picked up words that aren't actually people: "Meeting", "Discussion", "Project".

**Quick Cleanup:**
1. Go to Knowledge Base → People tab
2. Find entries with "In 0 files" or wrong entries
3. Click small red "Delete" button
4. Confirm deletion
5. Entry removed from database and knowledge base
6. Page refreshes automatically

**Auto-Cleanup:**
- System automatically removes people with 0 files on every page load
- Keeps knowledge base clean without manual intervention

### Use Case 6: Direct Navigation from Knowledge Base

**Scenario:**
You want to review the last conversation with Lekshmanan.

**Quick Access:**
1. Go to Knowledge Base → People tab
2. Find "Lekshmanan" card
3. Click on "📄 Last seen in: 1-to-1/1-to-1 with Lekshmanan.md"
4. Instantly opens that note in Notes Viewer
5. Names already highlighted (from previous detection)

**Benefits:**
- One-click navigation
- No manual file searching
- Context preserved
- Fast workflow

### Use Case 7: Name Transcript Errors

**Without learning:**
- SuperWhisper transcribes "Lekshmanan" as "Lexman"
- You manually fix it every time

**With Learning System:**
- Fix it once in the note: add `(Lekshmanan, not Lexman)`
- System learns the correction
- Future transcripts automatically fix "Lexman" → "Lekshmanan"

**Enhanced with AI Features:**
- Use AI correction for intelligent replacement
- Or merge names via drag-and-drop
- Creates auto-correction rules automatically

### Use Case 8: Project Association

**Without learning:**
- Meetings about "Project Phoenix" scattered across files

**With SuperWhisper Organiser:**
- System learns "Project Phoenix" from your notes
- AI recognizes project mentions in new meetings
- Suggests relevant file organization
- Context provided: "This relates to Project Phoenix"

---

## 🔧 CLI Commands

All previous commands work, plus new ones:

```bash
# Start web interface
python sworganiser.py web [--host HOST] [--port PORT]

# Scan notes to build knowledge base
python sworganiser.py scan-notes

# Watch for new recordings (daemon mode)
python sworganiser.py watch

# Process all existing recordings
python sworganiser.py process-all

# Process specific recording
python sworganiser.py process <folder_name>

# Show statistics
python sworganiser.py stats

# Create index file
python sworganiser.py index

# Archive old notes
python sworganiser.py archive --days 365

# Show version
python sworganiser.py version
```

---

## 📊 Database Schema

**See [DATA_MODEL.md](DATA_MODEL.md) for complete documentation.**

The enhanced database tracks:

- **`processed_recordings`**: Legacy compatibility, tracks processed recordings
- **`processing_history`**: Every processing event with full audit trail
- **`note_files`**: All note files with metadata and modification dates
- **`note_modifications`**: Track manual edits for learning
- **`knowledge_base`**: Learned entities (people, projects, meeting patterns)
- **`name_corrections`**: Transcript error corrections for auto-fixing
- **`processing_status`**: Current real-time processing state (singleton)
- **`note_detected_names`**: AI-detected names per file for highlighting and merging

### Key Features
- **8 Tables**: Comprehensive tracking of all aspects
- **File Count per Person**: JOIN query shows "In X files"
- **Orphaned Entry Cleanup**: Auto-removes people with 0 files
- **UNIQUE Constraints**: Prevents duplicate entries
- **Automatic Maintenance**: Self-cleaning on page loads

---

## 🔌 API Endpoints

The web app exposes REST APIs you can use:

### Status & Stats
- `GET /api/status` - Current processing status
- `GET /api/stats` - Processing statistics with charts data
- `GET /api/history` - Processing history (with pagination & filtering)

### Notes Management
- `GET /api/notes` - List all note files (legacy)
- `GET /api/note-tree` - Hierarchical file tree with latest dates
- `GET /api/notes/<path>` - Get note content with detected names
- `POST /api/notes/<path>` - Update note (triggers learning)
- `POST /api/notes/rename` - Rename note file
- `POST /api/notes/delete` - Delete note file
- `POST /api/notes/merge` - Merge multiple notes
- `POST /api/notes/extract` - Extract section to new file
- `POST /api/notes/move` - Move note to different folder

### AI-Powered Name Features
- `POST /api/notes/detect-names` - Detect person names in note with AI
- `POST /api/notes/correct-name` - AI-powered intelligent name replacement

### Knowledge Base
- `GET /api/knowledge` - Knowledge base summary with file counts
- `POST /api/knowledge/merge-names` - Merge two person names across all files
- `POST /api/knowledge/delete-name` - Delete non-person entry
- `POST /api/scan-notes` - Trigger knowledge base rebuild

### Example Usage

**Get all detected people with file counts:**
```bash
curl http://127.0.0.1:5000/api/knowledge
```

**Detect names in a note:**
```bash
curl -X POST http://127.0.0.1:5000/api/notes/detect-names \
  -H "Content-Type: application/json" \
  -d '{"file_path": "1-to-1/1-to-1 with Fred.md"}'
```

**Merge two names:**
```bash
curl -X POST http://127.0.0.1:5000/api/knowledge/merge-names \
  -H "Content-Type: application/json" \
  -d '{
    "name1": "Stefan",
    "name2": "Stephane",
    "keep_name": "Stephane"
  }'
```

**Get note tree with file sorting:**
```bash
curl http://127.0.0.1:5000/api/note-tree
# Returns hierarchical structure with latest_date per file
```

---

## ⚙️ Configuration

Your existing `config.yaml` works as-is. Optional new settings:

```yaml
# (Optional) Web server defaults
web:
  host: "127.0.0.1"
  port: 5000

# (Optional) Learning system tuning
learning:
  min_confidence: 0.5
  auto_scan_on_startup: true
  name_correction_threshold: 0.8
```

---

## 🔄 Getting Started

Simple setup:
- Install dependencies: `pip install -r requirements.txt`
- Configure: `cp config.example.yaml config.yaml` (edit as needed)
- Start: `python sworganiser.py web`
- Open: http://127.0.0.1:5000

---

## 🎨 Customization

### Custom Learning Patterns

Edit `learning.py` to add custom extraction patterns:

```python
def _extract_projects(self, content: str, file_path: Path) -> Set[str]:
    # Add your custom project detection logic
    pass
```

### Web UI Styling

Edit `static/css/style.css` to customize:
- Colors (CSS variables at top)
- Layout and spacing
- Component styles

### API Extensions

Add new endpoints in `webapp.py`:

```python
@app.route('/api/custom')
def api_custom():
    # Your custom endpoint
    pass
```

---

## 🐛 Troubleshooting

### Web Interface Won't Start

**Error:** `ModuleNotFoundError: No module named 'flask'`

**Solution:**
```bash
pip install flask flask-cors
```

### Knowledge Base Empty

**Symptom:** Knowledge page shows no entries

**Solution:**
```bash
python sworganiser.py scan-notes
```

### Notes Not Learning

**Check:**
1. Are you editing via web interface? (Learning triggers on save)
2. Run manual scan: `python sworganiser.py scan-notes`
3. Check logs: `tail -f organiser.log`

### Database Locked

**Error:** `database is locked`

**Solution:**
- Stop all running instances
- Close web browser
- Restart: `python sworganiser.py web`

---

## 📈 Performance

- **Startup**: ~2-5 seconds (includes knowledge scan)
- **Web UI**: < 100ms response times
- **Knowledge Scan**: ~1 second per 100 notes
- **Processing**: Speed depends on AI model

---

## 🔐 Security Notes

### Local Use Only (Default)

The web server binds to `127.0.0.1` by default - only accessible from your machine.

### Network Access

To allow network access:

```bash
python sworganiser.py web --host 0.0.0.0
```

⚠️ **Warning:** This exposes your notes to your local network. Only use on trusted networks.

### Authentication

SuperWhisper Organiser currently does not include authentication. For production use:
- Use a reverse proxy (nginx, apache)
- Add HTTP basic auth
- Use VPN or SSH tunnel

---

## 🚦 What's Next?

Future enhancements being considered:

- 📊 Analytics dashboard with charts
- 🔍 Full-text search across all notes
- 🤖 AI chat interface to query your notes
- 📱 Mobile-responsive design
- 🔔 Webhook notifications
- 🎨 Customizable note templates
- 📅 Calendar integration

---

## 💡 Tips & Best Practices

1. **Review and Edit Notes**: The more you edit, the smarter it gets
2. **Mark Corrections Clearly**: Use patterns like `(correct name, not wrong name)`
3. **Consistent Naming**: Use consistent people/project names across notes
4. **Regular Scans**: Run `scan-notes` after bulk editing
5. **Monitor Knowledge Base**: Check `/knowledge` to see what's learned

---

## 📝 License

See LICENSE file for details.

---

## 🙏 Feedback

Found a bug? Have a feature request? Open an issue or contribute!

The learning system improves with use - the more notes you process and edit, the better it becomes at organizing future meetings.

Enjoy your smarter, web-enabled SuperWhisper Organiser! 🎉
