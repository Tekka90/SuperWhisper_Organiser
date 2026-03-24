#!/usr/bin/env python3
"""
Web application for SuperWhisper Organiser
Provides a web interface for monitoring, viewing history, and managing notes.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

from .utils import load_config, expand_path, setup_logging
from .database import Database
from .learning import LearningSystem
from .analyzer import MeetingAnalyzer

logger = logging.getLogger('superwhisper_organiser')


def _extract_latest_date_from_file(file_path: Path) -> Optional[datetime]:
    """
    Extract the latest date mentioned in a markdown file.
    Looks for dates in various formats commonly used in meeting notes.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Month name to number mapping
        month_map = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        # Common date patterns in meeting notes
        date_patterns = [
            # ISO format: 2024-01-15
            (r'\b(\d{4})-(\d{2})-(\d{2})\b', 'iso'),
            # Format: February 11, 2025 or February 11 2025
            (r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b', 'long_month'),
            # Format: 15 Jan 2024
            (r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b', 'short_month'),
        ]
        
        latest_date = None
        
        for pattern, format_type in date_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                try:
                    groups = match.groups()
                    parsed_date = None
                    
                    if format_type == 'iso':
                        # ISO format: year-month-day
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        parsed_date = datetime(year, month, day)
                        
                    elif format_type == 'long_month':
                        # Format: February 11, 2025
                        month_name = groups[0].lower()
                        day = int(groups[1])
                        year = int(groups[2])
                        month = month_map.get(month_name)
                        if month:
                            parsed_date = datetime(year, month, day)
                            
                    elif format_type == 'short_month':
                        # Format: 15 Jan 2024
                        day = int(groups[0])
                        month_name = groups[1].lower()
                        year = int(groups[2])
                        month = month_map.get(month_name)
                        if month:
                            parsed_date = datetime(year, month, day)
                    
                    if parsed_date:
                        if latest_date is None or parsed_date > latest_date:
                            latest_date = parsed_date
                            
                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse date from match {match.group(0)}: {e}")
                    continue
        
        if latest_date:
            logger.debug(f"Extracted date {latest_date} from {file_path.name}")
        else:
            logger.debug(f"No date found in {file_path.name}")
            
        return latest_date
        
    except Exception as e:
        logger.debug(f"Error extracting date from {file_path}: {e}")
        return None


def _merge_note_contents(content1: str, content2: str) -> str:
    """
    Intelligently merge two note files by extracting meeting entries
    and sorting them chronologically (newest first).
    """
    def extract_meetings(content):
        """Extract individual meeting entries from content"""
        meetings = []
        
        # Split by ## headers (meeting entries)
        parts = re.split(r'\n## ', content)
        
        # First part might be file header or first meeting
        if parts:
            first = parts[0].strip()
            if first:
                meetings.append(first)
            
            # Process remaining meetings
            for part in parts[1:]:
                meetings.append('## ' + part)
        
        return meetings
    
    def extract_date_from_meeting(meeting_text):
        """Try to extract a date from meeting text for sorting"""
        # Common patterns in meeting headers
        date_patterns = [
            r'##\s+(\d{4}-\d{2}-\d{2})',  # 2024-01-15
            r'##\s+(\w+\s+\d{1,2},\s+\d{4})',  # January 15, 2024
            r'(\d{1,2}/\d{1,2}/\d{4})',  # 01/15/2024
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, meeting_text)
            if match:
                date_str = match.group(1)
                try:
                    # Try to parse different formats
                    if '-' in date_str:
                        return datetime.strptime(date_str, '%Y-%m-%d')
                    elif '/' in date_str:
                        return datetime.strptime(date_str, '%m/%d/%Y')
                    else:
                        return datetime.strptime(date_str, '%B %d, %Y')
                except:
                    pass
        
        # If no date found, use a very old date so it goes to bottom
        return datetime(1900, 1, 1)
    
    # Extract meetings from both files
    meetings1 = extract_meetings(content1)
    meetings2 = extract_meetings(content2)
    
    # Combine all meetings
    all_meetings = meetings1 + meetings2
    
    # Sort by date (newest first)
    sorted_meetings = sorted(
        all_meetings,
        key=lambda m: extract_date_from_meeting(m),
        reverse=True
    )
    
    # Join with double newlines
    return '\n\n'.join(sorted_meetings)


def _check_path_security(*files: Path):
    """Validate that all files are within the notes directory.

    Returns a (Response, status_code) error tuple on failure, or None on success.
    """
    resolved_notes = notes_path.resolve()
    for file in files:
        try:
            file.resolve().relative_to(resolved_notes)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid file path - not within notes directory'
            }), 403
    return None


