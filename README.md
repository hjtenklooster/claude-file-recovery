# claude-recovery

[![PyPI version](https://img.shields.io/pypi/v/claude-recovery.svg)](https://pypi.org/project/claude-recovery/)
[![Python versions](https://img.shields.io/pypi/pyversions/claude-recovery.svg)](https://pypi.org/project/claude-recovery/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Recover files created and modified by [Claude Code](https://docs.anthropic.com/en/docs/claude-code) from its JSONL session transcripts — even if you lost track of them across sessions.

Claude Code stores a full log of every tool call in `~/.claude/projects/`. This tool parses those transcripts, replays Write, Edit, and Read operations in order, and reconstructs the files so you can browse, search, and extract them.

![claude-recovery TUI demo](demo/demo.gif)

## Features

- **Interactive TUI** with fuzzy search and vim keybindings (j/k/g/G, `/` to search)
- **Point-in-time recovery** — reconstruct files at any historical snapshot, not just the latest
- **Colored diff view** showing how files changed over time (unified, full-context, and raw modes)
- **Batch extraction** — select multiple files and extract them all at once
- **Fast scanning** — parallel session parsing with orjson and fast-reject byte checks that skip ~77% of lines before parsing
- **Symlink deduplication** — detects aliased paths and merges them into canonical entries
- **Smart-case search** — case-sensitive only when your query contains uppercase (like ripgrep)

## Installation

```bash
# Recommended
uv tool install claude-recovery

# Or with pipx
pipx install claude-recovery

# Or with pip
pip install claude-recovery
```

Requires Python 3.10+.

## Quick Start

```bash
# Launch the interactive TUI (default command)
claude-recovery

# List all recoverable files
claude-recovery list-files

# Filter by pattern
claude-recovery list-files --filter '*.py'

# Export as CSV
claude-recovery list-files --filter '*.ts' --csv

# Extract files to disk
claude-recovery extract-files --output ./recovered --filter '*.py'

# Recover files as they were before a certain time
claude-recovery list-files --before '2025-02-20 14:00'

# Point to a different Claude data directory
claude-recovery --claude-dir /path/to/claude-backup
```

## How It Works

1. **Scan** — Discovers all JSONL session files under `~/.claude/projects/` and parses them in parallel using a thread pool. A fast-reject byte check skips progress and history-snapshot lines (~77% of all lines) before touching the JSON parser.

2. **Correlate** — Links tool-use requests in assistant messages to their results in user messages via `tool_use_id`. This is how file content (which only appears in results, not requests) gets attached to each operation.

3. **Reconstruct** — Replays operations in chronological order per file path. Write ops set content, Edit ops apply string replacements, and Read ops capture snapshots. The `--before` flag uses binary search to cut off at any point in time.

4. **Present** — The TUI lets you browse all recovered files, search with fuzzy matching, view colored diffs between snapshots, and batch-extract to disk.

## TUI Keybindings

| Key | Action |
|-----|--------|
| `j` / `k` | Move up/down |
| `g` / `G` | Jump to top/bottom |
| `/` | Search |
| `Ctrl+R` | Cycle search mode (fuzzy / glob / regex) |
| `x` or `Space` | Toggle file selection |
| `Enter` | View file detail + diffs |
| `d` | Cycle diff mode (unified / full-context / raw) |
| `Ctrl+E` | Extract selected files |
| `q` | Back / quit |

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup instructions.

## License

[MIT](LICENSE) — Rikkert ten Klooster
