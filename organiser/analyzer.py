#!/usr/bin/env python3
"""
OpenAI integration for analyzing meeting recordings
"""

import logging
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from openai import OpenAI
import httpx

from .utils import (
    load_meta_json,
    get_recording_date,
    format_duration,
    extract_participants_from_segments
)


logger = logging.getLogger('superwhisper_organiser.analyzer')


class MeetingAnalysis:
    """Structure for meeting analysis results"""
    
    def __init__(
        self,
        meeting_type: str,
        participants: List[str],
        topics: List[str],
        suggested_filename: str,
        summary: str,
        related_meetings: List[str] = None,
        confidence: str = "medium"
    ):
        self.meeting_type = meeting_type
        self.participants = participants
        self.topics = topics
        self.suggested_filename = suggested_filename
        self.summary = summary
        self.related_meetings = related_meetings or []
        self.confidence = confidence
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'meeting_type': self.meeting_type,
            'participants': self.participants,
            'topics': self.topics,
            'suggested_filename': self.suggested_filename,
            'summary': self.summary,
            'related_meetings': self.related_meetings,
            'confidence': self.confidence
        }


class MeetingAnalyzer:
    """Analyzes meeting recordings using OpenAI"""
    
    def __init__(self, config: Dict[str, Any], learning_system=None):
        self.config = config
        self.openai_config = config['openai']
        self.learning_system = learning_system
        
        # Check if we're using a local endpoint (disable SSL verification)
        base_url = self.openai_config.get('base_url')
        http_client = None
        
        if base_url and ('localhost' in base_url or '127.0.0.1' in base_url or '10.0.0.' in base_url or '192.168.' in base_url):
            # Local endpoint - create httpx client with SSL verification disabled
            logger.info("Using local endpoint - disabling SSL verification")
            http_client = httpx.Client(verify=False)
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.openai_config['api_key'],
            base_url=base_url,
            http_client=http_client
        )
        
        self.model = self.openai_config['model']
        self.temperature = self.openai_config.get('temperature', 0.3)
        self.max_tokens = self.openai_config.get('max_tokens', 2000)
        
        # Check if we should use JSON mode (some local models don't support it)
        self.use_json_mode = self.openai_config.get('use_json_mode', True)
        if http_client is not None:  # Local endpoint
            self.use_json_mode = False  # Disable for local models by default
            logger.info("JSON mode disabled for local model")
        
        logger.info(f"Initialized analyzer with model: {self.model}")
    
    def analyze_recording(
        self,
        recording_folder: Path,
        existing_notes: Optional[List[Path]] = None
    ) -> Optional[MeetingAnalysis]:
        """
        Analyze a meeting recording and determine how to organize it
        
        Args:
            recording_folder: Path to the recording folder
            existing_notes: List of existing note files for context
        
        Returns:
            MeetingAnalysis object or None if analysis fails
        """
        # Load meta.json
        meta = load_meta_json(recording_folder)
        
        if meta is None:
            logger.error(f"Could not load meta.json from {recording_folder}")
            return None
        
        # Extract relevant information
        llm_result = meta.get('llmResult', '')
        raw_result = meta.get('rawResult', '')
        segments = meta.get('segments', [])
        
        # Get basic metadata
        duration = meta.get('duration', 0)
        recording_date = get_recording_date(meta)
        
        if not llm_result and not raw_result:
            logger.error(f"No transcript or summary found in {recording_folder}")
            return None
        
        # Extract participants from segments
        auto_participants = extract_participants_from_segments(segments)
        
        # Build context from existing notes
        existing_context = self._build_existing_context(existing_notes)
        
        # Get learning context if available
        learning_context = ""
        if self.learning_system:
            # Clean up stale knowledge before building context (ensures fresh data)
            if hasattr(self.learning_system, 'db') and hasattr(self.learning_system, 'notes_path'):
                self.learning_system.db.cleanup_stale_knowledge(self.learning_system.notes_path)
                self.learning_system.db.cleanup_orphaned_people()
            learning_context = self.learning_system.build_system_prompt_context()
        
        # Apply name corrections to transcript if available
        if self.learning_system:
            llm_result = self.learning_system.apply_name_corrections(llm_result)
            raw_result = self.learning_system.apply_name_corrections(raw_result)
        
        # Create the analysis prompt
        prompt = self._create_analysis_prompt(
            llm_result=llm_result,
            raw_result=raw_result,
            auto_participants=auto_participants,
            duration=duration,
            recording_date=recording_date,
            existing_context=existing_context,
            learning_context=learning_context
        )
        
        # Call OpenAI
        try:
            logger.info(f"Analyzing recording {recording_folder.name}...")
            
            # Build request parameters
            request_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": self.config['analysis']['system_prompt']
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            
            # Add JSON mode if supported
            if self.use_json_mode:
                request_params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**request_params)
            
            # Parse response
            content = response.choices[0].message.content
            
            # Try to parse as JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # If parsing fails, try to extract JSON from the response
                logger.warning("Response is not valid JSON, attempting to extract...")
                # Look for JSON block in markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*({[^`]+})\s*```', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                else:
                    # Try to find any JSON-like structure
                    json_match = re.search(r'({[^{}]*(?:{[^{}]*}[^{}]*)*})', content, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(1))
                    else:
                        logger.error("Could not extract JSON from response")
                        return None
            
            analysis = MeetingAnalysis(
                meeting_type=result.get('meeting_type', 'general'),
                participants=result.get('participants', auto_participants),
                topics=result.get('topics', []),
                suggested_filename=result.get('suggested_filename', 'meeting-notes.md'),
                summary=result.get('summary', llm_result),
                related_meetings=result.get('related_meetings', []),
                confidence=result.get('confidence', 'medium')
            )
            
            logger.info(f"Analysis complete: {analysis.meeting_type} - {analysis.suggested_filename}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing recording: {e}", exc_info=True)
            return None
    
    def _create_analysis_prompt(
        self,
        llm_result: str,
        raw_result: str,
        auto_participants: List[str],
        duration: int,
        recording_date: Any,
        existing_context: str,
        learning_context: str = ""
    ) -> str:
        """Create the prompt for meeting analysis"""
        
        prompt = f"""Analyze this meeting recording and provide organization details.

## Meeting Information

**Duration:** {format_duration(duration)}
**Date:** {recording_date.isoformat() if recording_date else 'Unknown'}
**Auto-detected speakers:** {', '.join(auto_participants) if auto_participants else 'None'}

## AI-Generated Summary

{llm_result[:2000] if llm_result else 'No summary available'}

## Transcript Excerpt

{raw_result[:3000] if raw_result else 'No transcript available'}

"""
        
        if existing_context:
            prompt += f"""
## Existing Note Files (for reference)

{existing_context}

"""
        
        if learning_context:
            prompt += learning_context + "\n\n"
        
        prompt += """
## Your Task

Analyze this meeting and provide the following in JSON format:

{
  "meeting_type": "one_on_one|team_meeting|project_meeting|interview|workshop|general",
  "participants": ["Name1", "Name2", ...],  // Extract actual names from content
  "topics": ["Topic1", "Topic2", ...],  // Main topics discussed
  "suggested_filename": "filename.md",  // Suggested filename (e.g., "1-to-1 with John.md")
  "summary": "Brief summary of key points",
  "related_meetings": ["existing-file1.md", ...],  // Which existing files this relates to
  "confidence": "high|medium|low"  // Your confidence in the categorization
}

**Important:**
- Try to extract real participant names from the conversation, not just "Speaker 1"
- For 1-on-1 meetings, suggest filename like "1-to-1 with [Name].md"
- For recurring meetings, match with existing files if possible
- Be specific with topics
- The summary should be concise (2-3 sentences)
"""
        
        return prompt
    
    def _build_existing_context(self, existing_notes: Optional[List[Path]]) -> str:
        """Build context string from existing note files"""
        if not existing_notes:
            return ""
        
        context_lines = []
        
        for note_file in existing_notes[:10]:  # Limit to 10 most recent
            context_lines.append(f"- {note_file.name}")
        
        if len(existing_notes) > 10:
            context_lines.append(f"... and {len(existing_notes) - 10} more files")
        
        return "\n".join(context_lines)
    
    def extract_action_items(self, text: str) -> List[str]:
        """Extract action items from text using OpenAI"""
        try:
            request_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Extract action items from meeting notes. Return as a JSON array of strings like: {\"action_items\": [\"item1\", \"item2\"]}"
                    },
                    {
                        "role": "user",
                        "content": f"Extract action items from this text:\n\n{text[:2000]}"
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 500
            }
            
            if self.use_json_mode:
                request_params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**request_params)
            
            content = response.choices[0].message.content
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'{[^}]+}', content)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    return []
            
            return result.get('action_items', [])
            
        except Exception as e:
            logger.error(f"Error extracting action items: {e}")
            return []
    
    def suggest_merge(
        self,
        new_summary: str,
        existing_content: str,
        filename: str
    ) -> bool:
        """
        Use AI to determine if new notes should be merged with existing file
        
        Returns:
            True if notes should be appended, False if new file should be created
        """
        try:
            prompt = f"""Should these new meeting notes be appended to the existing file "{filename}"?

## Existing File Content (last 1000 chars)
{existing_content[-1000:]}

## New Meeting Summary
{new_summary[:500]}

Respond with JSON:
{{
  "should_merge": true/false,
  "reason": "brief explanation"
}}
"""
            
            request_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You help determine if meeting notes should be merged based on topic similarity and participants."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 200
            }
            
            if self.use_json_mode:
                request_params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**request_params)
            
            content = response.choices[0].message.content
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'{[^}]+}', content)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    # Default to merging
                    return True
            
            should_merge = result.get('should_merge', False)
            reason = result.get('reason', '')
            
            logger.info(f"Merge decision for {filename}: {should_merge} - {reason}")
            
            return should_merge
            
        except Exception as e:
            logger.error(f"Error in merge suggestion: {e}")
            # Default to merging if same filename
            return True
