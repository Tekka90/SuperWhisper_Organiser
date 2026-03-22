# SuperWhisper Organiser

An intelligent meeting notes organizer for SuperWhisper recordings with AI-powered name detection, correction, and comprehensive knowledge management through a modern web interface.

## ✨ Features

### Core Features
- **Automatic Detection**: Monitors SuperWhisper recordings folder for new meetings
- **Smart Organization**: Uses AI to identify meeting types, participants, and topics
- **Intelligent Filing**: Appends to existing note files or creates new ones based on context
- **1-on-1 Tracking**: Automatically groups meetings with the same person
- **Topic Grouping**: Identifies recurring meeting topics (e.g., sprint planning, design reviews)
- **Flexible AI**: Works with OpenAI API (cloud or local models)

### Web Interface
- **Dashboard**: Real-time processing status and statistics
- **Notes Viewer**: Browse, view, edit notes with Markdown rendering
- **Knowledge Base**: Manage detected people, projects, and patterns
- **Processing History**: Complete audit log of all recordings

### AI-Powered Name Management
- **Name Detection**: AI automatically finds and highlights person names in notes
- **Smart Correction**: Click-to-correct names with AI context understanding
- **Drag-and-Drop Merging**: Visual interface to merge duplicate names
- **Intelligent Replacement**: Handles grammar, possessives, and context
- **Auto-Highlighting**: Names persist in database, highlight on every visit

### Learning System
- **Continuous Learning**: Learns from your edits and corrections
- **Name Corrections**: Auto-fixes transcript errors in future recordings
- **Context Building**: Provides learned context to AI for better organization
- **Knowledge Graph**: Tracks people, projects, meeting patterns

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- OpenAI API key (or local OpenAI-compatible endpoint)
- SuperWhisper app installed and configured

### Automated Installation (Recommended)

For macOS users, use the automated installer to set up everything including auto-start on boot:

```bash
# 1. Create config.yaml from template
cp config.example.yaml config.yaml
# Edit config.yaml with your settings

# 2. Run the installer
bash scripts/install.sh

# 3. Access the web interface
open http://localhost:5000
```

The installer will:
- ✅ Create and configure a virtual environment
- ✅ Install all dependencies
- ✅ Create a macOS LaunchAgent service
- ✅ Auto-start both watcher and web interface on login
- ✅ Set up logging and error tracking

## 🧪 Running Tests

All unit tests use temporary databases and directories — the production
`processed_recordings.db` and your notes folder are **never touched**.

### Quick run

```bash
# Activate virtualenv first
source venv/bin/activate

# Run all 185 tests
scripts/run_tests.sh

# Or call pytest directly
python -m pytest tests/

# Run with coverage report (requires pytest-cov)
scripts/run_tests.sh --cov
```

### Targeting specific modules

```bash
python -m pytest tests/test_database.py    # Database layer (68 tests)
python -m pytest tests/test_utils.py       # Utility helpers (31 tests)
python -m pytest tests/test_learning.py    # LearningSystem (32 tests)
python -m pytest tests/test_analyzer.py    # MeetingAnalyzer / OpenAI (18 tests)
python -m pytest tests/test_webapp.py      # Flask REST API (51 tests)
```

### Test layout

```
tests/
├── conftest.py          # Shared fixtures (tmp db, tmp notes dir, Flask client)
├── test_database.py     # Database.* — all 8 tables, lifecycle, merge, cleanup
├── test_utils.py        # format_duration, load_meta_json, legacy DB helpers, …
├── test_learning.py     # Knowledge extraction, name corrections, context building
├── test_analyzer.py     # MeetingAnalysis, prompt building, OpenAI mock, fallback
└── test_webapp.py       # _extract_latest_date_from_file, _merge_note_contents,
                         # every REST endpoint (status, stats, notes CRUD, search,
                         # knowledge, merge-names, detect-names, correct-name, …)
```

### Design principles

- **No real I/O**: OpenAI is `MagicMock`-ed, database uses `tmp_path`, notes use a temp dir.
- **Production data never accessed**: `pytest.ini` sets `testpaths = tests`; the production config, database files, and notes folder are never touched.
- **Fast**: The full suite runs in about 1–2 seconds.

**What runs automatically:**
- **Watcher**: Monitors for new SuperWhisper recordings and processes them
- **Web Interface**: Available at http://localhost:5000 (or http://YOUR_IP:5000)

