# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-02-25

### Fixed
- Removed broken CONTRIBUTING.md link from PyPI README

## [0.1.1] - 2026-02-25

### Fixed
- Demo GIF now renders on PyPI (use absolute URL instead of relative path)
- Removed broken CONTRIBUTING.md link from README
- Lint fixes across all source files

## [0.1.0] - 2026-02-25

### Added
- CLI commands: `list-files`, `extract-files`, and `tui` (default when invoked without subcommand)
- Interactive TUI with fuzzy search, vim keybindings (j/k/g/G), and multi-select
- JSONL session transcript parsing with parallel scanning via ThreadPoolExecutor
- Fast-reject byte checks that skip ~77% of JSONL lines before JSON parsing
- File reconstruction by replaying Write, Edit, and Read operations in chronological order
- Two-pass `tool_use_id` correlation linking tool-use requests to their results
- Point-in-time recovery with `--before`/`-b` timestamp filter
- Colored unified diff view with three modes: unified, full-context, and raw content
- Search mode cycling (fuzzy / glob / regex) with Ctrl+R
- Smart-case search (case-sensitive only when query contains uppercase)
- Symlink deduplication with filesystem detection and TUI review screen
- Batch file extraction with Ctrl+E and output directory modal with path autocompletion
- Noop edit elimination via two-stage filtering (field-level fast check + replay simulation)
- `--filter` flag with fuzzy, glob, and regex matching for `list-files` and `extract-files`
- `--csv` output format for `list-files`
- Injected content detection and removal — threshold-based trailing-suffix detection strips `<system-reminder>` tags injected by Claude Code into Read operations
- TUI injection review screen with confirm/skip before file browsing
- `--no-injection-detection` flag to disable injected content filtering

[Unreleased]: https://github.com/hjtenklooster/claude-recovery/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/hjtenklooster/claude-recovery/releases/tag/v0.1.2
[0.1.1]: https://github.com/hjtenklooster/claude-recovery/releases/tag/v0.1.1
[0.1.0]: https://github.com/hjtenklooster/claude-recovery/releases/tag/v0.1.0
