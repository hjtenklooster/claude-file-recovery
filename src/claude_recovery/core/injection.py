"""Detect and strip injected content from Read tool operations.

Uses threshold-based trailing-suffix detection: for each Read op's stripped
content, extracts trailing blocks (separated by blank lines) and checks if
they appear in >= threshold fraction of files with Read ops. Content that
was injected by Claude Code (e.g. <system-reminder> tags) appears as the
same trailing block across many files and is detected this way.
"""

from __future__ import annotations

from collections import Counter

from claude_recovery.core.models import (
    InjectedContentPattern,
    OpType,
    RecoverableFile,
)


def _extract_trailing_block(content: str) -> str | None:
    """Extract the last non-empty block from content, separated by blank lines.

    A "block" is a contiguous group of non-empty lines at the end of the content.
    Returns None if the content has no trailing block (e.g. single block only).
    """
    lines = content.rstrip().split("\n")

    # Walk backwards to find the last non-empty line
    end = len(lines) - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    if end < 0:
        return None

    # Walk backwards from end to find start of last block (stop at blank line)
    start = end
    while start > 0 and lines[start - 1].strip():
        start -= 1

    # If the block starts at line 0, the entire content is one block — no trailing block
    if start == 0:
        return None

    # Check there's a blank line separator before the block
    if lines[start - 1].strip():
        return None

    trailing = "\n".join(lines[start : end + 1])
    return trailing.strip()


def detect_injected_content(
    files: dict[str, RecoverableFile],
    threshold: float = 0.20,
) -> list[InjectedContentPattern]:
    """Detect injected content patterns across all Read operations.

    Iterates all Read ops, extracts the trailing block (last paragraph) from
    each op's content, groups by exact match, and returns InjectedContentPattern
    for each trailing block that appears in >= threshold fraction of files
    with Read ops.
    """
    trailing_file_count: Counter[str] = Counter()
    trailing_op_count: Counter[str] = Counter()
    files_with_reads = 0

    for rf in files.values():
        read_ops = [op for op in rf.operations if op.type == OpType.READ and op.content]
        if not read_ops:
            continue
        files_with_reads += 1

        seen_in_file: set[str] = set()
        for op in read_ops:
            trailing = _extract_trailing_block(op.content)
            if not trailing:
                continue
            trailing_op_count[trailing] += 1
            if trailing not in seen_in_file:
                seen_in_file.add(trailing)
                trailing_file_count[trailing] += 1

    if files_with_reads == 0:
        return []

    min_files = int(files_with_reads * threshold)
    patterns: list[InjectedContentPattern] = []

    for idx, (content, file_count) in enumerate(trailing_file_count.most_common()):
        if file_count < min_files:
            break
        patterns.append(
            InjectedContentPattern(
                pattern_id=f"trailing-suffix-{idx + 1}",
                content=content,
                affected_op_count=trailing_op_count[content],
                affected_file_count=file_count,
                sample=content[:120] + ("..." if len(content) > 120 else ""),
                detection_method="threshold-suffix",
            )
        )

    return patterns


def strip_injected_content(
    files: dict[str, RecoverableFile],
    patterns: list[InjectedContentPattern],
) -> int:
    """Strip detected injected content from Read op content fields.

    Mutates op.content in-place for all affected Read ops.
    Returns the total number of ops modified.
    """
    if not patterns:
        return 0

    pattern_strings = {p.content for p in patterns}
    modified = 0

    for rf in files.values():
        for op in rf.operations:
            if op.type != OpType.READ or not op.content:
                continue
            trailing = _extract_trailing_block(op.content)
            if not trailing or trailing not in pattern_strings:
                continue
            # Remove the trailing block from op.content
            idx = op.content.rfind(trailing)
            if idx >= 0:
                op.content = op.content[:idx].rstrip()
                modified += 1

    return modified
