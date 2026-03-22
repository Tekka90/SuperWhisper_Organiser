#!/usr/bin/env python3
"""
Note organization and file management
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from .utils import (
    load_meta_json,
    get_recording_date,
    format_duration,
    sanitize_filename,
    find_similar_notes,
    expand_path
)
from .analyzer import MeetingAnalysis, MeetingAnalyzer


logger = logging.getLogger('superwhisper_organiser.organizer')


class NoteOrganizer:
    """Organizes meeting notes into structured markdown files"""
    
    def __init__(self, config: Dict[str, Any], analyzer: MeetingAnalyzer, database=None, learning_system=None):
        self.config = config
        self.analyzer = analyzer
        self.db = database
        self.learning_system = learning_system
        self.notes_path = expand_path(config['paths']['notes_output'])
        self.org_config = config['organization']
        
        # Create notes directory structure
        self._init_directories()
        
        logger.info(f"Initialized organizer with output path: {self.notes_path}")
    
    def _init_directories(self):
        """Create the notes directory structure"""
        self.notes_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for different meeting types
        for folder_name in self.org_config['folders'].values():
            folder_path = self.notes_path / folder_name
            folder_path.mkdir(exist_ok=True)
    
    def organize_recording(
        self,
        recording_folder: Path,
        analysis: MeetingAnalysis
    ) -> Optional[Path]:
        """
        Organize a recording into the appropriate note file
        
        Args:
            recording_folder: Path to the recording folder
            analysis: MeetingAnalysis results
        
        Returns:
            Path to the note file where content was saved
        """
        # Load meta.json for full details
        meta = load_meta_json(recording_folder)
        
        if meta is None:
            logger.error(f"Could not load meta.json from {recording_folder}")
            return None
        
        # Determine target folder based on meeting type
        folder_name = self.org_config['folders'].get(
            analysis.meeting_type,
            self.org_config['folders']['general']
        )
        target_folder = self.notes_path / folder_name
        
        # Determine filename
        filename = sanitize_filename(analysis.suggested_filename)
        if not filename.endswith('.md'):
            filename += '.md'
        
        target_file = target_folder / filename
        
        # Check if we should merge with existing file
        should_append = target_file.exists()
        
        if target_file.exists():
            # Use AI to decide if we should merge
            with open(target_file, 'r') as f:
                existing_content = f.read()
            
            should_append = self.analyzer.suggest_merge(
                analysis.summary,
                existing_content,
                filename
            )
            
            if not should_append:
                # Create with timestamp suffix
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                filename = f"{target_file.stem}-{timestamp}.md"
                target_file = target_folder / filename
        
        # Generate note content
        note_content = self._generate_note_content(
            recording_folder,
            meta,
            analysis
        )
        
        # Write to file
        try:
            if should_append and target_file.exists():
                # Prepend to existing file (newest on top)
                with open(target_file, 'r') as f:
                    existing = f.read()
                
                # Write new content first, then separator, then existing content
                with open(target_file, 'w') as f:
                    f.write(note_content + "\n\n---\n\n" + existing)
                
                logger.info(f"Prepended notes to: {target_file} (newest on top)")
                
                if self.db:
                    # Update database
                    rel_path = str(target_file.relative_to(self.notes_path))
                    self.db.increment_note_recording_count(rel_path)
            else:
                # Create new file
                with open(target_file, 'w') as f:
                    f.write(note_content)
                logger.info(f"Created new note file: {target_file}")
                
                if self.db:
                    # Register in database
                    rel_path = str(target_file.relative_to(self.notes_path))
                    self.db.register_note_file(rel_path, analysis.meeting_type)
            
            # Extract knowledge from the new note
            if self.learning_system:
                try:
                    self.learning_system._extract_knowledge_from_file(target_file)
                except Exception as e:
                    logger.warning(f"Could not extract knowledge from note: {e}")
            
            return target_file
            
        except Exception as e:
            logger.error(f"Error writing note file: {e}", exc_info=True)
            return None
    
    def _generate_note_content(
        self,
        recording_folder: Path,
        meta: Dict[str, Any],
        analysis: MeetingAnalysis
    ) -> str:
        """Generate the markdown content for the note"""
        
        # Get metadata
        recording_date = get_recording_date(meta)
        duration = meta.get('duration', 0)
        llm_result = meta.get('llmResult', '')
        
        # Format date
        date_format = self.org_config.get('date_format', '%B %d, %Y at %H:%M')
        if recording_date:
            date_str = recording_date.strftime(date_format)
        else:
            date_str = f"Recording {recording_folder.name}"
        
        # Build header using template
        header_template = self.org_config.get('note_header_template', '')
        
        header = header_template.format(
            date=date_str,
            title=analysis.summary.split('\n')[0][:100] if analysis.summary else "Meeting",
            participants=', '.join(analysis.participants) if analysis.participants else 'Unknown',
            duration=format_duration(duration)
        )
        
        # Build content
        content_parts = [header]
        
        # Add topics if available
        if analysis.topics:
            content_parts.append("**Topics:** " + ", ".join(analysis.topics))
            content_parts.append("")
        
        # Add summary
        content_parts.append("### Summary\n")
        content_parts.append(llm_result if llm_result else analysis.summary)
        content_parts.append("")
        
        # Extract and add action items
        action_items = self.analyzer.extract_action_items(llm_result)
        if action_items:
            content_parts.append("### Action Items\n")
            for item in action_items:
                content_parts.append(f"- [ ] {item}")
            content_parts.append("")
        
        # Add recording link if configured
        if self.org_config.get('include_recording_link', True):
            content_parts.append(f"**Recording:** `{recording_folder.name}`")
            content_parts.append("")
        
        return "\n".join(content_parts)
    
    def get_relevant_notes(
        self,
        meeting_type: str,
        participants: list
    ) -> list:
        """Find relevant existing note files"""
        context_days = self.config['analysis'].get('context_window_days', 90)
        
        similar_notes = find_similar_notes(
            self.notes_path,
            meeting_type,
            participants,
            context_days
        )
        
        return similar_notes
    
    def create_index(self):
        """Create an index file of all notes"""
        index_path = self.notes_path / 'INDEX.md'
        
        content = ["# Meeting Notes Index\n"]
        content.append(f"*Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}*\n")
        
        # Group by folder
        for folder_key, folder_name in self.org_config['folders'].items():
            folder_path = self.notes_path / folder_name
            
            if not folder_path.exists():
                continue
            
            md_files = sorted(folder_path.glob('*.md'), reverse=True)
            
            if not md_files:
                continue
            
            # Add section header
            content.append(f"## {folder_name.replace('-', ' ').title()}\n")
            
            for md_file in md_files:
                rel_path = md_file.relative_to(self.notes_path)
                content.append(f"- [{md_file.stem}]({rel_path})")
            
            content.append("")
        
        # Write index
        with open(index_path, 'w') as f:
            f.write('\n'.join(content))
        
        logger.info(f"Created index at: {index_path}")
    
    def archive_old_notes(self, days_old: int = 365):
        """Archive notes older than specified days"""
        archive_path = self.notes_path / 'archive'
        archive_path.mkdir(exist_ok=True)
        
        archived_count = 0
        cutoff_date = datetime.now().timestamp() - (days_old * 86400)
        
        for md_file in self.notes_path.rglob('*.md'):
            if md_file.parent == archive_path:
                continue
            
            if md_file.name == 'INDEX.md':
                continue
            
            # Check file age
            if md_file.stat().st_mtime < cutoff_date:
                # Move to archive
                year = datetime.fromtimestamp(md_file.stat().st_mtime).year
                year_folder = archive_path / str(year)
                year_folder.mkdir(exist_ok=True)
                
                target = year_folder / md_file.name
                md_file.rename(target)
                
                archived_count += 1
                logger.info(f"Archived: {md_file.name} -> {target}")
        
        logger.info(f"Archived {archived_count} old notes")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about organized notes"""
        stats = {
            'total_notes': 0,
            'by_type': {},
            'total_size_mb': 0
        }
        
        for folder_key, folder_name in self.org_config['folders'].items():
            folder_path = self.notes_path / folder_name
            
            if not folder_path.exists():
                continue
            
            md_files = list(folder_path.glob('*.md'))
            count = len(md_files)
            
            stats['by_type'][folder_name] = count
            stats['total_notes'] += count
            
            # Calculate total size
            for md_file in md_files:
                stats['total_size_mb'] += md_file.stat().st_size / (1024 * 1024)
        
        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        
        return stats
