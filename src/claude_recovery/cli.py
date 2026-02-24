from __future__ import annotations

import fnmatch
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from claude_recovery.core.reconstructor import reconstruct_latest
from claude_recovery.core.scanner import scan_all_sessions

app = typer.Typer(
    name="claude-recovery",
    help="Recover files created and modified by Claude Code from session transcripts.",
    invoke_without_command=True,
)
console = Console()


def _default_output_dir() -> Path:
    return Path(f"./recovered-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}")


def _scan_with_progress(claude_dir: Path) -> dict:
    """Scan all sessions with a Rich progress indicator."""
    from rich.progress import Progress

    result = {}

    with Progress(console=console) as progress:
        task = progress.add_task("Scanning sessions...", total=None)

        def on_progress(completed: int, total: int):
            progress.update(task, total=total, completed=completed)

        result = scan_all_sessions(claude_dir, progress_callback=on_progress)

    return result


@app.command("list-files")
def list_files(
    claude_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--claude-dir", "-c",
        help="Path to Claude Code user config directory",
    ),
    filter_pattern: str = typer.Option(
        "",
        "--filter", "-f",
        help="Glob pattern to filter file paths (e.g., '*.ts', '**/router*')",
    ),
    csv: bool = typer.Option(
        False,
        "--csv",
        help="Output in CSV format",
    ),
):
    """List all recoverable files with paths and latest modification dates."""
    files = _scan_with_progress(claude_dir)

    # Apply filter
    if filter_pattern:
        files = {
            p: f for p, f in files.items()
            if fnmatch.fnmatch(p, filter_pattern) or fnmatch.fnmatch(Path(p).name, filter_pattern)
        }

    # Sort by path (filename + directory)
    sorted_files = sorted(files.values(), key=lambda f: f.path)

    if csv:
        import csv as csv_mod
        import sys

        writer = csv_mod.writer(sys.stdout)
        writer.writerow(["last_modified", "ops", "full", "path"])
        for rf in sorted_files:
            ts = rf.latest_timestamp
            date_str = ts[:16].replace("T", " ") if ts else "unknown"
            full = "yes" if rf.has_full_content else "no"
            writer.writerow([date_str, rf.operation_count, full, rf.path])
        return

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


@app.command("extract-files")
def extract_files(
    claude_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--claude-dir", "-c",
        help="Path to Claude Code user config directory",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output", "-o",
        help="Output directory for recovered files (default: recovered-{timestamp})",
    ),
    filter_pattern: str = typer.Option(
        "",
        "--filter", "-f",
        help="Glob pattern to filter file paths",
    ),
):
    """Extract recovered files to disk, preserving directory structure."""
    if output_dir is None:
        output_dir = _default_output_dir()

    files = _scan_with_progress(claude_dir)

    # Apply filter
    if filter_pattern:
        files = {
            p: f for p, f in files.items()
            if fnmatch.fnmatch(p, filter_pattern) or fnmatch.fnmatch(Path(p).name, filter_pattern)
        }

    if not files:
        console.print("[yellow]No files match the filter.[/yellow]")
        raise typer.Exit()

    console.print(f"Reconstructing {len(files)} files...")

    success = 0
    failed = 0
    skipped = 0

    from rich.progress import Progress
    with Progress(console=console) as progress:
        task = progress.add_task("Extracting...", total=len(files))

        for rf in files.values():
            progress.advance(task)
            content = reconstruct_latest(rf)
            if content is None:
                skipped += 1
                continue

            # Build output path: output_dir + absolute path (strip leading /)
            rel_path = rf.path.lstrip("/")
            out_path = output_dir / rel_path

            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                success += 1
            except Exception:
                failed += 1

    console.print(
        f"\n[bold green]{success}[/bold green] extracted, "
        f"[bold yellow]{skipped}[/bold yellow] skipped (no content), "
        f"[bold red]{failed}[/bold red] failed."
    )


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context):
    """Default command — launches TUI (implemented in Phase 4)."""
    if ctx.invoked_subcommand is None:
        console.print("[yellow]TUI not yet implemented. Use 'list-files' or 'extract-files'.[/yellow]")
        raise typer.Exit()
