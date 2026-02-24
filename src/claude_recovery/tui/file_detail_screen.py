from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from claude_recovery.core.models import RecoverableFile
from claude_recovery.core.reconstructor import reconstruct_file_at


class FileDetailScreen(Screen):
    """Split-pane: snapshot timeline (left) + file content preview (right)."""

    BINDINGS = [
        Binding("q", "go_back", "Back", show=True),
        Binding("escape", "go_back", "Back", show=False),
        Binding("enter", "extract_snapshot", "Extract", show=True, priority=True),
        Binding("o", "change_output", "Output Dir", show=True),
        Binding("question_mark", "show_help", "Help", show=True),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, file: RecoverableFile):
        super().__init__()
        self.file = file
        # Operations in reverse chronological order (newest first) for display
        self._display_ops = list(reversed(file.operations))

    def compose(self) -> ComposeResult:
        yield Static(f" {self.file.path}", id="detail_header")
        with Horizontal(id="detail_panes"):
            with VerticalScroll(id="snapshots_pane"):
                yield OptionList(id="snapshot_list")
            with VerticalScroll(id="preview_pane"):
                yield Static("Select a snapshot to preview", id="file_content")
        yield Static("", id="output_dir")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#output_dir", Static).update(
            f" Output directory: {self.app.output_dir}"
        )
        snapshot_list = self.query_one("#snapshot_list", OptionList)
        for op in self._display_ops:
            ts = op.timestamp[:16].replace("T", " ") if op.timestamp else "unknown"
            op_label = op.type.value.replace("_", " ").title()
            label = f"{ts}  {op_label}"
            snapshot_list.add_option(Option(label))
        if self._display_ops:
            snapshot_list.highlighted = 0
            self._update_preview(0)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Update file preview when a different snapshot is highlighted."""
        if event.option_index is not None:
            self._update_preview(event.option_index)

    def _update_preview(self, display_index: int) -> None:
        """Reconstruct file at the selected snapshot and show in preview."""
        # Convert display index (newest-first) to operations index (oldest-first)
        ops_index = len(self.file.operations) - 1 - display_index
        content = reconstruct_file_at(self.file.operations, ops_index)
        preview = self.query_one("#file_content", Static)
        if content is not None:
            # Truncate very long files for display (show first 500 lines)
            lines = content.split("\n")
            if len(lines) > 500:
                display = "\n".join(lines[:500]) + f"\n\n... ({len(lines) - 500} more lines)"
            else:
                display = content
            preview.update(display)
        else:
            preview.update("[No content available at this snapshot]")

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_extract_snapshot(self) -> None:
        """Extract file at the currently highlighted snapshot."""
        snapshot_list = self.query_one("#snapshot_list", OptionList)
        idx = snapshot_list.highlighted
        if idx is None:
            return
        ops_index = len(self.file.operations) - 1 - idx
        content = reconstruct_file_at(self.file.operations, ops_index)
        if content is None:
            self.notify("No content at this snapshot", severity="warning")
            return

        app = self.app
        rel = self.file.path.lstrip("/")
        out = app.output_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        self.notify(f"Extracted to {out}")

    def action_cursor_down(self) -> None:
        self.query_one("#snapshot_list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#snapshot_list", OptionList).action_cursor_up()

    def action_change_output(self) -> None:
        """Prompt for a new output directory via notification."""
        app = self.app
        self.notify(
            f"Current output: {app.output_dir}\n"
            "Use --output flag to change at startup.",
            title="Output Directory",
            timeout=4,
        )

    def action_show_help(self) -> None:
        self.notify(
            "j/k Navigate snapshots  Enter Extract snapshot\n"
            "o Output-dir  q Back",
            title="Keyboard Help",
            timeout=4,
        )
