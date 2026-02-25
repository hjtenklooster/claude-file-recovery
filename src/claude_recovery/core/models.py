from __future__ import annotations

import enum
from dataclasses import dataclass, field


class OpType(enum.Enum):
    WRITE_CREATE = "write_create"
    WRITE_UPDATE = "write_update"
    EDIT = "edit"
    READ = "read"
    FILE_HISTORY = "file_history"


@dataclass
class FileOperation:
    """A single file-mutating or file-reading operation extracted from JSONL."""

    type: OpType
    file_path: str  # Always absolute
    timestamp: str  # ISO 8601 UTC
    session_id: str
    # Content fields — populated lazily or during reconstruction phase
    content: str | None = None  # For write/read: full file content
    original_file: str | None = None  # For edit: pre-edit content
    old_string: str | None = None  # For edit: search string
    new_string: str | None = None  # For edit: replacement string
    replace_all: bool = False  # For edit
    read_offset: int | None = None  # For read: starting line number (1-indexed)
    read_limit: int | None = None  # For read: number of lines to read
    read_start_line: int | None = None  # For read: actual start line from toolUseResult.file
    read_num_lines: int | None = None  # For read: actual line count from toolUseResult.file
    read_total_lines: int | None = None  # For read: total file lines from toolUseResult.file
    # Error state — set when tool_result has is_error: true
    is_error: bool = False
    error_message: str | None = None
    # Metadata
    tool_use_id: str | None = None
    is_subagent: bool = False
    line_number: int = 0  # JSONL line number (for ordering within session)
    source_path: str | None = None  # Set during symlink merge for ops from alias paths


@dataclass
class RecoverableFile:
    """A file that can be recovered, with all its operations across sessions."""

    path: str  # Absolute path
    operations: list[FileOperation] = field(default_factory=list)

    @property
    def latest_timestamp(self) -> str:
        """Most recent operation timestamp."""
        return max(op.timestamp for op in self.operations) if self.operations else ""

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    @property
    def has_full_content(self) -> bool:
        """Whether full file recovery is possible (has a Write, full Read, or file-history, not just Edits/partial Reads)."""
        for op in self.operations:
            if op.type in (OpType.WRITE_CREATE, OpType.WRITE_UPDATE, OpType.FILE_HISTORY):
                return True
            if op.type == OpType.READ and op.read_offset is None and op.read_limit is None:
                return True
        return False

    @property
    def op_type_summary(self) -> str:
        """e.g., '3 writes, 5 edits, 2 reads'"""
        counts: dict[str, int] = {}
        for op in self.operations:
            key = op.type.value.split("_")[0]  # write, edit, read, file
            counts[key] = counts.get(key, 0) + 1
        return ", ".join(f"{v} {k}{'s' if v != 1 else ''}" for k, v in sorted(counts.items()))


@dataclass
class InjectedContentPattern:
    """A detected pattern of injected content found across multiple Read operations."""

    pattern_id: str  # Descriptive name, e.g. "trailing-suffix-1"
    content: str  # The full injected content string
    affected_op_count: int  # Number of Read ops containing this pattern
    affected_file_count: int  # Number of unique files affected
    sample: str  # Truncated sample for display (first 120 chars)
    detection_method: str  # "threshold-suffix"
