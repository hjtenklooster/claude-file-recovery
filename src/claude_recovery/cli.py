from __future__ import annotations

import fnmatch
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from claude_recovery.core.scanner import scan_all_sessions

app = typer.Typer(
    name="claude-recovery",
    help="Recover files created and modified by Claude Code from session transcripts.",
    invoke_without_command=True,
)
console = Console()


def _default_output_dir() -> Path:
    return Path(f"./output-{datetime.now().strftime('%Y%m%d-%H%M%S')}")


def _scan_with_progress(backup_dir: Path) -> dict:
    """Scan all sessions with a Rich progress indicator."""
    from rich.progress import Progress

    result = {}

    with Progress(console=console) as progress:
        task = progress.add_task("Scanning sessions...", total=None)

        def on_progress(completed: int, total: int):
            progress.update(task, total=total, completed=completed)

        result = scan_all_sessions(backup_dir, progress_callback=on_progress)

    return result


@app.command("list-files")
def list_files(
    backup_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--backup-dir", "-b",
        help="Path to Claude backup directory",
    ),
    filter_pattern: str = typer.Option(
        "",
        "--filter", "-f",
        help="Glob pattern to filter file paths (e.g., '*.ts', '**/router*')",
    ),
):
    """List all recoverable files with paths and latest modification dates."""
    files = _scan_with_progress(backup_dir)

    # Apply filter
    if filter_pattern:
        files = {
            p: f for p, f in files.items()
            if fnmatch.fnmatch(p, filter_pattern) or fnmatch.fnmatch(Path(p).name, filter_pattern)
        }

    # Sort by path (filename + directory)
    sorted_files = sorted(files.values(), key=lambda f: f.path)

    table = Table(title=f"Recoverable Files ({len(sorted_files)} files)")
    table.add_column("Last Modified", style="cyan", no_wrap=True)
    table.add_column("Ops", justify="right", style="green")
    table.add_column("Full", justify="center", style="bold")
    table.add_column("Path", style="white")

    for rf in sorted_files:
        ts = rf.latest_timestamp
        date_str = ts[:16].replace("T", " ") if ts else "unknown"
        full = "[green]yes[/green]" if rf.has_full_content else "[red]no[/red]"
        table.add_row(date_str, str(rf.operation_count), full, rf.path)

    console.print(table)
    console.print(f"\n[bold]{len(sorted_files)}[/bold] recoverable files found.")


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context):
    """Default command — launches TUI (implemented in Phase 4)."""
    if ctx.invoked_subcommand is None:
        console.print("[yellow]TUI not yet implemented. Use 'list-files' or 'extract-files'.[/yellow]")
        raise typer.Exit()
