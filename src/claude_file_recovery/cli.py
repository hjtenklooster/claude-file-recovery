from __future__ import annotations

from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from claude_file_recovery.core.filters import SearchMode, filter_files, filter_by_timestamp
from claude_file_recovery.core.reconstructor import (
    reconstruct_at_timestamp,
    reconstruct_latest,
)
from claude_file_recovery.core.scanner import scan_all_sessions
from claude_file_recovery.core.timestamps import (
    normalize_timestamp,
    format_local_confirmation,
    utc_to_local,
)


def _version_callback(value: bool) -> None:
    if value:
        print(f"claude-file-recovery {version('claude-file-recovery')}")
        raise typer.Exit()


app = typer.Typer(
    name="claude-file-recovery",
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
        "--claude-dir",
        "-c",
        help="Path to Claude Code user config directory",
    ),
    filter_pattern: str = typer.Option(
        "",
        "--filter",
        "-f",
        help="Pattern to filter file paths (e.g., '*.ts' for glob, 'router' for fuzzy, '\\.py$' for regex)",
    ),
    mode: SearchMode = typer.Option(
        SearchMode.GLOB,
        "--mode",
        "-m",
        help="Filter mode: glob (default, e.g. '*.py'), regex (e.g. '\\.py$'), or fuzzy (e.g. 'routpy')",
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive",
        "-s",
        is_flag=True,
        help="Force case-sensitive matching (default: smart-case)",
    ),
    ignore_case: bool = typer.Option(
        False,
        "--ignore-case",
        "-i",
        is_flag=True,
        help="Force case-insensitive matching (default: smart-case)",
    ),
    before: str = typer.Option(
        "",
        "--before",
        "-b",
        help="Only include operations at or before this timestamp (e.g. '2026-01-30', '2026-01-30 15:00')",
    ),
    csv: bool = typer.Option(
        False,
        "--csv",
        help="Output in CSV format",
    ),
    no_injection_detection: bool = typer.Option(
        False,
        "--no-injection-detection",
        is_flag=True,
        help="Disable detection of injected content in Read operations",
    ),
):
    """List all recoverable files with paths and latest modification dates."""
    files = _scan_with_progress(claude_dir)

    # Detect injected content (warn only, no stripping — list-files doesn't output content)
    if not no_injection_detection:
        from claude_file_recovery.core.injection import detect_injected_content

        patterns = detect_injected_content(files)
        if patterns:
            total_ops = sum(p.affected_op_count for p in patterns)
            total_files = sum(p.affected_file_count for p in patterns)
            console.print(
                f"[yellow]Detected injected content in {total_ops} Read operations "
                f"across {total_files} files. Use extract-files to strip, or "
                f"--no-injection-detection to suppress this warning.[/yellow]"
            )

    # Apply filter
    case_override = True if case_sensitive else (False if ignore_case else None)
    files = filter_files(files, filter_pattern, mode, case_override)

    # Apply timestamp filter
    before_ts = ""
    if before:
        try:
            before_ts = normalize_timestamp(before)
        except ValueError as e:
            console.print(f"[red]Invalid --before timestamp: {e}[/red]")
            raise typer.Exit(code=1)
        console.print(
            f"Filtering operations before {format_local_confirmation(before_ts)}"
        )
        files = filter_by_timestamp(files, before_ts)

    # Sort by path (filename + directory)
    sorted_files = sorted(files.values(), key=lambda f: f.path)

    if csv:
        import csv as csv_mod
        import sys

        writer = csv_mod.writer(sys.stdout)
        writer.writerow(["last_modified", "ops", "full", "path"])
        for rf in sorted_files:
            date_str = (
                utc_to_local(rf.latest_timestamp) if rf.latest_timestamp else "unknown"
            )
            full = "yes" if rf.has_full_content else "no"
            writer.writerow([date_str, rf.operation_count, full, rf.path])
        return

    before_label = f", before {utc_to_local(before_ts)}" if before_ts else ""
    table = Table(title=f"Recoverable Files ({len(sorted_files)} files{before_label})")
    table.add_column("Last Modified", style="cyan", no_wrap=True)
    ops_header = "Ops (before cutoff)" if before_ts else "Ops"
    table.add_column(ops_header, justify="right", style="green")
    table.add_column("Full", justify="center", style="bold")
    table.add_column("Path", style="white")

    for rf in sorted_files:
        date_str = (
            utc_to_local(rf.latest_timestamp) if rf.latest_timestamp else "unknown"
        )
        full = "[green]yes[/green]" if rf.has_full_content else "[red]no[/red]"
        table.add_row(date_str, str(rf.operation_count), full, rf.path)

    console.print(table)
    console.print(f"\n[bold]{len(sorted_files)}[/bold] recoverable files found.")


