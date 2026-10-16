"""Start DeskLink without a shared .venv directory on Windows and macOS.

Third-party packages go into separate, OS-specific per-role folders under the
user's app-data directory; the system Python installation is left untouched.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

from platform_support import app_data_dir, is_macos

ROOT = Path(__file__).resolve().parent
MODES = {
    "client": {
        "requirements": "requirements-client.txt",
        "script": "desktop.py",
        "imports": ("tkinter", "PIL", "mss", "pynput", "websockets"),
        "log": "DeskLink-baslatma-log.txt",
    },
    "server": {
        "requirements": "requirements-server.txt",
        "script": "relay_server.py",
        "imports": ("websockets",),
        "log": "DeskLink-sunucu-log.txt",
    },
}


class Reporter:
    def __init__(self, mode: str, base_dir: Path):
        file_name = MODES[mode]["log"]
        candidates = [ROOT / file_name, base_dir / "logs" / file_name]
        self.log_path = None
        self.file = None
        for candidate in candidates:
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                self.file = candidate.open("w", encoding="utf-8", buffering=1)
                self.log_path = candidate
                break
            except OSError:
                pass
        if self.file is None:
            raise RuntimeError("Hata gunlugu icin yazilabilir klasor bulunamadi.")

    def say(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.file.write(msg + "\n")

    def close(self) -> None:
        self.file.close()


def local_data_dir() -> Path:
    return app_data_dir()


def target_dir(base_dir: Path, mode: str) -> Path:
    tag = f"py{sys.version_info.major}{sys.version_info.minor}-{platform.machine().lower()}"
    return base_dir / "packages" / tag / mode


def runtime_env(target: Path) -> dict[str, str]:
    env = os.environ.copy()
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(target) + (os.pathsep + old if old else "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def import_command(mode: str) -> list[str]:
    lines = ["import importlib.metadata as metadata", "import re"]
    lines.extend("import " + module for module in MODES[mode]["imports"])
    constraints = [("websockets", (15, 0, 0), (18, 0, 0))]
    if mode == "client":
        constraints.extend([
            ("Pillow", (11, 0, 0), (13, 0, 0)),
            ("mss", (10, 2, 0), (12, 0, 0)),
            ("pynput", (1, 7, 7), (2, 0, 0)),
        ])
    lines.extend([
        f"for dist, lower, upper in {constraints!r}:",
        "    version = metadata.version(dist)",
        r"    match = re.match(r'(\d+)\.(\d+)(?:\.(\d+))?', version)",
        "    if not match:",
        "        raise RuntimeError(f'{dist}: anlasilamayan surum {version}')",
        "    parts = [int(n) for n in match.groups() if n is not None]",
        "    parts += [0] * (3 - len(parts))",
        "    if not (lower <= tuple(parts) < upper):",
        "        raise RuntimeError(f'{dist}: uyumsuz surum {version}; guncelleme gerekli')",
    ])
    return [sys.executable, "-c", "\n".join(lines)]


def imports_ok(mode: str, env: dict[str, str]) -> tuple[bool, str]:
    proc = subprocess.run(import_command(mode), cwd=str(ROOT), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace", check=False)
    return proc.returncode == 0, proc.stdout.strip()


def run_stream(cmd: list[str], reporter: Reporter, env: dict[str, str]) -> int:
    reporter.say("Komut: " + " ".join(str(x) for x in cmd))
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                bufsize=1)
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                reporter.say(line.rstrip("\r\n"))
            return proc.wait()
        except KeyboardInterrupt:
            reporter.say("Durdurma istegi alindi.")
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return 130
        finally:
            if proc.stdout:
                proc.stdout.close()
    except OSError as exc:
        reporter.say(f"Komut baslatilamadi: {exc}")
        return 1


@contextmanager
def installation_lock(base_dir: Path, mode: str, reporter: Reporter):
    """Keep two concurrently opened clients from installing in the same folder."""
    lock_folder = base_dir / "locks"
    lock_folder.mkdir(parents=True, exist_ok=True)
    with (lock_folder / f"{mode}.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        acquired = False
        for attempt in range(600):
            try:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, BlockingIOError):
                if attempt == 0:
                    reporter.say("Baska DeskLink kurulumu bitene kadar bekleniyor...")
                if attempt % 20 == 19:
                    reporter.say("Kurulumun bitmesi bekleniyor...")
                time.sleep(0.5)
        if not acquired:
            raise TimeoutError("Baska bir DeskLink kurulumu 5 dakika icinde tamamlanmadi.")
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def ensure_deps(mode: str, base_dir: Path, reporter: Reporter) -> tuple[Path, dict[str, str]]:
    target = target_dir(base_dir, mode)
    target.mkdir(parents=True, exist_ok=True)
    env = runtime_env(target)
    with installation_lock(base_dir, mode, reporter):
        if mode == "client":
            tk_check = subprocess.run([sys.executable, "-c", "import tkinter"],
                                      cwd=str(ROOT), env=env, capture_output=True,
                                      text=True, errors="replace", check=False)
            if tk_check.returncode != 0:
                instructions = (
                    "macOS: Tkinter eksik. Python.org resmi macOS Python kurulumunu kullanin "
                    "veya Homebrew python-tk paketini yukleyin."
                    if is_macos() else
                    "Windows: Python kurulumunu Onar/Modify ile acip tcl/tk and IDLE bilesenini yukleyin."
                )
                raise RuntimeError(instructions + "\n" + tk_check.stdout + tk_check.stderr)
        ok, detail = imports_ok(mode, env)
        if ok:
            reporter.say("Gerekli kutuphaneler hazir; kurulum atlandi.")
            return target, env
        reporter.say("Eksik kutuphane bulundu. Ilk acilista internet gereklidir.")
        if detail:
            reporter.say("Ilk kontrol: " + detail.splitlines()[-1])
        pip_check = subprocess.run([sys.executable, "-m", "pip", "--version"],
                                   cwd=str(ROOT), env=env, capture_output=True,
                                   text=True, errors="replace", check=False)
        if pip_check.returncode != 0:
            reporter.say("pip yok; Python ensurepip ile onarilmaya calisiliyor...")
            if run_stream([sys.executable, "-m", "ensurepip", "--upgrade", "--user"],
                          reporter, env) != 0:
                raise RuntimeError("pip bulunamadi ve ensurepip de calismadi. Python kurulumunu onarin.")
        requirement_path = ROOT / MODES[mode]["requirements"]
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--upgrade", "--target", str(target), "-r", str(requirement_path)]
        reporter.say(f"Bagimliliklar kuruluyor: {target}")
        if run_stream(cmd, reporter, env) != 0:
            raise RuntimeError("Python kutuphaneleri kurulamadı. Yukaridaki pip hatasini inceleyin.")
        ok, detail = imports_ok(mode, env)
        if not ok:
            raise RuntimeError("Kurulumdan sonra kutuphane yuklenemedi:\n" + detail)
        reporter.say("Kutuphaneler dogrulandi.")
    return target, env


def main(mode: str) -> int:
    if sys.version_info < (3, 11):
        print("DeskLink icin Python 3.11 veya daha yeni surum gereklidir.")
        return 1
    base_dir = local_data_dir()
    try:
        reporter = Reporter(mode, base_dir)
    except (OSError, RuntimeError) as exc:
        print(f"Hata gunlugu olusturulamadi: {exc}")
        return 1
    try:
        reporter.say("=" * 61)
        reporter.say(f"DeskLink v0.2.0 - {'Windows/macOS istemcisi' if mode == 'client' else 'Test/relay sunucusu'}")
        reporter.say(f"Python: {sys.executable} ({sys.version.split()[0]})")
        reporter.say(f"Program klasoru: {ROOT}")
        reporter.say(f"Hata gunlugu: {reporter.log_path}")
        reporter.say("Bu surum paylasilan .venv klasorunu kullanmaz.")
        for required in (MODES[mode]["requirements"], MODES[mode]["script"]):
            if not (ROOT / required).is_file():
                raise FileNotFoundError(f"Eksik proje dosyasi: {required}. ZIP dosyasini tamamen ayiklayin.")
        target, env = ensure_deps(mode, base_dir, reporter)
        reporter.say(f"Bagimlilik klasoru: {target}")
        args = [sys.executable, str(ROOT / MODES[mode]["script"])]
        if mode == "server":
            if os.environ.get("DESKLINK_LAN_TEST") == "1":
                reporter.say("UYARI: LAN TEST SUNUCUSU ws:// ile sifresiz baglanti aciyor.")
                reporter.say("Yalnizca guvenilen yerel agda kullanin; portu internete yonlendirmeyin!")
                args.extend(["--bind", "0.0.0.0", "--port", "8765"])
            else:
                reporter.say("Yerel relay baslatiliyor: ws://127.0.0.1:8765")
                args.extend(["--bind", "127.0.0.1", "--port", "8765"])
        else:
            reporter.say("DeskLink arayuzu aciliyor...")
        code = run_stream(args, reporter, env)
        if code:
            reporter.say(f"HATA: Program cikis kodu: {code}")
        else:
            reporter.say("Program normal kapatildi.")
        return code
    except KeyboardInterrupt:
        reporter.say("Program kullanici tarafindan durduruldu.")
        return 130
    except Exception as exc:
        reporter.say(f"HATA: {exc}")
        reporter.say("Ayrintili hata kaydi:")
        for line in traceback.format_exc().splitlines():
            reporter.say(line)
        reporter.say("Hatayi ustte ve log dosyasinda gorebilirsiniz.")
        return 1
    finally:
        reporter.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeskLink Windows/macOS baslaticisi")
    parser.add_argument("mode", choices=sorted(MODES))
    args = parser.parse_args()
    sys.exit(main(args.mode))
