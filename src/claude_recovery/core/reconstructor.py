from __future__ import annotations

from claude_recovery.core.models import FileOperation, OpType, RecoverableFile


def apply_edit(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Apply an Edit operation to file content.

    replace_all=False: replace first occurrence only (str.replace with count=1)
    replace_all=True: replace all occurrences
    """
    if not old_string:
        return content
    if replace_all:
        return content.replace(old_string, new_string)
    return content.replace(old_string, new_string, 1)


def reconstruct_file_at(operations: list[FileOperation], up_to_index: int) -> str | None:
    """Reconstruct file content at a specific point in the operation timeline.

    Replays all operations from index 0 through up_to_index (inclusive).
    Returns the file content at that point, or None if reconstruction fails.
    """
    content: str | None = None

    for op in operations[: up_to_index + 1]:
        if op.type in (OpType.WRITE_CREATE, OpType.WRITE_UPDATE):
            content = op.content
        elif op.type == OpType.READ:
            if op.content is not None:
                content = op.content
        elif op.type == OpType.FILE_HISTORY:
            if op.content is not None:
                content = op.content
        elif op.type == OpType.EDIT:
            # If we have no base content yet, use originalFile from this edit
            if content is None and op.original_file is not None:
                content = op.original_file
            # Apply the edit
            if content is not None and op.old_string is not None and op.new_string is not None:
                content = apply_edit(content, op.old_string, op.new_string, op.replace_all)

    return content


def reconstruct_latest(file: RecoverableFile) -> str | None:
    """Reconstruct the latest version of a file."""
    if not file.operations:
        return None
    return reconstruct_file_at(file.operations, len(file.operations) - 1)
