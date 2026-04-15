#!/usr/bin/env python3
"""
Utility functions for SuperWhisper Organiser
"""

import os
import json
import logging
from logging.handlers import RotatingFileHandler
import sqlite3
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import re


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """Configure logging based on config"""
    log_config = config.get('logging', {})
    level = getattr(logging, log_config.get('level', 'INFO'))
    log_file = expand_path(log_config.get('file', 'logs/organiser.log'))
    
    # Create logs directory if needed
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    log_format = (
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        if log_config.get('timestamps', True)
        else '%(name)s - %(levelname)s - %(message)s'
    )
    formatter = logging.Formatter(log_format)

    # File handler: rotating log with configurable size and backup count
    max_bytes = log_config.get('max_size_mb', 10) * 1024 * 1024
    backup_count = log_config.get('backup_count', 3)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setFormatter(formatter)

    # Stream handler: WARNING and above only, so that INFO/DEBUG don't
    # pollute stderr (which start.sh redirects to the .error.log file)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[file_handler, stream_handler])
    
    return logging.getLogger('superwhisper_organiser')


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if config_path is None:
        config_path = Path(__file__).parent.parent / 'config.yaml'
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Expand environment variables in config
    config = expand_env_vars(config)
    
    return config


def expand_env_vars(obj: Any) -> Any:
    """Recursively expand environment variables in config"""
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # Replace ${VAR} with environment variable
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, obj)
        for var in matches:
            value = os.environ.get(var, '')
            obj = obj.replace(f'${{{var}}}', value)
        return obj
    return obj


def expand_path(path: str) -> Path:
    """Expand ~ and environment variables in path"""
    return Path(os.path.expanduser(os.path.expandvars(path)))


def load_meta_json(recording_folder: Path) -> Optional[Dict[str, Any]]:
    """Load meta.json from a recording folder"""
    meta_file = recording_folder / 'meta.json'
    
    if not meta_file.exists():
        return None
    
    try:
        with open(meta_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse meta.json in {recording_folder}: {e}")
        return None


def format_duration(milliseconds: int) -> str:
    """Format duration in milliseconds to human-readable string"""
    seconds = milliseconds / 1000
    
    if seconds < 60:
        return f"{int(seconds)} seconds"
    
    minutes = int(seconds / 60)
    remaining_seconds = int(seconds % 60)
    
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    return f"{hours}h {remaining_minutes}m"


def extract_participants_from_segments(segments: list) -> list:
    """Extract unique speaker names from segments"""
    speakers = set()
    
    for segment in segments:
        if 'speaker' in segment:
            speaker_id = segment['speaker']
            speakers.add(f"Speaker {speaker_id}")
    
    return sorted(list(speakers))


def get_recording_date(meta: Dict[str, Any]) -> datetime:
    """Extract recording date from meta.json"""
    if 'datetime' in meta:
        # Parse datetime string like "2025-02-04T10:03:57"
        try:
            return datetime.fromisoformat(meta['datetime'])
        except ValueError:
            pass
    
    # Fallback: use folder name (timestamp)
    return None


def init_database(db_path: Path) -> None:
    """Initialize the SQLite database for tracking processed recordings"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_recordings (
            folder_name TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL,
            note_file TEXT,
            meeting_type TEXT,
            participants TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def is_recording_processed(db_path: Path, folder_name: str) -> bool:
    """Check if a recording has already been processed"""
    if not db_path.exists():
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT COUNT(*) FROM processed_recordings WHERE folder_name = ?',
        (folder_name,)
    )
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count > 0


def mark_recording_processed(
    db_path: Path,
    folder_name: str,
    note_file: str,
    meeting_type: str,
    participants: list
) -> None:
    """Mark a recording as processed in the database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(
        '''
        INSERT OR REPLACE INTO processed_recordings
        (folder_name, processed_at, note_file, meeting_type, participants)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (
            folder_name,
            datetime.now().isoformat(),
            note_file,
            meeting_type,
            ','.join(participants) if participants else ''
        )
    )
    
    conn.commit()
    conn.close()


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename"""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    # Strip leading/trailing spaces
    name = name.strip()
    # Limit length
    if len(name) > 200:
        name = name[:200]
    
    return name


def get_file_modification_time(file_path: Path) -> datetime:
    """Get the last modification time of a file"""
    return datetime.fromtimestamp(file_path.stat().st_mtime)


def is_file_stable(file_path: Path, wait_seconds: int = 5) -> bool:
    """Check if a file hasn't been modified for the specified time"""
    if not file_path.exists():
        return False
    
    mtime = get_file_modification_time(file_path)
    age = (datetime.now() - mtime).total_seconds()
    
    return age >= wait_seconds


def find_similar_notes(
    notes_dir: Path,
    meeting_type: str,
    participants: list,
    context_days: int = 90
) -> list:
    """Find similar note files based on type and participants"""
    similar_notes = []
    
    if not notes_dir.exists():
        return similar_notes
    
    # Look for markdown files
    for md_file in notes_dir.rglob('*.md'):
        # Check file modification time
        mtime = get_file_modification_time(md_file)
        if (datetime.now() - mtime).days > context_days:
            continue
        
        # Check if filename matches participants
        filename_lower = md_file.stem.lower()
        
        for participant in participants:
            if participant.lower() in filename_lower:
                similar_notes.append(md_file)
                break
    
    return similar_notes
