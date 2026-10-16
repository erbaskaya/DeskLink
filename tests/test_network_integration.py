"""End-to-end protocol test with an in-memory JPEG capture and inert input device.

This tests the actual desktop network manager without touching the physical PC.
"""
import asyncio
from io import BytesIO
import json
import queue
import types
import unittest

from PIL import Image
from websockets.asyncio.server import serve

import desktop
from relay_server import RelayState


class FakeController:
    events = []
    def handle(self, msg, monitor):
        self.events.append(msg)

    def release_all(self):
        pass


async def event_named(q, name, timeout=4, predicate=None):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        try:
            what, value = q.get_nowait()
            if what == name and (predicate is None or predicate(value)):
                return value
        except queue.Empty:
            pass
        await asyncio.sleep(0.025)
    raise AssertionError(f"Event not seen: {name}")


class ManagerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_control = desktop.InputController
        desktop.InputController = FakeController
        FakeController.events = []
        self.relay = RelayState()
        self.server = await serve(self.relay.handle, "127.0.0.1", 0, compression=None)
        self.url = "ws://127.0.0.1:" + str(self.server.sockets[0].getsockname()[1])
        self.host_queue = queue.Queue()
        self.viewer_queue = queue.Queue()
        self.host = desktop.NetworkManager(self.url, self.host_queue)
        self.viewer = desktop.NetworkManager(self.url, self.viewer_queue)

    async def asyncTearDown(self):
        self.host.close()
        self.viewer.close()
        await asyncio.sleep(.20)
        self.server.close()
        await self.server.wait_closed()
        desktop.InputController = self.old_control

    async def test_real_client_connection_flow(self):
        host_id = await event_named(self.host_queue, "my_id", predicate=lambda val: len(val) == 9)
        await event_named(self.viewer_queue, "my_id", predicate=lambda val: len(val) == 9)
        jpg_io = BytesIO()
        Image.new("RGB", (16, 12), (100, 120, 150)).save(jpg_io, "JPEG")
        jpg = jpg_io.getvalue()

        async def fake_capture(instance, ws):
            await ws.send(json.dumps({"type": "frame_meta", "left": 0, "top": 0, "width": 16, "height": 12}))
            while instance.host_active:
                await ws.send(jpg)
                await asyncio.sleep(.13)

        self.host.capture_stream = types.MethodType(fake_capture, self.host)
        self.viewer.connect_viewer(host_id, self.host.pin)
        await event_named(self.viewer_queue, "viewer_status", predicate=lambda v: "onayı bekleniyor" in v)
        token = await event_named(self.host_queue, "consent_request")
        self.host.approve(token, True)
        await event_named(self.host_queue, "host_active", predicate=lambda b: b is True)
        await event_named(self.viewer_queue, "viewer_open")
        for _ in range(60):
            got = self.viewer.consume_frame()
            if got == jpg:
                break
            await asyncio.sleep(.05)
        else:
            self.fail("JPEG was not received by real manager")
        self.viewer.send_input({"kind": "mouse_move", "x": 0.5, "y": 0.6})
        for _ in range(60):
            if any(i.get("kind") == "mouse_move" for i in FakeController.events):
                break
            await asyncio.sleep(.05)
        else:
            self.fail("Mouse input did not reach mock controller")
        self.host.disconnect_host()
        await event_named(self.viewer_queue, "viewer_closed")


if __name__ == "__main__":
    unittest.main()
