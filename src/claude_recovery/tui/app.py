from __future__ import annotations

from pathlib import Path

from textual.app import App

from claude_recovery.core.models import RecoverableFile


class FileRecoveryApp(App):
    """Claude File Recovery TUI."""

    CSS_PATH = "styles.css"
    TITLE = "Claude File Recovery"

    def __init__(
        self,
        claude_dir: Path,
        output_dir: Path,
        file_index: dict[str, RecoverableFile],
    ):
        super().__init__()
        self.claude_dir = claude_dir
        self.output_dir = output_dir
        self.file_index = file_index
        self.selected_paths: set[str] = set()

    def on_mount(self) -> None:
        from claude_recovery.tui.file_list_screen import FileListScreen
        self.push_screen(FileListScreen())
