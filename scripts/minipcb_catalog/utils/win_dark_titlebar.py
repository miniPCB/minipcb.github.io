# minipcb_catalog/utils/win_dark_titlebar.py
"""
Enable dark titlebar on Windows 10 1809+ via DwmSetWindowAttribute.

This is a best-effort; it no-ops on non-Windows or older Windows.
Call enable_dark_titlebar(window) *after* window.show().
"""

from __future__ import annotations

import sys

def enable_dark_titlebar(qwidget) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(qwidget.winId())  # HWND
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # 20 on 1903+, 19 on 1809
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19

        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        def _set(attr: int, value: int) -> bool:
            val = wintypes.BOOL(value)
            res = dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(attr),
                ctypes.byref(val),
                ctypes.sizeof(val),
            )
            return res == 0

        if not _set(DWMWA_USE_IMMERSIVE_DARK_MODE, 1):
            _set(DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
    except Exception:
        # best-effort; silently ignore if it fails
        pass
