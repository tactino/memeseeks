"""Optional online meme search. Off unless configured; only official APIs.

Turning it on sends the search words to the provider. Images are relayed through the local server,
which fetches only URLs that a provider returned for an earlier search (never a client-supplied URL).
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MAX_IMAGE_BYTES = 15 * 1024 * 1024
USER_AGENT = "memeseeks (+https://github.com/tactino/memeseeks)"


class OnlineError(Exception):
    pass


@dataclass(frozen=True)
class OnlineHit:
    id: str
    title: str
    thumb: str
    full: str
    provider: str


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # providers put the reason in a JSON body
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            raise OnlineError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OnlineError(f"cannot reach {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


def http_download(url: str, max_bytes: int) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(max_bytes + 1)
            ctype = r.headers.get_content_type()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OnlineError(f"cannot download image: {exc}") from exc
    if len(data) > max_bytes:
        raise OnlineError("image too large")
    return data, ctype


def _image_urls(node) -> list[tuple[int, str]]:
    """Every (width, url) that looks like an image anywhere inside a result item."""
    found = []
    if isinstance(node, dict):
        url = node.get("url")
        if isinstance(url, str) and url.startswith("https://") and url.lower().split("?")[0].endswith(IMAGE_SUFFIXES):
            found.append((int(node.get("width") or 0), url))
        for value in node.values():
            found += _image_urls(value)
    elif isinstance(node, list):
        for value in node:
            found += _image_urls(value)
    return found


class KlipyMemes:
    """KLIPY's Meme API (free; get a key at https://klipy.com/developers)."""

    name = "KLIPY"
    BASE = "https://api.klipy.com/api/v1"

    def __init__(self, key: str, fetch=http_get_json, customer_id: str = "memeseeks-local", locale: str = "zh_CN"):
        self.key, self.fetch, self.customer_id, self.locale = key, fetch, customer_id, locale

    def search(self, query: str, n: int = 20) -> list[OnlineHit]:
        params = urllib.parse.urlencode({"q": query, "per_page": n, "page": 1,
                                         "customer_id": self.customer_id, "locale": self.locale})
        body = self.fetch(f"{self.BASE}/{urllib.parse.quote(self.key)}/static-memes/search?{params}")
        if not body.get("result", True):
            messages = body.get("errors", {}).get("message", ["unknown error"])
            raise OnlineError("KLIPY said: " + "; ".join(map(str, messages)))
        data = body.get("data", {})
        items = data.get("data", data) if isinstance(data, dict) else data
        hits = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or item.get("type") == "ad":
                continue
            urls = sorted(_image_urls(item))
            if not urls:
                continue
            thumb = next((u for w, u in urls if w >= 200), urls[0][1])
            hits.append(OnlineHit(id=f"klipy:{item.get('id') or item.get('slug')}", title=str(item.get("title") or ""),
                                  thumb=thumb, full=urls[-1][1], provider=self.name))
        return hits


class OnlineService:
    """Searches one source and relays its images; remembers which URLs each hit may fetch."""

    def __init__(self, source, download=http_download, remember: int = 2000):
        self.source, self.download = source, download
        self._urls: OrderedDict[str, dict[str, str]] = OrderedDict()
        self._remember = remember
        self._lock = threading.Lock()

    @property
    def provider(self) -> str:
        return self.source.name

    def search(self, query: str, n: int = 20) -> list[OnlineHit]:
        hits = self.source.search(query, n=n)
        with self._lock:
            for h in hits:
                self._urls[h.id] = {"thumb": h.thumb, "full": h.full}
                self._urls.move_to_end(h.id)
            while len(self._urls) > self._remember:
                self._urls.popitem(last=False)
        return hits

    def image(self, hit_id: str, variant: str) -> tuple[bytes, str] | None:
        with self._lock:
            url = self._urls.get(hit_id, {}).get(variant)
        if url is None:
            return None
        data, ctype = self.download(url, MAX_IMAGE_BYTES)
        if not ctype.startswith("image/"):
            raise OnlineError(f"not an image ({ctype})")
        return data, ctype
