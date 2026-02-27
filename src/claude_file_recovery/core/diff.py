from __future__ import annotations

import difflib

from rich.text import Text

from claude_file_recovery.core.models import FileOperation, OpType
from claude_file_recovery.core.reconstructor import reconstruct_file_at

# Nord-inspired diff color palette (soft, readable on dark backgrounds)
_STYLE_ADDED = "#a3be8c"  # Muted sage green (nord14)
_STYLE_REMOVED = "#bf616a"  # Muted soft red (nord11)
_STYLE_HUNK = "#81a1c1"  # Frost blue (nord9)
_STYLE_FILE_HEADER = "bold #d8dee9"  # Snow storm (nord4)
_STYLE_CONTEXT = "dim"


def compute_before_after(
    operations: list[FileOperation], index: int
) -> tuple[str | None, str | None]:
    """Compute the before and after states for a diff at the given operation index.

    Returns (before, after) where either may be None if content is unavailable.
    """
    after = reconstruct_file_at(operations, index)
    if after is None:
        return None, None

    if index == 0:
        return "", after

    op = operations[index]

    if op.type == OpType.EDIT and op.original_file is not None:
        # original_file is the authoritative pre-edit state from disk
        before = op.original_file
    else:
        before = reconstruct_file_at(operations, index - 1)

    if before is None:
        before = ""

    return before, after


def format_diff_text(before: str, after: str, filepath: str) -> Text:
    """Generate a colored unified diff as a rich.text.Text object."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=filepath,
            tofile=filepath,
        )
    )

    if not diff_lines:
        return Text("[No changes]", style="dim italic")

    text = Text()
    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            text.append(line, style=_STYLE_FILE_HEADER)
        elif line.startswith("@@"):
            text.append(line, style=_STYLE_HUNK)
        elif line.startswith("-"):
            text.append(line, style=_STYLE_REMOVED)
        elif line.startswith("+"):
            text.append(line, style=_STYLE_ADDED)
        else:
            text.append(line, style=_STYLE_CONTEXT)

    return text


def format_full_diff_text(before: str, after: str, filepath: str) -> Text:
    """Generate a colored unified diff with full file context."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)

    # Use a context large enough to cover the entire file
    n = max(len(before_lines), len(after_lines))

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=filepath,
            tofile=filepath,
            n=n,
        )
    )

    if not diff_lines:
        return Text("[No changes]", style="dim italic")

    text = Text()
    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            text.append(line, style=_STYLE_FILE_HEADER)
        elif line.startswith("@@"):
            text.append(line, style=_STYLE_HUNK)
        elif line.startswith("-"):
            text.append(line, style=_STYLE_REMOVED)
        elif line.startswith("+"):
            text.append(line, style=_STYLE_ADDED)
        else:
            text.append(line)

    return text


def format_read_range_view(
    full_content: str,
    read_offset: int | None,
    read_limit: int | None,
    *,
    full: bool = True,
) -> Text:
    """Render file content with gutter markers indicating the read range.

    Lines inside the read range get a thick gutter marker (┃) and normal styling.
    Lines outside the read range get a thin gutter marker (│) and dim styling.

    When full=True, all lines are shown (for Full Diff mode).
    When full=False, only the read-range lines are shown (for Diff mode).

    read_offset is 1-indexed (matching Read tool's "line number to start reading from").
    read_limit is the number of lines to read.
    """
    lines = full_content.split("\n")
    total = len(lines)

    # Convert 1-indexed offset to 0-indexed; default to full file
    start = (read_offset - 1) if read_offset is not None else 0
    start = max(0, start)
    count = read_limit if read_limit is not None else total
    end = min(start + count, total)

    is_full_read = read_offset is None and read_limit is None

    line_num_width = len(str(total))
    text = Text()

    if is_full_read:
        text.append("[Full file read]\n\n", style="dim italic")
    else:
        text.append(
            f"[Lines {start + 1}–{end} of {total} read]\n\n", style="dim italic"
        )

    for i, line in enumerate(lines):
        in_range = start <= i < end
        if not full and not in_range:
            continue
        num = str(i + 1).rjust(line_num_width)
        if in_range:
            text.append(f"  ┃ {num}  {line}\n", style="")
        else:
            text.append(f"  │ {num}  {line}\n", style="dim")

    return text
