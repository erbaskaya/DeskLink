"""DeskLink Windows/macOS client: visible, permission-based remote support."""
from __future__ import annotations

import asyncio
from io import BytesIO
import json
import ipaddress
import os
from pathlib import Path
import queue
import secrets
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from urllib.parse import urlsplit

from PIL import Image, ImageTk
from websockets.asyncio.client import connect

from control import InputController
from app_identity import APP_VERSION, DEFAULT_RELAY, bundled_brand_asset
from device_store import (
    get_or_create_identity, rotate_identity, get_server_url, put_server_url,
    contacts, save_contact, delete_contact, normalize_id,
)
from platform_support import (
    is_macos, mac_permission_status, missing_host_permissions,
    open_mac_privacy_settings, request_screen_capture_permission,
    settings_file, ui_font, mono_font,
)

APP_NAME = "DeskLink"
DEFAULT_URL = DEFAULT_RELAY
BG = "#0e1424"
CARD = "#182237"
INPUT_BG = "#0f1b31"
TEXT = "#eef4ff"
MUTED = "#a0abc0"
BLUE = "#4f8cff"
GREEN = "#22c55e"
RED = "#fb7185"


def set_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def config_path() -> Path:
    return settings_file()


def load_server_url() -> str:
    return get_server_url(DEFAULT_URL)


def save_server_url(url: str) -> None:
    put_server_url(url)


