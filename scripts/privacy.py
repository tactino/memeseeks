"""Find maintainer-specific strings (hosts, account dirs, local paths) in files that would be published."""

from __future__ import annotations

import re

# Parts of example/default values that are ordinary words, not identifying.
GENERIC = {"memeseeks", "private", "memes", "data", "path", "work", "home", "users", "code", "desktop"}


def denylist_parts(values) -> set[str]:
    """Identifying pieces of configured values: 6+ letters, or 4+ characters with a digit."""
    parts = set()
    for value in values:
        for part in re.split(r"[\\/:\-_.\s]+", value or ""):
            if part.lower() in GENERIC:
                continue
            if len(part) >= 6 or (len(part) >= 4 and any(c.isdigit() for c in part)):
                parts.add(part)
    return parts


def find_leaks(texts: dict[str, str], parts: set[str]) -> dict[str, list[str]]:
    """Whole-word, case-insensitive matches of `parts` in each text."""
    patterns = {p: re.compile(rf"(?<![0-9A-Za-z]){re.escape(p)}(?![0-9A-Za-z])", re.IGNORECASE) for p in parts}
    leaks = {}
    for name, text in texts.items():
        found = sorted(p for p, rx in patterns.items() if rx.search(text))
        if found:
            leaks[name] = found
    return leaks
