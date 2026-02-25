from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static


class InjectionReviewScreen(Screen):
    """Review detected injected content before stripping from recovered files."""

    BINDINGS = [
        Binding("enter", "confirm", "Strip Content", show=True, priority=True),
        Binding("c", "confirm", "Strip Content", show=False),
        Binding("s", "skip", "Skip", show=True),
        Binding("escape", "skip", "Skip", show=False),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static(" Injected Content Detected", id="injection_header")
        yield Static("", id="injection_explanation")
        yield Static("", id="injection_status")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app  # type: FileRecoveryApp
        patterns = app.injection_patterns

        if not patterns:
            self.query_one("#injection_explanation", Static).update(
                " No injected content detected in Read operations.\n"
                "\n"
                " Press Enter or s to continue."
            )
            self.query_one("#injection_status", Static).update(
                " No patterns found — press Enter to continue"
            )
            return

        # Build summary
        total_ops = sum(p.affected_op_count for p in patterns)
        total_files = sum(p.affected_file_count for p in patterns)

        lines = [
            f" Detected {len(patterns)} injected content pattern(s) in {total_ops} Read operations",
            f" across {total_files} files.\n",
            " Claude Code (versions 2.0.74-2.1.38) injected instructional tags into Read tool",
            " results. These tags end up in recovered file content unless stripped.\n",
        ]

        for p in patterns:
            lines.append(f" {p.affected_op_count} ops in {p.affected_file_count} files:")
            lines.append(" " + "─" * 60)
            for content_line in p.content.splitlines():
                lines.append(f" {content_line}")
            lines.append(" " + "─" * 60)
            lines.append("")

        lines.append(" Press Enter to strip injected content, or s to skip and keep raw content.")

        self.query_one("#injection_explanation", Static).update("\n".join(lines))
        self.query_one("#injection_status", Static).update(
            f" {len(patterns)} pattern(s), {total_ops} ops, {total_files} files — "
            f"Enter: strip | s: skip"
        )

    def action_confirm(self) -> None:
        """Strip injected content and navigate to next screen."""
        app = self.app  # type: FileRecoveryApp

        if app.injection_patterns:
            from claude_recovery.core.injection import strip_injected_content
            strip_injected_content(app.raw_file_index, app.injection_patterns)
            # Also strip from merged index if it exists
            if app.merged_file_index:
                strip_injected_content(app.merged_file_index, app.injection_patterns)
            app.injection_stripped = True
            self.notify(
                f"Stripped injected content from "
                f"{sum(p.affected_op_count for p in app.injection_patterns)} Read operations"
            )
        else:
            app.injection_stripped = False

        self._navigate_next()

    def action_skip(self) -> None:
        """Skip injection stripping — proceed with raw content."""
        app = self.app  # type: FileRecoveryApp
        app.injection_stripped = False
        self.notify("Injection filtering skipped — content preserved as-is")
        self._navigate_next()

    def _navigate_next(self) -> None:
        """Navigate to next screen using stack inspection pattern."""
        # On initial mount, the screen below us is SymlinkReviewScreen.
        # Pop to reveal it. If re-opened from FileListScreen, pop back to it.
        screen_stack = self.app.screen_stack
        if len(screen_stack) >= 2:
            from claude_recovery.tui.file_list_screen import FileListScreen
            if isinstance(screen_stack[-2], FileListScreen):
                self.app.pop_screen()
                return
        # Initial flow: pop ourselves to reveal the next screen in the stack
        self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit()
