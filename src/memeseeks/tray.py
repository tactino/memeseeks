"""迷因捕手 as a desktop app: the server in the background, the cat in the notification area, no console window.

  pythonw -m memeseeks.tray [--config launcher.json]

What the Windows installer's shortcuts run. launcher.json (next to the app's python folder, written by the
installer) says where the library and the models live: {"library": ..., "models": ...}. Clicking the cat opens the
web app; its menu has 打开迷因捕手 and 退出. A second start only opens the browser. Output goes to memeseeks.log in
the library folder, since there is no window to show it. Elsewhere than Windows it serves without an icon.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

PORT = 8765
MODELS = ("BAAI--bge-m3", "OFA-Sys--chinese-clip-vit-large-patch14-336px")  # the ones search needs downloaded


def app_dir() -> Path:
    """The installed app: python\\pythonw.exe lives one folder down."""
    return Path(sys.executable).resolve().parent.parent


def read_config(path: Path) -> dict:
    try:
        found = json.loads(path.read_text(encoding="utf-8-sig"))  # the installer writes UTF-8 with a BOM
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in found.items() if k in ("library", "models") and isinstance(v, str) and v.strip()}


def apply_config(config: dict, env=os.environ) -> None:
    """Where the library and the models live, for the rest of the app (it reads these on its own)."""
    if config.get("library"):
        env["MEMESEEKS_HOME"] = config["library"]
    if config.get("models"):
        env["HF_HOME"] = config["models"]


def models_missing(hf_home: str | None) -> bool:
    hub = Path(hf_home or Path.home() / ".cache" / "huggingface") / "hub"
    return not all((hub / f"models--{m}").is_dir() for m in MODELS)


def choose_mirror(env=os.environ, reachable=None) -> None:
    """Download the models from hf-mirror.com when Hugging Face cannot be reached quickly (usually: from China),
    as the install scripts do. Only asked when they still need downloading."""
    if env.get("HF_ENDPOINT") or not models_missing(env.get("HF_HOME")):
        return
    if not (reachable or _huggingface_answers)():
        env["HF_ENDPOINT"] = "https://hf-mirror.com"


def _huggingface_answers() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(urllib.request.Request("https://huggingface.co/api/models/BAAI/bge-m3", method="HEAD"),
                               timeout=6)
        return True
    except OSError:
        return False


def _log_to(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    log = open(folder / "memeseeks.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - for the process's life
    sys.stdout = sys.stderr = log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="迷因捕手 in the notification area")
    ap.add_argument("--config", type=Path, help="launcher.json (default: next to the app's python folder)")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    url = f"http://127.0.0.1:{args.port}/"
    apply_config(read_config(args.config or app_dir() / "launcher.json"))

    from .cli import _answers, _serve
    from .library import Library, Models, default_home

    if _answers(url):  # already running: a second click just opens it
        webbrowser.open(url)
        return 0
    home = default_home()
    if sys.stdout is None or sys.platform == "win32":  # pythonw: no console to write to
        _log_to(Path(home))
    choose_mirror()
    lib = Library(home)
    serve = lambda: _serve(lib, Models(), "127.0.0.1", args.port, None,  # noqa: E731
                           online=os.environ.get("MEMESEEKS_ONLINE", "off"), open_browser=True)
    if sys.platform != "win32":
        return serve()
    threading.Thread(target=serve, name="memeseeks-server", daemon=True).start()
    from .wintray import Tray

    icon = Path(__file__).parent / "web" / "icons" / "memeseeks.ico"
    hinted = Path(home) / ".tray-hinted"  # say once where it went, since it has no window
    hint = None if hinted.exists() else ("迷因捕手在这里", "点这只猫打开；右键可以退出。")
    hinted.touch()
    Tray(icon, "迷因捕手", [("打开迷因捕手", lambda: webbrowser.open(url)), ("退出", None)], hint=hint).run()
    os._exit(0)  # 退出: the server thread and the indexer stop with the process, as closing the old window did


if __name__ == "__main__":
    raise SystemExit(main())
