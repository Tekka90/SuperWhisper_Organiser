#!/usr/bin/env python3
"""
Learning system for SuperWhisper Organiser
Extracts knowledge from existing notes and tracks corrections
to improve future processing.
"""

import re
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger('superwhisper_organiser')

# Common words that match name patterns but are not person names
_FALSE_POSITIVE_NAMES = {
    'Meeting', 'Notes', 'Date', 'Time', 'Summary',
    'Action', 'Items', 'Speaker',
}


class LearningSystem:
    """
    Learns from existing notes to improve future processing:
    - Extracts person names, project names, meeting patterns
    - Tracks manual corrections made to notes
    - Builds context for intelligent file routing
    """
    
    def __init__(self, database, config: Dict[str, Any]):
        self.db = database
        self.config = config
        # Properly expand the path to resolve ~ and environment variables
        notes_path_str = config['paths']['notes_output']
        self.notes_path = Path(os.path.expanduser(os.path.expandvars(notes_path_str)))
        
    def scan_existing_notes(self, force_rescan: bool = False):
        """
        Scan all existing note files to extract knowledge
        """
        logger.info("Scanning existing notes for knowledge extraction...")
        
        if not self.notes_path.exists():
            logger.warning("Notes directory doesn't exist yet")
            return
        
        scanned_count = 0
        for md_file in self.notes_path.rglob('*.md'):
            if md_file.name.startswith('.'):
                continue
                
            try:
                self._extract_knowledge_from_file(md_file)
                scanned_count += 1
            except Exception as e:
                logger.error(f"Error scanning {md_file}: {e}")
        
        logger.info(f"Scanned {scanned_count} note files")
        self._log_knowledge_summary()
    
    def _extract_knowledge_from_file(self, file_path: Path):
        """Extract knowledge from a single note file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        file_path_str = str(file_path.relative_to(self.notes_path))
        
        # Extract file type from directory structure
        file_type = self._determine_file_type(file_path)
        
        # Extract person names
        people = self._extract_people(content, file_path)
        for person in people:
            self.db.add_knowledge(
                entity_type='person',
                entity_name=person,
                context=file_type,
                source_file=file_path_str,
                confidence=0.9
            )
        
        # Extract project names
        projects = self._extract_projects(content, file_path)
        for project in projects:
            self.db.add_knowledge(
                entity_type='project',
                entity_name=project,
                context=file_type,
                source_file=file_path_str,
                confidence=0.8
            )
        
        # Extract topics/tags
        topics = self._extract_topics(content)
        for topic in topics:
            self.db.add_knowledge(
                entity_type='topic',
                entity_name=topic,
                context=file_type,
                source_file=file_path_str,
                confidence=0.7
            )
        
        # Extract meeting patterns (1-on-1, team meetings, etc.)
        pattern = self._extract_meeting_pattern(file_path, content)
        if pattern:
            self.db.add_knowledge(
                entity_type='meeting_pattern',
                entity_name=pattern,
                context=file_path_str,
                source_file=file_path_str,
                confidence=1.0
            )
    
    def _determine_file_type(self, file_path: Path) -> str:
        """Determine the type of meeting based on file location"""
        parts = file_path.relative_to(self.notes_path).parts
        
        if '1-on-1' in parts or '1-to-1' in parts:
            return '1-on-1'
        elif 'team' in str(file_path).lower():
            return 'team-meeting'
        elif 'project' in str(file_path).lower():
            return 'project-meeting'
        else:
            return 'general'
    
    def _extract_people(self, content: str, file_path: Path) -> Set[str]:
        """Extract person names from content and filename"""
        people = set()
        
        # Extract from filename (common pattern: "1-on-1 with John.md")
        filename = file_path.stem
        
        # Pattern: "with [Name]" or "[Name] 1-on-1"
        name_patterns = [
            r'with\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:1-on-1|Meeting)',
            r'1-on-1\s+(?:with\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, filename)
            people.update(matches)
        
        # Extract from headers (# Meeting with John, ## Participants: John, Jane)
        header_matches = re.findall(r'(?:with|Participants?:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', content)
        people.update(header_matches)
        
        # Extract from "Attendees:" or "Participants:" sections
        attendee_section = re.search(r'(?:Attendees|Participants):\s*([^\n]+)', content)
        if attendee_section:
            names = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', attendee_section.group(1))
            people.update(names)
        
        # Filter out common false positives
        people = {p for p in people if p not in _FALSE_POSITIVE_NAMES and len(p) > 1}
        
        return people
    
    def _extract_projects(self, content: str, file_path: Path) -> Set[str]:
        """Extract project names from content"""
        projects = set()
        
        # Look for "Project:" markers
        project_matches = re.findall(r'Project:\s*([A-Z][A-Za-z0-9\s-]+)', content)
        projects.update(project_matches)
        
        # Look for capitalized phrases that might be project names
        # Pattern: 2-4 capitalized words
        potential_projects = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', content)
        
        # Filter by frequency (if mentioned multiple times, likely a project)
        from collections import Counter
        counter = Counter(potential_projects)
        frequent = {proj for proj, count in counter.items() if count >= 2}
        projects.update(frequent)
        
        # Extract from filename if it contains project keywords
        filename = file_path.stem
        if 'project' in filename.lower():
            project_name = re.sub(r'(?i)project\s+', '', filename)
            project_name = re.sub(r'(?i)\s+meeting.*', '', project_name)
            if project_name:
                projects.add(project_name.strip())
        
        return projects
    
    def _extract_topics(self, content: str) -> Set[str]:
        """Extract topics/tags from content"""
        topics = set()
        
        # Look for hashtags
        hashtags = re.findall(r'#([a-zA-Z][a-zA-Z0-9_-]+)', content)
        topics.update(hashtags)
        
        # Look for "Topics:" or "Tags:" sections
        topics_section = re.search(r'(?:Topics|Tags):\s*([^\n]+)', content)
        if topics_section:
            items = re.split(r'[,;]', topics_section.group(1))
            topics.update(item.strip() for item in items if item.strip())
        
        return topics
    
    def _extract_meeting_pattern(self, file_path: Path, content: str) -> Optional[str]:
        """Extract meeting pattern (e.g., '1-on-1:John', 'team:Engineering')"""
        file_type = self._determine_file_type(file_path)
        
        if file_type == '1-on-1':
            # For 1-on-1 meetings, ONLY extract from filename, not content
            # (content may mention other people but the file is about one person)
            person_name = self._extract_person_from_filename(file_path)
            if person_name:
                return f"1-on-1:{person_name}"
        elif file_type == 'team-meeting':
            # Extract team name from path or content
            team_name = self._extract_team_name(file_path, content)
            if team_name:
                return f"team:{team_name}"
        
        return file_type
    
    def _extract_person_from_filename(self, file_path: Path) -> Optional[str]:
        """Extract person name from 1-on-1 filename only"""
        filename = file_path.stem
        
        # Pattern: "1-on-1 with [Name]" or "1-to-1 with [Name]"
        name_patterns = [
            r'1-(?:on|to)-1\s+with\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'with\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, filename)
            if match:
                name = match.group(1)
                # Filter out false positives
                if name not in _FALSE_POSITIVE_NAMES:
                    return name
        
        return None
    
    def _extract_team_name(self, file_path: Path, content: str) -> Optional[str]:
        """Extract team name from file path or content"""
        # From path
        parts = file_path.relative_to(self.notes_path).parts
        for part in parts:
            if 'team' in part.lower():
                team = re.sub(r'(?i)team[s-]*', '', part).strip()
                if team:
                    return team
        
        # From content
        team_match = re.search(r'Team:\s*([A-Z][a-zA-Z\s]+)', content)
        if team_match:
            return team_match.group(1).strip()
        
        return None
    
    def detect_name_corrections(self, note_file: Path) -> List[Tuple[str, str]]:
        """
        Detect potential name corrections in a note file by comparing
        the current version with what might have been auto-transcribed.
        This is simplified - in reality, you'd need to track diffs.
        """
        corrections = []
        
        # This is a placeholder - real implementation would need to track
        # file versions or use git history to detect manual corrections
        # For now, we can look for common transcription error patterns
        
        with open(note_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for correction markers that users might add
        # e.g., "Fred (was incorrectly transcribed as 'Red')"
        correction_patterns = [
            r'([A-Z][a-z]+)\s*\((?:was|incorrectly).*?[\'""]([A-Za-z]+)[\'""]',
            r'(?:corrected?|fixed?):\s*[\'""]([A-Za-z]+)[\'""]\s*->\s*[\'""]?([A-Z][a-z]+)[\'""]?',
        ]
        
        for pattern in correction_patterns:
            matches = re.findall(pattern, content)
            for correct, incorrect in matches:
                corrections.append((incorrect.lower(), correct))
                self.db.add_name_correction(
                    incorrect_name=incorrect.lower(),
                    correct_name=correct,
                    source_file=str(note_file.relative_to(self.notes_path))
                )
        
        return corrections
    
    def get_learning_context(self) -> Dict[str, Any]:
        """
        Get learning context to be used in AI prompts for future processing.
        Returns structured information about known entities and patterns.
        """
        # Get people
        people = self.db.get_knowledge(entity_type='person', min_confidence=0.7)
        people_by_context = defaultdict(list)
        for p in people:
            people_by_context[p['context']].append(p['entity_name'])
        
        # Get projects
        projects = self.db.get_knowledge(entity_type='project', min_confidence=0.6)
        project_names = [p['entity_name'] for p in projects]
        
        # Get meeting patterns
        patterns = self.db.get_knowledge(entity_type='meeting_pattern')
        one_on_ones = [p['entity_name'].split(':')[1] for p in patterns if p['entity_name'].startswith('1-on-1:')]
        
        # Get name corrections
        name_corrections = self.db.get_name_corrections()
        correction_map = {nc['incorrect_name']: nc['correct_name'] for nc in name_corrections}
        
        return {
            'known_people': {
                'one_on_one': people_by_context.get('1-on-1', []),
                'team': people_by_context.get('team-meeting', []),
                'all': [p['entity_name'] for p in people]
            },
            'known_projects': project_names,
            'one_on_one_files': one_on_ones,
            'name_corrections': correction_map,
            'total_notes_scanned': len(people) + len(projects)
        }
    
    def build_system_prompt_context(self) -> str:
        """
        Build additional context to add to system prompts for the analyzer.
        This helps the AI make better decisions based on learned patterns.
        """
        context = self.get_learning_context()
        
        prompt_parts = []
        
        # Add known 1-on-1 people with typo detection emphasis
        if context['one_on_one_files']:
            one_on_ones = ', '.join(context['one_on_one_files'])
            prompt_parts.append(
                f"**Known 1-on-1 people:** {one_on_ones}\n"
                f"You might encounter a new person, but if you detect a name that is close to one of these, "
                f"it is probably a transcription error (typo). Please correct it to match the known name exactly. "
                f"If this meeting involves any of these people in a 1-on-1 context, consider appending to their existing file."
            )
        
        # Add all known people with typo detection emphasis
        if context['known_people']['all']:
            people = ', '.join(context['known_people']['all'][:20])  # Increased limit to 20
            prompt_parts.append(
                f"**All known people:** {people}\n"
                f"You might encounter a new person, but if you detect a name that is close to one of these, "
                f"it is probably a transcription error (typo). Please correct it to match the known name exactly."
            )
        
        # Add name corrections (known typos)
        if context['name_corrections']:
            corrections_str = ', '.join([f"'{inc}' → '{cor}'" for inc, cor in 
                                        list(context['name_corrections'].items())[:10]])
            prompt_parts.append(
                f"**Previously corrected typos:** {corrections_str}\n"
                f"Apply these corrections if you encounter these misspelled names."
            )
        
        # Add known projects
        if context['known_projects']:
            projects = ', '.join(context['known_projects'][:10])
            prompt_parts.append(
                f"**Known projects:** {projects}\n"
                f"If this meeting relates to any of these projects, mention it in your analysis."
            )
        
        if prompt_parts:
            return "\n\n**Context from previous notes:**\n\n" + "\n\n".join(prompt_parts)
        
        return ""
    
    def apply_name_corrections(self, text: str) -> str:
        """
        Apply known name corrections to text before or after processing.
        """
        corrections = self.db.get_name_corrections()
        
        corrected_text = text
        applied = []
        
        for nc in corrections:
            incorrect = nc['incorrect_name']
            correct = nc['correct_name']
            
            # Case-insensitive replacement while preserving the target case
            pattern = re.compile(re.escape(incorrect), re.IGNORECASE)
            if pattern.search(corrected_text):
                corrected_text = pattern.sub(correct, corrected_text)
                applied.append((incorrect, correct))
                self.db.increment_name_correction_usage(incorrect, correct)
        
        if applied:
            logger.info(f"Applied {len(applied)} name corrections")
        
        return corrected_text
    
    def _log_knowledge_summary(self):
        """Log summary of learned knowledge"""
        context = self.get_learning_context()
        
        logger.info(f"Knowledge Base Summary:")
        logger.info(f"  - People: {len(context['known_people']['all'])}")
        logger.info(f"  - Projects: {len(context['known_projects'])}")
        logger.info(f"  - 1-on-1 files: {len(context['one_on_one_files'])}")
        logger.info(f"  - Name corrections: {len(context['name_corrections'])}")
