from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson

from claude_file_recovery.core.models import FileOperation, OpType, RecoverableFile
from claude_file_recovery.core.reconstructor import apply_edit, splice_read


def discover_jsonl_files(backup_dir: Path) -> list[Path]:
    """Find all session JSONL files including subagent files.

    Walks projects/<slug>/*.jsonl (including .jsonl.backup.*) and
    projects/<slug>/<session>/subagents/*.jsonl.
    """
    projects_dir = backup_dir / "projects"
    if not projects_dir.exists():
        return []

    jsonl_files: list[Path] = []
    for root, dirs, files in os.walk(projects_dir):
        for f in files:
            if f.endswith(".jsonl") or ".jsonl.backup" in f:
                jsonl_files.append(Path(root) / f)
    return jsonl_files


def _is_subagent_file(path: Path) -> bool:
    """Check if a JSONL file is a subagent file (in a subagents/ directory)."""
    return "subagents" in path.parts


def _extract_session_id(path: Path) -> str:
    """Extract session UUID from the JSONL file path."""
    # Main session: projects/<slug>/<uuid>.jsonl
    # Backup: projects/<slug>/<uuid>.jsonl.backup.<timestamp>
    # Subagent: projects/<slug>/<uuid>/subagents/agent-<hex>.jsonl
    if _is_subagent_file(path):
        # The session UUID is the parent of 'subagents' directory
        idx = path.parts.index("subagents")
        return path.parts[idx - 1]
    # Split on ".jsonl" to handle both uuid.jsonl and uuid.jsonl.backup.TS
    return path.name.split(".jsonl")[0]


def strip_read_line_numbers(text: str) -> str:
    """Strip line-number prefixes from Read tool output.

    Format: right-aligned number + → (U+2192) + content
    Example: '     1→first line'
    """
    lines = text.split("\n")
    stripped = []
    for line in lines:
        # Match: optional whitespace + digits + → + rest
        m = re.match(r"^\s*\d+\u2192(.*)", line)
        if m:
            stripped.append(m.group(1))
        else:
            stripped.append(line)
    return "\n".join(stripped)


def _is_noop_edit(op: FileOperation) -> bool:
    """Check if an Edit operation would produce no actual change (fast field-level check)."""
    if op.type != OpType.EDIT:
        return False
    if op.is_error:
        return False  # Keep errored ops — they'll be shown as errors in the TUI
    if op.old_string is None or op.new_string is None:
        return True
    if not op.old_string:
        return True
    if op.old_string == op.new_string:
        return True
    if op.original_file is not None and op.old_string not in op.original_file:
        return True
    return False


def _filter_noop_edits_by_replay(
    operations: list[FileOperation],
) -> list[FileOperation]:
    """Remove Edit operations that produce no actual change when replayed in sequence.

    Catches cases that the field-level _is_noop_edit cannot detect, such as
    duplicate/retried edits where original_file overrides produce identical
    before/after states.
    """
    result: list[FileOperation] = []
    content: str | None = None

    for op in operations:
        if op.type in (OpType.WRITE_CREATE, OpType.WRITE_UPDATE):
            content = op.content
            result.append(op)
        elif op.type == OpType.READ:
            if op.content is not None:
                # Mirror reconstructor's is_full logic exactly, including request-param fallback
                if op.read_start_line is not None:
                    is_full = (
                        op.read_start_line == 1
                        and op.read_num_lines == op.read_total_lines
                    )
                else:
                    is_full = op.read_offset is None and op.read_limit is None
                if is_full:
                    content = op.content
                else:
                    start_line = op.read_start_line or op.read_offset
                    if content is None:
                        content = splice_read(
                            None,
                            op.content,
                            start_line,
                            op.read_num_lines,
                            op.read_total_lines,
                        )
                    else:
                        content = splice_read(
                            content,
                            op.content,
                            start_line,
                            op.read_num_lines,
                            op.read_total_lines,
                        )
            result.append(op)
        elif op.type == OpType.FILE_HISTORY:
            if op.content is not None:
                content = op.content
            result.append(op)
        elif op.type == OpType.EDIT:
            if op.is_error:
                # Keep errored ops — they didn't modify content
                result.append(op)
                continue
            if op.original_file is not None:
                # Edit has authoritative pre-edit state from disk.
                # Check if the edit changes the actual file, not our chain.
                after_edit = op.original_file
                if op.old_string is not None and op.new_string is not None:
                    after_edit = apply_edit(
                        op.original_file, op.old_string, op.new_string, op.replace_all
                    )
                content = after_edit
                if after_edit != op.original_file:
                    result.append(op)
                # else: edit didn't change the actual file — drop it
            else:
                # No original_file — check if edit changes reconstructed content
                before = content
                if (
                    content is not None
                    and op.old_string is not None
                    and op.new_string is not None
                ):
                    content = apply_edit(
                        content, op.old_string, op.new_string, op.replace_all
                    )
                if content != before:
                    result.append(op)
                # else: edit produced no change in reconstructed state — drop it
        else:
            result.append(op)

    return result


