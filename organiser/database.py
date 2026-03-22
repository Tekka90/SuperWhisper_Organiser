#!/usr/bin/env python3
"""
Enhanced database layer for SuperWhisper Organiser
Extends the simple SQLite tracking with full processing history,
note modifications tracking, and knowledge base.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger('superwhisper_organiser')


class Database:
    """Enhanced database operations"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_schema()
    
    def init_schema(self):
        """Initialize enhanced database schema"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Original processed_recordings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_recordings (
                folder_name TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL,
                note_file TEXT,
                meeting_type TEXT,
                participants TEXT,
                duration INTEGER,
                recording_date TEXT,
                status TEXT DEFAULT 'completed'
            )
        ''')
        
        # Processing history table (tracks every processing event)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                note_file TEXT,
                meeting_type TEXT,
                participants TEXT,
                error_message TEXT,
                metadata TEXT
            )
        ''')
        
        # Note files table (tracks all note files)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS note_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                last_modified TEXT NOT NULL,
                last_read TEXT,
                file_type TEXT,
                associated_recordings INTEGER DEFAULT 0,
                metadata TEXT
            )
        ''')
        
        # Note modifications table (tracks manual edits to notes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS note_modifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                modified_at TEXT NOT NULL,
                change_type TEXT,
                old_content TEXT,
                new_content TEXT,
                diff_summary TEXT
            )
        ''')
        
        # Knowledge base table (extracted entities and patterns)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                context TEXT,
                source_file TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                usage_count INTEGER DEFAULT 1,
                last_seen TEXT NOT NULL,
                UNIQUE(entity_type, entity_name)
            )
        ''')
        
        # Name corrections table (tracks transcript name corrections)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS name_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incorrect_name TEXT NOT NULL,
                correct_name TEXT NOT NULL,
                context TEXT,
                source_file TEXT,
                created_at TEXT NOT NULL,
                applied_count INTEGER DEFAULT 0,
                UNIQUE(incorrect_name, correct_name)
            )
        ''')
        
        # Current processing status table (singleton)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_processing INTEGER DEFAULT 0,
                current_folder TEXT,
                started_at TEXT,
                progress_percent INTEGER DEFAULT 0,
                status_message TEXT
            )
        ''')
        
        # Detected names table (tracks names detected in notes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS note_detected_names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                name TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                detection_method TEXT DEFAULT 'ai',
                UNIQUE(file_path, name)
            )
        ''')
        
        # Initialize status row if not exists
        cursor.execute('''
            INSERT OR IGNORE INTO processing_status (id, is_processing)
            VALUES (1, 0)
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Enhanced database schema initialized")
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # Processing status methods
    def set_processing_status(self, is_processing: bool, folder_name: str = None, 
                            progress: int = 0, message: str = None):
        """Update current processing status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE processing_status
            SET is_processing = ?,
                current_folder = ?,
                started_at = CASE WHEN ? = 1 THEN ? ELSE started_at END,
                progress_percent = ?,
                status_message = ?
            WHERE id = 1
        ''', (
            1 if is_processing else 0,
            folder_name,
            1 if is_processing else 0,
            datetime.now().isoformat() if is_processing else None,
            progress,
            message
        ))
        
        conn.commit()
        conn.close()
    
    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processing status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM processing_status WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return {
            'is_processing': False,
            'current_folder': None,
            'started_at': None,
            'progress_percent': 0,
            'status_message': None
        }
    
    # Processing history methods
    def start_processing(self, folder_name: str) -> int:
        """Start a new processing event, returns history ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO processing_history
            (folder_name, started_at, status)
            VALUES (?, ?, 'processing')
        ''', (folder_name, datetime.now().isoformat()))
        
        history_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        self.set_processing_status(True, folder_name, 0, f"Processing {folder_name}")
        return history_id
    
    def complete_processing(self, history_id: int, note_file: str, 
                           meeting_type: str, participants: List[str],
                           metadata: Dict[str, Any] = None):
        """Mark processing as completed"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE processing_history
            SET completed_at = ?,
                status = 'completed',
                note_file = ?,
                meeting_type = ?,
                participants = ?,
                metadata = ?
            WHERE id = ?
        ''', (
            datetime.now().isoformat(),
            note_file,
            meeting_type,
            ','.join(participants) if participants else '',
            json.dumps(metadata) if metadata else None,
            history_id
        ))
        
        conn.commit()
        conn.close()
        
        self.set_processing_status(False)
    
    def fail_processing(self, history_id: int, error_message: str):
        """Mark processing as failed"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE processing_history
            SET completed_at = ?,
                status = 'failed',
                error_message = ?
            WHERE id = ?
        ''', (
            datetime.now().isoformat(),
            error_message,
            history_id
        ))
        
        conn.commit()
        conn.close()
        
        self.set_processing_status(False)
    
    def get_processing_history(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get processing history with pagination"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM processing_history
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total processed
        cursor.execute('SELECT COUNT(*) as total FROM processed_recordings')
        total = cursor.fetchone()['total']
        
        # By type
        cursor.execute('''
            SELECT meeting_type, COUNT(*) as count
            FROM processed_recordings
            WHERE meeting_type IS NOT NULL
            GROUP BY meeting_type
        ''')
        by_type = {row['meeting_type']: row['count'] for row in cursor.fetchall()}
        
        # Recent activity (last 7 days)
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM processing_history
            WHERE started_at >= datetime('now', '-7 days')
        ''')
        recent = cursor.fetchone()['count']
        
        # Success/failure rates
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM processing_history
            GROUP BY status
        ''')
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'total_processed': total,
            'by_type': by_type,
            'last_7_days': recent,
            'by_status': by_status
        }
    
    # Note files methods
    def register_note_file(self, file_path: str, file_type: str = None, 
                          metadata: Dict[str, Any] = None):
        """Register or update a note file"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO note_files (file_path, created_at, last_modified, file_type, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                last_modified = ?,
                file_type = COALESCE(?, file_type),
                metadata = COALESCE(?, metadata)
        ''', (
            file_path, now, now, file_type, 
            json.dumps(metadata) if metadata else None,
            now, file_type, json.dumps(metadata) if metadata else None
        ))
        
        conn.commit()
        conn.close()
    
    def increment_note_recording_count(self, file_path: str):
        """Increment the associated recordings count for a note file"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE note_files
            SET associated_recordings = associated_recordings + 1,
                last_modified = ?
            WHERE file_path = ?
        ''', (datetime.now().isoformat(), file_path))
        
        conn.commit()
        conn.close()
    
    def mark_note_read(self, file_path: str):
        """Mark a note file as read"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE note_files
            SET last_read = ?
            WHERE file_path = ?
        ''', (datetime.now().isoformat(), file_path))
        
        conn.commit()
        conn.close()
    
    def update_note_file_path(self, old_path: str, new_path: str,
                               old_abs_path: str = None, new_abs_path: str = None):
        """Update the file path of a note file (for renames/moves)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            UPDATE note_files
            SET file_path = ?,
                last_modified = ?
            WHERE file_path = ?
        ''', (new_path, now, old_path))
        
        # Also update any references in note_modifications
        cursor.execute('''
            UPDATE note_modifications
            SET file_path = ?
            WHERE file_path = ?
        ''', (new_path, old_path))
        
        # Keep processing_history in sync using absolute paths
        if old_abs_path and new_abs_path:
            cursor.execute('''
                UPDATE processing_history
                SET note_file = ?
                WHERE note_file = ?
            ''', (new_abs_path, old_abs_path))
        
        conn.commit()
        conn.close()
    
    def get_note_files(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all note files with pagination"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM note_files
            ORDER BY last_modified DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # Note modifications tracking
    def track_note_modification(self, file_path: str, old_content: str, 
                               new_content: str, change_type: str = 'manual_edit'):
        """Track a modification to a note file"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Generate a simple diff summary
        diff_summary = self._generate_diff_summary(old_content, new_content)
        
        cursor.execute('''
            INSERT INTO note_modifications
            (file_path, modified_at, change_type, old_content, new_content, diff_summary)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            file_path,
            datetime.now().isoformat(),
            change_type,
            old_content,
            new_content,
            diff_summary
        ))
        
        conn.commit()
        conn.close()
    
    def get_deleted_notes(self) -> List[Dict[str, Any]]:
        """Get all deleted notes for cleanup purposes"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT file_path, modified_at
            FROM note_modifications
            WHERE change_type = 'deleted'
            ORDER BY modified_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def _generate_diff_summary(self, old: str, new: str) -> str:
        """Generate a simple diff summary"""
        old_lines = old.split('\n')
        new_lines = new.split('\n')
        
        added = len(new_lines) - len(old_lines)
        return f"Lines changed: {abs(added)} {'added' if added > 0 else 'removed'}"
    
    # Knowledge base methods
    def add_knowledge(self, entity_type: str, entity_name: str, 
                     context: str = None, source_file: str = None,
                     confidence: float = 1.0):
        """Add or update knowledge base entry"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO knowledge_base
            (entity_type, entity_name, context, source_file, confidence, created_at, last_seen, usage_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(entity_type, entity_name) DO UPDATE SET
                context = COALESCE(?, context),
                source_file = COALESCE(?, source_file),
                confidence = MAX(confidence, ?),
                usage_count = usage_count + 1,
                last_seen = ?
        ''', (
            entity_type, entity_name, context, source_file, confidence, now, now,
            context, source_file, confidence, now
        ))
        
        conn.commit()
        conn.close()
    
    def get_knowledge(self, entity_type: str = None, min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """Get knowledge base entries"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if entity_type == 'person':
            # For people, include file count from note_detected_names
            cursor.execute('''
                SELECT k.*,
                       COALESCE(n.file_count, 0) as file_count
                FROM knowledge_base k
                LEFT JOIN (
                    SELECT name, COUNT(DISTINCT file_path) as file_count
                    FROM note_detected_names
                    GROUP BY name
                ) n ON k.entity_name = n.name
                WHERE k.entity_type = ? AND k.confidence >= ?
                ORDER BY k.usage_count DESC, k.confidence DESC
            ''', (entity_type, min_confidence))
        elif entity_type:
            cursor.execute('''
                SELECT * FROM knowledge_base
                WHERE entity_type = ? AND confidence >= ?
                ORDER BY usage_count DESC, confidence DESC
            ''', (entity_type, min_confidence))
        else:
            cursor.execute('''
                SELECT * FROM knowledge_base
                WHERE confidence >= ?
                ORDER BY entity_type, usage_count DESC
            ''', (min_confidence,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def add_name_correction(self, incorrect_name: str, correct_name: str,
                           context: str = None, source_file: str = None):
        """Add a name correction pattern"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO name_corrections
            (incorrect_name, correct_name, context, source_file, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(incorrect_name, correct_name) DO UPDATE SET
                applied_count = applied_count + 1
        ''', (
            incorrect_name.lower(),
            correct_name,
            context,
            source_file,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_name_corrections(self) -> List[Dict[str, Any]]:
        """Get all name correction patterns"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM name_corrections
            ORDER BY applied_count DESC, created_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def increment_name_correction_usage(self, incorrect_name: str, correct_name: str):
        """Increment usage count for a name correction"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE name_corrections
            SET applied_count = applied_count + 1
            WHERE incorrect_name = ? AND correct_name = ?
        ''', (incorrect_name.lower(), correct_name))
        
        conn.commit()
        conn.close()
    
    # Detected names methods
    def store_detected_names(self, file_path: str, names: List[str], method: str = 'ai'):
        """Store detected names for a note file"""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Clear existing names for this file
        cursor.execute('DELETE FROM note_detected_names WHERE file_path = ?', (file_path,))
        
        # Insert new names
        for name in names:
            cursor.execute('''
                INSERT OR IGNORE INTO note_detected_names
                (file_path, name, detected_at, detection_method)
                VALUES (?, ?, ?, ?)
            ''', (file_path, name, now, method))
        
        conn.commit()
        conn.close()
        
        # Add to knowledge base (after closing connection)
        for name in names:
            self.add_knowledge('person', name, source_file=file_path, confidence=0.8)
    
    def get_detected_names(self, file_path: str) -> List[str]:
        """Get detected names for a note file"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT name FROM note_detected_names
            WHERE file_path = ?
            ORDER BY name
        ''', (file_path,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row['name'] for row in rows]
    
    def update_detected_name(self, file_path: str, old_name: str, new_name: str):
        """Update a detected name (after correction)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE note_detected_names
            SET name = ?
            WHERE file_path = ? AND name = ?
        ''', (new_name, file_path, old_name))
        
        conn.commit()
        conn.close()
        
        # Update knowledge base for new name
        self.add_knowledge('person', new_name, source_file=file_path, confidence=1.0)
        
        # Update old name's knowledge_base entry to point to a different file (if it still exists elsewhere)
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Find another file that contains the old name
        cursor.execute('''
            SELECT file_path FROM note_detected_names 
            WHERE name = ? 
            LIMIT 1
        ''', (old_name,))
        
        result = cursor.fetchone()
        
        if result:
            # Old name still exists in other files - update its source_file reference
            new_source_file = result['file_path']
            cursor.execute('''
                UPDATE knowledge_base
                SET source_file = ?, last_seen = ?
                WHERE entity_type = 'person' AND entity_name = ?
            ''', (new_source_file, datetime.now().isoformat(), old_name))
            conn.commit()
        
        conn.close()
        
        # Clean up orphaned entry (old name no longer exists in note_detected_names)
        self.cleanup_orphaned_people()
    
    def rename_detected_name_globally(self, old_name: str, new_name: str):
        """Rename a detected name across all files"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE note_detected_names
            SET name = ?
            WHERE name = ?
        ''', (new_name, old_name))
        
        # Update knowledge base
        cursor.execute('''
            UPDATE knowledge_base
            SET entity_name = ?
            WHERE entity_type = 'person' AND entity_name = ?
        ''', (new_name, old_name))
        
        conn.commit()
        conn.close()
    
    def merge_person_names(self, name1: str, name2: str, keep_name: str):
        """Merge two person names in knowledge base, combining usage counts"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        remove_name = name1 if keep_name == name2 else name2
        
        # Get both entries
        cursor.execute('''
            SELECT * FROM knowledge_base
            WHERE entity_type = 'person' AND entity_name IN (?, ?)
        ''', (name1, name2))
        entries = cursor.fetchall()
        
        if len(entries) == 0:
            conn.close()
            return
        
        # Calculate merged values
        total_usage = sum(e['usage_count'] for e in entries)
        max_confidence = max(e['confidence'] for e in entries)
        latest_seen = max(e['last_seen'] for e in entries)
        earliest_created = min(e['created_at'] for e in entries)
        
        # Delete the old entry from knowledge base
        cursor.execute('''
            DELETE FROM knowledge_base
            WHERE entity_type = 'person' AND entity_name = ?
        ''', (remove_name,))
        
        # Update the kept entry with merged values
        cursor.execute('''
            UPDATE knowledge_base
            SET usage_count = ?,
                confidence = ?,
                last_seen = ?,
                created_at = ?
            WHERE entity_type = 'person' AND entity_name = ?
        ''', (total_usage, max_confidence, latest_seen, earliest_created, keep_name))
        
        # If keep_name doesn't exist yet, insert it
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO knowledge_base
                (entity_type, entity_name, confidence, created_at, last_seen, usage_count)
                VALUES ('person', ?, ?, ?, ?, ?)
            ''', (keep_name, max_confidence, earliest_created, latest_seen, total_usage))
        
        # Update detected names - handle UNIQUE constraint carefully
        # First, delete remove_name entries where keep_name already exists (to avoid duplicates)
        cursor.execute('''
            DELETE FROM note_detected_names
            WHERE name = ? AND file_path IN (
                SELECT file_path FROM note_detected_names WHERE name = ?
            )
        ''', (remove_name, keep_name))
        
        # Now update remaining remove_name entries to keep_name
        cursor.execute('''
            UPDATE note_detected_names
            SET name = ?
            WHERE name = ?
        ''', (keep_name, remove_name))
        
        conn.commit()
        conn.close()
    
    def get_files_containing_names(self, names: List[str]) -> List[str]:
        """Get list of note files containing any of the given names"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(names))
        cursor.execute(f'''
            SELECT DISTINCT file_path
            FROM note_detected_names
            WHERE name IN ({placeholders})
        ''', names)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row['file_path'] for row in rows]
    
    def cleanup_orphaned_people(self):
        """Remove people from knowledge_base who have no files in note_detected_names"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Delete people with 0 files
        cursor.execute('''
            DELETE FROM knowledge_base
            WHERE entity_type = 'person'
            AND entity_name NOT IN (
                SELECT DISTINCT name FROM note_detected_names
            )
        ''')
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def cleanup_stale_knowledge(self, notes_path: Path):
        """Remove knowledge_base entries whose source files no longer exist or patterns are invalid"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get all knowledge entries with source_file
        cursor.execute('SELECT id, entity_type, entity_name, source_file FROM knowledge_base WHERE source_file IS NOT NULL')
        entries = cursor.fetchall()
        
        deleted_count = 0
        for entry_id, entity_type, entity_name, source_file in entries:
            if source_file:
                full_path = notes_path / source_file
                
                # Delete if file doesn't exist
                if not full_path.exists():
                    cursor.execute('DELETE FROM knowledge_base WHERE id = ?', (entry_id,))
                    deleted_count += 1
                # For meeting_pattern entries, validate the pattern matches the filename
                elif entity_type == 'meeting_pattern' and entity_name.startswith('1-on-1:'):
                    # Extract name from pattern (e.g., "1-on-1:John" -> "John")
                    pattern_name = entity_name.split(':', 1)[1]
                    # Check if filename contains "with [name]"
                    filename = full_path.stem.lower()
                    if f'with {pattern_name.lower()}' not in filename:
                        # Pattern doesn't match filename - delete it
                        cursor.execute('DELETE FROM knowledge_base WHERE id = ?', (entry_id,))
                        deleted_count += 1
                        logger.info(f"Removed invalid pattern: {entity_name} from {source_file}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"Cleaned up {deleted_count} stale knowledge entries")
        return deleted_count
    
    def delete_detected_name(self, name: str):
        """Remove a name from detected names (for non-person entries)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Delete from note_detected_names
        cursor.execute('DELETE FROM note_detected_names WHERE name = ?', (name,))
        
        # Delete from knowledge_base
        cursor.execute('DELETE FROM knowledge_base WHERE entity_name = ? AND entity_type = "person"', (name,))
        
        conn.commit()
        conn.close()

