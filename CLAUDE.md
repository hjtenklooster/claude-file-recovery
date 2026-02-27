# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

claude-file-recovery is a CLI/TUI tool that recovers files created and modified by Claude Code from its JSONL session transcripts (`~/.claude/projects/`). It parses Write, Edit, and Read tool-use entries, reconstructs file contents by replaying operations in order, and lets users browse/extract them.

## Commands

```bash
# Install in development mode (uses uv + hatch)
uv pip install -e .

# Run the TUI (default command)
claude-file-recovery
claude-file-recovery --claude-dir ./claude-backup

# List recoverable files
claude-file-recovery list-files
claude-file-recovery list-files --filter '*.ts' --csv

# Extract files to disk
claude-file-recovery extract-files --output ./recovered --filter '*.py'
```

There are no tests yet. No linter or formatter is configured.

## Architecture

**Entry point:** `src/claude_file_recovery/cli.py` — Typer app with three commands: `list-files`, `extract-files`, and `tui` (also the default when invoked without a subcommand).

**Core pipeline** (`src/claude_file_recovery/core/`):
- `scanner.py` — Discovers JSONL files under `projects/<slug>/`, parses them line-by-line with `orjson`, and extracts `FileOperation` objects from `assistant` entries (Write/Edit/Read tool_use blocks) and `user` entries (toolUseResult enrichment). Uses `ThreadPoolExecutor` to scan sessions in parallel. The two-pass correlation works via `tool_use_id`: tool_use blocks in assistant messages create pending ops, then toolUseResult in user messages enriches them with actual content and originalFile.
- `reconstructor.py` — Replays a `RecoverableFile`'s operations in chronological order to rebuild content. Write/Read ops set content directly; Edit ops apply string replacements. The `originalFile` field on Edit ops serves as a fallback base when no prior Write/Read exists.
- `models.py` — `OpType` enum (WRITE_CREATE, WRITE_UPDATE, EDIT, READ, FILE_HISTORY), `FileOperation` dataclass (content fields populated during scanning), `RecoverableFile` dataclass (groups ops by absolute file path, provides `has_full_content` and `latest_timestamp` properties).

**TUI** (`src/claude_file_recovery/tui/`): Textual app with two screens.
- `FileListScreen` — Fuzzy-searchable `SelectionList` with vim keybindings (j/k/g/G), multi-select via `x`/space, batch extract via Ctrl+E.
- `FileDetailScreen` — Placeholder (Phase 5 stub), shows file path only.
- `styles.css` — Textual CSS for layout.

**Data flow:** CLI scans `~/.claude` → builds `dict[str, RecoverableFile]` → passes to TUI or directly to extract/list logic.

## Key Design Decisions

- Operations are ordered by `(timestamp, session_id, line_number)` — timestamp for cross-session ordering, line_number for intra-session ordering.
- Read tool output has line-number prefixes (`  1→content`) that are stripped via regex in `strip_read_line_numbers()`.
- The scanner uses fast-reject byte checks (`b'"type":"progress"'`) before JSON parsing to skip ~77% of JSONL lines.
- `claude-backup/` in the repo root is a copy of `~/.claude` used during development — it is gitignored.