def _enrich_from_tool_use_result(
    result: dict, pending_ops: dict[str, FileOperation]
) -> None:
    """Enrich a pending FileOperation with data from toolUseResult.

    Write toolUseResult has: type, filePath, content, structuredPatch, originalFile
    Edit toolUseResult has: filePath, oldString, newString, originalFile, structuredPatch, replaceAll
    Read toolUseResult has: type, file (dict with filePath, content, startLine, numLines, totalLines)
    """
    file_path = result.get("filePath", "")
    # Read toolUseResult nests filePath inside the 'file' dict
    if not file_path:
        file_info = result.get("file")
        if isinstance(file_info, dict):
            file_path = file_info.get("filePath", "")
    if not file_path:
        return

    # Find the matching pending op by filePath.
    # Match the most recent pending op for this path.
    matching_op = None
    for op in reversed(list(pending_ops.values())):
        if op.file_path == file_path:
            matching_op = op
            break

    if not matching_op:
        return

    result_type = result.get("type")
    if result_type == "create":
        matching_op.type = OpType.WRITE_CREATE
        matching_op.content = result.get("content")
        matching_op.original_file = None
    elif result_type == "update":
        matching_op.type = OpType.WRITE_UPDATE
        matching_op.content = result.get("content")
        matching_op.original_file = result.get("originalFile")
    elif matching_op.type == OpType.EDIT:
        # Edit toolUseResult — enrich with originalFile and confirmed strings
        matching_op.original_file = result.get("originalFile")
        if result.get("oldString"):
            matching_op.old_string = result["oldString"]
        if result.get("newString") is not None:
            matching_op.new_string = result["newString"]
        if "replaceAll" in result:
            matching_op.replace_all = result["replaceAll"]
    elif matching_op.type == OpType.READ:
        # Read toolUseResult — extract response metadata from file dict
        file_info = result.get("file")
        if isinstance(file_info, dict):
            start_line = file_info.get("startLine")
            num_lines = file_info.get("numLines")
            total_lines = file_info.get("totalLines")
            if isinstance(start_line, int):
                matching_op.read_start_line = start_line
            if isinstance(num_lines, int):
                matching_op.read_num_lines = num_lines
            if isinstance(total_lines, int):
                matching_op.read_total_lines = total_lines


