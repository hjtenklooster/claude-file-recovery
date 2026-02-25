from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from claude_recovery.core.models import OpType, RecoverableFile
from claude_recovery.core.reconstructor import reconstruct_file_at
from claude_recovery.core.diff import compute_before_after, format_diff_text, format_full_diff_text, format_read_range_view


class FileDetailScreen(Screen):
    """Split-pane: snapshot timeline (left) + file content preview (right)."""

    BINDINGS = [
        Binding("q", "go_back", "Back", show=True),
        Binding("escape", "go_back", "Back", show=False),
        Binding("enter", "extract_snapshot", "Extract", show=True, priority=True),
        Binding("d", "toggle_diff", "Cycle View", show=True),
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
        self._view_mode: str = "diff"
        self._VIEW_MODES = ("diff", "full-diff", "content")
        self._current_display_index: int = 0

    _MODE_LABELS = {"content": "Recovered File", "diff": "Diff", "full-diff": "Full Diff"}
    _TAB_ID_TO_MODE = {"tab_diff": "diff", "tab_full_diff": "full-diff", "tab_content": "content"}

    def _render_tabs(self) -> list[Static]:
        """Build tab widgets for each view mode."""
        tabs = []
        for mode in self._VIEW_MODES:
            label = self._MODE_LABELS[mode]
            tab = Static(f" {label} ", classes="view-tab view-tab--active" if mode == self._view_mode else "view-tab")
            tab.id = f"tab_{mode.replace('-', '_')}"
            tabs.append(tab)
        return tabs

    def _update_tabs(self) -> None:
        for mode in self._VIEW_MODES:
            tab = self.query_one(f"#tab_{mode.replace('-', '_')}", Static)
            if mode == self._view_mode:
                tab.set_classes("view-tab view-tab--active")
            else:
                tab.set_classes("view-tab")

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail_header"):
            for tab in self._render_tabs():
                yield tab
            yield Static(f" {self.file.path}", id="detail_path")
        yield Static(
            " Each row on the left is a snapshot — a Write, Edit, or Read operation on this file.\n"
            " Use d to cycle views: Diff (changes only), Full Diff (full file with changes marked),\n"
            " and Recovered File (reconstructed content at that point in time).\n"
            " Press Enter to extract the file at the selected snapshot. q to go back.",
            id="detail_explanation",
        )
        with Horizontal(id="detail_panes"):
            with VerticalScroll(id="snapshots_pane"):
                yield OptionList(id="snapshot_list")
            with VerticalScroll(id="preview_pane"):
                yield Static("Select a snapshot to preview", id="file_content")
        yield Static("", id="view_hint")
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

    def _get_view_hint(self, op: "FileOperation", is_read_op: bool, is_partial_read: bool) -> str:
        """Return a one-line description of what the current view is showing."""
        op_label = op.type.value.replace("_", " ").title()
        if self._view_mode == "diff":
            if is_partial_read:
                return f" {op_label}: Showing only the lines that were read, with line numbers"
            elif is_read_op:
                return f" {op_label}: Full file read"
            elif op.type == OpType.EDIT:
                return f" {op_label}: Showing unified diff of the changes made by this edit"
            elif op.type in (OpType.WRITE_CREATE, OpType.WRITE_UPDATE):
                return f" {op_label}: Showing unified diff vs previous state"
            return f" {op_label}: Showing unified diff of changes"
        elif self._view_mode == "full-diff":
            if is_partial_read:
                return f" {op_label}: Full file with read range marked (┃ = read, │ = outside)"
            elif is_read_op:
                return f" {op_label}: Full file read"
            elif op.type == OpType.EDIT:
                return f" {op_label}: Full file with inline diff of the edit changes"
            elif op.type in (OpType.WRITE_CREATE, OpType.WRITE_UPDATE):
                return f" {op_label}: Full file with inline diff vs previous state"
            return f" {op_label}: Full file with inline diff of changes"
        else:
            return f" {op_label}: Full reconstructed file at this snapshot"

    def _update_preview(self, display_index: int) -> None:
        """Reconstruct file at the selected snapshot and show in preview."""
        self._current_display_index = display_index
        # Convert display index (newest-first) to operations index (oldest-first)
        ops_index = len(self.file.operations) - 1 - display_index
        op = self.file.operations[ops_index]
        preview = self.query_one("#file_content", Static)

        # Build provenance header for merged files
        # Character-level wrapping is handled by CSS: text-wrap: nowrap + text-overflow: fold
        provenance = ""
        if op.source_path:
            provenance = (
                f"source:    {op.source_path}\n"
                f"canonical: {self.file.path}\n\n"
            )
        elif any(o.source_path for o in self.file.operations):
            # This file has merged ops but this particular op is from the canonical path
            provenance = f"source:    {self.file.path}\n\n"

        is_read_op = op.type == OpType.READ
        is_partial_read = is_read_op and (
            op.read_offset is not None or op.read_limit is not None
        )

        self.query_one("#view_hint", Static).update(
            self._get_view_hint(op, is_read_op, is_partial_read)
        )

        def _with_provenance(content):
            """Prepend provenance header, handling both str and Rich Text."""
            if not provenance:
                return content
            from rich.text import Text as RichText
            if isinstance(content, RichText):
                result = RichText(provenance)
                result.append(content)
                return result
            return provenance + content

        if self._view_mode in ("diff", "full-diff"):
            if is_read_op:
                content = reconstruct_file_at(self.file.operations, ops_index)
                if content is not None:
                    text = format_read_range_view(
                        content, op.read_offset, op.read_limit,
                        full=(self._view_mode == "full-diff"),
                    )
                    preview.update(_with_provenance(text))
                else:
                    preview.update("[No content available at this snapshot]")
            else:
                before, after = compute_before_after(self.file.operations, ops_index)
                if before is None or after is None:
                    preview.update("[No diff available for this snapshot]")
                elif self._view_mode == "full-diff":
                    text = format_full_diff_text(before, after, self.file.path)
                    preview.update(_with_provenance(text))
                else:
                    text = format_diff_text(before, after, self.file.path)
                    preview.update(_with_provenance(text))
        else:
            content = reconstruct_file_at(self.file.operations, ops_index)
            if content is not None:
                lines = content.split("\n")
                if len(lines) > 500:
                    display = "\n".join(lines[:500]) + f"\n\n... ({len(lines) - 500} more lines)"
                else:
                    display = content
                preview.update(_with_provenance(display))
            else:
                preview.update("[No content available at this snapshot]")

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def _set_view_mode(self, mode: str) -> None:
        """Switch to the given view mode and refresh."""
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._update_tabs()
        self._update_preview(self._current_display_index)

    def on_click(self, event) -> None:
        """Handle clicks on view-mode tabs."""
        widget = event.widget
        if widget and widget.id in self._TAB_ID_TO_MODE:
            self._set_view_mode(self._TAB_ID_TO_MODE[widget.id])

    def action_toggle_diff(self) -> None:
        """Cycle through view modes: Diff → Full Diff → Content → Diff."""
        idx = self._VIEW_MODES.index(self._view_mode)
        self._set_view_mode(self._VIEW_MODES[(idx + 1) % len(self._VIEW_MODES)])

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
        """Open modal to change the output directory."""
        from claude_recovery.tui.output_dir_modal import OutputDirModal
        self.app.push_screen(
            OutputDirModal(self.app.output_dir),
            callback=self._handle_output_dir_result,
        )

    def _handle_output_dir_result(self, result: Path | None) -> None:
        """Apply the new output directory from the modal."""
        if result is not None:
            self.app.output_dir = result
            self.query_one("#output_dir", Static).update(
                f" Output directory: {self.app.output_dir}"
            )

    def action_show_help(self) -> None:
        self.notify(
            "j/k Navigate snapshots  d Cycle view (Content/Diff/Full Diff)\n"
            "Enter Extract snapshot  o Output-dir  q Back",
            title="Keyboard Help",
            timeout=4,
        )
