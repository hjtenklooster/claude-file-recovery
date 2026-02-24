from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson

from claude_recovery.core.models import FileOperation, OpType, RecoverableFile


def discover_jsonl_files(backup_dir: Path) -> list[Path]:
    """Find all session JSONL files including subagent files.

    Walks projects/<slug>/*.jsonl and projects/<slug>/<session>/subagents/*.jsonl.
    """
    projects_dir = backup_dir / "projects"
    if not projects_dir.exists():
        return []

    jsonl_files: list[Path] = []
    for root, dirs, files in os.walk(projects_dir):
        for f in files:
            if f.endswith(".jsonl"):
                jsonl_files.append(Path(root) / f)
    return jsonl_files


def _is_subagent_file(path: Path) -> bool:
    """Check if a JSONL file is a subagent file (in a subagents/ directory)."""
    return "subagents" in path.parts


def _extract_session_id(path: Path) -> str:
    """Extract session UUID from the JSONL file path."""
    # Main session: projects/<slug>/<uuid>.jsonl
    # Subagent: projects/<slug>/<uuid>/subagents/agent-<hex>.jsonl
    if _is_subagent_file(path):
        # The session UUID is the parent of 'subagents' directory
        idx = path.parts.index("subagents")
        return path.parts[idx - 1]
    return path.stem


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


def _enrich_from_tool_use_result(result: dict, pending_ops: dict[str, FileOperation]) -> None:
    """Enrich a pending FileOperation with data from toolUseResult.

    Write toolUseResult has: type, filePath, content, structuredPatch, originalFile
    Edit toolUseResult has: filePath, oldString, newString, originalFile, structuredPatch, replaceAll
    """
    file_path = result.get("filePath", "")
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


def scan_session(path: Path) -> list[FileOperation]:
    """Scan a single JSONL session file for file operations.

    Extracts both metadata (file path, timestamp, type) and content
    (toolUseResult fields for Write/Edit, inline content for Read).
    """
    ops: list[FileOperation] = []
    # Map tool_use_id -> FileOperation for correlating with toolUseResult
    pending_ops: dict[str, FileOperation] = {}
    is_subagent = _is_subagent_file(path)
    session_id = _extract_session_id(path)

    with open(path, "rb") as f:
        for line_num, line in enumerate(f, 1):
            # Fast reject: 77% of lines are progress entries
            if b'"type":"progress"' in line or b'"type": "progress"' in line:
                continue
            if b'"type":"file-history-snapshot"' in line or b'"type": "file-history-snapshot"' in line:
                continue

            try:
                entry = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            timestamp = entry.get("timestamp", "")

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
                    _enrich_from_tool_use_result(tool_result, pending_ops)

                # Extract Read content from message.content tool_result blocks
                msg_content = entry.get("message", {}).get("content", [])
                if isinstance(msg_content, list):
                    for block in msg_content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id")
                            if tool_use_id and tool_use_id in pending_ops:
                                op = pending_ops[tool_use_id]
                                if op.type == OpType.READ and op.content is None:
                                    raw = block.get("content", "")
                                    if isinstance(raw, str) and "\u2192" in raw:
                                        op.content = strip_read_line_numbers(raw)
                                    elif isinstance(raw, str):
                                        op.content = raw

    return ops


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
        futures = {executor.submit(scan_session, p): p for p in jsonl_files}
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

    return files
