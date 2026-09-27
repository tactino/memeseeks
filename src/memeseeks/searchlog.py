"""搜索记录: what was searched, and which meme was then opened, copied, saved, shared, liked or put in an album.

Off unless the setting is on; kept in <library>/search-log.jsonl on this computer only. It is how search gets
measured on the searches people really make: a meme acted on after a search is the one that search was for, and a
search followed shortly by another one that found something says the first wording missed. `memeseeks searchlog`
sums it up and can write it out as a queries.csv for `memeseeks eval`.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path

FILE = "search-log.jsonl"
ACTIONS = ("open", "copy", "save", "share", "like", "album")
REPHRASE_SECONDS = 180  # a search with nothing acted on, then another within this long that found it


class SearchLog:
    def __init__(self, library_root, clock=time.time):
        self.path = Path(library_root) / FILE
        self.clock = clock
        self._lock = threading.Lock()

    def add(self, event: dict) -> None:
        line = json.dumps({"t": round(self.clock(), 3), **event}, ensure_ascii=False) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line)

    def search(self, query: str, matches: list[str], maybe: list[str]) -> None:
        self.add({"type": "search", "q": query, "matches": matches, "maybe": maybe})

    def act(self, query: str, image_id: str, action: str, rank: int | None, section: str | None) -> None:
        self.add({"type": "act", "q": query, "id": image_id, "action": action, "rank": rank, "section": section})

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:  # a line cut short by a crash: skip it
                continue
        return out


def sessions(events: list[dict]) -> list[dict]:
    """One row per search: its query, when, what it showed, and the memes acted on after it (before the next
    search of a different query)."""
    rows: list[dict] = []
    for e in events:
        if e.get("type") == "search":
            if rows and rows[-1]["q"] == e["q"] and e["t"] - rows[-1]["t"] < REPHRASE_SECONDS:
                continue  # the same search shown again (back to the results): one search
            rows.append({"q": e["q"], "t": e["t"], "matches": e.get("matches", []), "maybe": e.get("maybe", []),
                         "acted": []})
        elif e.get("type") == "act" and rows and rows[-1]["q"] == e.get("q"):
            if e["id"] not in rows[-1]["acted"]:
                rows[-1]["acted"].append(e["id"])
    return rows


def summary(events: list[dict]) -> dict:
    """Counts only (never the queries): how many searches found what they were for, and where it was."""
    rows = sessions(events)
    found = [r for r in rows if r["acted"]]
    first = [r["acted"][0] for r in found]
    in_matches = sum(i in r["matches"] for r, i in zip(found, first))
    top1 = sum((r["matches"] + r["maybe"])[:1] == [i] for r, i in zip(found, first))
    rephrased = sum(1 for a, b in zip(rows, rows[1:]) if not a["acted"] and b["acted"] and b["t"] - a["t"] < REPHRASE_SECONDS)
    return {"searches": len(rows), "found": len(found), "found_first": top1, "found_in_matches": in_matches,
            "found_in_maybe": len(found) - in_matches, "missed_then_rephrased": rephrased,
            "nothing_acted": len(rows) - len(found)}


def export(events: list[dict], relpath: dict[str, str], out: Path) -> int:
    """queries.csv for `memeseeks eval`: each search that found something, and each wording that missed a meme
    found right after under another, with the meme(s) it was for. Returns how many rows."""
    rows = sessions(events)
    wanted: dict[str, list[str]] = {}
    for r in rows:
        if r["acted"]:
            wanted.setdefault(r["q"], []).extend(i for i in r["acted"] if i not in wanted.get(r["q"], []))
    for a, b in zip(rows, rows[1:]):
        if not a["acted"] and b["acted"] and b["t"] - a["t"] < REPHRASE_SECONDS:
            wanted.setdefault(a["q"], []).extend(i for i in b["acted"][:1] if i not in wanted.get(a["q"], []))
    lines = [(q, ";".join(relpath[i] for i in ids if i in relpath)) for q, ids in wanted.items()]
    lines = [(q, files) for q, files in lines if files]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query", "expected"])
        w.writerows(lines)
    return len(lines)
