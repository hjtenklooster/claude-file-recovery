from __future__ import annotations

from claude_recovery.core.models import RecoverableFile
from claude_recovery.core.symlinks.models import SymlinkGroup


def merge_file_index(
    file_index: dict[str, RecoverableFile],
    groups: list[SymlinkGroup],
) -> dict[str, RecoverableFile]:
    """Build a new file index with symlinked paths merged into canonical entries.

    For each SymlinkGroup, finds all RecoverableFile entries whose paths
    start with an alias directory prefix, merges their operations into the
    corresponding canonical-path entry (remapping the file path from
    alias to canonical), and sets source_path on ops from alias paths.

    Returns a new dict — the original file_index is not mutated.
    """
    # Build alias->canonical prefix mapping
    alias_to_canonical: dict[str, str] = {}
    for group in groups:
        for alias in group.aliases:
            alias_to_canonical[alias] = group.canonical

    # Sort alias prefixes longest-first so we match the most specific alias
    sorted_aliases = sorted(alias_to_canonical.keys(), key=len, reverse=True)

    def resolve_path(path: str) -> tuple[str, str | None]:
        """Resolve a path to its canonical form.

        Returns (canonical_path, original_alias_path_or_None).
        """
        for alias in sorted_aliases:
            if path == alias or path.startswith(alias + "/"):
                canonical_prefix = alias_to_canonical[alias]
                canonical_path = canonical_prefix + path[len(alias):]
                return canonical_path, path
        return path, None

    # Build new index
    new_index: dict[str, RecoverableFile] = {}

    for path, rf in file_index.items():
        canonical_path, original_path = resolve_path(path)

        if canonical_path not in new_index:
            new_index[canonical_path] = RecoverableFile(path=canonical_path)

        target = new_index[canonical_path]
        for op in rf.operations:
            if original_path is not None:
                op.source_path = original_path
            target.operations.append(op)

    # Re-sort operations in each merged entry
    for rf in new_index.values():
        rf.operations.sort(key=lambda o: (o.timestamp, o.session_id, o.line_number))

    return new_index
