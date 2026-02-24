from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from claude_recovery.core.models import RecoverableFile


class FileDetailScreen(Screen):
    """Detail view for a single file — full implementation in Phase 5."""

    BINDINGS = [
        Binding("q", "go_back", "Back", show=True),
        Binding("escape", "go_back", "Back", show=False),
    ]

    def __init__(self, file: RecoverableFile):
        super().__init__()
        self.file = file

    def compose(self) -> ComposeResult:
        yield Static(
            f" {self.file.path}\n\n[Detail view — coming in Phase 5]",
            id="detail_placeholder",
        )
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()
