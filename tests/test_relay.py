import asyncio
import json
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from relay_server import RelayState, MAX_MESSAGE


async def get_json(ws):
    raw = await asyncio.wait_for(ws.recv(), 3)
    assert isinstance(raw, str), raw
    return json.loads(raw)


async def send_json(ws, obj):
    await ws.send(json.dumps(obj))


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = RelayState()
        self.server = await serve(self.state.handle, "127.0.0.1", 0,
                                  compression=None, max_size=MAX_MESSAGE)
        self.url = "ws://127.0.0.1:" + str(self.server.sockets[0].getsockname()[1])
        self.ws_list = []

    async def asyncTearDown(self):
        for ws in self.ws_list:
            await ws.close()
        self.server.close()
        await self.server.wait_closed()

    async def new(self):
        ws = await connect(self.url, compression=None, proxy=None)
        self.ws_list.append(ws)
        return ws

    async def register_host(self):
        host = await self.new()
        await send_json(host, {"type": "register", "pin": "85004002"})
        registered = await get_json(host)
        self.assertEqual(registered["type"], "registered")
        self.assertRegex(registered["id"], r"^[0-9]{9}$")
        return host, registered["id"]

    async def test_approval_denial_stream_and_disconnect(self):
        host, identifier = await self.register_host()
        viewer = await self.new()
        req = {"type": "connect", "id": identifier, "pin": "85004002"}
        await send_json(viewer, req)
        self.assertEqual((await get_json(viewer))["type"], "pending")
        request = await get_json(host)
        self.assertEqual(request["type"], "connection_request")
        await send_json(host, {"type": "approve", "token": request["token"], "accept": False})
        self.assertEqual((await get_json(viewer))["type"], "rejected")
        await send_json(viewer, req)
        self.assertEqual((await get_json(viewer))["type"], "pending")
        request = await get_json(host)
        await send_json(host, {"type": "approve", "token": request["token"], "accept": True})
        self.assertEqual((await get_json(viewer))["type"], "accepted")
        self.assertEqual((await get_json(host))["type"], "viewer_connected")

        meta = {"type": "frame_meta", "width": 1920, "height": 1080, "left": 0, "top": 0}
        await send_json(host, meta)
        self.assertEqual(await get_json(viewer), meta)
        jpeg = b"\xff\xd8SAMPLE_JPEG\xff\xd9"
        await host.send(jpeg)
        self.assertEqual(await viewer.recv(), jpeg)
        inp = {"type": "input", "kind": "mouse_move", "x": 0.7, "y": 0.3}
        await send_json(viewer, inp)
        self.assertEqual(await get_json(host), inp)
        # Out-of-bounds coordinates must be discarded.
        await send_json(viewer, {"type": "input", "kind": "mouse_move", "x": 999, "y": 0})
        good = {"type": "input", "kind": "key", "action": "down", "key": "a"}
        await send_json(viewer, good)
        self.assertEqual(await get_json(host), good)
        await send_json(viewer, {"type": "disconnect"})
        self.assertEqual((await get_json(host))["type"], "viewer_left")
        self.assertEqual((await get_json(viewer))["type"], "closed")
        self.assertIsNone(self.state.hosts[identifier].viewer)

    async def test_wrong_pin_rejected_busy_and_closed(self):
        host, identifier = await self.register_host()
        intruder = await self.new()
        await send_json(intruder, {"type": "connect", "id": identifier, "pin": "00000000"})
        err = await get_json(intruder)
        self.assertEqual(err["type"], "error")
        self.assertIn("hatalı", err["message"])
        viewer = await self.new()
        await send_json(viewer, {"type": "connect", "id": identifier, "pin": "85004002"})
        self.assertEqual((await get_json(viewer))["type"], "pending")
        await send_json(intruder, {"type": "connect", "id": identifier, "pin": "85004002"})
        self.assertEqual((await get_json(intruder))["type"], "error")
        req = await get_json(host)
        await send_json(host, {"type": "approve", "token": req["token"], "accept": True})
        self.assertEqual((await get_json(viewer))["type"], "accepted")
        self.assertEqual((await get_json(host))["type"], "viewer_connected")
        await host.close()
        self.assertEqual((await get_json(viewer))["type"], "closed")
        self.assertNotIn(identifier, self.state.hosts)

    async def test_host_can_revoke_connection(self):
        host, identifier = await self.register_host()
        viewer = await self.new()
        await send_json(viewer, {"type": "connect", "id": identifier, "pin": "85004002"})
        self.assertEqual((await get_json(viewer))["type"], "pending")
        req = await get_json(host)
        await send_json(host, {"type": "approve", "token": req["token"], "accept": True})
        self.assertEqual((await get_json(viewer))["type"], "accepted")
        self.assertEqual((await get_json(host))["type"], "viewer_connected")
        await send_json(host, {"type": "disconnect"})
        self.assertEqual((await get_json(host))["type"], "viewer_left")
        self.assertEqual((await get_json(viewer))["type"], "closed")
        self.assertIsNone(self.state.hosts[identifier].viewer)

    async def test_wrong_pin_rate_limit(self):
        host, identifier = await self.register_host()
        viewer = await self.new()
        for _ in range(8):
            await send_json(viewer, {"type": "connect", "id": identifier, "pin": "00000000"})
            self.assertEqual((await get_json(viewer))["type"], "error")
        await send_json(viewer, {"type": "connect", "id": identifier, "pin": "85004002"})
        msg = await get_json(viewer)
        self.assertEqual(msg["type"], "error")
        self.assertIn("fazla", msg["message"])


if __name__ == "__main__":
    unittest.main()
