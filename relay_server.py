"""DeskLink MVP: consent-based WebSocket screen relay.

The relay sees screen contents. Expose it over the Internet only with TLS
(WSS directly, or a TLS reverse proxy). This is not an E2E design.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
import hmac
import json
import logging
import secrets
import ssl
import time
from typing import Any

from websockets.asyncio.server import serve

LOGGER = logging.getLogger("desklink.relay")
MAX_FRAME = 2_000_000
MAX_MESSAGE = 2_100_000
PENDING_TIMEOUT = 30


def encoded(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))


@dataclass(eq=False)
class HostSession:
    ws: Any
    id: str
    pin: str
    viewer: Any = None
    pending: Any = None
    pending_token: str = ""
    pending_task: asyncio.Task | None = None


class RelayState:
    def __init__(self) -> None:
        self.hosts: dict[str, HostSession] = {}
        self.viewer_links: dict[Any, tuple[HostSession, str]] = {}
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    async def send(ws: Any, msg: dict) -> None:
        await ws.send(encoded(msg))

    @staticmethod
    def remote_ip(ws: Any) -> str:
        peer = ws.remote_address
        return str(peer[0]) if peer else "unknown"

    def is_blocked(self, ws: Any) -> bool:
        ip = self.remote_ip(ws)
        attempts = self.failures[ip]
        now = time.monotonic()
        while attempts and now - attempts[0] > 600:
            attempts.popleft()
        return len(attempts) >= 8

    def failed_attempt(self, ws: Any) -> None:
        self.failures[self.remote_ip(ws)].append(time.monotonic())

    async def handle(self, ws: Any) -> None:
        registered: HostSession | None = None
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    if registered and registered.viewer and raw.startswith(b"\xff\xd8") and raw.endswith(b"\xff\xd9") and len(raw) <= MAX_FRAME:
                        try:
                            await registered.viewer.send(raw)
                        except Exception:
                            await self.leave_viewer(registered.viewer)
                    continue
                if len(raw) > 2000:
                    await self.send(ws, {"type": "error", "message": "Geçersiz mesaj."})
                    continue
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    await self.send(ws, {"type": "error", "message": "Geçersiz JSON."})
                    continue
                if not isinstance(msg, dict):
                    continue
                action = msg.get("type")

                if action == "register" and registered is None and ws not in self.viewer_links:
                    pin = msg.get("pin")
                    if not isinstance(pin, str) or len(pin) != 8 or not pin.isascii() or not pin.isdecimal():
                        await self.send(ws, {"type": "error", "message": "PIN 8 rakam olmalıdır."})
                        continue
                    if len(self.hosts) >= 5000:
                        await self.send(ws, {"type": "error", "message": "Sunucu dolu."})
                        continue
                    identifier = ""
                    for _ in range(20):
                        identifier = f"{secrets.randbelow(900_000_000) + 100_000_000:09d}"
                        if identifier not in self.hosts:
                            break
                    else:
                        await self.send(ws, {"type": "error", "message": "Yeni ID üretilemedi."})
                        continue
                    registered = HostSession(ws=ws, id=identifier, pin=pin)
                    self.hosts[identifier] = registered
                    await self.send(ws, {"type": "registered", "id": identifier})
                    LOGGER.info("Host connected ID=%s", identifier)
                    continue

                if action == "connect" and registered is None and ws not in self.viewer_links:
                    host_id = msg.get("id")
                    pin = msg.get("pin")
                    if self.is_blocked(ws):
                        await self.send(ws, {"type": "error", "message": "Çok fazla deneme. Daha sonra tekrar deneyin."})
                        continue
                    if (not isinstance(host_id, str) or not isinstance(pin, str)
                            or len(host_id) != 9 or not host_id.isascii() or not host_id.isdecimal()
                            or len(pin) != 8 or not pin.isascii() or not pin.isdecimal()):
                        self.failed_attempt(ws)
                        await self.send(ws, {"type": "error", "message": "ID veya erişim kodu hatalı."})
                        continue
                    host = self.hosts.get(host_id)
                    if host is None or not hmac.compare_digest(pin, host.pin):
                        self.failed_attempt(ws)
                        await self.send(ws, {"type": "error", "message": "ID veya erişim kodu hatalı."})
                        continue
                    if host.viewer is not None or host.pending is not None:
                        await self.send(ws, {"type": "error", "message": "Karşı bilgisayar meşgul."})
                        continue
                    token = secrets.token_hex(12)
                    host.pending = ws
                    host.pending_token = token
                    self.viewer_links[ws] = (host, "pending")
                    await self.send(ws, {"type": "pending"})
                    try:
                        await self.send(host.ws, {"type": "connection_request", "token": token})
                    except Exception:
                        await self.leave_viewer(ws)
                        continue
                    host.pending_task = asyncio.create_task(self.expire_request(host, ws, token))
                    continue

                if registered is not None and action == "approve":
                    token = msg.get("token")
                    if registered.pending is None or token != registered.pending_token:
                        continue
                    viewer = registered.pending
                    registered.pending = None
                    registered.pending_token = ""
                    if registered.pending_task:
                        registered.pending_task.cancel()
                        registered.pending_task = None
                    if msg.get("accept") is True:
                        registered.viewer = viewer
                        self.viewer_links[viewer] = (registered, "active")
                        try:
                            await self.send(viewer, {"type": "accepted"})
                            await self.send(registered.ws, {"type": "viewer_connected"})
                        except Exception:
                            await self.leave_viewer(viewer)
                    else:
                        self.viewer_links.pop(viewer, None)
                        try:
                            await self.send(viewer, {"type": "rejected"})
                        except Exception:
                            pass
                    continue

                if registered is not None and action == "frame_meta" and registered.viewer:
                    if self.valid_frame_meta(msg):
                        try:
                            await self.send(registered.viewer, msg)
                        except Exception:
                            await self.leave_viewer(registered.viewer)
                    continue

                if registered is not None and action == "disconnect":
                    if registered.viewer:
                        viewer = registered.viewer
                        await self.leave_viewer(viewer)
                        try:
                            await self.send(viewer, {"type": "closed", "reason": "Karşı bilgisayar bağlantıyı sonlandırdı."})
                        except Exception:
                            pass
                    if registered.pending:
                        viewer = registered.pending
                        await self.leave_viewer(viewer)
                        try:
                            await self.send(viewer, {"type": "rejected"})
                        except Exception:
                            pass
                    continue

                if ws in self.viewer_links:
                    host, state = self.viewer_links[ws]
                    if action == "disconnect":
                        await self.leave_viewer(ws)
                        await self.send(ws, {"type": "closed"})
                    elif action == "input" and state == "active" and self.valid_input(msg):
                        try:
                            await self.send(host.ws, msg)
                        except Exception:
                            await self.leave_viewer(ws)
                    continue

                await self.send(ws, {"type": "error", "message": "Beklenmeyen istek."})
        except Exception as exc:
            LOGGER.debug("Socket terminated: %s", exc)
        finally:
            if registered:
                if self.hosts.get(registered.id) is registered:
                    self.hosts.pop(registered.id, None)
                for v in (registered.pending, registered.viewer):
                    if v is not None:
                        self.viewer_links.pop(v, None)
                        try:
                            await self.send(v, {"type": "closed", "reason": "Bilgisayar çevrimdışı."})
                        except Exception:
                            pass
                if registered.pending_task:
                    registered.pending_task.cancel()
                LOGGER.info("Host disconnected ID=%s", registered.id)
            elif ws in self.viewer_links:
                await self.leave_viewer(ws)

    @staticmethod
    def valid_frame_meta(msg: dict) -> bool:
        values = (msg.get("left"), msg.get("top"), msg.get("width"), msg.get("height"))
        if any(type(v) is not int for v in values):
            return False
        left, top, w, h = values
        return -100_000 <= left <= 100_000 and -100_000 <= top <= 100_000 and 1 <= w <= 16_384 and 1 <= h <= 16_384

    @staticmethod
    def valid_input(msg: dict) -> bool:
        kind = msg.get("kind")
        if kind == "mouse_move":
            x, y = msg.get("x"), msg.get("y")
            return type(x) in (int, float) and type(y) in (int, float) and 0 <= x <= 1 and 0 <= y <= 1
        if kind == "mouse_button":
            return msg.get("button") in ("left", "right", "middle") and msg.get("action") in ("down", "up")
        if kind == "scroll":
            return type(msg.get("delta")) is int and -10 <= msg["delta"] <= 10
        if kind == "key":
            key = msg.get("key")
            char = msg.get("char", "")
            return (isinstance(key, str) and 1 <= len(key) <= 32
                    and all(c.isprintable() and c != "\x7f" for c in key)
                    and isinstance(char, str) and len(char) <= 1 and all(c.isprintable() for c in char)
                    and msg.get("action") in ("down", "up"))
        return kind == "release_all"

    async def expire_request(self, host: HostSession, viewer: Any, token: str) -> None:
        try:
            await asyncio.sleep(PENDING_TIMEOUT)
            if host.pending is viewer and host.pending_token == token:
                await self.leave_viewer(viewer)
                await self.send(viewer, {"type": "error", "message": "İzin isteğinin süresi doldu."})
        except asyncio.CancelledError:
            pass

    async def leave_viewer(self, ws: Any) -> None:
        link = self.viewer_links.pop(ws, None)
        if link is None:
            return
        host, state = link
        if state == "pending" and host.pending is ws:
            host.pending = None
            host.pending_token = ""
            if host.pending_task and host.pending_task is not asyncio.current_task():
                host.pending_task.cancel()
            host.pending_task = None
            try:
                await self.send(host.ws, {"type": "request_canceled"})
            except Exception:
                pass
        if state == "active" and host.viewer is ws:
            host.viewer = None
            try:
                await self.send(host.ws, {"type": "viewer_left"})
            except Exception:
                pass


async def run_server(args: argparse.Namespace) -> None:
    context = None
    if bool(args.cert) != bool(args.key):
        raise SystemExit("--cert ve --key birlikte verilmelidir.")
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.cert, args.key)
    elif args.bind not in ("127.0.0.1", "::1", "localhost"):
        LOGGER.warning("DİKKAT: Bu dinleme adresi TLS'siz! Yalnızca TLS reverse proxy arkasında kullanın.")

    relay = RelayState()
    scheme = "wss" if context else "ws"
    LOGGER.info("DeskLink relay listening: %s://%s:%s", scheme, args.bind, args.port)
    async with serve(relay.handle, args.bind, args.port,
                     ssl=context, max_size=MAX_MESSAGE, max_queue=4,
                     compression=None, ping_interval=20, ping_timeout=20) as server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="DeskLink onaylı uzak masaüstü relay sunucusu")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cert", help="TLS sertifikası (PEM)")
    parser.add_argument("--key", help="TLS özel anahtarı (PEM)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
