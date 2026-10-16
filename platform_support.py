"""Small OS-specific helpers for DeskLink's Windows/macOS client.

macOS access checks are best-effort preflights. No permissions are silently
changed; the user must approve them in macOS System Settings.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys


CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
APPLICATION_SERVICES = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
MAC_PRIVACY_PANES = {
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
}


def is_macos() -> bool:
    return sys.platform == "darwin"


def ui_font() -> str:
    return "Helvetica Neue" if is_macos() else "Segoe UI"


def mono_font() -> str:
    return "Menlo" if is_macos() else "Consolas"


def app_data_dir() -> Path:
    """User-writable OS-standard location, not a shared project .venv."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / "DeskLink"
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "DeskLink"
    return Path.home() / ".desklink"


def settings_file() -> Path:
    if sys.platform == "win32":
        # Preserve the settings location used by DeskLink 0.1.x.
        return Path(os.environ.get("APPDATA") or Path.home()) / "DeskLink" / "settings.json"
    return app_data_dir() / "settings.json"


def _native_bool(framework: str, symbol: str) -> bool | None:
    """Call a no-argument system permission function without third-party deps."""
    try:
        lib = ctypes.CDLL(framework)
        method = getattr(lib, symbol)
        method.argtypes = []
        method.restype = ctypes.c_bool
        return bool(method())
    except (AttributeError, OSError, ValueError):
        # Older macOS releases or missing native API: status is unknown.
        return None


def mac_permission_status() -> dict[str, bool | None]:
    if not is_macos():
        return {"screen": None, "accessibility": None}
    return {
        "screen": _native_bool(CORE_GRAPHICS, "CGPreflightScreenCaptureAccess"),
        "accessibility": _native_bool(APPLICATION_SERVICES, "AXIsProcessTrusted"),
    }


def request_screen_capture_permission() -> bool | None:
    """Prompt for screen capture only when the Mac user presses the UI button."""
    if not is_macos():
        return None
    return _native_bool(CORE_GRAPHICS, "CGRequestScreenCaptureAccess")


def open_mac_privacy_settings(kind: str) -> bool:
    if not is_macos() or kind not in MAC_PRIVACY_PANES:
        return False
    try:
        subprocess.Popen(["open", MAC_PRIVACY_PANES[kind]], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def missing_host_permissions(status: dict[str, bool | None]) -> tuple[str, ...]:
    """Only definite denials block an approved remote control session."""
    missing: list[str] = []
    if status.get("screen") is False:
        missing.append("Ekran ve Sistem Sesi Kaydı")
    if status.get("accessibility") is False:
        missing.append("Erişilebilirlik")
    return tuple(missing)
