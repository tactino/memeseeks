"""迷因捕手 in a window of its own (Windows): the web app in the WebView2 control Windows has (the one Edge is made
of), titled 迷因捕手 with the cat as its icon and no browser around it.

Closing the window only hides it: memeseeks keeps running in the notification area and the cat brings the window
back. Links that open a new page (a meme's source, installing the browser script) go to the system browser.
Without pywebview or WebView2 the tray opens the web app in the browser instead (tray.py).

The window opens at once on a splash (splash.py) and moves on to the web app when the server answers. On Windows 11
its title bar and border take the page's paper and ink, and follow the theme (the page tells it, see app.js).
"""

from __future__ import annotations

import threading
from pathlib import Path

TITLE = "迷因捕手"
# COLORREF (0x00BBGGRR) of the title bar and of its text and the border, per theme: paper and ink (tokens.css)
CAPTION = {"paper": (0xE4EFF3, 0x111416), "night": (0x131617, 0xD6E6ED)}


def paint_title_bar(hwnd: int, theme: str) -> None:
    """Windows 11 draws the title bar and the border in these colours; earlier Windows ignores it."""
    import ctypes
    from ctypes import wintypes

    back, ink = CAPTION.get(theme, CAPTION["paper"])
    for attribute, colour in ((35, back), (36, ink), (34, ink)):  # DWMWA_CAPTION_COLOR, _TEXT_COLOR, _BORDER_COLOR
        value = ctypes.c_uint32(colour)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(value), 4)


class _PageApi:
    """What the page may ask of the window (window.pywebview.api): only to follow its theme."""

    def __init__(self, paint):
        self.theme = lambda name: paint(name if name in CAPTION else "paper")


def available() -> bool:
    try:
        import webview  # noqa: F401  (pywebview, with pythonnet for WebView2)
    except Exception:
        return False
    return True


class AppWindow:
    def __init__(self, url: str, icon: Path, storage: Path, on_hidden=None, splash: str | None = None,
                 theme: str = "paper"):
        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True  # 保存
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        self.webview, self.url, self.icon, self.storage, self.on_hidden = webview, url, icon, storage, on_hidden
        self.quitting = False
        self.hidden_once = threading.Event()
        self.hwnd, self.theme = None, theme
        self.window = webview.create_window(TITLE, None if splash else url, html=splash, width=1280, height=860,
                                            min_size=(420, 560), background_color="#171613" if theme == "night" else "#F3EFE4",
                                            text_select=True, js_api=_PageApi(self._paint))
        self.window.events.closing += self._closing
        self.window.events.shown += self._shown

    def _shown(self):
        try:
            self.hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:  # another backend: keep the system's title bar
            return
        self._paint(self.theme)

    def _paint(self, theme: str) -> None:
        self.theme = theme
        if self.hwnd:
            try:
                paint_title_bar(self.hwnd, theme)
            except Exception:
                pass

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

    def run(self, until_up=None) -> None:
        """On the main thread; returns once the window is destroyed (退出). until_up(), if given, waits for the server
        (True once it answers); meanwhile the window shows the splash it was made with."""
        self.storage.mkdir(parents=True, exist_ok=True)
        self.webview.start(self._open if until_up else None, (until_up,) if until_up else (), gui="edgechromium",
                           private_mode=False, storage_path=str(self.storage), icon=str(self.icon))

    def _open(self, until_up) -> None:
        if until_up():
            self.window.load_url(self.url)
        else:
            self.window.evaluate_js('document.getElementById("status").textContent = '
                                    '"迷因捕手没能启动。重新打开一次试试；还不行的话，看看图库文件夹里的 memeseeks.log。"')