def _replace_name_in_files(files_to_update: list, old_name: str, new_name: str,
                            change_type: str) -> int:
    """Replace old_name with new_name (word-boundary aware) across given file paths.

    Returns the count of files actually modified.
    """
    pattern = re.compile(r'\b' + re.escape(old_name) + r'\b', re.IGNORECASE)
    files_updated = 0
    for file_path in files_to_update:
        try:
            note_file = notes_path / file_path
            if not note_file.exists():
                logger.warning(f"File not found: {file_path}")
                continue
            old_content = note_file.read_text(encoding='utf-8')
            matches = pattern.findall(old_content)
            logger.info(f"File {file_path}: Found {len(matches)} occurrences of '{old_name}'")
            new_content = pattern.sub(new_name, old_content)
            if new_content != old_content:
                note_file.write_text(new_content, encoding='utf-8')
                files_updated += 1
                db.track_note_modification(
                    file_path=file_path,
                    old_content=old_content[:200],
                    new_content=new_content[:200],
                    change_type=change_type
                )
                logger.info(f"Updated file: {file_path}")
        except Exception as e:
            logger.error(f"Error updating file {file_path}: {e}")
            continue
    return files_updated


# Project root — two levels up from this file (organiser/webapp.py → project root)
_ROOT = Path(__file__).parent.parent

# Initialize Flask app
app = Flask(
    __name__,
    template_folder=str(_ROOT / 'templates'),
    static_folder=str(_ROOT / 'static'),
)
CORS(app)

# Global state
config = None
db = None
learning_system = None
analyzer = None
notes_path = None


def init_webapp(config_path: Optional[str] = None):
    """Initialize the web application"""
    global config, db, learning_system, analyzer, notes_path
    
    # Load configuration
    config = load_config(config_path)
    
    # Setup logging
    setup_logging(config)
    
    # Initialize database
    db_path = expand_path(config['paths']['database'])
    db = Database(db_path)
    
    # Initialize learning system
    learning_system = LearningSystem(db, config)
    
    # Initialize analyzer (for AI-powered features)
    try:
        analyzer = MeetingAnalyzer(config, learning_system)
        logger.info("Meeting analyzer initialized")
    except Exception as e:
        logger.warning(f"Could not initialize analyzer (AI features disabled): {e}")
        analyzer = None
    
    # Setup notes path
    notes_path = expand_path(config['paths']['notes_output'])
    
    logger.info("Web application initialized")


# API Endpoints

@app.route('/api/status')
def api_status():
    """Get current processing status"""
    try:
        status = db.get_processing_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats')
def api_stats():
    """Get processing statistics"""
    try:
        stats = db.get_processing_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/history')
