from __future__ import annotations

import difflib

from rich.text import Text

from claude_recovery.core.models import FileOperation, OpType
from claude_recovery.core.reconstructor import reconstruct_file_at


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
        prev_op = operations[index - 1]
        if prev_op.type == OpType.EDIT:
            # Consecutive edits: use reconstructed chain for accurate incremental diff
            before = reconstruct_file_at(operations, index - 1)
        else:
            # Non-consecutive edit: original_file is authoritative
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
            text.append(line, style="bold blue")
        elif line.startswith("@@"):
            text.append(line, style="cyan")
        elif line.startswith("-"):
            text.append(line, style="red")
        elif line.startswith("+"):
            text.append(line, style="green")
        else:
            text.append(line, style="dim")

    return text


def format_read_range_view(
    full_content: str,
    read_offset: int | None,
    read_limit: int | None,
) -> Text:
    """Render full file content with gutter markers indicating the read range.

    Lines inside the read range get a thick gutter marker (┃) and normal styling.
    Lines outside the read range get a thin gutter marker (│) and dim styling.

    read_offset is 1-indexed (matching Read tool's "line number to start reading from").
    read_limit is the number of lines to read.
    """
    lines = full_content.split("\n")
    total = len(lines)

    # Default: show everything as "in range" if no offset/limit
    if read_offset is None and read_limit is None:
        return Text(full_content)

    # Convert 1-indexed offset to 0-indexed; default to start if None
    start = (read_offset - 1) if read_offset is not None else 0
    start = max(0, start)
    count = read_limit if read_limit is not None else total
    end = min(start + count, total)

    line_num_width = len(str(total))
    text = Text()

    for i, line in enumerate(lines):
        num = str(i + 1).rjust(line_num_width)
        if start <= i < end:
            text.append(f"  ┃ {num}  {line}\n", style="")
        else:
            text.append(f"  │ {num}  {line}\n", style="dim")

    return text
