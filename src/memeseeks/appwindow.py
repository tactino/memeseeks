"""迷因捕手 in a window of its own (Windows): the web app in the WebView2 control Windows has (the one Edge is made
of), titled 迷因捕手 with the cat as its icon and no browser around it.

Closing the window only hides it: memeseeks keeps running in the notification area and the cat brings the window
back. Links that open a new page (a meme's source, installing the browser script) go to the system browser.
Without pywebview or WebView2 the tray opens the web app in the browser instead (tray.py).
"""

from __future__ import annotations

import threading
from pathlib import Path

TITLE = "迷因捕手"


def available() -> bool:
    try:
        import webview  # noqa: F401  (pywebview, with pythonnet for WebView2)
    except Exception:
        return False
    return True


class AppWindow:
    def __init__(self, url: str, icon: Path, storage: Path, on_hidden=None):
        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True  # 保存
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        self.webview, self.icon, self.storage, self.on_hidden = webview, icon, storage, on_hidden
        self.quitting = False
        self.hidden_once = threading.Event()
        self.window = webview.create_window(TITLE, url, width=1280, height=860, min_size=(420, 560),
                                            background_color="#F3EEE4", text_select=True)
        self.window.events.closing += self._closing

    def _closing(self):
        if self.quitting:
            return True
        self.window.hide()  # keep running in the notification area
        if self.on_hidden and not self.hidden_once.is_set():
            self.hidden_once.set()
            self.on_hidden()
        return False  # cancel the close

    def show(self) -> None:
        self.window.show()
        self.window.restore()

    def quit(self) -> None:
        self.quitting = True
        self.window.destroy()

    def run(self) -> None:
        """On the main thread; returns once the window is destroyed (退出)."""
        self.storage.mkdir(parents=True, exist_ok=True)
        self.webview.start(gui="edgechromium", private_mode=False, storage_path=str(self.storage), icon=str(self.icon))
