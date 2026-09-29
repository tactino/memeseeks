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
APP_ID = "memeseeks.memeseeks"  # the taskbar's name for us; the installer's shortcuts carry the same


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
    """Whether search still has models to download (models/store.py says which)."""
    from .models.store import downloads

    hub = Path(hf_home or Path.home() / ".cache" / "huggingface") / "hub"
    return not all((hub / ("models--" + repo.replace("/", "--"))).is_dir() for repo in downloads())


def choose_mirror(env=os.environ, reachable=None) -> None:
    """Download the models from hf-mirror.com when Hugging Face cannot be reached quickly (usually: from China),
    as the install scripts do. Only asked when they still need downloading."""
    if env.get("HF_ENDPOINT") or not models_missing(env.get("HF_HOME")):
        return
    if not (reachable or _huggingface_answers)():
        env["HF_ENDPOINT"] = "https://hf-mirror.com"


def opener(url: str, open_url=webbrowser.open, clock=None, within: float = 2.0):
    """Opens the web app, once for a double click (Windows sends a double click as two clicks)."""
    import time

    clock = clock or time.monotonic
    last = [None]

    def open_once() -> None:
        now = clock()
        if last[0] is None or now - last[0] >= within:
            last[0] = now
            open_url(url)
    return open_once


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

    if sys.platform == "win32":
        from .wintray import app_id, first_instance, wake_other

        app_id(APP_ID)
        if not first_instance(f"Local\\memeseeks-tray-{args.port}"):  # already starting or running
            if not wake_other() and _answers(url):  # it shows its window, or else the browser
                webbrowser.open(url)
            return 0
    if _answers(url):  # already running (started some other way): a second click just opens it
        webbrowser.open(url)
        return 0
    home = default_home()
    if sys.stdout is None or sys.platform == "win32":  # pythonw: no console to write to
        _log_to(Path(home))
    choose_mirror()
    lib = Library(home)
    from .appwindow import available

    windowed = sys.platform == "win32" and available()
    serve = lambda: _serve(lib, Models(), "127.0.0.1", args.port, None,  # noqa: E731
                           online=os.environ.get("MEMESEEKS_ONLINE", "off"), open_browser=not windowed)
    if sys.platform != "win32":
        return serve()
    threading.Thread(target=serve, name="memeseeks-server", daemon=True).start()
    from .wintray import Tray

    icon = Path(__file__).parent / "web" / "icons" / "memeseeks.ico"
    hinted = Path(home) / ".tray-hinted"  # say once where it is, the first time it has no window
    if not windowed:
        hint = None if hinted.exists() else ("迷因捕手在这里", "点这只猫打开；右键可以退出。")
        hinted.touch()
        Tray(icon, "迷因捕手", [("打开迷因捕手", opener(url)), ("退出", None)], hint=hint).run()
        os._exit(0)  # 退出: the server thread and the indexer stop with the process, as closing the old window did
    run_windowed(url, icon, hinted, _answers, Path(home))


def run_windowed(url: str, icon: Path, hinted: Path, answers, home: Path | None = None) -> None:
    """The window on the main thread (WebView2 wants it there), the cat on a thread of its own. The window opens at
    once on a splash and moves on to the web app when the server answers."""
    import time

    from . import splash
    from .appwindow import AppWindow
    from .wintray import Tray

    def until_up() -> bool:
        deadline = time.monotonic() + 90  # a first start also waits for Windows to check the new files
        while not answers(url):
            if time.monotonic() > deadline:
                return False
            time.sleep(0.3)
        return True

    parts: dict = {}

    def hidden() -> None:
        if not hinted.exists() and "tray" in parts:
            hinted.touch()
            parts["tray"].show_hint("迷因捕手还在这里", "关掉窗口它也在右下角运行：点这只猫打开，右键可以退出。")

    looks = splash.looks(home)
    app = AppWindow(url, icon, storage=app_dir() / "webview-data", on_hidden=hidden, splash=splash.html(home),
                    theme=looks["theme"])

    def cat() -> None:
        # made on this thread: a window's messages go to the thread that made it, and this one waits for them
        parts["tray"] = Tray(icon, "迷因捕手", [("打开迷因捕手", opener(url, open_url=lambda _: app.show())),
                                               ("在浏览器里打开", opener(url)), ("退出", None)])
        parts["tray"].run()
        try:
            app.quit()  # 退出 from the cat's menu closes the window too
        except Exception:
            pass

    tray = threading.Thread(target=cat, name="memeseeks-tray", daemon=True)
    tray.start()
    try:
        app.run(until_up)
    except Exception as exc:  # no WebView2 after all: the browser, and the cat as before
        print(f"the window could not open ({type(exc).__name__}: {exc}); using the browser")
        parts["tray"].items[0] = ("打开迷因捕手", opener(url))
        webbrowser.open(url)
        tray.join()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