**Service management:**
```bash
# Check status
launchctl list | grep com.superwhisper.organiser

# View logs
tail -f logs/organiser.log
tail -f logs/organiser.error.log

# Restart service
launchctl kickstart -k gui/$(id -u)/com.superwhisper.organiser

# Uninstall
bash scripts/uninstall.sh
```

### Manual Installation

If you prefer manual setup or are on Linux/Windows:

1. Navigate to this directory:
   ```bash
   cd "/Users/stephane/Documents/superwhisper/SuperWhisper Organiser"
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure the application:
   ```bash
   cp config.example.yaml config.yaml
   # Edit config.yaml with your settings
   ```

4. Set your OpenAI API key:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   # Or add it to config.yaml
   ```

5. Start the web interface:
   ```bash
   python sworganiser.py web
   ```

6. Open in your browser:
   - Local: http://localhost:5000
   - Network: http://YOUR_IP:5000

## 📖 Usage

### Web Interface (Recommended)

```bash
# Start web server (accessible from network)
python sworganiser.py web

# Access from:
# - Local machine: http://localhost:5000
# - Other machines: http://YOUR_IP:5000 (e.g., http://10.0.0.20:5000)

# To restrict to localhost only:
python sworganiser.py web --host 127.0.0.1
```

**Web Features:**
- **Dashboard**: View processing status and statistics
- **Notes Viewer**: Browse/edit notes, detect and correct names with AI
- **Knowledge Base**: Manage people, merge duplicates via drag-and-drop
- **History**: Review all processing events

See [WEB_INTERFACE_GUIDE.md](docs/WEB_INTERFACE_GUIDE.md) for detailed web interface documentation.

### CLI Commands

```bash
# Watch for new recordings (daemon mode)
python sworganiser.py watch

# Process all unprocessed recordings
python sworganiser.py process-all

# Process specific recording
python sworganiser.py process <folder_name>

# Rebuild knowledge base from notes
python sworganiser.py scan-notes

# Show statistics
python sworganiser.py stats

# Show version
python sworganiser.py version
```

## How It Works

1. **Monitoring**: The app watches the SuperWhisper recordings folder for new meeting recordings
2. **Detection**: When a new meeting is complete (meta.json file is stable), it's queued for processing
3. **Analysis**: OpenAI analyzes the meeting transcript and summary to identify:
   - Meeting type (1-on-1, team meeting, interview, etc.)
   - Participants
   - Topics discussed
   - Related previous meetings
4. **Organization**: Based on the analysis, notes are:
   - Appended to existing topic files (e.g., "1-to-1 with John.md")
   - Or saved to new files for new topics
5. **Formatting**: Notes include:
   - Date and time
   - Participants
   - Summary
   - Key points and action items
   - Link to original recording

## 📂 File Structure

```
SuperWhisper Organiser/
├── README.md                    # This file - Getting started guide
├── docs/
│   ├── DATA_MODEL.md                # Complete database schema documentation
│   ├── WEB_INTERFACE_GUIDE.md       # Web UI features and usage
│   └── IMPLEMENTATION_SUMMARY.md   # Technical implementation notes
├── scripts/
│   ├── start.sh / stop.sh / status.sh  # Service management
│   ├── install.sh / uninstall.sh       # Setup and teardown
│   └── run_tests.sh                    # Test runner
├── copilot-instructions.md      # Development context for AI assistants
├── requirements.txt             # Python dependencies
├── config.yaml                  # User configuration file
├── config.example.yaml          # Configuration template
│
├── sworganiser.py                      # Application entry point (~300 lines)
├── webapp.py                    # Flask web application (~1280 lines)
├── database.py                  # Database layer - 8 tables (~795 lines)
├── watcher.py                   # File system monitoring (~250 lines)
├── analyzer.py                  # OpenAI AI integration (~500 lines)  
├── organizer.py                 # Note file management (~600 lines)
├── learning.py                  # Learning system (~400 lines)
├── utils.py                     # Utilities (~200 lines)
│
├── templates/                   # HTML templates for web UI
│   ├── index.html              # Dashboard
│   ├── notes.html              # Notes viewer/editor
│   ├── knowledge.html          # Knowledge base
│   └── history.html            # Processing history
│
├── static/                      # Frontend assets
│   ├── js/
│   │   ├── notes.js            # Notes UI logic (~900 lines)
│   │   └── knowledge.js        # Knowledge base UI (~480 lines)
│   └── css/
│       └── style.css           # All styles (~890 lines)
│
├── processed_recordings.db      # SQLite database (8 tables)
├── organiser.log               # Application logs
└── notes/                      # Output directory for organized notes
    ├── 1-to-1/                 # Individual meetings
    ├── team-meetings/          # Team meetings
    ├── project-meetings/       # Project discussions
    └── ...                     # Other categories
```

