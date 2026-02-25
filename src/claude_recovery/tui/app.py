from __future__ import annotations

from pathlib import Path

from textual.app import App

from claude_recovery.core.models import InjectedContentPattern, RecoverableFile
from claude_recovery.core.symlinks.models import SymlinkGroup


class FileRecoveryApp(App):
    """Claude File Recovery TUI."""

    CSS_PATH = "styles.css"
    TITLE = "Claude File Recovery"

    def __init__(
        self,
        claude_dir: Path,
        output_dir: Path,
        file_index: dict[str, RecoverableFile],
        symlink_groups: list[SymlinkGroup] | None = None,
        symlinks_yaml_path: Path | None = None,
        injection_patterns: list[InjectedContentPattern] | None = None,
    ):
        super().__init__()
        self.claude_dir = claude_dir
        self.output_dir = output_dir
        self.raw_file_index: dict[str, RecoverableFile] = file_index
        self.merged_file_index: dict[str, RecoverableFile] | None = None
        self.file_index: dict[str, RecoverableFile] = file_index
        self.symlink_groups: list[SymlinkGroup] = symlink_groups or []
        self.symlinks_yaml_path: Path | None = symlinks_yaml_path
        self.symlinks_enabled: bool = False
        self.selected_paths: set[str] = set()
        self.injection_patterns: list[InjectedContentPattern] = injection_patterns or []
        self.injection_stripped: bool = False

    def on_mount(self) -> None:
        from claude_recovery.tui.symlink_review_screen import SymlinkReviewScreen
        self.push_screen(SymlinkReviewScreen())
        from claude_recovery.tui.injection_review_screen import InjectionReviewScreen
        self.push_screen(InjectionReviewScreen())
