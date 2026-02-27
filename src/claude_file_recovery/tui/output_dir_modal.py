from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets import Input, Static


class PathSuggester(Suggester):
    """Inline ghost-text completion for filesystem directory paths."""

    def __init__(self):
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        return await asyncio.to_thread(self._suggest_sync, value)

    def _suggest_sync(self, value: str) -> str | None:
        if not value:
            return None
        tilde_prefix = value.startswith("~/") or value == "~"
        try:
            path = Path(value).expanduser()
        except RuntimeError:
            return None
        parent = path.parent if not path.is_dir() else path
        prefix = path.name if not path.is_dir() else ""
        try:
            for child in sorted(parent.iterdir()):
                if child.is_dir() and child.name.startswith(prefix):
                    result = str(child) + "/"
                    if tilde_prefix:
                        home = str(Path.home())
                        if result.startswith(home):
                            result = "~" + result[len(home) :]
                    return result
        except OSError:
            pass
        return None


class OutputDirModal(ModalScreen[Path | None]):
    """Modal dialog to change the output directory at runtime."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("tab", "accept_suggestion", "Accept suggestion", show=False),
    ]

    def __init__(self, current_path: Path):
        super().__init__()
        self.current_path = current_path

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_container"):
            yield Static("Change Output Directory", id="modal_title")
            yield Static(f"Current: {self.current_path}", id="modal_current")
            yield Input(
                value=str(self.current_path),
                placeholder="Enter directory path...",
                id="modal_input",
                suggester=PathSuggester(),
            )
            yield Static(
                "Enter to confirm · Escape to cancel · Tab/→ to accept suggestion",
                id="modal_hint",
            )

    def on_mount(self) -> None:
        inp = self.query_one("#modal_input", Input)
        inp.focus()
        inp.action_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            self.dismiss(None)
            return
        self.dismiss(Path(value).expanduser())

    def action_accept_suggestion(self) -> None:
        self.query_one("#modal_input", Input).action_cursor_right()

    def action_cancel(self) -> None:
        self.dismiss(None)
