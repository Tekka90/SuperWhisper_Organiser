#!/usr/bin/env python3
"""
Dry-run analysis for a single SuperWhisper recording folder.

Runs the full analysis pipeline (including the vision pre-pass when screenshots
are present) and prints everything that would be written to the database and
note files — without touching either.

Usage:
    python scripts/test_analysis.py /path/to/superwhisper/recording/folder
    python scripts/test_analysis.py ~/Documents/superwhisper/recordings/20240315-143022

Optional flags:
    --vision-only  Run only the vision pre-pass; print the prompt sent and the
                   raw JSON response. Skips the main LLM call entirely.
    --no-vision    Temporarily disable the vision pre-pass even if enabled in config
    --verbose      Show the full prompt sent to the main LLM
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path

# Resolve project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from organiser.utils import load_config, load_meta_json, get_recording_date, format_duration
from organiser.analyzer import MeetingAnalyzer
from organiser.organizer import NoteOrganizer

DIVIDER = "─" * 72


def hr(title: str = ""):
    if title:
        pad = DIVIDER[: max(0, (len(DIVIDER) - len(title) - 2) // 2)]
        print(f"\n{pad} {title} {pad}\n")
    else:
        print(f"\n{DIVIDER}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run the analysis pipeline on a SuperWhisper recording folder."
    )
    parser.add_argument("folder", help="Path to the recording folder")
    parser.add_argument(
        "--vision-only",
        action="store_true",
        help="Run only the vision pre-pass and exit (implies verbose)",
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Disable vision pre-pass for this run",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full prompt sent to the main LLM",
    )
    args = parser.parse_args()

    if args.vision_only and args.no_vision:
        print("ERROR: --vision-only and --no-vision are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    recording_folder = Path(args.folder).expanduser().resolve()
    if not recording_folder.is_dir():
        print(f"ERROR: '{recording_folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    meta_file = recording_folder / "meta.json"
    if not meta_file.exists():
        print(f"ERROR: No meta.json found in '{recording_folder}'.", file=sys.stderr)
        sys.exit(1)

    # ── Load config ────────────────────────────────────────────────────────
    config = load_config()

    if args.no_vision:
        config.setdefault("vision", {})["enabled"] = False
        print("[--no-vision] Vision pre-pass disabled for this run.\n")

    # ── Load meta.json early (needed by both modes) ───────────────────────
    meta = load_meta_json(recording_folder)

    # ── Build analyzer (no DB, no learning) ───────────────────────────────
    analyzer = MeetingAnalyzer(config)

    # ── Vision-only mode: run just the pre-pass and exit ──────────────────
    if args.vision_only:
        _run_vision_only(analyzer, recording_folder, meta)
        return

    # Patch: intercept vision pre-pass so we can show its output separately
    _orig_extract = analyzer._extract_context_from_screenshots

    vision_result_holder = {}

    def _patched_extract(screenshot_parts):
        result = _orig_extract(screenshot_parts)
        vision_result_holder["result"] = result
        vision_result_holder["count"] = len(screenshot_parts)
        return result

    analyzer._extract_context_from_screenshots = _patched_extract

    # Patch: intercept prompt construction so --verbose can print it
    _orig_prompt = analyzer._create_analysis_prompt
    prompt_holder = {}

    def _patched_prompt(**kwargs):
        p = _orig_prompt(**kwargs)
        prompt_holder["prompt"] = p
        return p

    analyzer._create_analysis_prompt = _patched_prompt

    # ── Build organizer (no DB, no learning) in dry-run mode ──────────────
    # We only need _generate_note_content; we never call organize_recording.
    organizer = NoteOrganizer(config, analyzer, database=None, learning_system=None)

    # ── Print recording folder details ────────────────────────────────────
    recording_date = get_recording_date(meta)
    duration = meta.get("duration", 0)

    hr("RECORDING")
    print(f"  Folder  : {recording_folder}")
    print(f"  Date    : {recording_date.isoformat() if recording_date else 'unknown'}")
    print(f"  Duration: {format_duration(duration)}")
    llm_result = meta.get("llmResult", "")
    raw_result = meta.get("result", "")
    if llm_result:
        print(f"  Summary : {llm_result[:120].replace(chr(10), ' ')}{'…' if len(llm_result) > 120 else ''}")

    # ── Run the analysis ───────────────────────────────────────────────────
    hr("RUNNING ANALYSIS")
    print("Calling analyzer.analyze_recording() …\n")

    analysis = analyzer.analyze_recording(recording_folder)

    if analysis is None:
        print("\nERROR: analysis returned None. Check logs above for details.")
        sys.exit(1)

    # ── Vision pre-pass result ────────────────────────────────────────────
    if vision_result_holder:
        hr("VISION PRE-PASS")
        print(f"  Screenshots sent : {vision_result_holder.get('count', 0)}")
        vr = vision_result_holder.get("result")
        if vr:
            print(f"  Meeting title    : {vr.get('meeting_title', '(none)')}")
            print(f"  Participants     : {', '.join(vr.get('participants', []))}")
            ctx = vr.get("extra_context", "")
            if ctx:
                print(f"  Extra context    : {ctx}")
        else:
            print("  Vision pre-pass returned no result (failed or no screenshots).")

    # ── Analysis result ───────────────────────────────────────────────────
    hr("ANALYSIS RESULT")
    print(f"  Meeting type     : {analysis.meeting_type}")
    print(f"  Confidence       : {analysis.confidence}")
    print(f"  Participants     : {', '.join(analysis.participants) if analysis.participants else '(none)'}")
    print(f"  Topics           : {', '.join(analysis.topics) if analysis.topics else '(none)'}")
    print(f"  Suggested file   : {analysis.suggested_filename}")
    if analysis.related_meetings:
        print(f"  Related meetings : {', '.join(analysis.related_meetings)}")
    print(f"\n  Summary:\n{textwrap.indent(analysis.summary, '    ')}")

    # ── Prompt (verbose) ─────────────────────────────────────────────────
    if args.verbose and prompt_holder.get("prompt"):
        hr("PROMPT SENT TO MAIN LLM")
        print(prompt_holder["prompt"])

    # ── Simulate note content ─────────────────────────────────────────────
    hr("GENERATED NOTE CONTENT (dry-run)")

    note_content = organizer._generate_note_content(recording_folder, meta, analysis)

    # Determine where the note *would* go
    folder_name = config["organization"]["folders"].get(
        analysis.meeting_type,
        config["organization"]["folders"]["general"],
    )
    notes_path = Path(config["paths"]["notes_output"]).expanduser()
    target_file = notes_path / folder_name / analysis.suggested_filename
    if not analysis.suggested_filename.endswith(".md"):
        target_file = target_file.with_suffix(".md")

    exists = target_file.exists()
    print(f"  Would write to : {target_file}")
    print(f"  File exists    : {'YES — content would be prepended' if exists else 'no — new file'}\n")
    print(note_content)

    hr("DONE")
    print("No files were written. DB was not touched.\n")


def _run_vision_only(analyzer: "MeetingAnalyzer", recording_folder: Path, meta: dict):
    """Run only the vision pre-pass and print the prompt + raw LLM response."""
    from organiser.utils import get_recording_date, format_duration

    recording_date = get_recording_date(meta)
    duration = meta.get("duration", 0)

    hr("RECORDING")
    print(f"  Folder  : {recording_folder}")
    print(f"  Date    : {recording_date.isoformat() if recording_date else 'unknown'}")
    print(f"  Duration: {format_duration(duration)}")

    if not analyzer.vision_enabled:
        print("\nERROR: vision is disabled in config. Use a config with vision.enabled=true.",
              file=sys.stderr)
        sys.exit(1)

    screenshot_parts = analyzer._load_screenshots(recording_folder)
    if not screenshot_parts:
        print("\nNo screenshots found in this recording folder.")
        sys.exit(0)

    hr(f"VISION PROMPT  ({len(screenshot_parts)} screenshot(s))")

    # Print the text portion of the prompt (first content item)
    vision_prompt = [
        {
            "type": "text",
            "text": (
                f"You are analysing screenshots taken during a video call on the computer "
                f"of {analyzer.user_name or 'the user'}.\n\n"
                f"The screenshots were captured from different application windows open "
                f"during the meeting:\n"
                f"- **Meeting window** (e.g. Microsoft Teams): the window title bar shows "
                f"the exact call name; the participant panel lists all attendees.\n"
                f"- **Calendar** (e.g. Outlook / Apple Calendar): may show the planned "
                f"event name, duration, and the full invited attendee list.\n"
                f"- **Other windows** (chat, email): may give useful context.\n\n"
                f"Please extract:\n"
                f"1. The **meeting title**\n"
                f"2. The **full list of participant names** (always include "
                f"{analyzer.user_name or 'the host'} — they own the machine and may appear "
                f"as a short name, display name, or 'me/you' in the UI; use "
                f"\"{analyzer.user_name or 'the host'}\" as the canonical form)\n"
                f"3. Any **extra context** useful for classifying the meeting\n\n"
                f"Important: include each person exactly once. If someone appears "
                f"under multiple forms (e.g. first name only, full name, display name), "
                f"keep the most complete version. "
                f"\"{analyzer.user_name or 'the host'}\" may appear in several forms in "
                f"the UI — always use \"{analyzer.user_name or 'the host'}\" as the "
                f"canonical name.\n\n"
                f"Respond ONLY with JSON:\n"
                f'{{\n'
                f'  "meeting_title": "<exact title or empty string>",\n'
                f'  "participants": ["Full Name 1", "Full Name 2"],\n'
                f'  "extra_context": "<brief context string or empty string>"\n'
                f'}}'
            ),
        }
    ]
    print(vision_prompt[0]["text"])
    print(f"\n  + {len(screenshot_parts)} image(s) attached (base64, not shown)")

    hr("CALLING VISION MODEL")
    print(f"  Model       : {analyzer.vision_model}")
    print(f"  Temperature : {analyzer.vision_temperature}")
    print(f"  Max tokens  : {analyzer.vision_max_tokens}\n")

    # Call the model directly, capturing the raw response
    try:
        full_prompt = vision_prompt + screenshot_parts
        response = analyzer.client.chat.completions.create(
            model=analyzer.vision_model,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=analyzer.vision_temperature,
            max_tokens=analyzer.vision_max_tokens,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"ERROR calling vision model: {e}", file=sys.stderr)
        sys.exit(1)

    hr("RAW RESPONSE")
    print(raw)

    # Try to parse and pretty-print
    import re
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            hr("PARSED RESULT")
            print(f"  Meeting title : {parsed.get('meeting_title', '(none)')}")
            participants = parsed.get('participants', [])
            if analyzer.user_name and analyzer.user_name not in participants:
                participants.insert(0, analyzer.user_name)
            print(f"  Participants  : {', '.join(participants)}")
            ctx = parsed.get('extra_context', '')
            if ctx:
                print(f"  Extra context : {ctx}")
        except json.JSONDecodeError:
            print("  (could not parse JSON from response)")
    else:
        print("  (no JSON object found in response)")

    hr("DONE")
    print("Vision-only run complete. No files written.\n")


if __name__ == "__main__":
    main()
