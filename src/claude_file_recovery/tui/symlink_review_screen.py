from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from pathlib import Path

from claude_file_recovery.core.symlinks.models import save_symlink_yaml
from claude_file_recovery.core.symlinks.merge import merge_file_index


class SymlinkReviewScreen(Screen):
    """Review detected symlink mappings before applying them to the file index."""

    BINDINGS = [
        Binding("d", "delete_alias", "Delete", show=True),
        Binding("delete", "delete_alias", "Delete", show=False),
        Binding("enter", "confirm", "Confirm", show=True, priority=True),
        Binding("c", "confirm", "Confirm", show=False),
        Binding("e", "generate_example", "Example YAML", show=True),
        Binding("S", "skip_symlinks", "Disable Detection", show=True),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
    ]

    def __init__(self):
        super().__init__()
        # Flat list mapping: each entry is either ("canonical", group_idx, None)
        # or ("alias", group_idx, alias_idx) or ("separator", group_idx, None)
        self._entries: list[tuple[str, int, int | None]] = []
        self._dirty = False  # True if user made changes (e.g. deleted an alias)

    def compose(self) -> ComposeResult:
        yield Static(" Symlink Detection", id="symlink_header")
        yield Static("", id="symlink_explanation")
        yield OptionList(id="symlink_list")
        yield Static("", id="symlink_status")
        yield Footer()

    def _yaml_path(self) -> Path:
        app = self.app  # type: FileRecoveryApp
        return app.symlinks_yaml_path or (app.output_dir / "symlinks.yaml")

    def on_mount(self) -> None:
        app = self.app  # type: FileRecoveryApp
        yaml_path = self._yaml_path()
        has_groups = any(g.aliases for g in app.symlink_groups)

        if has_groups:
            self.query_one("#symlink_explanation", Static).update(
                " These paths were detected as filesystem symlinks resolving to the same file.\n"
                " When enabled, edits made through different symlinked paths are merged into a\n"
                " single file for more complete recovery.\n"
                "\n"
                " Review the mappings below. Use d to remove incorrect entries, Enter to confirm.\n"
                f" On confirm, mappings are saved to {yaml_path} (editable by hand).\n"
                f" Reuse next time with: claude-file-recovery --symlink-file {yaml_path}\n"
                " Press S to disable symlink detection and skip."
            )
        else:
            self.query_one("#symlink_explanation", Static).update(
                " No filesystem symlinks were detected among the recovered file paths.\n"
                "\n"
                " If you know that some paths are equivalent (e.g. a worktree, a bind mount,\n"
                " or a renamed directory), you can define symlink mappings manually in a YAML file.\n"
                " This merges edits made through different paths into a single file.\n"
                "\n"
                f" Press e to generate an example YAML file at {yaml_path}\n"
                f" Then edit it and reuse with: claude-file-recovery --symlink-file {yaml_path}\n"
                " Press S to go back to the file list."
            )
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Rebuild the option list from current symlink_groups."""
        option_list = self.query_one("#symlink_list", OptionList)
        option_list.clear_options()
        self._entries.clear()

        app = self.app  # type: FileRecoveryApp
        groups = app.symlink_groups

        for gi, group in enumerate(groups):
            if not group.aliases:
                continue
            # Canonical header
            option_list.add_option(Option(f"{group.canonical}  [canonical]"))
            self._entries.append(("canonical", gi, None))

            for ai, alias in enumerate(group.aliases):
                option_list.add_option(Option(f"    {alias}"))
                self._entries.append(("alias", gi, ai))

            option_list.add_option(None)
            self._entries.append(("separator", gi, None))

        total_aliases = sum(len(g.aliases) for g in groups)
        total_groups = sum(1 for g in groups if g.aliases)
        self.query_one("#symlink_status", Static).update(
            f" {total_groups} groups, {total_aliases} aliases — "
            f"d: delete alias | Enter: confirm & continue"
        )

    def action_delete_alias(self) -> None:
        """Delete the highlighted alias entry."""
        option_list = self.query_one("#symlink_list", OptionList)
        idx = option_list.highlighted
        if idx is None or idx >= len(self._entries):
            return

        entry_type, group_idx, alias_idx = self._entries[idx]
        if entry_type != "alias":
            self.notify(
                "Can only delete alias entries (indented lines)", severity="warning"
            )
            return

        app = self.app  # type: FileRecoveryApp
        group = app.symlink_groups[group_idx]
        alias = group.aliases[alias_idx]

        # Remove from detection_methods and aliases
        group.detection_methods.pop(alias, None)
        group.aliases.pop(alias_idx)

        self._dirty = True
        self._rebuild_list()
        self.notify(f"Removed: {alias}")

    def action_generate_example(self) -> None:
        """Generate an example YAML symlink mapping file."""
        yaml_path = self._yaml_path()

        example = (
            "# Symlink mappings for claude-file-recovery\n"
            "# Each key is the canonical (real) path.\n"
            "# Values are alias paths whose edits should be merged into the canonical.\n"
            "#\n"
            "# Example:\n"
            "# /Users/you/src/project:\n"
            "#   - /Users/you/worktrees/feature/src/project\n"
            "#   - /tmp/project\n"
            "#\n"
            "# Reuse with: claude-file-recovery --symlink-file {path}\n".format(
                path=yaml_path
            )
        )

        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(example, encoding="utf-8")
        self.notify(f"Example YAML written to {yaml_path}")

    def action_skip_symlinks(self) -> None:
        """Skip symlink merging — proceed with raw file index."""
        app = self.app  # type: FileRecoveryApp
        app.symlinks_enabled = False
        app.file_index = app.raw_file_index

        self.notify("Symlink deduplication disabled")

        screen_stack = self.app.screen_stack
        if len(screen_stack) >= 2:
            from claude_file_recovery.tui.file_list_screen import FileListScreen

            if isinstance(screen_stack[-2], FileListScreen):
                self.app.pop_screen()
                return
        from claude_file_recovery.tui.file_list_screen import FileListScreen

        self.app.push_screen(FileListScreen())

    def action_confirm(self) -> None:
        """Confirm mappings, save YAML, merge file_index, push FileListScreen."""
        app = self.app  # type: FileRecoveryApp

        # Filter out empty groups
        active_groups = [g for g in app.symlink_groups if g.aliases]

        # Save YAML (only if file is new or user made changes)
        yaml_path = app.symlinks_yaml_path or (app.output_dir / "symlinks.yaml")
        is_new_file = not yaml_path.exists()
        if is_new_file or self._dirty:
            save_symlink_yaml(active_groups, yaml_path)
            self.notify(f"Saved {len(active_groups)} symlink groups to {yaml_path}")
        app.symlinks_yaml_path = yaml_path

        # Merge file_index and store for toggle
        merged = merge_file_index(app.raw_file_index, active_groups)
        app.merged_file_index = merged
        app.file_index = merged
        app.symlinks_enabled = True
        app.symlink_groups = active_groups

        # If we were pushed on top of FileListScreen, pop back to it
        # Otherwise (initial mount), push a new FileListScreen
        screen_stack = self.app.screen_stack
        if len(screen_stack) >= 2:
            from claude_file_recovery.tui.file_list_screen import FileListScreen

            if isinstance(screen_stack[-2], FileListScreen):
                self.app.pop_screen()
                return
        from claude_file_recovery.tui.file_list_screen import FileListScreen

        self.app.push_screen(FileListScreen())

    def action_show_help(self) -> None:
        self.notify(
            "d Delete alias  Enter Confirm & continue  e Example YAML\n"
            "S Disable detection  j/k Up/Down  g/G Top/Bottom  q Quit",
            title="Keyboard Help",
            timeout=5,
        )

    def action_cursor_down(self) -> None:
        self.query_one("#symlink_list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#symlink_list", OptionList).action_cursor_up()

    def action_go_top(self) -> None:
        ol = self.query_one("#symlink_list", OptionList)
        if ol.option_count > 0:
            ol.highlighted = 0
            ol.scroll_home()

    def action_go_bottom(self) -> None:
        ol = self.query_one("#symlink_list", OptionList)
        last = ol.option_count - 1
        if last >= 0:
            ol.highlighted = last
            ol.scroll_end()

    def action_quit_app(self) -> None:
        self.app.exit()