@app.command("extract-files")
def extract_files(
    claude_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--claude-dir",
        "-c",
        help="Path to Claude Code user config directory",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for recovered files (default: recovered-{timestamp})",
    ),
    symlink_file: Path = typer.Option(
        None,
        "--symlink-file",
        help="Path to a YAML file with symlink mappings for deduplication",
    ),
    filter_pattern: str = typer.Option(
        "",
        "--filter",
        "-f",
        help="Pattern to filter file paths (e.g., '*.ts' for glob, 'router' for fuzzy, '\\.py$' for regex)",
    ),
    mode: SearchMode = typer.Option(
        SearchMode.GLOB,
        "--mode",
        "-m",
        help="Filter mode: glob (default, e.g. '*.py'), regex (e.g. '\\.py$'), or fuzzy (e.g. 'routpy')",
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive",
        "-s",
        is_flag=True,
        help="Force case-sensitive matching (default: smart-case)",
    ),
    ignore_case: bool = typer.Option(
        False,
        "--ignore-case",
        "-i",
        is_flag=True,
        help="Force case-insensitive matching (default: smart-case)",
    ),
    before: str = typer.Option(
        "",
        "--before",
        "-b",
        help="Only include operations at or before this timestamp (e.g. '2026-01-30', '2026-01-30 15:00')",
    ),
    no_injection_detection: bool = typer.Option(
        False,
        "--no-injection-detection",
        is_flag=True,
        help="Disable detection and removal of injected content in Read operations",
    ),
):
    """Extract recovered files to disk, preserving directory structure."""
    if output_dir is None:
        output_dir = _default_output_dir()

    files = _scan_with_progress(claude_dir)

    # Detect and strip injected content
    if not no_injection_detection:
        from claude_file_recovery.core.injection import (
            detect_injected_content,
            strip_injected_content,
        )

        patterns = detect_injected_content(files)
        if patterns:
            total_ops = sum(p.affected_op_count for p in patterns)
            total_files = sum(p.affected_file_count for p in patterns)
            console.print(
                f"[yellow]Detected injected content in {total_ops} Read operations "
                f"across {total_files} files. Stripping from recovered content.[/yellow]"
            )
            strip_injected_content(files, patterns)

    # Apply symlink deduplication if YAML provided
    if symlink_file and symlink_file.exists():
        from claude_file_recovery.core.symlinks import load_symlink_yaml, merge_file_index

        groups = load_symlink_yaml(symlink_file)
        if groups:
            console.print(
                f"Applying {len(groups)} symlink mappings for deduplication..."
            )
            files = merge_file_index(files, groups)

    # Apply filter
    case_override = True if case_sensitive else (False if ignore_case else None)
    files = filter_files(files, filter_pattern, mode, case_override)

    # Apply timestamp filter
    before_ts = ""
    if before:
        try:
            before_ts = normalize_timestamp(before)
        except ValueError as e:
            console.print(f"[red]Invalid --before timestamp: {e}[/red]")
            raise typer.Exit(code=1)
        console.print(
            f"Filtering operations before {format_local_confirmation(before_ts)}"
        )
        files = filter_by_timestamp(files, before_ts)

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
            if before_ts:
                content = reconstruct_at_timestamp(rf, before_ts)
            else:
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
    if success:
        console.print(f"Output directory: [bold]{output_dir.resolve()}[/bold]")


@app.command("identify-symlinks")
def identify_symlinks(
    claude_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--claude-dir",
        "-c",
        help="Path to Claude Code user config directory",
    ),
    output: Path = typer.Option(
        Path("./symlinks.yaml"),
        "--output",
        "-o",
        help="Output path for the YAML symlink mapping file",
    ),
    no_symlink_detection: bool = typer.Option(
        False,
        "--no-symlink-detection",
        is_flag=True,
        help="Disable filesystem-based symlink detection",
    ),
):
    """Detect symlinked file paths and write a YAML mapping file."""
    from claude_file_recovery.core.symlinks import (
        detect_fs_symlinks,
        save_symlink_yaml,
    )

    files = _scan_with_progress(claude_dir)
    file_paths = list(files.keys())
    console.print(f"Analyzing {len(file_paths)} file paths for symlinks...")

    groups = []

    if not no_symlink_detection:
        console.print("Running filesystem detection...")
        groups = detect_fs_symlinks(file_paths)
        console.print(f"  Found {len(groups)} symlink groups via filesystem")

    if not groups:
        console.print("[yellow]No symlink mappings detected.[/yellow]")
        raise typer.Exit()

    # Display summary table
    table = Table(title=f"Symlink Mappings ({len(groups)} groups)")
    table.add_column("Canonical Path", style="cyan")
    table.add_column("Alias", style="white")
    table.add_column("Method", style="green", justify="center")

    for group in groups:
        first = True
        for alias in group.aliases:
            method = group.detection_methods.get(alias, "?")
            table.add_row(
                group.canonical if first else "",
                alias,
                f"[{method}]",
            )
            first = False

    console.print(table)

    save_symlink_yaml(groups, output)
    console.print(f"\nSymlink mappings written to [bold]{output}[/bold]")


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    version_flag: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        is_eager=True,
        callback=_version_callback,
        is_flag=True,
    ),
    claude_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--claude-dir",
        "-c",
        help="Path to Claude Code user config directory",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for recovered files (default: recovered-{timestamp})",
    ),
    symlink_file: Path = typer.Option(
        None,
        "--symlink-file",
        help="Path to a YAML file with pre-defined symlink mappings",
    ),
    no_symlink_detection: bool = typer.Option(
        False,
        "--no-symlink-detection",
        is_flag=True,
        help="Disable filesystem-based symlink detection",
    ),
    no_injection_detection: bool = typer.Option(
        False,
        "--no-injection-detection",
        is_flag=True,
        help="Disable detection and removal of injected content in Read operations",
    ),
):
    """Default command — launches the interactive TUI."""
    if ctx.invoked_subcommand is None:
        if output_dir is None:
            output_dir = _default_output_dir()
        _launch_tui_impl(
            claude_dir,
            output_dir,
            symlink_file,
            no_symlink_detection,
            no_injection_detection,
        )


