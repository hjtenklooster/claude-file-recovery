"""Unified path-matching filters for CLI and TUI."""

from __future__ import annotations

import enum
import fnmatch
import re

from textual.fuzzy import Matcher

from claude_recovery.core.models import RecoverableFile


class SearchMode(str, enum.Enum):
    """Available search/filter modes."""

    FUZZY = "fuzzy"
    GLOB = "glob"
    REGEX = "regex"


def smart_case_sensitive(pattern: str, explicit_override: bool | None = None) -> bool:
    """Determine case sensitivity using smart-case convention.

    Returns True (case-sensitive) if the pattern contains any uppercase character.
    Returns False (case-insensitive) if the pattern is all-lowercase.
    An explicit override (True/False) takes precedence over smart-case.
    """
    if explicit_override is not None:
        return explicit_override
    return any(c.isupper() for c in pattern)


def match_path(
    path: str,
    pattern: str,
    mode: SearchMode,
    case_sensitive: bool,
) -> float:
    """Score how well *path* matches *pattern* under the given mode.

    Returns:
        >0.0 for a match (fuzzy returns a relevance score; glob/regex return 1.0).
        0.0 for no match.
    """
    if not pattern:
        return 1.0  # empty pattern matches everything

    if mode is SearchMode.FUZZY:
        matcher = Matcher(pattern, case_sensitive=case_sensitive)
        return matcher.match(path)

    if mode is SearchMode.GLOB:
        p, basename = path, path.rsplit("/", 1)[-1] if "/" in path else path
        if case_sensitive:
            matched = fnmatch.fnmatchcase(p, pattern) or fnmatch.fnmatchcase(
                basename, pattern
            )
        else:
            matched = fnmatch.fnmatch(p.lower(), pattern.lower()) or fnmatch.fnmatch(
                basename.lower(), pattern.lower()
            )
        return 1.0 if matched else 0.0

    if mode is SearchMode.REGEX:
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            return 1.0 if re.search(pattern, path, flags) else 0.0
        except re.error:
            return 0.0

    return 0.0


def validate_regex(pattern: str) -> str | None:
    """Return an error message if *pattern* is not valid regex, else None."""
    try:
        re.compile(pattern)
        return None
    except re.error as e:
        return str(e)


def filter_files(
    files: dict[str, object],
    pattern: str,
    mode: SearchMode = SearchMode.GLOB,
    case_sensitive_override: bool | None = None,
) -> dict[str, object]:
    """Filter a {path: RecoverableFile} dict using the given mode and pattern.

    Preserves the original dict order (no re-ranking for glob/regex).
    For fuzzy mode, results are sorted by descending score.
    """
    if not pattern:
        return files

    case_sensitive = smart_case_sensitive(pattern, case_sensitive_override)

    if mode is SearchMode.FUZZY:
        scored = []
        for path, rf in files.items():
            score = match_path(path, pattern, mode, case_sensitive)
            if score > 0:
                scored.append((score, path, rf))
        scored.sort(key=lambda x: x[0], reverse=True)
        return {path: rf for _, path, rf in scored}

    return {
        path: rf
        for path, rf in files.items()
        if match_path(path, pattern, mode, case_sensitive) > 0
    }


def filter_by_timestamp(
    files: dict[str, RecoverableFile],
    before_ts: str,
) -> dict[str, RecoverableFile]:
    """Return files with only operations at or before the cutoff timestamp.

    Each returned RecoverableFile has its operations trimmed to only those
    with timestamp <= before_ts. Files with no qualifying operations are
    excluded. Short-circuits on empty before_ts.
    """
    if not before_ts:
        return files

    result = {}
    for path, rf in files.items():
        trimmed_ops = [op for op in rf.operations if op.timestamp <= before_ts]
        if trimmed_ops:
            result[path] = RecoverableFile(path, trimmed_ops)
    return result
