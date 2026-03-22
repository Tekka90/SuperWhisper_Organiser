#!/usr/bin/env python3
"""
SuperWhisper Organiser - Main Entry Point

Automatically organizes SuperWhisper meeting recordings into smart note files.
"""

import sys
import signal
import logging
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from organiser.utils import (
    load_config,
    setup_logging,
    expand_path
)
from organiser.database import Database
from organiser.learning import LearningSystem
from organiser.watcher import RecordingWatcher
from organiser.analyzer import MeetingAnalyzer
from organiser.organizer import NoteOrganizer


logger = None
console = Console()


class OrganiserApp:
    """Main application class"""
    
    def __init__(self, config_path: Optional[str] = None):
        # Load configuration
        self.config = load_config(config_path)
        
        # Store config path for later use
        self.config['_config_path'] = config_path
        
        # Setup logging
        global logger
        logger = setup_logging(self.config)
        
        # Initialize database
        db_path = expand_path(self.config['paths']['database'])
        self.db = Database(db_path)
        
        # Initialize learning system
        self.learning_system = LearningSystem(self.db, self.config)
        
        # Scan existing notes on startup
        try:
            self.learning_system.scan_existing_notes()
        except Exception as e:
            logger.warning(f"Could not scan existing notes: {e}")
        
        # Initialize components with learning system
        self.analyzer = MeetingAnalyzer(self.config, self.learning_system)
        self.organizer = NoteOrganizer(self.config, self.analyzer, self.db, self.learning_system)
        self.watcher = RecordingWatcher(self.config, self.process_recording)
        
        logger.info("SuperWhisper Organiser initialized")
    
    def process_recording(self, recording_folder: Path):
        """Process a single recording"""
        folder_name = recording_folder.name
        
        logger.info(f"Processing recording: {folder_name}")
        
        # Start processing tracking
        history_id = self.db.start_processing(folder_name)
        
        try:
            # Get relevant existing notes
            relevant_notes = []  # Could be enhanced to pass to analyzer
            
            # Analyze the recording
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task(f"Analyzing {folder_name}...", total=None)
                
                analysis = self.analyzer.analyze_recording(
                    recording_folder,
                    relevant_notes
                )
                
                progress.update(task, completed=True)
            
            if analysis is None:
                logger.error(f"Failed to analyze recording: {folder_name}")
                self.db.fail_processing(history_id, "Analysis failed")
                return
            
            # Display analysis
            console.print(Panel(
                f"[bold]Type:[/bold] {analysis.meeting_type}\n"
                f"[bold]Participants:[/bold] {', '.join(analysis.participants)}\n"
                f"[bold]Topics:[/bold] {', '.join(analysis.topics)}\n"
                f"[bold]Suggested file:[/bold] {analysis.suggested_filename}",
                title=f"Meeting Analysis: {folder_name}",
                border_style="green"
            ))
            
            # Organize the notes
            note_file = self.organizer.organize_recording(recording_folder, analysis)
            
            if note_file:
                console.print(f"[green]✓[/green] Notes saved to: {note_file}")
                
                # Mark as processed in enhanced database
                self.db.complete_processing(
                    history_id,
                    str(note_file),
                    analysis.meeting_type,
                    analysis.participants,
                    analysis.to_dict()
                )
                
                # Also mark in old database for backward compatibility
                from organiser.utils import mark_recording_processed
                db_path = expand_path(self.config['paths']['database'])
                mark_recording_processed(
                    db_path,
                    folder_name,
                    str(note_file),
                    analysis.meeting_type,
                    analysis.participants
                )
            else:
                logger.error(f"Failed to organize notes for: {folder_name}")
                self.db.fail_processing(history_id, "Failed to organize notes")
                
        except Exception as e:
            logger.error(f"Error processing recording {folder_name}: {e}", exc_info=True)
            console.print(f"[red]✗[/red] Error processing {folder_name}: {e}")
            self.db.fail_processing(history_id, str(e))
    
    def run_daemon(self):
        """Run as a daemon, continuously monitoring for new recordings"""
        console.print(Panel(
            "[bold green]SuperWhisper Organiser[/bold green]\n"
            "Monitoring for new meeting recordings...\n"
            "Press Ctrl+C to stop",
            border_style="blue"
        ))
        
        self.watcher.run()
    
    def process_all(self):
        """Process all existing unprocessed recordings"""
        console.print("[bold]Processing existing recordings...[/bold]")
        self.watcher.process_existing()
        console.print("[green]✓[/green] All recordings processed")
    
    def process_folder(self, folder_name: str):
        """Process a specific recording folder"""
        recordings_path = expand_path(self.config['paths']['recordings'])
        recording_folder = recordings_path / folder_name
        
        if not recording_folder.exists():
            console.print(f"[red]✗[/red] Recording folder not found: {folder_name}")
            return
        
        self.process_recording(recording_folder)
    
    def show_stats(self):
        """Display statistics about organized notes"""
        stats = self.organizer.get_stats()
        
        table = Table(title="Note Statistics")
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="magenta", justify="right")
        
        for folder_name, count in stats['by_type'].items():
            table.add_row(folder_name, str(count))
        
        table.add_row("[bold]Total[/bold]", f"[bold]{stats['total_notes']}[/bold]")
        table.add_row("Total Size", f"{stats['total_size_mb']} MB")
        
        console.print(table)
    
    def create_index(self):
        """Create an index of all notes"""
        console.print("[bold]Creating index...[/bold]")
        self.organizer.create_index()
        console.print("[green]✓[/green] Index created")
    
    def archive_old(self, days: int):
        """Archive notes older than specified days"""
        console.print(f"[bold]Archiving notes older than {days} days...[/bold]")
        self.organizer.archive_old_notes(days)
        console.print("[green]✓[/green] Archiving complete")


