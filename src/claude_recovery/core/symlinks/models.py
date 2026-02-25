from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SymlinkGroup:
    """A canonical path and its known aliases (symlinked/copied paths).

    detection_methods maps each alias path to its detection method string
    ("FS" or "Path"). This metadata is used for TUI display only —
    it is NOT persisted to the YAML file.
    """

    canonical: str
    aliases: list[str] = field(default_factory=list)
    detection_methods: dict[str, str] = field(default_factory=dict)


def save_symlink_yaml(groups: list[SymlinkGroup], path: Path) -> None:
    """Write symlink groups to a YAML file.

    Format:
        /private/tmp/project:
          - /tmp/project
        /home/user/src/project:
          - /home/user/worktrees/feature/src/project
    """
    data: dict[str, list[str]] = {}
    for group in groups:
        if group.aliases:  # skip empty groups
            data[group.canonical] = sorted(group.aliases)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")


def load_symlink_yaml(path: Path) -> list[SymlinkGroup]:
    """Load symlink groups from a YAML file.

    Returns SymlinkGroup objects with no detection_methods set
    (since the YAML doesn't store detection metadata).
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []

    groups = []
    for canonical, aliases in raw.items():
        if isinstance(aliases, list):
            groups.append(
                SymlinkGroup(
                    canonical=str(canonical),
                    aliases=[str(a) for a in aliases],
                )
            )
    return groups
