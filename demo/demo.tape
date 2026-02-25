# VHS tape for recording a demo of the claude-recovery TUI
# https://github.com/charmbracelet/vhs
#
# Usage:
#   cd /path/to/claude-recovery
#   python demo/generate_demo_data.py   # generate demo data first
#   vhs demo/demo.tape                  # record the GIF
#
# Requirements: vhs, claude-recovery installed (uv tool install -e .)

Output demo/demo.gif

Set FontSize 21
Set Width 1800
Set Height 1050
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Shell zsh

# Launch the TUI with demo data
Type "claude-recovery --claude-dir demo/demo-claude-data"
Enter
Sleep 3s

# === Injection review screen — let viewer read it, then strip ===
Sleep 3s
Enter
Sleep 1s

# === Symlink review screen — let viewer read it ===
Sleep 3s
Type "S"
Sleep 2s

# === File list is now visible ===
# Search for app.py right away
Type "/"
Sleep 500ms
Type "app.py"
Sleep 2s

# Move focus to file list and highlight first item
Tab
Sleep 500ms
Type "j"
Sleep 500ms

# === Open app.py (3 ops) ===
Enter
Sleep 3s

# Viewing latest snapshot (Write Update) — browse snapshots
# j to Edit operation
Type "j"
Sleep 2s

# j to initial Write Create
Type "j"
Sleep 2s

# Back to latest
Type "k"
Sleep 400ms
Type "k"
Sleep 1s

# Cycle diff mode
Type "d"
Sleep 2s

# Cycle again
Type "d"
Sleep 2s

# === Back to file list ===
Type "q"
Sleep 1s

# Select files with x for batch extract
# Cursor is on app.py — select it
Type "x"
Sleep 400ms
# Move to auth.py and select
Type "j"
Sleep 300ms
Type "x"
Sleep 400ms
# Move to config.py and select
Type "j"
Sleep 300ms
Type "x"
Sleep 1s

# Batch extract with Ctrl+E
Ctrl+E
Sleep 3s

# Exit the app
Type "q"
Sleep 5s
