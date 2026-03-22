#!/usr/bin/env python3
"""
File system watcher for SuperWhisper recordings
"""

import time
import logging
from pathlib import Path
from typing import Callable, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .utils import (
    load_meta_json,
    is_file_stable,
    is_recording_processed,
    expand_path
)


logger = logging.getLogger('superwhisper_organiser.watcher')


def _is_processing_complete(meta: Dict[str, Any]) -> bool:
    """Check if SuperWhisper has finished processing the recording."""
    return bool(meta.get('llmResult') and meta.get('result'))


class RecordingHandler(FileSystemEventHandler):
    """Handler for file system events in the recordings directory"""
    
    def __init__(
        self,
        config: Dict[str, Any],
        on_new_recording: Callable[[Path], None]
    ):
        self.config = config
        self.on_new_recording = on_new_recording
        self.target_mode = config['monitoring']['target_mode']
        self.stability_wait = config['monitoring']['stability_wait']
        self.db_path = expand_path(config['paths']['database'])
        self.pending_recordings = set()
        
        logger.info(f"Initialized handler for recordings with mode: {self.target_mode}")
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events"""
        if event.is_directory:
            return
        
        # We're interested in meta.json files
        if not event.src_path.endswith('meta.json'):
            return
        
        recording_folder = Path(event.src_path).parent
        self._check_recording(recording_folder)
    
    def on_created(self, event: FileSystemEvent):
        """Handle file creation events"""
        if event.is_directory:
            # New recording folder created
            recording_folder = Path(event.src_path)
            self._check_recording(recording_folder)
        elif event.src_path.endswith('meta.json'):
            recording_folder = Path(event.src_path).parent
            self._check_recording(recording_folder)
    
    def _check_recording(self, recording_folder: Path):
        """Check if a recording is complete and ready to process"""
        folder_name = recording_folder.name
        
        # Skip if already processed
        if is_recording_processed(self.db_path, folder_name):
            return
        
        # Skip if already pending
        if folder_name in self.pending_recordings:
            return
        
        meta_file = recording_folder / 'meta.json'
        
        # Check if meta.json exists and is stable
        if not meta_file.exists():
            return
        
        if not is_file_stable(meta_file, self.stability_wait):
            logger.debug(f"Recording {folder_name} not yet stable, waiting...")
            self.pending_recordings.add(folder_name)
            return
        
        # Load and check meta.json
        meta = load_meta_json(recording_folder)
        
        if meta is None:
            logger.warning(f"Could not load meta.json for {folder_name}")
            return
        
        # Check if this is the target mode (e.g., "Meeting")
        mode_name = meta.get('modeName', '')
        
        if mode_name != self.target_mode:
            logger.debug(f"Skipping recording {folder_name} with mode: {mode_name}")
            return
        
        # Check if processing is complete
        if not _is_processing_complete(meta):
            logger.debug(f"Recording {folder_name} processing not complete")
            self.pending_recordings.add(folder_name)
            return
        
        # Recording is ready!
        logger.info(f"New complete recording detected: {folder_name}")
        self.pending_recordings.discard(folder_name)
        
        try:
            self.on_new_recording(recording_folder)
        except Exception as e:
            logger.error(f"Error processing recording {folder_name}: {e}", exc_info=True)
    
    def check_pending(self):
        """Re-check pending recordings that weren't stable before"""
        for folder_name in list(self.pending_recordings):
            recording_folder = Path(self.config['paths']['recordings']) / folder_name
            self._check_recording(recording_folder)


class RecordingWatcher:
    """Watches the SuperWhisper recordings folder for new meetings"""
    
    def __init__(
        self,
        config: Dict[str, Any],
        on_new_recording: Callable[[Path], None]
    ):
        self.config = config
        self.recordings_path = expand_path(config['paths']['recordings'])
        self.on_new_recording = on_new_recording
        self.observer = None
        self.handler = None
        
        logger.info(f"Initialized watcher for: {self.recordings_path}")
    
    def start(self):
        """Start watching the recordings directory"""
        if not self.recordings_path.exists():
            raise FileNotFoundError(f"Recordings path does not exist: {self.recordings_path}")
        
        self.handler = RecordingHandler(self.config, self.on_new_recording)
        self.observer = Observer()
        self.observer.schedule(
            self.handler,
            str(self.recordings_path),
            recursive=True
        )
        self.observer.start()
        
        logger.info("Watcher started")
    
    def stop(self):
        """Stop watching"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Watcher stopped")
    
    def process_existing(self):
        """Process all existing unprocessed recordings"""
        logger.info("Scanning for existing unprocessed recordings...")
        
        db_path = expand_path(self.config['paths']['database'])
        target_mode = self.config['monitoring']['target_mode']
        count = 0
        
        # Iterate through all recording folders
        for recording_folder in sorted(self.recordings_path.iterdir()):
            if not recording_folder.is_dir():
                continue
            
            folder_name = recording_folder.name
            
            # Skip if already processed
            if is_recording_processed(db_path, folder_name):
                continue
            
            # Load meta.json
            meta = load_meta_json(recording_folder)
            
            if meta is None:
                continue
            
            # Check mode
            if meta.get('modeName', '') != target_mode:
                continue
            
            # Check if complete
            if not _is_processing_complete(meta):
                logger.debug(f"Skipping incomplete recording: {folder_name}")
                continue
            
            logger.info(f"Processing existing recording: {folder_name}")
            
            try:
                self.on_new_recording(recording_folder)
                count += 1
            except Exception as e:
                logger.error(f"Error processing {folder_name}: {e}", exc_info=True)
        
        logger.info(f"Processed {count} existing recordings")
    
    def run(self):
        """Run the watcher continuously"""
        try:
            self.start()
            
            # Process existing recordings on startup if configured
            if self.config['monitoring'].get('process_on_startup', True):
                self.process_existing()
            
            logger.info("Watching for new recordings... Press Ctrl+C to stop")
            
            poll_interval = self.config['monitoring'].get('poll_interval', 10)
            # Periodic full re-scan interval in seconds (catches events watchdog may miss on macOS)
            scan_interval = self.config['monitoring'].get('scan_interval', 60)
            last_scan_time = time.time()
            
            while True:
                time.sleep(poll_interval)
                
                # Check pending recordings
                if self.handler:
                    self.handler.check_pending()
                
                # Periodically do a full filesystem scan to catch any events
                # that watchdog (macOS FSEvents) may have missed
                now = time.time()
                if now - last_scan_time >= scan_interval:
                    logger.debug("Performing periodic scan for missed recordings...")
                    self.process_existing()
                    last_scan_time = now
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()
