from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from claude_recovery.core.filters import (
    SearchMode,
    match_path,
    validate_regex,
    smart_case_sensitive,
)
from claude_recovery.core.timestamps import utc_to_local
from claude_recovery.core.models import RecoverableFile
from claude_recovery.core.reconstructor import reconstruct_latest


class FileSelectionList(SelectionList):
    """SelectionList that doesn't toggle on enter — reserves it for detail view."""

    BINDINGS = [
        Binding("space", "screen_selection_mode", "Range Select", show=True),
    ]

    class DoubleClicked(Message):
        """Posted when the list is double-clicked."""

    def action_select(self) -> None:
        """Override enter to do nothing; toggle is handled by x key."""
        pass

    def action_screen_selection_mode(self) -> None:
        """Forward space to the screen's selection mode action."""
        self.screen.action_selection_mode()

    def on_click(self, event) -> None:
        if event.chain >= 2:
            self.post_message(self.DoubleClicked())


class FileListScreen(Screen):
    """Full-width file list with fuzzy search, multi-select, vim navigation."""

    search_mode: reactive[SearchMode] = reactive(SearchMode.FUZZY)

    BINDINGS = [
        Binding("slash", "search", "Search", show=True),
        Binding("x", "toggle_select", "Select", show=True),
        Binding("space", "selection_mode", "Range Select", show=True),
        Binding("ctrl+a", "select_all_filtered", "Select All", show=True),
        Binding("ctrl+x", "deselect_all_filtered", "Deselect All", show=False),
        Binding("ctrl+e", "extract", "Extract", show=True),
        Binding("ctrl+r", "cycle_mode", "Mode", show=True),
        Binding("enter", "open_detail", "Detail", show=True, priority=True),
        Binding("s", "open_symlinks", "Symlinks", show=True),
        Binding("S", "toggle_symlinks", "Toggle Symlinks", show=False),
        Binding("o", "change_output", "Output Dir", show=True),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),  # Shift+G
    ]

    DEBOUNCE_DELAY = 0.3  # seconds

    def __init__(self):
        super().__init__()
        self._selection_mode = False
        self._search_query = ""
        self._all_files: list[RecoverableFile] = []
        self._filtered_paths: list[str] = []
        self._debounce_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="search_bar"):
            yield Label("\\[FUZZY]", id="mode_label")
            yield Input(placeholder="Press / to search...", id="filter")
        yield Static(
            " Select files with x (or Space for range select), then Ctrl+E to extract the\n"
            " latest reconstructed state. Press Enter or double-click to open a file's\n"
            " history — browse snapshots, view diffs, and extract at a specific point in time.\n"
            "\n"
            " / to search, Ctrl+R to cycle mode (fuzzy/glob/regex). s for symlink settings.\n"
            " o to change output directory. j/k navigate, g/G top/bottom, ? for full help.",
            id="file_explanation",
        )
        yield FileSelectionList(id="file_list")
        yield Static("", id="output_dir")
        with Horizontal(id="status_bar"):
            yield Static("", id="status")
            yield Static("", id="symlink_text")
            yield Label("S", id="symlink_key")
            yield Static("", id="symlink_action")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app  # type: FileRecoveryApp
        self._all_files = sorted(
            app.file_index.values(),
            key=lambda f: f.path,
        )
        self._repopulate_list()
        self.query_one("#filter", Input).focus()

    def _repopulate_list(self) -> None:
        """Repopulate the selection list based on current search query."""
        file_list = self.query_one("#file_list", SelectionList)
        file_list.clear_options()

        app = self.app  # type: FileRecoveryApp
        self._filtered_paths = []

        if self._search_query:
            case_sensitive = smart_case_sensitive(self._search_query)
            mode = self.search_mode

            # Handle invalid regex gracefully
            if mode is SearchMode.REGEX:
                error = validate_regex(self._search_query)
                mode_label = self.query_one("#mode_label", Label)
                if error:
                    mode_label.add_class("error")
                    items = self._all_files  # show all files on invalid regex
                else:
                    mode_label.remove_class("error")
                    items = [
                        rf
                        for rf in self._all_files
                        if match_path(rf.path, self._search_query, mode, case_sensitive)
                        > 0
                    ]
            elif mode is SearchMode.FUZZY:
                scored = []
                for rf in self._all_files:
                    score = match_path(
                        rf.path, self._search_query, mode, case_sensitive
                    )
                    if score > 0:
                        scored.append((score, rf))
                scored.sort(key=lambda x: x[0], reverse=True)
                items = [rf for _, rf in scored]
            else:
                # GLOB mode — binary match, keep original order
                items = [
                    rf
                    for rf in self._all_files
                    if match_path(rf.path, self._search_query, mode, case_sensitive) > 0
                ]
        else:
            # Clear any error state when query is empty
            self.query_one("#mode_label", Label).remove_class("error")
            items = self._all_files

        for rf in items:
            ts = (
                utc_to_local(rf.latest_timestamp, "%Y-%m-%d")
                if rf.latest_timestamp
                else "unknown"
            )
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
        if app.symlinks_enabled and app.merged_file_index:
            groups = len([g for g in app.symlink_groups if g.aliases])
            symlink_text = f"symlink detection: enabled ({groups} groups) "
            action_text = " to disable"
        else:
            symlink_text = "symlink detection: disabled "
            action_text = " to enable"
        self.query_one("#output_dir", Static).update(
            f" Output directory: {app.output_dir}"
        )
        self.query_one("#status", Static).update(
            f" {selected} selected | {filtered} shown | {total} total{mode}"
        )
        self.query_one("#symlink_text", Static).update(f" | {symlink_text}")
        self.query_one("#symlink_action", Static).update(action_text)

    def on_selection_list_selected_changed(self, event) -> None:
        """Track selection state in app.selected_paths."""
        app = self.app
        file_list = self.query_one("#file_list", SelectionList)
        app.selected_paths = set(file_list.selected)
        self._update_status()

    def on_input_changed(self, event: Input.Changed) -> None:
        """React to search input changes — debounce then filter."""
        self._search_query = event.value
        self.query_one("#file_list").add_class("stale")
        if self._debounce_timer:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(self.DEBOUNCE_DELAY, self._apply_filter)

    def _apply_filter(self) -> None:
        """Called after debounce delay — run the actual filter."""
        self._repopulate_list()
        self.query_one("#file_list").remove_class("stale")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Switch focus to file list when Enter is pressed in search input."""
        self.query_one("#file_list", SelectionList).focus()

    def on_key(self, event) -> None:
        """Handle Escape key to return focus from search input to file list."""
        if event.key == "escape":
            filter_input = self.query_one("#filter", Input)
            if filter_input.has_focus:
                self.query_one("#file_list", SelectionList).focus()
                event.stop()

    def action_search(self) -> None:
        self.query_one("#filter", Input).focus()

    _MODE_ORDER = [SearchMode.FUZZY, SearchMode.GLOB, SearchMode.REGEX]

    def action_cycle_mode(self) -> None:
        """Cycle search mode: FUZZY → GLOB → REGEX → FUZZY."""
        idx = self._MODE_ORDER.index(self.search_mode)
        self.search_mode = self._MODE_ORDER[(idx + 1) % len(self._MODE_ORDER)]

    def watch_search_mode(self, mode: SearchMode) -> None:
        """React to search mode changes — update label and re-filter."""
        mode_label = self.query_one("#mode_label", Label)
        mode_label.update(f"\\[{mode.value.upper()}]")
        mode_label.remove_class("error")
        self._repopulate_list()

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
        # Warn if injected content was not stripped
        if app.injection_patterns and not app.injection_stripped:
            self.notify(
                "Warning: injected content was NOT stripped (you chose to skip). "
                "Extracted files may contain injected tags.",
                severity="warning",
                timeout=6,
            )
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

    def on_file_selection_list_double_clicked(self) -> None:
        self.action_open_detail()

    def action_open_detail(self) -> None:
        """Open the detail view for the highlighted file, or switch focus from search."""
        if self.query_one("#filter", Input).has_focus:
            self.query_one("#file_list", SelectionList).focus()
            return
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

    def action_toggle_symlinks(self) -> None:
        """Toggle symlink deduplication on/off."""
        app = self.app  # type: FileRecoveryApp

        if app.symlinks_enabled:
            # Turning off — always possible
            app.symlinks_enabled = False
            app.file_index = app.raw_file_index
            self.notify("Symlink deduplication disabled")
            self._all_files = sorted(
                app.file_index.values(),
                key=lambda f: f.latest_timestamp,
                reverse=True,
            )
            self._repopulate_list()
            return

        # Turning on — use existing merged index if available
        if app.merged_file_index:
            app.symlinks_enabled = True
            app.file_index = app.merged_file_index
            self.notify("Symlink deduplication enabled")
            self._all_files = sorted(
                app.file_index.values(),
                key=lambda f: f.latest_timestamp,
                reverse=True,
            )
            self._repopulate_list()
            return

        # No merged index yet — run detection and open the review screen
        from claude_recovery.core.symlinks import detect_fs_symlinks

        file_paths = list(app.raw_file_index.keys())
        groups = detect_fs_symlinks(file_paths)
        app.symlink_groups = groups or []
        from claude_recovery.tui.symlink_review_screen import SymlinkReviewScreen

        self.app.push_screen(SymlinkReviewScreen())

    def action_open_symlinks(self) -> None:
        """Open the symlink review screen."""
        from claude_recovery.tui.symlink_review_screen import SymlinkReviewScreen

        self.app.push_screen(SymlinkReviewScreen())

    def on_screen_resume(self) -> None:
        """Refresh file list when returning from another screen (e.g., after re-merge)."""
        app = self.app  # type: FileRecoveryApp
        self._all_files = sorted(
            app.file_index.values(),
            key=lambda f: f.path,
        )
        self._repopulate_list()

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
            self._update_status()

    def action_show_help(self) -> None:
        self.notify(
            "/ Search  Ctrl+R Mode  x Select  Space Selection-mode  Ctrl+A Select-all\n"
            "Ctrl+E Extract  Enter Detail  s Symlinks  S Toggle-symlinks\n"
            "o Output-dir  j/k Up/Down  g/G Top/Bottom  q Quit",
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
