from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.fuzzy import Matcher
from textual.screen import Screen
from textual.widgets import Footer, Input, SelectionList, Static
from textual.widgets.selection_list import Selection

from claude_recovery.core.models import RecoverableFile
from claude_recovery.core.reconstructor import reconstruct_latest


class FileSelectionList(SelectionList):
    """SelectionList that doesn't toggle on enter — reserves it for detail view."""

    def action_select(self) -> None:
        """Override enter to do nothing; toggle is handled by x key."""
        pass


class FileListScreen(Screen):
    """Full-width file list with fuzzy search, multi-select, vim navigation."""

    BINDINGS = [
        Binding("slash", "search", "Search", show=True),
        Binding("x", "toggle_select", "Select", show=True),
        Binding("space", "selection_mode", "Range Select", show=True),
        Binding("ctrl+a", "select_all_filtered", "Select All", show=True),
        Binding("ctrl+x", "deselect_all_filtered", "Deselect All", show=False),
        Binding("ctrl+e", "extract", "Extract", show=True),
        Binding("enter", "open_detail", "Detail", show=True, priority=True),
        Binding("o", "change_output", "Output Dir", show=True),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),  # Shift+G
    ]

    def __init__(self):
        super().__init__()
        self._selection_mode = False
        self._search_query = ""
        self._all_files: list[RecoverableFile] = []
        self._filtered_paths: list[str] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Press / to search...", id="filter")
        yield FileSelectionList(id="file_list")
        yield Static("", id="output_dir")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app  # type: FileRecoveryApp
        self._all_files = sorted(
            app.file_index.values(),
            key=lambda f: f.latest_timestamp,
            reverse=True,
        )
        self._repopulate_list()
        # Start with list focused, not input
        self.query_one("#file_list").focus()

    def _repopulate_list(self) -> None:
        """Repopulate the selection list based on current search query."""
        file_list = self.query_one("#file_list", SelectionList)
        file_list.clear_options()

        app = self.app  # type: FileRecoveryApp
        self._filtered_paths = []

        if self._search_query:
            matcher = Matcher(self._search_query)
            scored = []
            for rf in self._all_files:
                score = matcher.match(rf.path)
                if score > 0:
                    scored.append((score, rf))
            scored.sort(key=lambda x: x[0], reverse=True)
            items = [rf for _, rf in scored]
        else:
            items = self._all_files

        for rf in items:
            ts = rf.latest_timestamp[:10] if rf.latest_timestamp else "unknown"
            label = f"{ts}  {rf.path}  ({rf.operation_count} ops)"
            is_selected = rf.path in app.selected_paths
            file_list.add_option(Selection(label, rf.path, is_selected))
            self._filtered_paths.append(rf.path)

        self._update_status()

    def _update_status(self) -> None:
        app = self.app  # type: FileRecoveryApp
        selected = len(app.selected_paths)
        filtered = len(self._filtered_paths)
        total = len(self._all_files)
        mode = " [SELECTION MODE]" if self._selection_mode else ""
        self.query_one("#output_dir", Static).update(
            f" Output directory: {app.output_dir}"
        )
        self.query_one("#status", Static).update(
            f" {selected} selected | {filtered} shown | {total} total{mode}"
        )

    def on_selection_list_selected_changed(self, event) -> None:
        """Track selection state in app.selected_paths."""
        app = self.app
        file_list = self.query_one("#file_list", SelectionList)
        app.selected_paths = set(file_list.selected)
        self._update_status()

    def on_input_changed(self, event: Input.Changed) -> None:
        """React to search input changes — fuzzy filter the list."""
        self._search_query = event.value
        self._repopulate_list()

    def on_key(self, event) -> None:
        """Handle Escape key to return focus from search input to file list."""
        if event.key == "escape":
            filter_input = self.query_one("#filter", Input)
            if filter_input.has_focus:
                self.query_one("#file_list", SelectionList).focus()
                event.stop()

    def action_search(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_toggle_select(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        idx = file_list.highlighted
        if idx is not None:
            file_list.toggle(file_list.get_option_at_index(idx))

    def action_selection_mode(self) -> None:
        """Toggle selection mode — movement keys will auto-toggle items."""
        self._selection_mode = not self._selection_mode
        self._update_status()

    def action_select_all_filtered(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        for i in range(file_list.option_count):
            file_list.select(file_list.get_option_at_index(i))

    def action_deselect_all_filtered(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        for i in range(file_list.option_count):
            file_list.deselect(file_list.get_option_at_index(i))

    def action_extract(self) -> None:
        app = self.app
        if not app.selected_paths:
            self.notify("No files selected", severity="warning")
            return
        success = 0
        for path in app.selected_paths:
            rf = app.file_index.get(path)
            if not rf:
                continue
            content = reconstruct_latest(rf)
            if content is None:
                continue
            rel = path.lstrip("/")
            out = app.output_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
            success += 1
        self.notify(f"Extracted {success} files to {app.output_dir}")

    def action_open_detail(self) -> None:
        """Open the detail view for the highlighted file."""
        file_list = self.query_one("#file_list", SelectionList)
        idx = file_list.highlighted
        if idx is None:
            return
        # Get the file path from the selection value
        path = self._filtered_paths[idx]
        rf = self.app.file_index.get(path)
        if rf:
            from claude_recovery.tui.file_detail_screen import FileDetailScreen
            self.app.push_screen(FileDetailScreen(rf))

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
            "/ Search  x Select  Space Selection-mode  Ctrl+A Select-all\n"
            "Ctrl+E Extract  Enter Detail  o Output-dir  q Quit\n"
            "j/k Up/Down  g/G Top/Bottom",
            title="Keyboard Help",
            timeout=6,
        )

    def action_cursor_down(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        file_list.action_cursor_down()
        if self._selection_mode:
            idx = file_list.highlighted
            if idx is not None:
                file_list.toggle(file_list.get_option_at_index(idx))

    def action_cursor_up(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        file_list.action_cursor_up()
        if self._selection_mode:
            idx = file_list.highlighted
            if idx is not None:
                file_list.toggle(file_list.get_option_at_index(idx))

    def action_go_top(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        if file_list.option_count > 0:
            file_list.highlighted = 0
            file_list.scroll_home()

    def action_go_bottom(self) -> None:
        file_list = self.query_one("#file_list", SelectionList)
        last = file_list.option_count - 1
        if last >= 0:
            file_list.highlighted = last
            file_list.scroll_end()

    def action_quit_app(self) -> None:
        self.app.exit()
