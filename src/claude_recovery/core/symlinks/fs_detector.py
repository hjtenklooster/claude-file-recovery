from __future__ import annotations

import os
from pathlib import Path

from claude_recovery.core.symlinks.models import SymlinkGroup


def find_symlinks_in_path(filepath: str, cache: dict[str, str | None]) -> str | None:
    """Walk directory components from root down, return shallowest symlink or None."""
    parts = Path(filepath).parts
    for i in range(1, len(parts)):
        prefix = str(Path(*parts[: i + 1]))

        if prefix not in cache:
            try:
                if os.path.islink(prefix):
                    target = os.readlink(prefix)
                    if not os.path.isabs(target):
                        target = str(Path(prefix).parent / target)
                    target = os.path.normpath(target)
                    cache[prefix] = target
                else:
                    cache[prefix] = None
            except OSError:
                cache[prefix] = None

        if cache[prefix] is not None:
            return prefix  # shallowest symlink

    return None


def detect_fs_symlinks(file_paths: list[str]) -> list[SymlinkGroup]:
    """Detect symlink directories by probing the live filesystem.

    For each file path, walks components from root down and checks
    os.path.islink(). Groups paths by the shallowest symlink component
    found, then groups symlinks pointing to the same target.

    Returns SymlinkGroup objects where:
    - canonical = the resolved target directory
    - aliases = the symlink directory paths
    - detection_methods = {"<alias>": "FS"} for each alias
    """
    cache: dict[str, str | None] = {}
    # symlink_component_path -> {"target": resolved, "paths": [file_paths]}
    symlink_map: dict[str, dict] = {}

    for fp in file_paths:
        symlink_component = find_symlinks_in_path(fp, cache)
        if symlink_component:
            target = cache[symlink_component]
            if symlink_component not in symlink_map:
                symlink_map[symlink_component] = {"target": target, "paths": []}
            symlink_map[symlink_component]["paths"].append(fp)

    # Group symlinks by their resolved target
    target_to_symlinks: dict[str, list[str]] = {}
    for symlink_path, info in symlink_map.items():
        target = info["target"]
        if target not in target_to_symlinks:
            target_to_symlinks[target] = []
        target_to_symlinks[target].append(symlink_path)

    groups = []
    for target, symlink_paths in target_to_symlinks.items():
        methods = {sp: "FS" for sp in symlink_paths}
        groups.append(SymlinkGroup(
            canonical=target,
            aliases=sorted(symlink_paths),
            detection_methods=methods,
        ))

    return groups
