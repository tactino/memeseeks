"""手机访问: the web app on this computer's LAN address as well, behind a token (docs/design.md, Settings).

Off by default. Turned on (from the settings page on this computer), a second server listens on one LAN
address, on the same port, and every /api/ request there needs the token; the settings page shows it as a QR
code for the phone to scan. The first server stays on 127.0.0.1 and needs nothing, as before. The choice
(on or off, and which address) is kept in the library, so it survives a restart.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
from pathlib import Path

from .index import _atomic_write_text
from .inbox import persistent_secret

TOKEN_FILE = "phone-token"
STATE_FILE = "phone.json"


def rank_addresses(found: list[str], default: str | None) -> list[str]:
    """Private IPv4 addresses a phone on the same Wi-Fi could reach, likeliest first: home routers hand out
    192.168.x.x, then 10.x (often a VPN), then 172.16-31.x (often a virtual switch); within each, the
    address of the default route first."""
    def kind(ip: str) -> int | None:
        try:
            a = ipaddress.IPv4Address(ip)
        except ValueError:
            return None
        if a.is_loopback or a.is_link_local or not a.is_private:
            return None
        return 0 if ip.startswith("192.168.") else 1 if ip.startswith("10.") else 2
    unique: list[str] = list(dict.fromkeys([*([default] if default else []), *found]))
    usable = [ip for ip in unique if kind(ip) is not None]
    return sorted(usable, key=lambda ip: (kind(ip), ip != default))


def lan_addresses() -> list[str]:
    default = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # TEST-NET-1: only picks the route, sends nothing
            default = s.getsockname()[0]
    except OSError:
        pass
    try:
        found = [str(info[4][0]) for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        found = []
    return rank_addresses(found, default)


def _start_uvicorn(app, host: str, port: int):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="memeseeks-phone", daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:  # uvicorn gives up on a port it cannot bind
        server.should_exit = True
        raise OSError(f"没能在 {host}:{port} 上开启（这个端口可能被别的程序占用了）")
    return server, thread


def _stop_uvicorn(handle) -> None:
    server, thread = handle
    server.should_exit = True
    server.force_exit = True  # don't wait for a phone's idle keep-alive connections to go away
    thread.join(5)


class Phone:
    def __init__(self, library_root, port: int, make_app, start=_start_uvicorn, stop=_stop_uvicorn,
                 addresses=lan_addresses):
        self.root, self.port, self.make_app = Path(library_root), port, make_app
        self._start, self._stop, self._addresses = start, stop, addresses
        self._lock = threading.Lock()
        self._handle = None
        self.address: str | None = None
        self.error: str | None = None

    # ---- what is kept in the library ----
    @property
    def token(self) -> str:
        return persistent_secret(self.root / TOKEN_FILE)

    def _saved(self) -> dict:
        try:
            return json.loads((self.root / STATE_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, on: bool, address: str | None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(self.root / STATE_FILE, json.dumps({"version": 1, "on": on, "address": address}))

    # ---- turning it on and off ----
    def resume(self) -> None:
        """At start-up: on again if it was on when the app last ran."""
        saved = self._saved()
        if saved.get("on"):
            self.set(True, saved.get("address"))

    def set(self, on: bool, address: str | None = None) -> dict:
        with self._lock:
            self._close()
            self.error = None
            if on:
                found = self._addresses()
                chosen = address if address in found else (found[0] if found else None)
                if chosen is None:
                    self.error = "没找到这台电脑的局域网地址：它连上 Wi-Fi 或网线了吗？"
                else:
                    try:
                        self._handle = self._start(self.make_app(self.token), chosen, self.port)
                        self.address = chosen
                    except OSError as exc:
                        self.error = str(exc)
            self._save(on, address or self.address or self._saved().get("address"))  # remembered while off
        return self.status(local=True)

    def rotate(self) -> dict:
        """A new token: every phone that scanned the old code has to scan again."""
        (self.root / TOKEN_FILE).unlink(missing_ok=True)
        return self.set(True, self.address) if self._handle else self.status(local=True)

    def close(self) -> None:
        with self._lock:
            self._close()

    def _close(self) -> None:
        if self._handle is not None:
            self._stop(self._handle)
        self._handle, self.address = None, None

    def url(self) -> str | None:
        return f"http://{self.address}:{self.port}/?token={self.token}" if self._handle and self.address else None

    def status(self, local: bool) -> dict:
        """The link (with the token) only for this computer; a phone sees that it is on, nothing more."""
        on = bool(self._saved().get("on"))
        found = {"available": True, "on": on, "running": self._handle is not None, "error": self.error}
        if local:
            found.update(url=self.url(), address=self.address, addresses=self._addresses() if on else [])
        return found