@app.command("tui")
def tui_command(
    claude_dir: Path = typer.Option(
        Path.home() / ".claude",
        "--claude-dir",
        "-c",
        help="Path to Claude Code user config directory",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for recovered files (default: recovered-{timestamp})",
    ),
    symlink_file: Path = typer.Option(
        None,
        "--symlink-file",
        help="Path to a YAML file with pre-defined symlink mappings",
    ),
    no_symlink_detection: bool = typer.Option(
        False,
        "--no-symlink-detection",
        is_flag=True,
        help="Disable filesystem-based symlink detection",
    ),
    no_injection_detection: bool = typer.Option(
        False,
        "--no-injection-detection",
        is_flag=True,
        help="Disable detection and removal of injected content in Read operations",
    ),
):
    """Launch the interactive TUI."""
    if output_dir is None:
        output_dir = _default_output_dir()
    _launch_tui_impl(
        claude_dir,
        output_dir,
        symlink_file,
        no_symlink_detection,
        no_injection_detection,
    )


def _launch_tui_impl(
    claude_dir: Path,
    output_dir: Path,
    symlinks_yaml: Path | None = None,
    no_symlink_detection: bool = False,
    no_injection_detection: bool = False,
):
    """Scan sessions and launch the Textual TUI."""
    file_index = _scan_with_progress(claude_dir)
    console.print(f"Found {len(file_index)} recoverable files. Launching TUI...")

    # Detect injected content
    injection_patterns = []
    if not no_injection_detection:
        from claude_file_recovery.core.injection import detect_injected_content

        injection_patterns = detect_injected_content(file_index)
        if injection_patterns:
            total_ops = sum(p.affected_op_count for p in injection_patterns)
            console.print(f"Detected injected content in {total_ops} Read operations")

    # Detect or load symlink mappings
    from claude_file_recovery.core.symlinks import (
        detect_fs_symlinks,
        load_symlink_yaml,
    )

    symlink_groups = []
    symlinks_yaml_path = symlinks_yaml

    if symlinks_yaml and symlinks_yaml.exists():
        console.print(f"Loading symlink mappings from {symlinks_yaml}...")
        symlink_groups = load_symlink_yaml(symlinks_yaml)
        console.print(f"  Loaded {len(symlink_groups)} groups")
    else:
        file_paths = list(file_index.keys())

        if not no_symlink_detection:
            symlink_groups = detect_fs_symlinks(file_paths)

        if symlink_groups:
            console.print(f"Detected {len(symlink_groups)} symlink groups")

    from claude_file_recovery.tui.app import FileRecoveryApp

    tui_app = FileRecoveryApp(
        claude_dir=claude_dir,
        output_dir=output_dir,
        file_index=file_index,
        symlink_groups=symlink_groups if symlink_groups else None,
        symlinks_yaml_path=symlinks_yaml_path,
        injection_patterns=injection_patterns,
    )
    tui_app.run()

    # Print resume command — detect how the CLI was invoked
    import os
    import sys

    parent_cmd = os.environ.get("_", "")
    if "uv" in parent_cmd:
        cmd = "uv run claude-file-recovery"
    elif sys.argv[0].endswith("claude-file-recovery"):
        cmd = "claude-file-recovery"
    else:
        cmd = "python -m claude_file_recovery"
    parts = [cmd]
    parts.append(f"--claude-dir {tui_app.claude_dir}")
    parts.append(f"--output {tui_app.output_dir}")
    if tui_app.symlinks_enabled and tui_app.symlinks_yaml_path:
        parts.append(f"--symlink-file {tui_app.symlinks_yaml_path}")
    elif not tui_app.symlinks_enabled:
        parts.append("--no-symlink-detection")
    console.print(f"\nResume with:\n  {' '.join(parts)}", soft_wrap=True)
