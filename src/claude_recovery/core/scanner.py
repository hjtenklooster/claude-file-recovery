from __future__ import annotations

import os
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


def scan_session(path: Path) -> list[FileOperation]:
    """Scan a single JSONL session file for file-mutating tool calls.

    Phase 1: extracts file paths, timestamps, and operation types only.
    Content fields are left as None — populated in Phase 2.
    """
    ops: list[FileOperation] = []
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
                        ops.append(FileOperation(
                            type=OpType.WRITE_CREATE,  # Refined in Phase 2 from toolUseResult
                            file_path=file_path,
                            timestamp=timestamp,
                            session_id=session_id,
                            tool_use_id=block.get("id"),
                            is_subagent=is_subagent,
                            line_number=line_num,
                        ))
                    elif name == "Edit":
                        ops.append(FileOperation(
                            type=OpType.EDIT,
                            file_path=file_path,
                            timestamp=timestamp,
                            session_id=session_id,
                            tool_use_id=block.get("id"),
                            is_subagent=is_subagent,
                            line_number=line_num,
                        ))
                    elif name == "Read":
                        ops.append(FileOperation(
                            type=OpType.READ,
                            file_path=file_path,
                            timestamp=timestamp,
                            session_id=session_id,
                            tool_use_id=block.get("id"),
                            is_subagent=is_subagent,
                            line_number=line_num,
                        ))

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
