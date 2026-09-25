"""Optional online meme search. Off unless configured; only official APIs.

The server only hands the page its settings. The browser then asks the provider and loads the
images straight from it, as KLIPY's terms require (no relaying, caching, reordering or filtering).
Turning it on therefore sends the search words, and the viewer's IP, to the provider.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

CUSTOMER_ID_FILE = "online-customer-id"


@dataclass(frozen=True)
class OnlineConfig:
    provider: str
    search_url: str
    share_url: str
    attribution_url: str
    params: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        return {"enabled": True, **asdict(self)}


def klipy_config(key: str, customer_id: str, locale: str = "cn", content_filter: str = "medium",
                 per_page: int = 24) -> OnlineConfig:
    """KLIPY's Meme API (free; get a key at https://partner.klipy.com)."""
    base = f"https://api.klipy.com/api/v1/{key}/static-memes"
    return OnlineConfig(provider="KLIPY", search_url=f"{base}/search", share_url=f"{base}/share/",
                        attribution_url="https://klipy.com",
                        params={"customer_id": customer_id, "locale": locale,
                                "content_filter": content_filter, "per_page": per_page})


def customer_id_for(library_root: str | Path) -> str:
    """A random id per library, so the provider can tell users apart without learning who they are."""
    path = Path(library_root) / CUSTOMER_ID_FILE
    try:
        found = path.read_text(encoding="utf-8").strip()
        if len(found) >= 16:
            return found
    except OSError:
        pass
    new = secrets.token_hex(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return new
