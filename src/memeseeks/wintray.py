"""An icon in the Windows notification area with a menu, on the Windows API alone (ctypes): nothing extra to ship.

Tray(icon.ico, tip, [(label, action), ...]).run() blocks until 退出. A click runs the first item; a right click shows
the menu; an item whose action is None quits. The icon comes back by itself when Explorer restarts.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY, WM_CLOSE, WM_COMMAND, WM_NULL = 0x0002, 0x0010, 0x0111, 0x0000
WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
WM_TRAY = 0x8000 + 1  # WM_APP + 1: what the icon sends its window
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
MF_STRING, MF_SEPARATOR = 0x0, 0x800
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x20, 0x100, 0x80
FIRST_ITEM = 1000
CLASS_NAME = "memeseeks-tray"


_mutex = None


def first_instance(name: str) -> bool:
    """Whether no other process holds this name: two quick clicks must not start two servers, which then fight
    over the model downloads' locks and neither loads. The name is held until the process ends."""
    global _mutex
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _mutex = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]


def _signatures() -> None:
    sig = [
        (user32.RegisterClassW, wintypes.ATOM, [ctypes.POINTER(WNDCLASSW)]),
        (user32.CreateWindowExW, wintypes.HWND, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                                 wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]),
        (user32.DefWindowProcW, LRESULT, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
        (user32.DestroyWindow, wintypes.BOOL, [wintypes.HWND]),
        (user32.GetMessageW, wintypes.BOOL, [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]),
        (user32.TranslateMessage, wintypes.BOOL, [ctypes.POINTER(wintypes.MSG)]),
        (user32.DispatchMessageW, LRESULT, [ctypes.POINTER(wintypes.MSG)]),
        (user32.PostQuitMessage, None, [ctypes.c_int]),
        (user32.PostMessageW, wintypes.BOOL, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
        (user32.RegisterWindowMessageW, wintypes.UINT, [wintypes.LPCWSTR]),
        (user32.LoadImageW, wintypes.HANDLE, [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                              ctypes.c_int, wintypes.UINT]),
        (user32.CreatePopupMenu, wintypes.HMENU, []),
        (user32.AppendMenuW, wintypes.BOOL, [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]),
        (user32.TrackPopupMenu, wintypes.BOOL, [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                wintypes.HWND, wintypes.LPVOID]),
        (user32.DestroyMenu, wintypes.BOOL, [wintypes.HMENU]),
        (user32.GetCursorPos, wintypes.BOOL, [ctypes.POINTER(wintypes.POINT)]),
        (user32.SetForegroundWindow, wintypes.BOOL, [wintypes.HWND]),
        (kernel32.GetModuleHandleW, wintypes.HMODULE, [wintypes.LPCWSTR]),
        (shell32.Shell_NotifyIconW, wintypes.BOOL, [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]),
    ]
    for fn, restype, argtypes in sig:
        fn.restype, fn.argtypes = restype, argtypes


class Tray:
    def __init__(self, icon_path, tip: str, items: list, hint: tuple[str, str] | None = None):
        _signatures()
        self.items, self.hint = items, hint
        self._proc = WNDPROC(self._window_proc)  # kept alive for as long as the window
        instance = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW(lpfnWndProc=self._proc, hInstance=instance, lpszClassName=CLASS_NAME)
        user32.RegisterClassW(ctypes.byref(cls))
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")  # before any message arrives
        # a hidden top-level window, not a message-only one: only top-level windows hear that Explorer restarted
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, tip, 0, 0, 0, 0, 0, None, None, instance, None)
        icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        self.nid = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self.hwnd, uID=1,
                                   uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP, uCallbackMessage=WM_TRAY, hIcon=icon)
        self.nid.szTip = tip[:127]
        self.added = False

    def _add(self) -> bool:
        self.added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid)))
        return self.added

    def show_hint(self, title: str, text: str) -> None:
        """A notification from the icon (Windows 10/11 shows it as a toast)."""
        self.nid.uFlags |= NIF_INFO
        self.nid.szInfoTitle, self.nid.szInfo = title[:63], text[:255]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))
        self.nid.uFlags &= ~NIF_INFO

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        for k, (label, _) in enumerate(self.items):
            user32.AppendMenuW(menu, MF_STRING, FIRST_ITEM + k, label)
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)  # or the menu will not close when you click elsewhere
        chosen = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD | TPM_NONOTIFY,
                                       point.x, point.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if chosen:
            self._do(chosen - FIRST_ITEM)

    def _do(self, k: int) -> None:
        if not 0 <= k < len(self.items):
            return
        action = self.items[k][1]
        if action is None:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        else:
            try:
                action()
            except Exception:  # an item must never take the icon down
                pass

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam == WM_LBUTTONUP:
                self._do(0)
            elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._menu()
            return 0
        if msg == self._taskbar_created and self._taskbar_created:  # Explorer restarted: put the icon back
            self._add()
            return 0
        if msg == WM_CLOSE:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> None:
        if not self._add():
            print(f"the notification-area icon could not be added (error {ctypes.get_last_error()})")
        if self.hint:
            self.show_hint(*self.hint)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