# CLI Commands
@click.group(invoke_without_command=True)
@click.pass_context
@click.option('--config', '-c', help='Path to config file', type=click.Path())
@click.option('--daemon', '-d', is_flag=True, help='Run as daemon')
def cli(ctx, config, daemon):
    """SuperWhisper Organiser - Intelligent meeting notes organization"""
    
    try:
        app = OrganiserApp(config)
        ctx.obj = app
        
        if daemon:
            app.run_daemon()
        elif ctx.invoked_subcommand is None:
            # No subcommand, show help
            click.echo(ctx.get_help())
            
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        if logger:
            logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.pass_obj
def watch(app):
    """Watch for new recordings (daemon mode)"""
    app.run_daemon()


@cli.command()
@click.pass_obj
def process_all(app):
    """Process all existing unprocessed recordings"""
    app.process_all()


@cli.command()
@click.argument('folder_name')
@click.pass_obj
def process(app, folder_name):
    """Process a specific recording folder"""
    app.process_folder(folder_name)


@cli.command()
@click.pass_obj
def stats(app):
    """Show statistics about organized notes"""
    app.show_stats()


@cli.command()
@click.pass_obj
def index(app):
    """Create an index file of all notes"""
    app.create_index()


@cli.command()
@click.option('--days', '-d', default=365, help='Days old to archive')
@click.pass_obj
def archive(app, days):
    """Archive old notes"""
    app.archive_old(days)


@cli.command()
@click.option('--host', '-h', default=None, help='Web server host (0.0.0.0 for network access)')
@click.option('--port', '-p', default=None, help='Web server port', type=int)
@click.pass_obj
def web(app, host, port):
    """Start the web interface"""
    from organiser.webapp import run_webapp
    
    # Get config path from app
    config_path = app.config.get('_config_path')
    
    # Use config defaults if not specified
    web_config = app.config.get('web', {})
    if host is None:
        host = web_config.get('host', '0.0.0.0')
    if port is None:
        port = web_config.get('port', 5000)
    
    console.print(Panel(
        f"[bold green]Starting Web Interface[/bold green]\n"
        f"URL: http://{host}:{port}\n"
        f"Press Ctrl+C to stop",
        border_style="blue"
    ))
    
    run_webapp(host=host, port=port, config_path=config_path)


@cli.command()
@click.pass_obj
def scan_notes(app):
    """Scan existing notes to build knowledge base"""
    console.print("[bold]Scanning notes for learning...[/bold]")
    app.learning_system.scan_existing_notes(force_rescan=True)
    console.print("[green]✓[/green] Scan complete")


@cli.command()
def version():
    """Show version information"""
    console.print("[bold]SuperWhisper Organiser[/bold] v2.0.0")
    console.print("Intelligent meeting notes organization for SuperWhisper")
    console.print("Now with web interface and learning capabilities!")


def signal_handler(sig, frame):
    """Handle interrupt signals gracefully"""
    console.print("\n[yellow]Shutting down gracefully...[/yellow]")
    sys.exit(0)


if __name__ == '__main__':
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run CLI
    cli()
