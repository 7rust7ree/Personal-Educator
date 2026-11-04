"""Run Personal Educator as a desktop app: local server + native window (macOS / Windows).

    python -m backend.desktop
"""
import socket
import threading
import time
import urllib.request

import uvicorn
import webview

from . import config


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ClipboardApi:
    """System clipboard for the page (the window's web view can't read the clipboard itself)."""

    def copy(self, text: str) -> bool:
        try:
            import AppKit
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            return bool(pb.setString_forType_(text, AppKit.NSPasteboardTypeString))
        except ImportError:  # Windows / Linux
            return _tk_clipboard(text)

    def paste(self) -> str:
        try:
            import AppKit
            return AppKit.NSPasteboard.generalPasteboard().stringForType_(AppKit.NSPasteboardTypeString) or ""
        except ImportError:
            return _tk_clipboard()


def _tk_clipboard(text: str | None = None):
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    try:
        if text is None:
            try:
                return root.clipboard_get()
            except tkinter.TclError:
                return ""
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        return True
    finally:
        root.destroy()


def _wait_until_up(url: str, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url + "/api/usage", timeout=1)
            return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("server didn't start")


def main() -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config("backend.app:app", host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    _wait_until_up(url)

    webview.create_window("Personal Educator", url, width=1440, height=920, min_size=(900, 640),
                          background_color="#07080c", text_select=True, js_api=ClipboardApi())
    storage = config.DATA_DIR / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(storage))
    server.should_exit = True


if __name__ == "__main__":
    main()
