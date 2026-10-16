"""Compile DeskLink on the target build OS (NOT on the customer's PC).

Windows => dist/DeskLink.exe (onefile; bundled Python + dependencies)
macOS => dist/DeskLink.app (bundled Python; Intel or Apple Silicon native)
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "brand"

def command_for_platform(system: str | None = None) -> list[str]:
    system = system or sys.platform
    if system not in ("darwin", "win32"):
        raise RuntimeError("DeskLink .exe icin Windows; .app icin macOS uzerinde derleyin.")
    common = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
              "--windowed", "--name", "DeskLink",
              "--add-data", f"{ASSETS}{os.pathsep}brand",
              "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / ".pyinstaller"),
              "--specpath", str(ROOT)]
    if system == "win32":
        common += ["--onefile", "--icon", str(ASSETS / "DeskLink.ico"),
                   "--hidden-import", "mss.windows",
                   "--hidden-import", "pynput.keyboard._win32",
                   "--hidden-import", "pynput.mouse._win32"]
    else:
        common += ["--onedir", "--osx-bundle-identifier", "com.desklink.remote",
                   "--icon", str(ASSETS / "DeskLink.icns"),
                   "--hidden-import", "mss.darwin",
                   "--hidden-import", "pynput.keyboard._darwin",
                   "--hidden-import", "pynput.mouse._darwin"]
    common.append(str(ROOT / "desktop.py"))
    return common

if __name__ == "__main__":
    args = command_for_platform()
    print("Building DeskLink with Python included...", flush=True)
    subprocess.run(args, cwd=ROOT, check=True)
    print(f"Standalone package: {ROOT / 'dist' / ('DeskLink.exe' if sys.platform=='win32' else 'DeskLink.app')}")
