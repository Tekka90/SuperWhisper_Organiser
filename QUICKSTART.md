# Quick Start Guide

Get SuperWhisper Organiser running in 5 minutes.

## Prerequisites

✅ SuperWhisper app installed and configured  
✅ Python 3.8+ installed  
✅ OpenAI API key (or local OpenAI-compatible endpoint)

## Installation

### 1. Run Install Script

```bash
bash scripts/install.sh
```

This will:
- Check prerequisites (Python 3.8+, pip)
- Create a Python virtual environment
- Install all dependencies
- Verify config.yaml exists

### 2. Configure

Edit `config.yaml`:

```bash
nano config.yaml
```

**Required changes:**
- Set your OpenAI API key (or add to environment)
- Verify recordings path: `~/Documents/superwhisper/recordings`
- Verify notes output path

**Optional changes:**
- Adjust AI model (default: gpt-4-turbo-preview)
- Change poll interval (default: 10 seconds)
- Customize note templates
- Adjust folder organization

### 3. Set API Key

Choose one method:

**Option A: Environment Variable (Recommended)**
```bash
export OPENAI_API_KEY='sk-your-key-here'
```

**Option B: Config File**
Edit `config.yaml` and set:
```yaml
openai:
  api_key: "sk-your-key-here"
```

**Option C: .env File**
Create a `.env` file:
```
OPENAI_API_KEY=sk-your-key-here
```

## Usage

### First Run - Process Existing Meetings

```bash
source venv/bin/activate
python sworganiser.py process-all
```

This will analyze all your existing meeting recordings and organize them.

### Run as Daemon (Recommended)

Start monitoring for new meetings:

```bash
python sworganiser.py --daemon
```

Or using the watch command:

```bash
python sworganiser.py watch
```

Keep this running in the background or set up as a system service.

### Process Specific Recording

```bash
python sworganiser.py process 1738663480
```

### View Statistics

```bash
python sworganiser.py stats
```

### Create Index

Generate an index file of all notes:

```bash
python sworganiser.py index
```

### Archive Old Notes

Move notes older than 1 year to archive:

```bash
python sworganiser.py archive --days 365
```

## Verify It's Working

1. **Check logs:**
   ```bash
   tail -f organiser.log
   ```

2. **Manually trigger a test:**
   - Record a short test meeting in SuperWhisper
   - Wait for processing to complete
   - Check the daemon output
   - Verify note file was created in `notes/` folder

3. **Review output:**
   ```bash
   ls -la notes/
   ls -la notes/*/
   ```

## Folder Structure

After running, you'll see:

```
SuperWhisper Organiser/
├── notes/
│   ├── 1-to-1/              # Individual meetings
│   ├── team-meetings/       # Team meetings
│   ├── project-meetings/    # Project discussions
│   ├── interviews/          # Interviews
│   ├── workshops/           # Workshops
│   ├── general/             # Other meetings
│   └── INDEX.md            # Generated index
├── processed_recordings.db  # Tracking database
├── organiser.log           # Application logs
└── config.yaml             # Your configuration
```

## Troubleshooting

### No recordings being processed

**Check:** Is the daemon running?
```bash
ps aux | grep "sworganiser.py"
```

**Check:** Are recordings in the right folder?
```bash
ls ~/Documents/superwhisper/recordings | tail -5
```

**Check:** Do recordings have Meeting mode?
```bash
cat ~/Documents/superwhisper/recordings/[TIMESTAMP]/meta.json | grep modeName
```

### OpenAI errors

**Check:** API key is set
```bash
echo $OPENAI_API_KEY
```

**Check:** API quotas and rate limits at platform.openai.com

**Check:** For local models, verify endpoint is accessible:
```bash
curl http://localhost:1234/v1/models
```

### Notes not organized well

- Increase temperature in config for more creative categorization
- Adjust the system prompt in `config.yaml`
- Check that meeting has good transcript quality
- Review logs for AI analysis details

## Running as Background Service

### Using nohup (Simple)

```bash
nohup python sworganiser.py --daemon > /dev/null 2>&1 &
```

### Using screen (Better)

```bash
screen -S organiser
python sworganiser.py --daemon
# Press Ctrl+A then D to detach
# Reattach: screen -r organiser
```

### As macOS Launch Agent (Best)

Create `~/Library/LaunchAgents/com.superwhisper.organiser.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.superwhisper.organiser</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/stephane/Documents/superwhisper/SuperWhisper Organiser/venv/bin/python</string>
        <string>/Users/stephane/Documents/superwhisper/SuperWhisper Organiser/sworganiser.py</string>
        <string>--daemon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/stephane/Documents/superwhisper/SuperWhisper Organiser</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/superwhisper-organiser.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/superwhisper-organiser-error.log</string>
</dict>
</plist>
```

Then:
```bash
launchctl load ~/Library/LaunchAgents/com.superwhisper.organiser.plist
launchctl start com.superwhisper.organiser
```

## Tips

- Run `process-all` regularly to catch any missed recordings
- Review the generated notes and adjust prompts if needed
- Use `stats` command to see organization breakdown
- Create index regularly for easy navigation
- Archive old notes to keep the main folder clean

## Getting Help

- Check `organiser.log` for detailed error messages
- Review `copilot-instructions.md` for development context
- See `README.md` for complete documentation
- Inspect `meta.json` files to understand SuperWhisper's output

## What's Next?

Once everything is working:

1. **Customize prompts** - Adjust the AI analysis to your meeting style
2. **Organize existing notes** - Run through old recordings
3. **Set up automation** - Configure as launch agent
4. **Integrate with workflow** - Connect with note-taking apps
5. **Extend functionality** - Add custom features (see copilot-instructions.md)

---

**Happy organizing! 🎤📝**
