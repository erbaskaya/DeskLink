"""Windows/macOS keyboard and mouse input, only during approved sessions."""
from __future__ import annotations


class InputController:
    """Translate a deliberately small, validated remote input protocol."""

    KEY_MAP = {
        "return": "enter", "kp_enter": "enter", "escape": "esc", "backspace": "backspace",
        "delete": "delete", "insert": "insert", "tab": "tab", "iso_left_tab": "tab",
        "space": "space", "up": "up", "down": "down", "left": "left", "right": "right",
        "home": "home", "end": "end", "prior": "page_up", "next": "page_down",
        "page_up": "page_up", "page_down": "page_down", "caps_lock": "caps_lock",
        "num_lock": "num_lock", "scroll_lock": "scroll_lock", "pause": "pause",
        "shift_l": "shift_l", "shift_r": "shift_r", "control_l": "ctrl_l",
        "control_r": "ctrl_r", "alt_l": "alt_l", "alt_r": "alt_r",
        "super_l": "cmd_l", "super_r": "cmd_r", "win_l": "cmd_l", "win_r": "cmd_r",
        "meta_l": "cmd_l", "meta_r": "cmd_r", "command": "cmd",
        "option_l": "alt_l", "option_r": "alt_r",
        "print": "print_screen", "snapshot": "print_screen",
    }

    SYMBOL_MAP = {
        "minus": "-", "equal": "=", "comma": ",", "period": ".", "slash": "/",
        "backslash": "\\", "semicolon": ";", "apostrophe": "'",
        "bracketleft": "[", "bracketright": "]", "grave": "`",
        "kp_add": "+", "kp_subtract": "-", "kp_multiply": "*", "kp_divide": "/",
        "kp_decimal": ".",
    }

    def __init__(self) -> None:
        from pynput.keyboard import Controller as KeyboardController, Key
        from pynput.mouse import Controller as MouseController, Button
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.Key = Key
        self.Button = Button
        self.pressed_keys: dict[str, object] = {}
        self.pressed_buttons: set[str] = set()

    def key_value(self, name: str, char: str = ""):
        low = name.lower()
        special = self.KEY_MAP.get(low)
        if special:
            value = getattr(self.Key, special, None)
            if value is None and special.endswith(("_l", "_r")):
                # macOS pynput versions may expose a generic modifier only.
                value = getattr(self.Key, special.rsplit("_", 1)[0], None)
            return value
        if low in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[low]
        if len(low) > 1 and low.startswith("kp_") and len(low) == 4 and low[-1].isdigit():
            return low[-1]
        if len(low) > 1 and low.startswith("f") and low[1:].isdigit():
            number = int(low[1:])
            if 1 <= number <= 20:
                return getattr(self.Key, low, None)
        if len(name) == 1 and name.isprintable():
            return name
        if len(char) == 1 and char.isprintable():
            return char
        return None

    def handle(self, msg: dict, monitor: dict[str, int]) -> None:
        kind = msg.get("kind")
        if kind == "mouse_move":
            x, y = float(msg["x"]), float(msg["y"])
            left = monitor["left"]
            top = monitor["top"]
            px = left + round(min(1.0, max(0.0, x)) * (monitor["width"] - 1))
            py = top + round(min(1.0, max(0.0, y)) * (monitor["height"] - 1))
            self.mouse.position = (px, py)
        elif kind == "mouse_button":
            name = msg["button"]
            btn = getattr(self.Button, name, None)
            if btn is None:
                return
            if msg["action"] == "down" and name not in self.pressed_buttons:
                self.mouse.press(btn)
                self.pressed_buttons.add(name)
            elif msg["action"] == "up" and name in self.pressed_buttons:
                self.mouse.release(btn)
                self.pressed_buttons.discard(name)
        elif kind == "scroll":
            self.mouse.scroll(0, int(msg["delta"]))
        elif kind == "key":
            name = msg["key"]
            value = self.key_value(name, msg.get("char", ""))
            if value is None:
                return
            if msg["action"] == "down" and name not in self.pressed_keys:
                self.keyboard.press(value)
                self.pressed_keys[name] = value
            elif msg["action"] == "up" and name in self.pressed_keys:
                self.keyboard.release(self.pressed_keys.pop(name))
        elif kind == "release_all":
            self.release_all()

    def release_all(self) -> None:
        for val in list(self.pressed_keys.values()):
            try:
                self.keyboard.release(val)
            except Exception:
                pass
        self.pressed_keys.clear()
        for name in tuple(self.pressed_buttons):
            try:
                self.mouse.release(getattr(self.Button, name))
            except Exception:
                pass
        self.pressed_buttons.clear()
