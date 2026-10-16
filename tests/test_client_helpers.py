import types
import unittest

from control import InputController
from desktop import monitor_to_dict, validate_server_url


class Recorder:
    def __init__(self):
        self.calls = []
        self.position = (0, 0)

    def press(self, x):
        self.calls.append(("down", x))

    def release(self, x):
        self.calls.append(("up", x))

    def scroll(self, x, y):
        self.calls.append(("scroll", x, y))


class HelperTests(unittest.TestCase):
    def test_url_protection(self):
        self.assertTrue(validate_server_url("wss://desk.example.com")[0])
        self.assertTrue(validate_server_url("ws://127.0.0.1:8765")[0])
        self.assertFalse(validate_server_url("ws://8.8.8.8:8765")[0])
        self.assertFalse(validate_server_url("https://example.com")[0])
        self.assertFalse(validate_server_url("wss://user:pass@example.com")[0])

    def test_monitor_conversion(self):
        monitor = types.SimpleNamespace(left=-1920, top=0, width=1920, height=1080)
        self.assertEqual(monitor_to_dict(monitor), {"left": -1920, "top": 0,
                                                    "width": 1920, "height": 1080})

    def test_input_mapper_and_release(self):
        bridge = InputController.__new__(InputController)
        bridge.keyboard = Recorder()
        bridge.mouse = Recorder()
        bridge.Key = types.SimpleNamespace(ctrl_l="left-control", enter="enter")
        bridge.Button = types.SimpleNamespace(left="left-button", right="right-button", middle="middle-button")
        bridge.pressed_keys = {}
        bridge.pressed_buttons = set()
        monitor = {"left": -100, "top": 120, "width": 1000, "height": 1000}
        bridge.handle({"kind": "mouse_move", "x": 1.0, "y": 0.0}, monitor)
        self.assertEqual(bridge.mouse.position, (899, 120))
        bridge.handle({"kind": "mouse_button", "action": "down", "button": "left"}, monitor)
        bridge.handle({"kind": "key", "action": "down", "key": "control_l"}, monitor)
        bridge.handle({"kind": "key", "action": "down", "key": "a"}, monitor)
        bridge.handle({"kind": "release_all"}, monitor)
        self.assertIn(("up", "left-control"), bridge.keyboard.calls)
        self.assertIn(("up", "a"), bridge.keyboard.calls)
        self.assertIn(("up", "left-button"), bridge.mouse.calls)
        self.assertEqual(bridge.pressed_keys, {})
        self.assertEqual(bridge.pressed_buttons, set())


if __name__ == "__main__":
    unittest.main()