def is_trusted_lan_ip(host: str) -> bool:
    """Allow unencrypted WebSocket *only* for explicit RFC1918 LAN testing."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fd00::/8")
    return any(addr in ipaddress.ip_network(net) for net in networks)


def validate_server_url(url: str) -> tuple[bool, str]:
    try:
        u = urlsplit(url)
        if u.scheme not in ("ws", "wss") or not u.hostname or u.username or u.password or u.fragment:
            return False, "Sunucu adresi ws:// veya wss:// ile başlamalıdır."
        if u.scheme == "ws" and u.hostname.lower() not in ("localhost", "127.0.0.1", "::1") and not is_trusted_lan_ip(u.hostname):
            return False, "İnternette wss:// kullanın. Şifresiz ws:// yalnızca localhost veya özel ağ IP adresinde test içindir."
        if not u.port and u.netloc.endswith(":"):
            return False, "Port geçersiz."
        return True, ""
    except ValueError:
        return False, "Sunucu adresi geçersiz."


def monitor_to_dict(mon) -> dict[str, int]:
    return {
        field: int(mon[field] if isinstance(mon, dict) else getattr(mon, field))
        for field in ("left", "top", "width", "height")
    }


class NetworkManager:
    def __init__(self, url: str, ui_events: queue.Queue):
        self.url = url
        self.device_id, self.device_key = get_or_create_identity()
        self.device_label = "Mac bilgisayar" if is_macos() else "Windows bilgisayar" if sys.platform == "win32" else "Bilgisayar"
        self.ui_events = ui_events
        self.frames_lock = threading.Lock()
        self.last_frame: bytes | None = None
        self.loop = asyncio.new_event_loop()
        self.host_ws = None
        self.viewer_ws = None
        self.host_active = False
        self.viewer_active = False
        self.viewer_connecting = False
        self.running = True
        self.capture_task: asyncio.Task | None = None
        self.input_controller: InputController | None = None
        self.monitor_region = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        self.worker = threading.Thread(target=self._thread_run, daemon=True, name="desklink-network")
        self.worker.start()

    def _thread_run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self.host_loop())
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.close()

    def emit(self, action: str, payload=None) -> None:
        try:
            self.ui_events.put_nowait((action, payload))
        except queue.Full:
            pass

    def submit(self, coro) -> None:
        if self.running:
            try:
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            except RuntimeError:
                coro.close()
        else:
            coro.close()

    def consume_frame(self) -> bytes | None:
        with self.frames_lock:
            frame = self.last_frame
            self.last_frame = None
            return frame

    def change_url(self, new_url: str) -> None:
        self.submit(self._change_url(new_url))

    async def _change_url(self, new_url: str) -> None:
        self.url = new_url
        for ws in (self.viewer_ws, self.host_ws):
            if ws:
                await ws.close()

    async def host_loop(self) -> None:
        while self.running:
            self.emit("host_status", "Sunucuya bağlanıyor...")
            try:
                async with connect(self.url, compression=None, max_size=2_100_000, max_queue=4,
                                   ping_interval=20, ping_timeout=20, proxy=None) as ws:
                    self.host_ws = ws
                    await ws.send(json.dumps({"type": "register", "device_id": self.device_id,
                                              "device_key": self.device_key, "name": self.device_label}))
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            continue
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        kind = msg.get("type")
                        if kind == "registered":
                            self.emit("my_id", msg.get("id", ""))
                            self.emit("host_status", "Bağlı · bağlantı istekleri alınabilir")
                        elif kind == "id_conflict":
                            # Extremely rare (randomly generated ID already reserved).
                            self.device_id, self.device_key = rotate_identity()
                            await ws.send(json.dumps({"type": "register", "device_id": self.device_id,
                                                      "device_key": self.device_key, "name": self.device_label}))
                        elif kind == "connection_request":
                            self.emit("consent_request", msg)
                        elif kind == "request_canceled":
                            self.emit("request_canceled")
                        elif kind == "viewer_connected":
                            self.host_active = True
                            try:
                                self.input_controller = InputController()
                            except Exception as exc:
                                self.emit("host_status", f"Giriş denetimi açılamadı: {exc}")
                                await ws.send(json.dumps({"type": "disconnect"}))
                                continue
                            self.emit("host_active", True)
                            self.capture_task = asyncio.create_task(self.capture_stream(ws))
                        elif kind == "input" and self.host_active:
                            try:
                                if self.input_controller:
                                    self.input_controller.handle(msg, self.monitor_region)
                            except Exception as exc:
                                self.emit("host_status", f"Fare/klavye uyarısı: {exc}")
                        elif kind == "viewer_left":
                            await self.stop_capture()
                            self.emit("host_active", False)
                        elif kind == "error":
                            self.emit("host_status", msg.get("message", "Sunucu hatası"))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.emit("host_status", f"Bağlantı yok: {str(exc)[:115]}")
            finally:
                self.host_ws = None
                await self.stop_capture()
                self.emit("my_id", self.device_id)
                self.emit("host_active", False)
            if self.running:
                await asyncio.sleep(2.0)

    async def stop_capture(self) -> None:
        self.host_active = False
        if self.capture_task:
            t = self.capture_task
            self.capture_task = None
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        if self.input_controller:
            self.input_controller.release_all()
        self.input_controller = None

    async def capture_stream(self, ws) -> None:
        # Runs only AFTER local user approval. Only the primary display in MVP.
        from mss import MSS
        last_meta = None
        try:
            with MSS() as capturer:
                while self.running and self.host_active:
                    began = time.monotonic()
                    monitor = monitor_to_dict(capturer.primary_monitor)
                    self.monitor_region = monitor
                    if last_meta != monitor:
                        await ws.send(json.dumps({"type": "frame_meta", **monitor}))
                        last_meta = monitor
                    shot = capturer.grab(capturer.primary_monitor)
                    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    image.thumbnail((1600, 900), Image.Resampling.BILINEAR)
                    data = BytesIO()
                    image.save(data, format="JPEG", quality=52, optimize=False)
                    frame = data.getvalue()
                    if len(frame) <= 2_000_000:
                        await ws.send(frame)
                    await asyncio.sleep(max(0.035, 0.20 - (time.monotonic() - began)))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.emit("host_status", f"Ekran paylaşımı hatası: {exc}")
            try:
                await ws.send(json.dumps({"type": "disconnect"}))
            except Exception:
                pass

    def approve(self, token: str, allowed: bool) -> None:
        self.submit(self._approve(token, allowed))

    async def _approve(self, token: str, allowed: bool) -> None:
        if self.host_ws:
            await self.host_ws.send(json.dumps({"type": "approve", "token": token, "accept": allowed}))

    def disconnect_host(self) -> None:
        self.submit(self._disconnect_host())

    async def _disconnect_host(self) -> None:
        if self.host_ws and self.host_active:
            await self.host_ws.send('{"type":"disconnect"}')
            await self.stop_capture()
            self.emit("host_active", False)

    def connect_viewer(self, identifier: str) -> None:
        self.submit(self.viewer_loop(identifier))

    async def viewer_loop(self, identifier: str) -> None:
        if self.viewer_connecting or self.viewer_ws is not None:
            return
        self.viewer_connecting = True
        self.emit("viewer_status", "Bağlanıyor...")
        was_connected = False
        try:
            async with connect(self.url, max_size=2_100_000, max_queue=2, compression=None,
                               ping_interval=20, ping_timeout=20, proxy=None) as ws:
                self.viewer_ws = ws
                # Authenticate the requesting device separately. Only its ID is shown to
                # the host; the 256-bit device key is sent only to the relay over WSS.
                await ws.send(json.dumps({"type": "identify", "device_id": self.device_id,
                                          "device_key": self.device_key}))
                async for raw in ws:
                    if isinstance(raw, bytes):
                        if self.viewer_active and len(raw) <= 2_000_000:
                            with self.frames_lock:
                                self.last_frame = raw  # drop old frames instead of accumulating lag
                        continue
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    kind = msg.get("type")
                    if kind == "identified":
                        await ws.send(json.dumps({"type": "connect", "id": identifier}))
                    elif kind == "pending":
                        self.emit("viewer_status", "Karşı bilgisayara bildirim gönderildi; onay bekleniyor...")
                    elif kind == "accepted":
                        was_connected = True
                        self.viewer_active = True
                        self.emit("viewer_accepted", {"id": identifier, "name": msg.get("name", "")})
                        self.emit("viewer_open")
                        self.emit("viewer_status", "Uzak bağlantı aktif")
                    elif kind == "frame_meta":
                        self.emit("viewer_meta", msg)
                    elif kind in ("rejected", "closed", "error"):
                        default = {
                            "rejected": "Karşı bilgisayar bağlantıyı reddetti.",
                            "closed": "Bağlantı karşı taraftan kapatıldı.",
                            "error": "Sunucu bağlantı hatası.",
                        }[kind]
                        self.emit("viewer_error" if kind != "closed" else "viewer_status",
                                  msg.get("message", msg.get("reason", default)))
                        break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.emit("viewer_error", f"Bağlantı hatası: {str(exc)[:180]}")
        finally:
            self.viewer_ws = None
            self.viewer_connecting = False
            self.viewer_active = False
            with self.frames_lock:
                self.last_frame = None
            self.emit("viewer_closed", was_connected)

    def send_input(self, payload: dict) -> None:
        self.submit(self._send_input(payload))

    async def _send_input(self, payload: dict) -> None:
        if self.viewer_ws and self.viewer_active:
            await self.viewer_ws.send(json.dumps({"type": "input", **payload}))

    def disconnect_viewer(self) -> None:
        self.submit(self._disconnect_viewer())

    async def _disconnect_viewer(self) -> None:
        if self.viewer_ws:
            try:
                await self.viewer_ws.send('{"type":"disconnect"}')
            finally:
                await self.viewer_ws.close()

    def close(self) -> None:
        self.running = False
        async def _close_sockets():
            for ws in (self.viewer_ws, self.host_ws):
                if ws:
                    await ws.close()
            await self.stop_capture()
            self.loop.call_soon(self.loop.stop)
        # Close both sockets and the event loop; no background service is installed.
        try:
            asyncio.run_coroutine_threadsafe(_close_sockets(), self.loop)
        except RuntimeError:
            pass


class RemoteWindow:
    def __init__(self, app: "DeskLinkApp") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("DeskLink | Uzak bilgisayar")
        self.window.geometry("1200x780")
        self.window.configure(bg=BG)
        app.set_brand_icon(self.window)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Uzak ekran yükleniyor...")
        toolbar = tk.Frame(self.window, bg=CARD, padx=14, pady=10)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="UZAK MASAÜSTÜ", bg=CARD, fg=TEXT,
                 font=(ui_font(), 13, "bold")).pack(side="left")
        tk.Label(toolbar, textvariable=self.status, bg=CARD, fg=MUTED,
                 font=(ui_font(), 10)).pack(side="left", padx=26)
        tk.Button(toolbar, text="BAĞLANTIYI KES", command=self.close,
                  bg=RED, fg="#172033", font=(ui_font(), 10, "bold"),
                  relief="flat", padx=14, pady=7).pack(side="right")
        self.canvas = tk.Canvas(self.window, bg="#070c16", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.canvas.bind("<Configure>", lambda event: self.repaint())
        self.canvas.bind("<Motion>", self.mouse_move)
        for index, name in ((1, "left"), (2, "middle"), (3, "right")):
            self.canvas.bind(f"<ButtonPress-{index}>", lambda e, n=name: self.mouse_button(e, n, "down"))
            self.canvas.bind(f"<ButtonRelease-{index}>", lambda e, n=name: self.mouse_button(e, n, "up"))
        self.canvas.bind("<MouseWheel>", self.scroll)
        self.canvas.bind("<Button-4>", lambda event: self.app.net.send_input({"kind": "scroll", "delta": 1}))
        self.canvas.bind("<Button-5>", lambda event: self.app.net.send_input({"kind": "scroll", "delta": -1}))
        self.canvas.bind("<KeyPress>", self.key_press)
        self.canvas.bind("<KeyRelease>", self.key_release)
        self.canvas.bind("<FocusOut>", lambda event: self.app.net.send_input({"kind": "release_all"}))
        self.window.after(500, self.canvas.focus_set)
        self.picture = None
        self.rendered = None
        self.display_rect: tuple[float, float, float, float] | None = None
        self.last_mouse = 0.0

    def update_frame(self, frame: bytes) -> None:
        try:
            with Image.open(BytesIO(frame)) as image:
                if image.format != "JPEG" or image.width > 5000 or image.height > 5000:
                    return
                self.picture = image.convert("RGB")
            self.repaint()
            self.status.set("Bağlandı · ekran ve kontrol aktif")
        except (OSError, ValueError):
            pass

    def repaint(self) -> None:
        if self.picture is None or not self.canvas.winfo_exists():
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 20 or h < 20:
            return
        iw, ih = self.picture.size
        ratio = min(w / iw, h / ih)
        rw, rh = max(1, round(iw * ratio)), max(1, round(ih * ratio))
        left, top = (w - rw) / 2, (h - rh) / 2
        scaled = self.picture.resize((rw, rh), Image.Resampling.BILINEAR)
        self.rendered = ImageTk.PhotoImage(scaled)
        self.canvas.delete("frame")
        self.canvas.create_image(left, top, image=self.rendered, anchor="nw", tags="frame")
        self.display_rect = (left, top, rw, rh)

    def local_point(self, event) -> tuple[float, float] | None:
        rect = self.display_rect
        if rect is None:
            return None
        left, top, width, height = rect
        if not (left <= event.x <= left + width and top <= event.y <= top + height):
            return None
        return (min(1.0, max(0.0, (event.x - left) / width)),
                min(1.0, max(0.0, (event.y - top) / height)))

    def mouse_move(self, event) -> None:
        now = time.monotonic()
        if now - self.last_mouse < 0.045:
            return
        point = self.local_point(event)
        if point:
            self.last_mouse = now
            self.app.net.send_input({"kind": "mouse_move", "x": point[0], "y": point[1]})

    def mouse_button(self, event, name: str, action: str):
        self.canvas.focus_set()
        point = self.local_point(event)
        if point:
            self.app.net.send_input({"kind": "mouse_move", "x": point[0], "y": point[1]})
        if point or action == "up":
            self.app.net.send_input({"kind": "mouse_button", "button": name, "action": action})
        return "break"

    def scroll(self, event):
        if self.local_point(event):
            delta = 1 if event.delta > 0 else -1
            self.app.net.send_input({"kind": "scroll", "delta": delta})
        return "break"

    def key_press(self, event):
        key = event.keysym.lower()
        if not key:
            return "break"
        if key == "f4" and (event.state & 0x0008):
            # Keep Alt+F4 usable locally as the standard disconnect-window shortcut.
            return None
        self.app.net.send_input({"kind": "key", "action": "down", "key": key,
                                 "char": event.char if len(event.char) == 1 and event.char.isprintable() else ""})
        return "break"

    def key_release(self, event):
        key = event.keysym.lower()
        if key:
            self.app.net.send_input({"kind": "key", "action": "up", "key": key})
        return "break"

    def close(self):
        self.app.net.send_input({"kind": "release_all"})
        self.app.net.disconnect_viewer()
        if self.window.winfo_exists():
            self.window.destroy()
        self.app.remote_window = None


class DeskLinkApp:
    def __init__(self) -> None:
        set_windows_dpi_awareness()
        self.root = tk.Tk()
        self.root.title(f"DeskLink v{APP_VERSION} — Uzak Masaüstü")
        self.set_brand_icon(self.root)
        self.root.geometry("940x810" if is_macos() else "940x745")
        self.root.minsize(780, 750 if is_macos() else 700)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.events: queue.Queue = queue.Queue(maxsize=500)
        self.remote_window: RemoteWindow | None = None
        self.server_var = tk.StringVar(value=load_server_url())
        ok, _ = validate_server_url(self.server_var.get().strip())
        if not ok:
            self.server_var.set(DEFAULT_URL)
        self.net = NetworkManager(self.server_var.get().strip(), self.events)
        self.id_var = tk.StringVar(value=f"{self.net.device_id[:3]} {self.net.device_id[3:6]} {self.net.device_id[6:]}")
        self.saved_items: list[dict] = []
        self.host_status = tk.StringVar(value="Bağlantı başlatılıyor...")
        self.viewer_status = tk.StringVar(value="Kayıtlı bilgisayarı seçin veya 9 haneli ID girin.")
        self.target_id = tk.StringVar()
        self.is_host_active = False
        self.mac_permissions_var = tk.StringVar(value="macOS izinleri kontrol ediliyor...") if is_macos() else None
        self.setup_ui()
        self.refresh_contacts()
        self.root.after(60, self.process_events)

    @staticmethod
    def set_brand_icon(window) -> None:
        try:
            icon = tk.PhotoImage(file=str(bundled_brand_asset("DeskLink-icon-256.png")))
            window.iconphoto(True, icon)
            window._desklink_icon = icon  # Keep Tk image data live.
        except (tk.TclError, OSError):
            pass

    def label(self, parent, value: str, size=11, color=MUTED, bold=False, **kwargs):
        return tk.Label(parent, text=value, font=(ui_font(), size, "bold" if bold else "normal"),
                        fg=color, bg=parent.cget("bg"), **kwargs)

    def input(self, parent, variable, width=24, show=None):
        entry = tk.Entry(parent, textvariable=variable, font=(ui_font(), 13),
                         bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                         highlightthickness=1, highlightbackground="#32415d",
                         highlightcolor=BLUE, width=width, show=show)
        return entry

    def button(self, parent, name, command, color=BLUE, fg="white", small=False):
        if is_macos():
            # Aqua ignores tk.Button background colors and may leave white text
            # on a light button. Native ttk buttons are readable in light/dark mode.
            return ttk.Button(parent, text=name, command=command, padding=(10, 5) if small else (13, 9))
        return tk.Button(parent, text=name, command=command, bg=color, fg=fg,
                         font=(ui_font(), 10 if small else 11, "bold"), relief="flat",
                         padx=11 if small else 16, pady=6 if small else 11,
                         activebackground=color, activeforeground=fg, cursor="hand2")

    def setup_ui(self) -> None:
        top = tk.Frame(self.root, bg=BG, padx=30, pady=10)
        top.pack(fill="x")
        try:
            self.brand_logo = tk.PhotoImage(file=str(bundled_brand_asset("DeskLink-logo-dark.png")))
            # 760x164 source displays as approximately 254x55 in Tk.
            self.brand_logo = self.brand_logo.subsample(3, 3)
            tk.Label(top, image=self.brand_logo, bg=BG).pack(anchor="w")
        except (tk.TclError, OSError):
            self.label(top, "DeskLink", size=26, color=TEXT, bold=True).pack(anchor="w")
        self.label(top, f"Windows ve macOS arasında onaylı uzak bağlantı  ·  v{APP_VERSION}",
                   size=11).pack(anchor="w", pady=(1, 0))

        server_card = tk.Frame(self.root, bg=CARD, padx=20, pady=10)
        server_card.pack(fill="x", padx=30, pady=(0, 12))
        self.label(server_card, "BAĞLANTI SUNUCUSU", bold=True, color=TEXT).pack(anchor="w")
        row = tk.Frame(server_card, bg=CARD)
        row.pack(fill="x", pady=(9, 0))
        self.input(row, self.server_var, 46).pack(side="left", fill="x", expand=True, ipady=7)
        self.button(row, "Uygula", self.apply_url, color="#344762").pack(side="left", padx=(12, 0))
        self.label(server_card,
                   "Cloudflare: wss://desklink-relay.erbaskayam.workers.dev/ws",
                   size=9, justify="left").pack(anchor="w", pady=(9, 0))

        if is_macos():
            permissions_row = tk.Frame(server_card, bg=CARD)
            permissions_row.pack(fill="x", pady=(12, 0))
            self.button(permissions_row, "Ekran Kaydı İzni", lambda: self.mac_open_permission("screen"),
                        color="#344762").pack(side="left", padx=(0, 7))
            self.button(permissions_row, "Erişilebilirlik İzni", lambda: self.mac_open_permission("accessibility"),
                        color="#344762").pack(side="left", padx=(0, 7))
            self.button(permissions_row, "İzinleri yenile", self.refresh_mac_permissions,
                        color="#344762").pack(side="left")
            tk.Label(server_card, textvariable=self.mac_permissions_var, bg=CARD, fg=MUTED,
                     font=(ui_font(), 9), anchor="w").pack(fill="x", pady=(8, 0))
            self.refresh_mac_permissions()

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=30)
        main.grid_columnconfigure(0, weight=1, uniform="sides")
        main.grid_columnconfigure(1, weight=1, uniform="sides")
        main.grid_rowconfigure(0, weight=1)

        own = tk.Frame(main, bg=CARD, padx=19, pady=12)
        own.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        self.label(own, "BU BİLGİSAYAR", size=12, bold=True, color=TEXT).pack(anchor="w")
        self.label(own, "Kalıcı ID'nizi karşı tarafa iletin.", size=9).pack(anchor="w", pady=(7, 20))
        self.label(own, "Bilgisayar ID", size=10).pack(anchor="w")
        tk.Label(own, textvariable=self.id_var, font=(mono_font(), 24, "bold"), fg=TEXT, bg=CARD).pack(anchor="w", pady=(5, 12))
        self.button(own, "ID kopyala", self.copy_id, color="#344762").pack(anchor="w")
        self.label(own, "ID, program kapatılıp açıldığında değişmez.", size=10,
                   color=GREEN).pack(anchor="w", pady=(19, 0))
        self.label(own, "Bağlanmak isteyen kişi için bu ekranda onay bildirimi çıkar.",
                   size=9, wraplength=325, justify="left").pack(anchor="w", pady=(15, 0))
        self.host_notice = self.label(own, "Henüz bağlantı yok.", size=10, color=GREEN)
        self.host_notice.pack(anchor="w", pady=(21, 8))
        self.stop_host_button = self.button(own, "UZAK KONTROLÜ DURDUR", self.net.disconnect_host, color=RED, fg="#151c2c")

        other = tk.Frame(main, bg=CARD, padx=19, pady=12)
        other.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        self.label(other, "BAŞKA BİLGİSAYARA BAĞLAN", size=12, bold=True, color=TEXT).pack(anchor="w")
        self.label(other, "Karşı tarafta DeskLink açık olmalıdır.", size=9).pack(anchor="w", pady=(7, 12))
        self.label(other, "Karşı bilgisayarın 9 haneli ID'si", size=10).pack(anchor="w")
        self.input(other, self.target_id).pack(anchor="w", fill="x", ipady=7, pady=(7, 12))
        self.button(other, "BAĞLAN · KARŞI TARAFA BİLDİRİM GÖNDER", self.start_remote).pack(fill="x")
        self.label(other, "Karşı bilgisayarda onay penceresi açılır; onaysız kontrol yok.",
                   size=9, wraplength=350, justify="left").pack(anchor="w", pady=(6, 8))

        self.label(other, "KAYITLI BİLGİSAYARLAR", size=10, bold=True, color=TEXT).pack(anchor="w")
        self.label(other, "Birini seçin ve Bağlan'a basın.", size=9).pack(anchor="w", pady=(3, 4))
        list_frame = tk.Frame(other, bg=INPUT_BG, highlightthickness=1, highlightbackground="#32415d")
        list_frame.pack(fill="both", expand=True, pady=(4, 8))
        self.saved_list = tk.Listbox(list_frame, bg=INPUT_BG, fg=TEXT, selectbackground=BLUE,
                                     selectforeground="white", highlightthickness=0, borderwidth=0,
                                     font=(ui_font(), 11), exportselection=False, height=3)
        self.saved_list.pack(fill="both", expand=True, padx=6, pady=5)
        self.saved_list.bind("<<ListboxSelect>>", self.select_saved)
        self.saved_list.bind("<Double-Button-1>", lambda _event: self.start_remote())
        actions = tk.Frame(other, bg=CARD)
        actions.pack(fill="x")
        self.button(actions, "ID'yi kaydet", self.save_target, color="#344762", small=True).pack(side="left", padx=(0, 6))
        self.button(actions, "Yeniden adlandır", self.rename_saved, color="#344762", small=True).pack(side="left", padx=(0, 6))
        self.button(actions, "Sil", self.remove_saved, color="#344762", small=True).pack(side="left")

        bottom = tk.Frame(self.root, bg=BG, padx=30, pady=5)
        bottom.pack(fill="x")
        tk.Label(bottom, textvariable=self.host_status, bg=BG, fg=MUTED,
                 font=(ui_font(), 10)).pack(anchor="w")
        tk.Label(bottom, textvariable=self.viewer_status, bg=BG, fg=MUTED,
                 font=(ui_font(), 10)).pack(anchor="w", pady=(4, 0))
        self.toggle_host(False)

    def refresh_mac_permissions(self) -> None:
        if not is_macos() or self.mac_permissions_var is None:
            return
        state = mac_permission_status()
        def describe(value: bool | None) -> str:
            return "İzinli" if value is True else "İzin gerekli" if value is False else "Kontrol edilemedi"
        self.mac_permissions_var.set(
            f"macOS: Ekran Kaydı — {describe(state['screen'])}  |  "
            f"Erişilebilirlik — {describe(state['accessibility'])}"
        )

    def mac_open_permission(self, kind: str) -> None:
        if not is_macos():
            return
        if kind == "screen":
            # The macOS screen-capture prompt is triggered only by the user's click.
            request_screen_capture_permission()
        ok = open_mac_privacy_settings(kind)
        self.refresh_mac_permissions()
        label = "Ekran ve Sistem Sesi Kaydı" if kind == "screen" else "Erişilebilirlik"
        messagebox.showinfo(
            "macOS izinleri",
            f"Sistem Ayarları > Gizlilik ve Güvenlik > {label} bölümünden "
            "DeskLink'e (Terminal üzerinden açıldıysa Terminal/Python'a) izin verin.\n\n"
            "İzin değişikliğinden sonra DeskLink'i tamamen kapatıp yeniden başlatın."
            + ("" if ok else "\n\nSistem Ayarlarını kendiniz açmanız gerekiyor."),
            parent=self.root,
        )

    def mac_host_permissions_ok(self) -> bool:
        if not is_macos():
            return True
        missing = missing_host_permissions(mac_permission_status())
        self.refresh_mac_permissions()
        if not missing:
            return True
        messagebox.showwarning(
            "macOS izinleri gerekli",
            "Bu Mac'in ekranını paylaşmak ve uzaktan kontrol ettirmek için şu izinler gerekli:\n\n"
            + "\n".join("• " + item for item in missing)
            + "\n\nDeskLink ana ekranındaki izin düğmelerinden ayarları açın ve "
            "uygulamayı yeniden başlatın. Bağlantı isteği şimdi reddedilecek.",
            parent=self.root,
        )
        return False

    def toggle_host(self, active: bool) -> None:
        self.is_host_active = active
        if active:
            self.host_notice.config(text="● EKRANINIZ PAYLAŞILIYOR — Fare/klavye kontrolü açık!", fg=RED)
            self.stop_host_button.pack(anchor="w", pady=(7, 0))
        else:
            self.host_notice.config(text="● Başka bir bilgisayar kontrol etmiyor.", fg=GREEN)
            self.stop_host_button.pack_forget()

    def copy_id(self) -> None:
        value = self.id_var.get().replace(" ", "")
        if len(value) == 9 and value.isdigit():
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.root.update_idletasks()

    def apply_url(self) -> None:
        url = self.server_var.get().strip()
        ok, reason = validate_server_url(url)
        if not ok:
            messagebox.showerror("Geçersiz sunucu", reason, parent=self.root)
            return
        try:
            save_server_url(url)
        except OSError as exc:
            messagebox.showerror("Ayarlar", str(exc), parent=self.root)
            return
        self.net.change_url(url)
        self.refresh_contacts()
        self.host_status.set("Sunucu adresi değiştirildi; yeniden bağlanılıyor...")

    def refresh_contacts(self, selected_id: str = "") -> None:
        self.saved_items = contacts(self.server_var.get().strip())
        self.saved_list.delete(0, tk.END)
        for item in self.saved_items:
            self.saved_list.insert(tk.END, f"{item['name']}   ·   {item['id'][:3]} {item['id'][3:6]} {item['id'][6:]}")
        for index, item in enumerate(self.saved_items):
            if item['id'] == selected_id:
                self.saved_list.selection_set(index)
                self.saved_list.see(index)
                break

    def select_saved(self, _event=None) -> None:
        selected = self.saved_list.curselection()
        if selected and selected[0] < len(self.saved_items):
            self.target_id.set(self.saved_items[selected[0]]['id'])

    def save_target(self) -> None:
        identifier = normalize_id(self.target_id.get())
        if len(identifier) != 9:
            messagebox.showwarning("Kayıt", "Önce geçerli 9 haneli ID girin.", parent=self.root)
            return
        name = simpledialog.askstring("Bilgisayarı kaydet", "Bu bilgisayara bir isim verin:",
                                      initialvalue=f"Bilgisayar {identifier}", parent=self.root)
        if name is None:
            return
        try:
            save_contact(self.server_var.get().strip(), identifier, name)
            self.refresh_contacts(identifier)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Kayıt hatası", str(exc), parent=self.root)

    def rename_saved(self) -> None:
        selection = self.saved_list.curselection()
        if not selection:
            return
        item = self.saved_items[selection[0]]
        name = simpledialog.askstring("Bilgisayarı yeniden adlandır", "Yeni isim:",
                                      initialvalue=item['name'], parent=self.root)
        if name is None or not name.strip():
            return
        try:
            save_contact(self.server_var.get().strip(), item['id'], name)
            self.refresh_contacts(item['id'])
        except OSError as exc:
            messagebox.showerror("Kayıt hatası", str(exc), parent=self.root)

    def remove_saved(self) -> None:
        selection = self.saved_list.curselection()
        if not selection:
            return
        item = self.saved_items[selection[0]]
        if messagebox.askyesno("Kayıtlı bilgisayarı sil", f"{item['name']} kayıtlardan silinsin mi?", parent=self.root):
            try:
                delete_contact(self.server_var.get().strip(), item['id'])
                self.refresh_contacts()
            except OSError as exc:
                messagebox.showerror("Kayıt hatası", str(exc), parent=self.root)

    def start_remote(self) -> None:
        identifier = normalize_id(self.target_id.get())
        if len(identifier) != 9:
            messagebox.showwarning("Bilgi eksik", "9 haneli bilgisayar ID'sini girin veya kayıtlı cihaz seçin.", parent=self.root)
            return
        if self.net.viewer_connecting or self.net.viewer_ws:
            messagebox.showinfo("Bağlantı", "Zaten bir bağlantı isteği var.", parent=self.root)
            return
        self.net.connect_viewer(identifier)

    def process_events(self) -> None:
        try:
            for _ in range(90):
                try:
                    action, value = self.events.get_nowait()
                except queue.Empty:
                    break
                if action == "my_id":
                    self.id_var.set(f"{value[:3]} {value[3:6]} {value[6:]}" if value else "--- --- ---")
                elif action == "host_status":
                    self.host_status.set(str(value))
                elif action == "host_active":
                    self.toggle_host(bool(value))
                elif action == "consent_request":
                    if not isinstance(value, dict) or not value.get('token'):
                        continue
                    requester_id = str(value.get('requester_id') or 'Kimliği belirtilmeyen cihaz')
                    requester_name = str(value.get('requester_name') or 'Bir bilgisayar')[:48]
                    if self.root.state() == "iconic":
                        self.root.deiconify()
                    self.root.lift()
                    try:
                        self.root.attributes('-topmost', True)
                        self.root.bell()
                    except tk.TclError:
                        pass
                    allowed = messagebox.askyesno(
                        "DeskLink · Bağlantı isteği",
                        f"{requester_name} ({requester_id}) bilgisayarınıza bağlanmak istiyor.\n\n"
                        "İzin verirseniz ekranınızı görebilir ve fare/klavyenizi kontrol edebilir.\n\n"
                        "Bu isteği yalnızca tanıyorsanız onaylayın. Bağlantıya izin verilsin mi?",
                        icon="warning", parent=self.root)
                    try:
                        self.root.attributes('-topmost', False)
                    except tk.TclError:
                        pass
                    if allowed and not self.mac_host_permissions_ok():
                        allowed = False
                    self.net.approve(value['token'], allowed)
                elif action == "viewer_accepted":
                    try:
                        target = value['id']
                        previous = next((item for item in contacts(self.server_var.get().strip())
                                         if item['id'] == target), None)
                        label = (previous or {}).get('name') or value.get('name') or f"Bilgisayar {target}"
                        save_contact(self.server_var.get().strip(), target, label, connected=True)
                        self.refresh_contacts(target)
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        self.viewer_status.set(f"Bağlandı; cihaz kaydedilemedi: {exc}")
                elif action == "viewer_status":
                    self.viewer_status.set(str(value))
                elif action == "viewer_error":
                    self.viewer_status.set(str(value))
                    messagebox.showerror("Uzak bağlantı", str(value), parent=self.root)
                elif action == "viewer_open":
                    if self.remote_window is None:
                        self.remote_window = RemoteWindow(self)
                elif action == "viewer_closed":
                    if self.remote_window:
                        try:
                            self.remote_window.window.destroy()
                        except tk.TclError:
                            pass
                        self.remote_window = None
                    self.viewer_status.set("Bağlantı kapalı.")
                elif action == "viewer_meta":
                    if self.remote_window:
                        w, h = value.get("width", "?"), value.get("height", "?")
                        self.remote_window.status.set(f"Uzak ekran {w} × {h}")
            frame = self.net.consume_frame()
            if frame and self.remote_window:
                self.remote_window.update_frame(frame)
        except tk.TclError:
            return
        self.root.after(65, self.process_events)

    def close(self) -> None:
        self.net.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    DeskLinkApp().run()