def api_history():
    """Get processing history with pagination"""
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        history = db.get_processing_history(limit=limit, offset=offset)
        
        return jsonify({
            'success': True,
            'history': history,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes')
def api_notes():
    """Get list of all note files"""
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Get from database
        note_files = db.get_note_files(limit=limit, offset=offset)
        
        # Enrich with file system info
        enriched_notes = []
        for nf in note_files:
            file_path = notes_path / nf['file_path']
            if file_path.exists():
                stat = file_path.stat()
                nf['size'] = stat.st_size
                nf['exists'] = True
            else:
                nf['exists'] = False
            enriched_notes.append(nf)
        
        return jsonify({
            'success': True,
            'notes': enriched_notes,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        logger.error(f"Error getting notes: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/<path:filename>')
def api_note_content(filename):
    """Get content of a specific note file"""
    try:
        file_path = notes_path / filename
        
        if not file_path.exists():
            return jsonify({
                'success': False,
                'error': 'Note file not found'
            }), 404
        
        # Check if path is within notes directory (security)
        err = _check_path_security(file_path)
        if err:
            return err
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Mark as read
        db.mark_note_read(filename)
        
        # Get metadata
        stat = file_path.stat()
        
        # Get detected names from database
        detected_names = db.get_detected_names(filename)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'content': content,
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'detected_names': detected_names
        })
    except Exception as e:
        logger.error(f"Error reading note {filename}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/<path:filename>', methods=['POST'])
def api_update_note(filename):
    """Update content of a note file"""
    try:
        file_path = notes_path / filename
        
        if not file_path.exists():
            return jsonify({
                'success': False,
                'error': 'Note file not found'
            }), 404
        
        # Check if path is within notes directory (security)
        err = _check_path_security(file_path)
        if err:
            return err
        
        data = request.get_json()
        new_content = data.get('content', '')
        
        # Read old content for tracking
        with open(file_path, 'r', encoding='utf-8') as f:
            old_content = f.read()
        
        # Write new content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Track modification
        db.track_note_modification(
            file_path=filename,
            old_content=old_content,
            new_content=new_content,
            change_type='web_edit'
        )
        
        # Detect and learn from corrections
        learning_system.detect_name_corrections(file_path)
        
        # Re-extract knowledge from updated file
        learning_system._extract_knowledge_from_file(file_path)
        
        # Clean up stale knowledge entries
        db.cleanup_stale_knowledge(notes_path)
        db.cleanup_orphaned_people()
        
        logger.info(f"Note updated via web: {filename}")
        
        return jsonify({
            'success': True,
            'message': 'Note updated successfully',
            'filename': filename
        })
    except Exception as e:
        logger.error(f"Error updating note {filename}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/rename', methods=['POST'])
def api_rename_note():
    """Rename a note file"""
    try:
        data = request.get_json()
        old_path = data.get('old_path', '')
        new_name = data.get('new_name', '')
        
        if not old_path or not new_name:
            return jsonify({
                'success': False,
                'error': 'Missing old_path or new_name'
            }), 400
        
        old_file = notes_path / old_path
        
        if not old_file.exists():
            return jsonify({
                'success': False,
                'error': 'Source file not found'
            }), 404
        
        # Check if path is within notes directory (security)
        err = _check_path_security(old_file)
        if err:
            return err
        
        # Build new path (same directory, new filename)
        new_file = old_file.parent / new_name
        
        if new_file.exists():
            return jsonify({
                'success': False,
                'error': f'A file named "{new_name}" already exists in this location'
            }), 409
        
        # Detect if this is a name correction before renaming
        correction_detected = False
        old_name_base = old_file.stem  # Filename without extension
        new_name_base = Path(new_name).stem
        
        # Check if this looks like a person name correction
        # (filename change in 1-to-1 folder or similar pattern)
        if old_name_base != new_name_base and '1-to-1' in str(old_path).lower():
            # Track as name correction
            db.add_name_correction(
                incorrect_name=old_name_base,
                correct_name=new_name_base,
                source_file=old_path,
                context='filename_rename'
            )
            correction_detected = True
            logger.info(f"Name correction detected: {old_name_base} → {new_name_base}")
        
        # Perform rename
        old_file.rename(new_file)
        
        # Update database tracking
        new_path = str(new_file.relative_to(notes_path))
        db.update_note_file_path(old_path, new_path,
                                 old_abs_path=str(old_file),
                                 new_abs_path=str(new_file))
        
        # Track the modification (using file path as content to indicate rename)
        db.track_note_modification(
            file_path=new_path,
            old_content=f'renamed_from:{old_path}',
            new_content=f'renamed_to:{new_path}',
            change_type='rename'
        )
        
        # Clean up stale knowledge entries
        db.cleanup_stale_knowledge(notes_path)
        
        logger.info(f"Note renamed: {old_path} → {new_path}")
        
        return jsonify({
            'success': True,
            'message': 'Note renamed successfully',
            'new_path': new_path,
            'correction_detected': correction_detected
        })
    except Exception as e:
        logger.error(f"Error renaming note: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/merge', methods=['POST'])
def api_merge_notes():
    """Merge two note files, preserving chronological order"""
    try:
        data = request.get_json()
        source_path = data.get('source_path', '')
        target_path = data.get('target_path', '')
        final_name = data.get('final_name', '')
        
        if not source_path or not target_path or not final_name:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        source_file = notes_path / source_path
        target_file = notes_path / target_path
        
        if not source_file.exists() or not target_file.exists():
            return jsonify({
                'success': False,
                'error': 'One or both files not found'
            }), 404
        
        # Security check
        err = _check_path_security(source_file, target_file)
        if err:
            return err
        
        # Read both files
        with open(source_file, 'r', encoding='utf-8') as f:
            source_content = f.read()
        
        with open(target_file, 'r', encoding='utf-8') as f:
            target_content = f.read()
        
        # Merge content intelligently
        merged_content = _merge_note_contents(source_content, target_content)
        
        # Determine final path (use target's directory)
        final_file = target_file.parent / final_name
        
        # If final name is different from both, create new file
        if final_file != source_file and final_file != target_file:
            # Create new merged file
            with open(final_file, 'w', encoding='utf-8') as f:
                f.write(merged_content)
            
            # Delete both source files
            source_file.unlink()
            target_file.unlink()
            
            # Update database
            final_path = str(final_file.relative_to(notes_path))
            db.register_note_file(final_path, file_type='merged')
            db.update_note_file_path(source_path, final_path,
                                     old_abs_path=str(source_file),
                                     new_abs_path=str(final_file))
            db.update_note_file_path(target_path, final_path,
                                     old_abs_path=str(target_file),
                                     new_abs_path=str(final_file))
        else:
            # Keep one file, delete the other
            if final_file == target_file:
                # Write merged content to target, delete source
                with open(target_file, 'w', encoding='utf-8') as f:
                    f.write(merged_content)
                source_file.unlink()
                final_path = target_path
                db.update_note_file_path(source_path, final_path,
                                         old_abs_path=str(source_file),
                                         new_abs_path=str(target_file))
            else:
                # Write merged content to source, delete target
                with open(source_file, 'w', encoding='utf-8') as f:
                    f.write(merged_content)
                target_file.unlink()
                final_path = source_path
                db.update_note_file_path(target_path, final_path,
                                         old_abs_path=str(target_file),
                                         new_abs_path=str(source_file))
        
        # Track modification
        db.track_note_modification(
            file_path=final_path,
            old_content=f'merged_from:{source_path},{target_path}',
            new_content=merged_content[:500],  # Store snippet
            change_type='merge'
        )
        
        # Re-extract knowledge from merged file
        learning_system._extract_knowledge_from_file(notes_path / final_path)
        
        logger.info(f"Notes merged: {source_path} + {target_path} → {final_path}")
        
        return jsonify({
            'success': True,
            'message': 'Notes merged successfully',
            'final_path': final_path
        })
    except Exception as e:
        logger.error(f"Error merging notes: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/extract', methods=['POST'])
def api_extract_meeting():
    """Extract a single meeting from a multi-meeting file"""
    try:
        data = request.get_json()
        source_path = data.get('source_path', '')
        meeting_index = data.get('meeting_index', 0)
        new_filename = data.get('new_filename', '')
        
        if not source_path or new_filename == '':
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        source_file = notes_path / source_path
        
        if not source_file.exists():
            return jsonify({
                'success': False,
                'error': 'Source file not found'
            }), 404
        
        # Security check
        err = _check_path_security(source_file)
        if err:
            return err
        
        # Read source file
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract meetings
        meetings = _extract_meetings_from_content(content)
        
        if meeting_index < 0 or meeting_index >= len(meetings):
            return jsonify({
                'success': False,
                'error': 'Invalid meeting index'
            }), 400
        
        # Get the meeting to extract
        extracted_meeting = meetings[meeting_index]
        
        # Remove from original
        remaining_meetings = [m for i, m in enumerate(meetings) if i != meeting_index]
        
        # Create new file in same directory
        new_file = source_file.parent / new_filename
        
        if new_file.exists():
            return jsonify({
                'success': False,
                'error': f'File "{new_filename}" already exists'
            }), 409
        
        # Write extracted meeting to new file
        with open(new_file, 'w', encoding='utf-8') as f:
            f.write(extracted_meeting)
        
        # Update original file with remaining meetings
        if remaining_meetings:
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write('\n\n---\n\n'.join(remaining_meetings))
        else:
            # If no meetings left, delete the file
            source_file.unlink()
        
        # Register new file in database
        new_path = str(new_file.relative_to(notes_path))
        db.register_note_file(new_path, file_type='extracted')
        
        # Track modification
        db.track_note_modification(
            file_path=new_path,
            old_content='',
            new_content=extracted_meeting[:500],
            change_type='extract'
        )
        
        # Extract knowledge from new file
        learning_system._extract_knowledge_from_file(new_file)
        
        logger.info(f"Meeting extracted: {source_path} → {new_path}")
        
        return jsonify({
            'success': True,
            'message': 'Meeting extracted successfully',
            'new_file': new_path
        })
    except Exception as e:
        logger.error(f"Error extracting meeting: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _extract_meetings_from_content(content):
    """Helper to extract individual meetings from content"""
    # Split by --- separator first
    if '---' in content:
        parts = re.split(r'\n---\n+', content)
        return [p.strip() for p in parts if p.strip()]
    
    # Otherwise split by ## headers
    parts = re.split(r'\n(?=## )', content)
    return [p.strip() for p in parts if p.strip()]


@app.route('/api/notes/delete', methods=['POST'])
def api_delete_note():
    """Delete a note file (tracked in database for future recording cleanup)"""
    try:
        data = request.get_json()
        file_path = data.get('file_path', '')
        
        if not file_path:
            return jsonify({
                'success': False,
                'error': 'Missing file_path parameter'
            }), 400
        
        note_file = notes_path / file_path
        
        if not note_file.exists():
            return jsonify({
                'success': False,
                'error': 'File not found'
            }), 404
        
        # Security check
        err = _check_path_security(note_file)
        if err:
            return err
        
        # Track deletion in database before removing file
        db.track_note_modification(
            file_path=file_path,
            old_content='',
            new_content='',
            change_type='deleted'
        )
        
        # Delete the file
        note_file.unlink()
        
        # Clean up stale knowledge entries and orphaned people
        db.cleanup_stale_knowledge(notes_path)
        db.cleanup_orphaned_people()
        
        logger.info(f"Note deleted: {file_path}")
        
        return jsonify({
            'success': True,
            'message': 'Note deleted successfully'
        })
    except Exception as e:
        logger.error(f"Error deleting note: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/move', methods=['POST'])
def api_move_note():
    """Move a note file to a different folder"""
    try:
        data = request.get_json()
        source_path = data.get('source_path', '')
        target_folder = data.get('target_folder', '')
        
        if not source_path or not target_folder:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        source_file = notes_path / source_path
        
        if not source_file.exists():
            return jsonify({
                'success': False,
                'error': 'Source file not found'
            }), 404
        
        # Security check
        err = _check_path_security(source_file)
        if err:
            return err
        
        # Build target path
        filename = source_file.name
        target_file = notes_path / target_folder / filename
        
        # Create target folder if it doesn't exist
        target_file.parent.mkdir(parents=True, exist_ok=True)
        
        if target_file.exists():
            return jsonify({
                'success': False,
                'error': f'A file named "{filename}" already exists in "{target_folder}"'
            }), 409
        
        # Move the file
        source_file.rename(target_file)
        
        # Update database tracking
        new_path = str(target_file.relative_to(notes_path))
        db.update_note_file_path(source_path, new_path,
                                 old_abs_path=str(source_file),
                                 new_abs_path=str(target_file))
        
        # Track the modification
        db.track_note_modification(
            file_path=new_path,
            old_content=f'moved_from:{source_path}',
            new_content=f'moved_to:{new_path}',
            change_type='move'
        )
        
        logger.info(f"Note moved: {source_path} → {new_path}")
        
        return jsonify({
            'success': True,
            'message': 'Note moved successfully',
            'new_path': new_path
        })
    except Exception as e:
        logger.error(f"Error moving note: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/detect-names', methods=['POST'])
def api_detect_names():
    """Detect person names in note content using AI"""
    try:
        if not analyzer:
            return jsonify({
                'success': False,
                'error': 'AI analyzer not available'
            }), 503
        
        data = request.get_json()
        file_path = data.get('file_path', '')
        content = data.get('content', '')
        
        if not content:
            return jsonify({
                'success': False,
                'error': 'No content provided'
            }), 400
        
        # Use OpenAI to detect names
        dn_cfg = analyzer.config.get('analysis', {}).get('detect_names', {})
        system_prompt = dn_cfg.get(
            'system_prompt',
            'You are a helpful assistant that extracts person names from meeting transcripts. Return only a JSON array of names, no other text.'
        )
        user_prompt_template = dn_cfg.get(
            'user_prompt',
            'Analyze this meeting transcript and extract all person names mentioned.\nReturn ONLY a JSON array of unique names, nothing else.\n\nExample output format:\n["John Smith", "Sarah Johnson"]\n\nTranscript:'
        )
        prompt = user_prompt_template.rstrip() + '\n' + content

        try:
            response = analyzer.client.chat.completions.create(
                model=analyzer.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=dn_cfg.get('temperature', 0.1),
                max_tokens=dn_cfg.get('max_tokens', 500)
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse the JSON array
            names = json.loads(result)
            
            # Store detected names in database
            if file_path:
                db.store_detected_names(file_path, names, method='ai')
            
            logger.info(f"Detected {len(names)} names in transcript")
            
            return jsonify({
                'success': True,
                'names': names
            })
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to parse AI response'
            }), 500
            
    except Exception as e:
        logger.error(f"Error detecting names: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/correct-name', methods=['POST'])
def api_correct_name():
    """Update database after name correction in note (file already updated by frontend)"""
    try:
        data = request.get_json()
        file_path = data.get('file_path', '')
        old_name = data.get('old_name', '')
        new_name = data.get('new_name', '')
        
        if not file_path or not old_name or not new_name:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        note_file = notes_path / file_path
        
        if not note_file.exists():
            return jsonify({
                'success': False,
                'error': 'Note file not found'
            }), 404
        
        # Security check
        err = _check_path_security(note_file)
        if err:
            return err
        
        # Track in database
        db.add_name_correction(
            incorrect_name=old_name,
            correct_name=new_name,
            source_file=file_path,
            context='manual_correction'
        )
        
        # Update detected names
        db.update_detected_name(file_path, old_name, new_name)
        
        db.track_note_modification(
            file_path=file_path,
            old_content='',  # Not needed for tracking
            new_content='',
            change_type='name_correction'
        )
        
        logger.info(f"Name corrected: {old_name} → {new_name} in {file_path}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully corrected "{old_name}" to "{new_name}"'
        })
            
    except Exception as e:
        logger.error(f"Error correcting name: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/notes/search', methods=['GET'])
def api_search_notes():
    """Search notes by filename and content"""
    try:
        query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify({
                'success': True,
                'results': []
            })
        
        query_lower = query.lower()
        results = []
        
        # Search through all note files
        for note_file in notes_path.rglob('*.md'):
            if note_file.name.startswith('.'):
                continue
            
            try:
                relative_path = note_file.relative_to(notes_path)
                relative_path_str = str(relative_path)
                filename = note_file.stem
                
                # Check if filename matches
                filename_match = query_lower in filename.lower()
                
                # Read content and search
                with open(note_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                content_lower = content.lower()
                content_match = query_lower in content_lower
                
                if filename_match or content_match:
                    # Extract snippets with context
                    snippets = []
                    if content_match:
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if query_lower in line.lower():
                                # Get context: previous and next line
                                start = max(0, i - 1)
                                end = min(len(lines), i + 2)
                                context_lines = lines[start:end]
                                snippet = '\n'.join(context_lines)
                                snippets.append({
                                    'line_number': i + 1,
                                    'text': snippet
                                })
                                
                                # Limit to 3 snippets per file
                                if len(snippets) >= 3:
                                    break
                    
                    results.append({
                        'path': relative_path_str,
                        'filename': filename,
                        'title_match': filename_match,
                        'content_match': content_match,
                        'snippets': snippets
                    })
            
            except Exception as e:
                logger.error(f"Error searching file {note_file}: {e}")
                continue
        
        # Sort results: title matches first, then by filename
        results.sort(key=lambda x: (not x['title_match'], x['filename']))
        
        return jsonify({
            'success': True,
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error searching notes: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/knowledge')
def api_knowledge():
    """Get knowledge base summary"""
    try:
        context = learning_system.get_learning_context()
        
        # Clean up stale knowledge entries (files that no longer exist)
        stale_count = db.cleanup_stale_knowledge(notes_path)
        if stale_count > 0:
            logger.info(f"Cleaned up {stale_count} stale knowledge entries")
            # Refresh context after cleanup
            context = learning_system.get_learning_context()
        
        # Clean up orphaned people (those with 0 files in note_detected_names)
        deleted_count = db.cleanup_orphaned_people()
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} orphaned people entries")
            # Refresh context again if we cleaned up people
            context = learning_system.get_learning_context()
        
        # Get detailed knowledge
        people = db.get_knowledge(entity_type='person', min_confidence=0.5)
        projects = db.get_knowledge(entity_type='project', min_confidence=0.5)
        patterns = db.get_knowledge(entity_type='meeting_pattern')
        corrections = db.get_name_corrections()
        
        response = jsonify({
            'success': True,
            'context': context,
            'knowledge': {
                'people': people,
                'projects': projects,
                'patterns': patterns,
                'name_corrections': corrections
            }
        })
        
        # Prevent caching to ensure fresh data
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        logger.error(f"Error getting knowledge: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/scan-notes', methods=['POST'])
def api_scan_notes():
    """Trigger a rescan of existing notes to update knowledge base"""
    try:
        force = request.get_json().get('force', False) if request.is_json else False
        learning_system.scan_existing_notes(force_rescan=force)
        
        return jsonify({
            'success': True,
            'message': 'Notes scanned successfully'
        })
    except Exception as e:
        logger.error(f"Error scanning notes: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/knowledge/delete-name', methods=['POST'])
def api_delete_name():
    """Delete a name from detected names (for non-person entries)"""
    try:
        data = request.get_json()
        name = data.get('name', '')
        
        if not name:
            return jsonify({
                'success': False,
                'error': 'Missing name parameter'
            }), 400
        
        # Delete from database
        db.delete_detected_name(name)
        
        logger.info(f"Deleted name: {name}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted "{name}"'
        })
        
    except Exception as e:
        logger.error(f"Error deleting name: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/knowledge/merge-names', methods=['POST'])
def api_merge_names():
    """Merge two person names across all notes and knowledge base"""
    try:
        data = request.get_json()
        name1 = data.get('name1', '')
        name2 = data.get('name2', '')
        keep_name = data.get('keep_name', '')
        
        if not name1 or not name2 or not keep_name:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        if keep_name not in [name1, name2]:
            return jsonify({
                'success': False,
                'error': 'keep_name must be either name1 or name2'
            }), 400
        
        remove_name = name1 if keep_name == name2 else name2
        
        # Get all files containing either name
        files_to_update = db.get_files_containing_names([name1, name2])
        
        logger.info(f"Merging names: '{remove_name}' \u2192 '{keep_name}' in {len(files_to_update)} files")
        
        # Update each file
        files_updated = _replace_name_in_files(files_to_update, remove_name, keep_name, 'name_merge')
        
        # Merge in database
        db.merge_person_names(name1, name2, keep_name)
        
        # Add name correction entry
        db.add_name_correction(
            incorrect_name=remove_name,
            correct_name=keep_name,
            source_file='knowledge_base_merge',
            context='manual_merge'
        )
        
        logger.info(f"Name merge complete: {files_updated} files updated")
        
        return jsonify({
            'success': True,
            'message': f'Successfully merged "{remove_name}" into "{keep_name}"',
            'files_updated': files_updated
        })
        
    except Exception as e:
        logger.error(f"Error merging names: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/knowledge/correct-name', methods=['POST'])
def api_correct_name_globally():
    """Correct a name across all notes (updates all files + database)"""
    try:
        data = request.get_json()
        logger.info(f"Received correct-name request with data: {data}")
        
        old_name = data.get('old_name', '')
        new_name = data.get('new_name', '')
        
        logger.info(f"Parsed: old_name='{old_name}', new_name='{new_name}'")
        
        if not old_name or not new_name:
            logger.error(f"Missing parameters: old_name='{old_name}', new_name='{new_name}'")
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        if old_name == new_name:
            return jsonify({
                'success': False,
                'error': 'Names are identical'
            }), 400
        
        # Get all files containing the old name
        files_to_update = db.get_files_containing_names([old_name])
        
        logger.info(f"Correcting name: '{old_name}' \u2192 '{new_name}' in {len(files_to_update)} files")
        
        # Update each file
        files_updated = _replace_name_in_files(files_to_update, old_name, new_name, 'name_correction')
        
        # Update database using rename_detected_name_globally
        db.rename_detected_name_globally(old_name, new_name)
        
        # Add name correction entry
        db.add_name_correction(
            incorrect_name=old_name,
            correct_name=new_name,
            source_file='knowledge_base_correction',
            context='manual_correction'
        )
        
        logger.info(f"Name correction complete: {files_updated} files updated")
        
        return jsonify({
            'success': True,
            'message': f'Successfully corrected "{old_name}" to "{new_name}"',
            'files_updated': files_updated
        })
        
    except Exception as e:
        logger.error(f"Error correcting name: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/note-tree')
def api_note_tree():
    """Get hierarchical tree structure of notes"""
    try:
        if not notes_path.exists():
            return jsonify({
                'success': True,
                'tree': []
            })
        
        def build_tree(path: Path, rel_path: str = ""):
            items = []
            
            try:
                for item in sorted(path.iterdir()):
                    if item.name.startswith('.'):
                        continue
                    
                    item_rel = str(Path(rel_path) / item.name) if rel_path else item.name
                    
                    if item.is_dir():
                        items.append({
                            'name': item.name,
                            'type': 'folder',
                            'path': item_rel,
                            'children': build_tree(item, item_rel)
                        })
                    elif item.suffix == '.md':
                        stat = item.stat()
                        
                        # Extract latest date from file content
                        latest_date = _extract_latest_date_from_file(item)
                        
                        items.append({
                            'name': item.name,
                            'type': 'file',
                            'path': item_rel,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'latest_date': latest_date.isoformat() if latest_date else None
                        })
            except PermissionError:
                pass
            
            # Sort files by latest_date (newest first), folders stay at top
            def sort_key(item):
                if item['type'] == 'folder':
                    return (0, item['name'])  # Folders first, alphabetically
                else:
                    # Files: sort by latest_date (newest first), then by name
                    date_val = item.get('latest_date')
                    if date_val:
                        # Negative timestamp to reverse order (newest first)
                        timestamp = datetime.fromisoformat(date_val).timestamp()
                        logger.debug(f"File {item['name']}: date={date_val}, sort_key=(1, {-timestamp})")
                        return (1, -timestamp, item['name'])
                    else:
                        # Files without dates go to the end
                        logger.debug(f"File {item['name']}: no date found, goes to end")
                        return (2, item['name'])
            
            items.sort(key=sort_key)
            
            return items
        
        tree = build_tree(notes_path)
        
        response = jsonify({
            'success': True,
            'tree': tree
        })
        
        # Prevent caching to ensure fresh data
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        logger.error(f"Error building note tree: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Web UI Routes

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/history')
def history():
    """Processing history page"""
    return render_template('history.html')


@app.route('/notes-viewer')
def notes_viewer():
    """Notes viewer and editor page"""
    return render_template('notes.html')


@app.route('/knowledge')
def knowledge():
    """Knowledge base viewer page"""
    return render_template('knowledge.html')


# Static files
@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory(str(_ROOT / 'static'), filename)


def run_webapp(host='0.0.0.0', port=5000, config_path=None):
    """Run the web application"""
    init_webapp(config_path)
    
    # Use config values if not overridden by parameters
    if config and 'web' in config:
        web_config = config['web']
        # Use config values if parameters are defaults
        if host == '0.0.0.0':
            host = web_config.get('host', '0.0.0.0')
        if port == 5000:
            port = web_config.get('port', 5000)
    
    logger.info(f"Starting web server on {host}:{port}")
    print(f"\n🌐 SuperWhisper Organiser Web Interface")
    print(f"   URL: http://{host}:{port}")
    print(f"   Press Ctrl+C to stop\n")
    
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    run_webapp()