def scan_session(path: Path, backup_dir: Path | None = None) -> list[FileOperation]:
    """Scan a single JSONL session file for file operations.

    Extracts both metadata (file path, timestamp, type) and content
    (toolUseResult fields for Write/Edit, inline content for Read).
    When backup_dir is provided, also parses file-history-snapshot entries
    and reads corresponding disk files from file-history/<session-id>/.
    """
    ops: list[FileOperation] = []
    # Map tool_use_id -> FileOperation for correlating with toolUseResult
    pending_ops: dict[str, FileOperation] = {}
    is_subagent = _is_subagent_file(path)
    session_id = _extract_session_id(path)
    cwd: str | None = None  # Populated from first entry with cwd field

    with open(path, "rb") as f:
        for line_num, line in enumerate(f, 1):
            # Fast reject: 77% of lines are progress entries
            if b'"type":"progress"' in line or b'"type": "progress"' in line:
                continue
            try:
                entry = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            timestamp = entry.get("timestamp", "")

            # Track cwd for resolving relative paths in file-history snapshots
            if cwd is None:
                entry_cwd = entry.get("cwd")
                if entry_cwd:
                    cwd = entry_cwd

            if entry_type == "assistant":
                # Scan for Write/Edit/Read tool_use blocks
                for block in entry.get("message", {}).get("content", []):
                    if block.get("type") != "tool_use":
                        continue
                    name = block.get("name")
                    inp = block.get("input", {})
                    file_path = inp.get("file_path", "")

                    if not file_path:
                        continue

                    if name == "Write":
                        op = FileOperation(
                            type=OpType.WRITE_CREATE,  # Refined from toolUseResult
                            file_path=file_path,
                            timestamp=timestamp,
                            session_id=session_id,
                            content=inp.get("content"),  # Fallback content from input
                            tool_use_id=block.get("id"),
                            is_subagent=is_subagent,
                            line_number=line_num,
                        )
                        ops.append(op)
                        if op.tool_use_id:
                            pending_ops[op.tool_use_id] = op
                    elif name == "Edit":
                        op = FileOperation(
                            type=OpType.EDIT,
                            file_path=file_path,
                            timestamp=timestamp,
                            session_id=session_id,
                            old_string=inp.get("old_string"),
                            new_string=inp.get("new_string"),
                            replace_all=inp.get("replace_all", False),
                            tool_use_id=block.get("id"),
                            is_subagent=is_subagent,
                            line_number=line_num,
                        )
                        ops.append(op)
                        if op.tool_use_id:
                            pending_ops[op.tool_use_id] = op
                    elif name == "Read":
                        op = FileOperation(
                            type=OpType.READ,
                            file_path=file_path,
                            timestamp=timestamp,
                            session_id=session_id,
                            read_offset=inp.get("offset"),
                            read_limit=inp.get("limit"),
                            tool_use_id=block.get("id"),
                            is_subagent=is_subagent,
                            line_number=line_num,
                        )
                        ops.append(op)
                        if op.tool_use_id:
                            pending_ops[op.tool_use_id] = op

            elif entry_type == "user":
                # Extract content from toolUseResult (top-level field)
                tool_result = entry.get("toolUseResult")
                if isinstance(tool_result, dict) and tool_result:
                    # Resolve externalized tool output if present
                    persisted_path = tool_result.get("persistedOutputPath")
                    if persisted_path:
                        try:
                            full_content = Path(persisted_path).read_text(
                                encoding="utf-8", errors="replace"
                            )
                            tool_result["stdout"] = full_content
                        except (OSError, IOError):
                            pass  # Keep truncated content if file not found

                    _enrich_from_tool_use_result(tool_result, pending_ops)

                # Also detect errors from top-level toolUseResult string
                if isinstance(tool_result, str) and tool_result.startswith("Error: "):
                    # Match to most recent pending op by tool_use_id in content
                    tool_use_id_from_content = None
                    msg_content_err = entry.get("message", {}).get("content", [])
                    if isinstance(msg_content_err, list):
                        for b in msg_content_err:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                tool_use_id_from_content = b.get("tool_use_id")
                                break
                    if (
                        tool_use_id_from_content
                        and tool_use_id_from_content in pending_ops
                    ):
                        err_op = pending_ops[tool_use_id_from_content]
                        err_op.is_error = True
                        err_op.error_message = tool_result[len("Error: ") :]

                # Extract content and detect errors from message.content tool_result blocks
                msg_content = entry.get("message", {}).get("content", [])
                if isinstance(msg_content, list):
                    for block in msg_content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id")
                            # Resolve persisted output in tool_result content
                            block_content = block.get("content", "")
                            if (
                                isinstance(block_content, str)
                                and block_content.startswith("<persisted-output>")
                                and isinstance(tool_result, dict)
                                and tool_result.get("persistedOutputPath")
                            ):
                                try:
                                    full_content = Path(
                                        tool_result["persistedOutputPath"]
                                    ).read_text(encoding="utf-8", errors="replace")
                                    block["content"] = full_content
                                except (OSError, IOError):
                                    pass  # Keep truncated content

                            if tool_use_id and tool_use_id in pending_ops:
                                op = pending_ops[tool_use_id]
                                if block.get("is_error"):
                                    op.is_error = True
                                    raw = block.get("content", "")
                                    if isinstance(raw, str):
                                        m = re.match(
                                            r"<tool_use_error>(.*)</tool_use_error>",
                                            raw,
                                            re.DOTALL,
                                        )
                                        op.error_message = (
                                            m.group(1).strip() if m else raw.strip()
                                        )
                                elif op.type == OpType.READ and op.content is None:
                                    raw = block.get("content", "")
                                    if isinstance(raw, str) and "\u2192" in raw:
                                        op.content = strip_read_line_numbers(raw)
                                    elif isinstance(raw, str):
                                        op.content = raw

            elif entry_type == "file-history-snapshot" and backup_dir is not None:
                snapshot = entry.get("snapshot", {})
                tracked = snapshot.get("trackedFileBackups", {})
                for rel_path, backup_info in tracked.items():
                    backup_filename = backup_info.get("backupFileName")
                    backup_time = backup_info.get("backupTime", timestamp)
                    if not backup_filename:
                        continue

                    # Resolve relative path to absolute using session cwd
                    if cwd and not os.path.isabs(rel_path):
                        abs_path = os.path.normpath(os.path.join(cwd, rel_path))
                    else:
                        abs_path = rel_path

                    # Read the snapshot file from disk
                    snapshot_file = (
                        backup_dir / "file-history" / session_id / backup_filename
                    )
                    try:
                        file_content = snapshot_file.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    except (OSError, IOError):
                        continue  # Skip if file doesn't exist or can't be read

                    op = FileOperation(
                        type=OpType.FILE_HISTORY,
                        file_path=abs_path,
                        timestamp=backup_time,
                        session_id=session_id,
                        content=file_content,
                        line_number=line_num,
                    )
                    ops.append(op)

    return [op for op in ops if not _is_noop_edit(op)]


def scan_all_sessions(
    backup_dir: Path,
    max_workers: int = 8,
    progress_callback=None,
) -> dict[str, RecoverableFile]:
    """Scan all JSONL files and build a dict of recoverable files keyed by absolute path.

    Operations within each session are ordered by JSONL line number.
    Cross-session operations for the same file are ordered by timestamp.
    """
    jsonl_files = discover_jsonl_files(backup_dir)
    all_ops: list[FileOperation] = []
    completed = 0
    total = len(jsonl_files)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_session, p, backup_dir): p for p in jsonl_files}
        for future in as_completed(futures):
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
            try:
                ops = future.result()
                all_ops.extend(ops)
            except Exception:
                continue  # Skip malformed files

    # Group by absolute file path
    files: dict[str, RecoverableFile] = {}
    for op in all_ops:
        if op.file_path not in files:
            files[op.file_path] = RecoverableFile(path=op.file_path)
        files[op.file_path].operations.append(op)

    # Sort operations: within same session by line_number, across sessions by timestamp
    for rf in files.values():
        rf.operations.sort(key=lambda o: (o.timestamp, o.session_id, o.line_number))
        rf.operations = _filter_noop_edits_by_replay(rf.operations)

    return files
