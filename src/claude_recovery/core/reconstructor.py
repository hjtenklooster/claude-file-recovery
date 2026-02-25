from __future__ import annotations

import bisect

from claude_recovery.core.models import FileOperation, OpType, RecoverableFile


def apply_edit(
    content: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """Apply an Edit operation to file content.

    replace_all=False: replace first occurrence only (str.replace with count=1)
    replace_all=True: replace all occurrences
    """
    if not old_string:
        return content
    if replace_all:
        return content.replace(old_string, new_string)
    return content.replace(old_string, new_string, 1)


def splice_read(
    existing: str | None,
    new_content: str,
    start_line: int | None,
    num_lines: int | None,
    total_lines: int | None,
) -> str:
    """Splice partial Read content into existing content at the correct line positions.

    Uses response metadata (start_line, num_lines, total_lines) from toolUseResult.file
    to position the new content. Extends the line array with empty lines when the file
    is longer than existing content.
    """
    new_lines = new_content.split("\n")
    start = (start_line - 1) if start_line else 0

    if existing is None:
        lines = [""] * (total_lines or (start + len(new_lines)))
    else:
        lines = existing.split("\n")
        target_len = total_lines or (start + len(new_lines))
        if len(lines) < target_len:
            lines.extend([""] * (target_len - len(lines)))

    lines[start : start + len(new_lines)] = new_lines
    return "\n".join(lines)


def reconstruct_file_at(
    operations: list[FileOperation], up_to_index: int
) -> str | None:
    """Reconstruct file content at a specific point in the operation timeline.

    Replays all operations from index 0 through up_to_index (inclusive).
    Returns the file content at that point, or None if reconstruction fails.
    """
    content: str | None = None

    for op in operations[: up_to_index + 1]:
        if op.type in (OpType.WRITE_CREATE, OpType.WRITE_UPDATE):
            content = op.content
        elif op.type == OpType.READ:
            if op.content is None:
                continue
            # A read is full if neither request nor response metadata indicates a partial range.
            # Response metadata (read_start_line etc.) wins when available; otherwise fall
            # back to request params (read_offset / read_limit).
            if op.read_start_line is not None:
                is_full = (
                    op.read_start_line == 1 and op.read_num_lines == op.read_total_lines
                )
            else:
                is_full = op.read_offset is None and op.read_limit is None
            if is_full:
                # Full read — always authoritative, like a Write
                content = op.content
            elif content is None:
                # First op for this file is a partial read — initialize with splicing.
                # Use response metadata when available; fall back to request offset.
                start_line = op.read_start_line or op.read_offset
                content = splice_read(
                    None,
                    op.content,
                    start_line,
                    op.read_num_lines,
                    op.read_total_lines,
                )
            else:
                # Partial read — splice into existing content.
                # Use response metadata when available; fall back to request offset.
                start_line = op.read_start_line or op.read_offset
                content = splice_read(
                    content,
                    op.content,
                    start_line,
                    op.read_num_lines,
                    op.read_total_lines,
                )
        elif op.type == OpType.FILE_HISTORY:
            if op.content is not None:
                content = op.content
        elif op.type == OpType.EDIT:
            # Prefer original_file (authoritative pre-edit state from toolUseResult)
            # over current content, which may be stale or from a partial Read.
            if op.original_file is not None:
                content = op.original_file
            # Apply the edit
            if (
                content is not None
                and op.old_string is not None
                and op.new_string is not None
            ):
                content = apply_edit(
                    content, op.old_string, op.new_string, op.replace_all
                )

    return content


def reconstruct_latest(file: RecoverableFile) -> str | None:
    """Reconstruct the latest version of a file."""
    if not file.operations:
        return None
    return reconstruct_file_at(file.operations, len(file.operations) - 1)


def reconstruct_at_timestamp(file: RecoverableFile, before_ts: str) -> str | None:
    """Reconstruct file content at a specific point in time.

    Finds the last operation where op.timestamp <= before_ts using bisect,
    then delegates to reconstruct_file_at(). Returns None if no operations
    qualify (all ops are after the cutoff).
    """
    if not file.operations:
        return None
    timestamps = [op.timestamp for op in file.operations]
    idx = bisect.bisect_right(timestamps, before_ts) - 1
    if idx < 0:
        return None
    return reconstruct_file_at(file.operations, idx)
