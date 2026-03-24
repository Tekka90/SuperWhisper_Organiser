#!/usr/bin/env python3
"""
OpenAI integration for analyzing meeting recordings
"""

import base64
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

        # Vision / screenshot support
        vision_cfg = config.get('vision', {})
        self.vision_enabled = vision_cfg.get('enabled', False)
        self.vision_model = vision_cfg.get('model', self.model)
        self.vision_max_screenshots = vision_cfg.get('max_screenshots', 5)
        self.vision_detail = vision_cfg.get('detail', 'low')
        self.vision_max_tokens = vision_cfg.get('max_tokens', 500)
        self.vision_temperature = vision_cfg.get('temperature', 0.1)
        self.user_name = config.get('monitoring', {}).get('user_name', '')

        logger.info(f"Initialized analyzer with model: {self.model}")
        if self.vision_enabled:
            logger.info(f"Vision enabled – using model: {self.vision_model}")
    
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
        
        # Extract participants from segments (fallback only)
        auto_participants = extract_participants_from_segments(segments)

        # ── Step 2b: Vision pre-pass ──────────────────────────────────────
        # If screenshots are available, ask the vision model first to identify
        # the real participant names, meeting title and any extra context.
        # This authoritative data replaces the diarisation placeholders.
        screenshot_parts = self._load_screenshots(recording_folder)
        vision_context = None
        if screenshot_parts:
            vision_context = self._extract_context_from_screenshots(screenshot_parts)
            if vision_context:
                logger.info(
                    f"Vision pre-pass complete – title: '{vision_context.get('meeting_title', '')}'  "
                    f"participants: {vision_context.get('participants', [])}"
                )
        
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
        
        # Create the analysis prompt (screenshots already consumed by vision pre-pass)
        prompt = self._create_analysis_prompt(
            llm_result=llm_result,
            raw_result=raw_result,
            auto_participants=auto_participants,
            duration=duration,
            recording_date=recording_date,
            existing_context=existing_context,
            learning_context=learning_context,
            vision_context=vision_context
        )

        # Call OpenAI (text-only – vision was already done in the pre-pass)
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

            # Guarantee the local user is always in the participant list
            if self.user_name and self.user_name not in analysis.participants:
                analysis.participants.insert(0, self.user_name)

            logger.info(f"Analysis complete: {analysis.meeting_type} - {analysis.suggested_filename}")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing recording: {e}", exc_info=True)
            return None
    
    def _extract_context_from_screenshots(self, screenshot_parts: List[dict]) -> Optional[dict]:
        """First-pass vision call: extract meeting title, participants and context.

        The screenshots are expected to contain:
          - The Teams meeting window (title bar = call name, participant panel)
          - Optionally: a calendar screenshot (planned duration, attendees)
          - Optionally: Outlook / Teams chat context

        Returns a dict with keys:
          meeting_title  : str   – best guess at the call name
          participants   : list  – real full names found in any screenshot
          extra_context  : str   – any other useful details (agenda, org, etc.)
        or None if the call fails.
        """
        prompt_template = self.config.get('vision', {}).get('prompt', '')
        if not prompt_template:
            # Fallback if config predates the vision.prompt key
            prompt_template = (
                "You are analysing screenshots taken during a video call on the computer of {user_name}.\n\n"
                "Please extract:\n"
                "1. The **meeting title** – from the title bar or calendar event name. Be exact.\n"
                "2. The **full list of participant names**. Always include \"{user_name}\" since they own the machine.\n"
                "3. Any **extra context** useful for classifying the meeting.\n\n"
                "Respond ONLY with a JSON object:\n"
                "{\n  \"meeting_title\": \"<title or empty>\",\n"
                "  \"participants\": [\"Full Name 1\"],\n"
                "  \"extra_context\": \"<context or empty>\"\n}\n"
            )
        user_name = self.user_name or 'the user'
        prompt_text = prompt_template.replace('{user_name}', user_name)
        vision_prompt = [
            {"type": "text", "text": prompt_text}
        ] + screenshot_parts

        try:
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{"role": "user", "content": vision_prompt}],
                temperature=self.vision_temperature,
                max_tokens=self.vision_max_tokens
            )
            raw = response.choices[0].message.content.strip()

            # Strip markdown fences if present
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                raw = match.group(0)

            result = json.loads(raw)
            # Guarantee user is in list
            if self.user_name and self.user_name not in result.get('participants', []):
                result.setdefault('participants', []).insert(0, self.user_name)
            return result

        except Exception as e:
            logger.warning(f"Vision pre-pass failed: {e}")
            return None

    def _create_analysis_prompt(
        self,
        llm_result: str,
        raw_result: str,
        auto_participants: List[str],
        duration: int,
        recording_date: Any,
        existing_context: str,
        learning_context: str = "",
        vision_context: Optional[dict] = None
    ) -> str:
        """Create the prompt for meeting analysis"""

        # Prefer vision-extracted data over transcript diarisation
        if vision_context:
            confirmed_participants = vision_context.get('participants', auto_participants)
            meeting_title_hint = vision_context.get('meeting_title', '')
            extra_context = vision_context.get('extra_context', '')
        else:
            confirmed_participants = auto_participants
            meeting_title_hint = ''
            extra_context = ''

        # Ensure user is always listed
        if self.user_name and self.user_name not in confirmed_participants:
            confirmed_participants = [self.user_name] + list(confirmed_participants)

        prompt = f"""Analyze this meeting recording and provide organization details.

## Meeting Information

**Duration:** {format_duration(duration)}
**Date:** {recording_date.isoformat() if recording_date else 'Unknown'}
**Confirmed participants (from screenshots):** {', '.join(confirmed_participants) if confirmed_participants else 'Unknown'}
{f'**Meeting title (from screenshots):** {meeting_title_hint}' if meeting_title_hint else ''}
{f'**Additional context (from screenshots):** {extra_context}' if extra_context else ''}

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

        filename_instruction = (
            f'The meeting title from screenshots is "{meeting_title_hint}" – use it as the basis for `suggested_filename`.'
            if meeting_title_hint
            else 'Infer the filename from the summary and participants.'
        )
        task_template = self.config['analysis'].get('user_prompt_task', '')
        task = (
            task_template
            .replace('{user_name}', self.user_name or 'The host')
            .replace('{filename_instruction}', filename_instruction)
        )
        prompt += task
        return prompt
    
    def _load_screenshots(self, recording_folder: Path) -> List[dict]:
        """Find and base64-encode screenshots left by capture_meeting.swift.

        Returns a list of image_url content parts ready for the OpenAI API.
        Only runs when vision is enabled in config.
        """
        if not self.vision_enabled:
            return []

        files: List[Path] = []
        for pattern in ('screenshot_*.png', 'screenshot_*.jpg', 'screenshot_*.jpeg'):
            files.extend(sorted(recording_folder.glob(pattern)))

        if not files:
            logger.debug(f"No screenshots found in {recording_folder.name}")
            return []

        # Prioritise windows whose filename suggests it is the main meeting window
        # (capture_meeting.swift names them _win1, _win2 … in z-order).
        files = files[:self.vision_max_screenshots]
        logger.info(f"Found {len(files)} screenshot(s) – sending to vision model")

        parts = []
        for f in files:
            try:
                img_bytes = self._resize_screenshot(f)
                data = base64.b64encode(img_bytes).decode()
                mime = 'image/jpeg' if f.suffix.lower() in ('.jpg', '.jpeg') else 'image/png'
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{data}",
                        "detail": self.vision_detail
                    }
                })
            except Exception as e:
                logger.warning(f"Could not read screenshot {f.name}: {e}")

        return parts

    @staticmethod
    def _resize_screenshot(path: Path, max_side: int = 1024) -> bytes:
        """Return the image bytes for *path*, resized so the longest side is at
        most *max_side* pixels.  Uses Pillow; falls back to raw bytes if Pillow
        is not available or the image cannot be opened."""
        try:
            from PIL import Image
            import io
            with Image.open(path) as img:
                w, h = img.size
                if max(w, h) > max_side:
                    scale = max_side / max(w, h)
                    new_size = (int(w * scale), int(h * scale))
                    img = img.resize(new_size, Image.LANCZOS)
                    logger.debug(f"{path.name}: resized {w}x{h} → {new_size[0]}x{new_size[1]}")
                buf = io.BytesIO()
                fmt = 'JPEG' if path.suffix.lower() in ('.jpg', '.jpeg') else 'PNG'
                img.save(buf, format=fmt)
                return buf.getvalue()
        except Exception as e:
            logger.debug(f"{path.name}: resize skipped ({e}), using raw bytes")
            return path.read_bytes()

    def _build_user_content(self, text_prompt: str, screenshot_parts: List[dict]):
        """Return a plain string (text only) or a multimodal list (text + images)."""
        if not screenshot_parts:
            return text_prompt
        # Multimodal: text block first, then one image block per screenshot
        return [{"type": "text", "text": text_prompt}] + screenshot_parts

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
            ai_cfg = self.config['analysis'].get('action_items', {})
            request_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": ai_cfg.get(
                            'system_prompt',
                            'Extract action items from meeting notes. Return as a JSON array of strings like: {"action_items": ["item1", "item2"]}'
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Extract action items from this text:\n\n{text[:2000]}"
                    }
                ],
                "temperature": ai_cfg.get('temperature', 0.2),
                "max_tokens": ai_cfg.get('max_tokens', 500)
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
            md_cfg = self.config['analysis'].get('merge_decision', {})
            request_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": md_cfg.get(
                            'system_prompt',
                            'You help determine if meeting notes should be merged based on topic similarity and participants.'
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": md_cfg.get('temperature', 0.2),
                "max_tokens": md_cfg.get('max_tokens', 200)
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