## 📝 Notes Organization

The app organizes notes into a smart folder structure:

- **1-to-1/**: Individual meetings (e.g., "1-to-1 with Lekshmanan.md")
- **team-meetings/**: Recurring team meetings (sorted by latest date)
- **project-meetings/**: Project-specific discussions
- **interviews/**: Interview notes
- **general/**: Miscellaneous meetings

Each file accumulates notes from related meetings, with the most recent at the top.

### Example Note Structure

```markdown
## March 18, 2026 at 13:55 - Discussion about project timeline

**Participants:** Fred, Stephane (highlighted with AI detection)
**Duration:** 25m 55s

**Topics:** Project deadlines, Resource allocation, Risk management

### Summary
[AI-generated summary of the meeting]

### Key Points
- Project deadline moved to April 15th
- Need 2 additional developers
- Risk: Database migration complexity

### Action Items
- [ ] Fred: Draft project plan by Friday
- [ ] Stephane: Review resource requirements

---
```

## 🔧 Configuration

Edit `config.yaml` to customize:

```yaml
paths:
  recordings: "~/Documents/superwhisper/recordings"
  notes_output: "~/Documents/superwhisper/SuperWhisper Organiser/notes"
  database: "~/Documents/superwhisper/SuperWhisper Organiser/processed_recordings.db"

openai:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4-turbo-preview"
  temperature: 0.3
  max_tokens: 2000

monitoring:
  poll_interval: 10
  target_mode: "Meeting"
  stability_wait: 5
  process_on_startup: true
```

See `config.example.yaml` for all available options.

## 🗄️ Database

**8 SQLite tables** track everything:
- processed_recordings - Processed recording tracking
- processing_history - Complete audit log
- note_files - All note file metadata
- note_modifications - Manual edit tracking
- knowledge_base - People, projects, patterns
- name_corrections - Transcript error fixes
- processing_status - Real-time status (singleton)
- note_detected_names - AI-detected names per file

See [DATA_MODEL.md](docs/DATA_MODEL.md) for complete schema documentation.

## 📚 Documentation

- **[README.md](README.md)** (this file) - Getting started and overview
- **[WEB_INTERFACE_GUIDE.md](docs/WEB_INTERFACE_GUIDE.md)** - Complete web UI guide with examples
- **[DATA_MODEL.md](docs/DATA_MODEL.md)** - Database schema and relationships
- **[copilot-instructions.md](copilot-instructions.md)** - Development context for AI coding assistants

## 🐛 Troubleshooting

### Common Issues

**Web server won't start:**
- Port 5000 in use: Try different port with `--port 8080`
- Missing dependencies: `pip install -r requirements.txt`
- Python version: Requires 3.8+

**Names not detecting:**
- Click "Detect names" button in note viewer
- Ensure note has person names (not just topics)
- Check browser console for errors

**No recordings being processed:**
- Check `recordings_path` in config.yaml
- Ensure recordings have `modeName: "Meeting"` in meta.json
- Verify `watch` command is running

**OpenAI API errors:**
- Verify API key: `echo $OPENAI_API_KEY`
- Check quota and rate limits
- For local models, verify endpoint URL

**Database locked:**
- Another process accessing database
- Check for zombie processes: `ps aux | grep python`
- Restart application

### Getting Help

1. Check logs: `tail -f organiser.log`
2. Review browser console (F12) for frontend errors
3. Test API endpoints with curl
4. Check database: `sqlite3 processed_recordings.db "SELECT COUNT(*) FROM note_detected_names"`

## 🚀 Development

See [copilot-instructions.md](copilot-instructions.md) for:
- Complete architecture overview
- API endpoint patterns
- Frontend/backend conventions
- Adding new features
- Testing guidelines
- Common development patterns

## 📊 Version

**Current Version:** 1.0

Includes all features:
- Recording processing and organization
- Web interface with dashboard, notes viewer, history
- Learning system and knowledge base
- AI-powered name detection, correction, and merging

## 📄 License

MIT License - Feel free to modify and extend for your needs.

---

**Quick Links:**
- Start web interface: `python sworganiser.py web`
- View dashboard: http://localhost:5000
- Network access: http://YOUR_IP:5000
- Detect names: Click button in notes viewer
- Merge names: Drag in Knowledge Base
- Documentation: [WEB_INTERFACE_GUIDE.md](docs/WEB_INTERFACE_GUIDE.md)
