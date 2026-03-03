"""
Mozaik atomic action helper - CLI for single Win32 actions.

Used by Claude Code to drive Mozaik step by step with screenshot
feedback between actions.

Usage:
  python scripts/moz_action.py screenshot [name]
  python scripts/moz_action.py click X Y [desc]
  python scripts/moz_action.py dclick X Y [desc]
  python scripts/moz_action.py drag X1 Y1 X2 Y2 [desc]
  python scripts/moz_action.py type "text here"
  python scripts/moz_action.py key escape|enter|tab
  python scripts/moz_action.py info
"""

import sys
import time
import os
import json
from datetime import datetime

from PIL import ImageGrab
import win32gui
import win32api
import win32con

SCREENSHOT_DIR = "data/copilot"
STATE_FILE = "data/copilot/state.json"


def find_mozaik():
    results = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if "Mozaik Enterprise" in t and "Room Viewer" not in t:
                results.append((hwnd, t))
        return True
    win32gui.EnumWindows(cb, None)
    if not results:
        print("ERROR: Mozaik Enterprise not found")
        sys.exit(1)
    hwnd, title = results[0]
    rect = win32gui.GetWindowRect(hwnd)
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    return hwnd, rect, w, h, title


def do_click(rect, x, y, desc=""):
    ax, ay = rect[0] + x, rect[1] + y
    win32api.SetCursorPos((ax, ay))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)
    print(f"OK click ({x},{y}) {desc}")


def do_dclick(rect, x, y, desc=""):
    ax, ay = rect[0] + x, rect[1] + y
    win32api.SetCursorPos((ax, ay))
    time.sleep(0.05)
    for _ in range(2):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.05)
    time.sleep(0.3)
    print(f"OK dclick ({x},{y}) {desc}")


def do_drag(rect, x1, y1, x2, y2, desc=""):
    ax1, ay1 = rect[0] + x1, rect[1] + y1
    ax2, ay2 = rect[0] + x2, rect[1] + y2
    win32api.SetCursorPos((ax1, ay1))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.1)
    for i in range(1, 16):
        ix = ax1 + (ax2 - ax1) * i // 15
        iy = ay1 + (ay2 - ay1) * i // 15
        win32api.SetCursorPos((ix, iy))
        time.sleep(0.03)
    time.sleep(0.1)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)
    print(f"OK drag ({x1},{y1})->({x2},{y2}) {desc}")


def do_type(text):
    for c in text:
        vk = win32api.VkKeyScan(c)
        if vk != -1:
            shift = (vk >> 8) & 1
            vk = vk & 0xFF
            if shift:
                win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            if shift:
                win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
    print(f"OK type '{text}'")


def do_key(name):
    key_map = {
        "escape": win32con.VK_ESCAPE,
        "esc": win32con.VK_ESCAPE,
        "enter": win32con.VK_RETURN,
        "return": win32con.VK_RETURN,
        "tab": win32con.VK_TAB,
        "space": win32con.VK_SPACE,
        "delete": win32con.VK_DELETE,
        "backspace": win32con.VK_BACK,
        "up": win32con.VK_UP,
        "down": win32con.VK_DOWN,
        "left": win32con.VK_LEFT,
        "right": win32con.VK_RIGHT,
        "a": ord('A'), "w": ord('W'), "s": ord('S'), "d": ord('D'),
    }
    vk = key_map.get(name.lower())
    if vk is None:
        print(f"ERROR: unknown key '{name}'")
        sys.exit(1)
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    print(f"OK key {name}")


def do_screenshot(name=None):
    hwnd, rect, w, h, title = find_mozaik()
    rect = win32gui.GetWindowRect(hwnd)
    img = ImageGrab.grab(bbox=rect)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    if not name:
        name = datetime.now().strftime("%H%M%S")
    path = f"{SCREENSHOT_DIR}/{name}.png"
    img.save(path)
    print(f"OK screenshot {path} ({w}x{h})")
    return path


def do_info():
    hwnd, rect, w, h, title = find_mozaik()
    print(f"Window: {title}")
    print(f"Size: {w}x{h}")
    print(f"Position: ({rect[0]},{rect[1]})-({rect[2]},{rect[3]})")

    # Check for dialogs
    dialogs = []
    def find_dialogs(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if t and "Mozaik Enterprise" not in t:
                if cls in ("#32770", "Dialog", "WindowsForms10.Window"):
                    dialogs.append({"title": t, "class": cls, "hwnd": hwnd})
                elif any(kw in t for kw in ["Warning", "Error", "Confirm", "Fit", "Collision", "Product", "Align"]):
                    dialogs.append({"title": t, "class": cls, "hwnd": hwnd})
        return True
    win32gui.EnumWindows(find_dialogs, None)

    if dialogs:
        print(f"Dialogs: {len(dialogs)}")
        for d in dialogs:
            r = win32gui.GetWindowRect(d["hwnd"])
            print(f"  - '{d['title']}' ({d['class']}) at ({r[0]},{r[1]})-({r[2]},{r[3]})")
    else:
        print("Dialogs: none")


def do_multi(commands_json):
    """Execute multiple actions in sequence from a JSON array.

    Each entry: {"action": "click", "x": 210, "y": 63, "desc": "Room tab", "wait": 0.5}
    Supported actions: click, dclick, drag, type, key, screenshot, wait
    """
    hwnd, rect, w, h, title = find_mozaik()
    commands = json.loads(commands_json)

    for i, cmd in enumerate(commands):
        action = cmd["action"]
        wait_after = cmd.get("wait", 0.3)

        # Refresh rect before each action
        rect = win32gui.GetWindowRect(hwnd)

        if action == "click":
            do_click(rect, cmd["x"], cmd["y"], cmd.get("desc", ""))
        elif action == "dclick":
            do_dclick(rect, cmd["x"], cmd["y"], cmd.get("desc", ""))
        elif action == "drag":
            do_drag(rect, cmd["x1"], cmd["y1"], cmd["x2"], cmd["y2"], cmd.get("desc", ""))
        elif action == "type":
            do_type(cmd["text"])
        elif action == "key":
            do_key(cmd["name"])
        elif action == "screenshot":
            do_screenshot(cmd.get("name"))
        elif action == "wait":
            pass  # just the wait_after below
        else:
            print(f"WARN: unknown action '{action}' at step {i}")

        if wait_after > 0:
            time.sleep(wait_after)

    print(f"OK multi: {len(commands)} actions completed")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1].lower()
    hwnd, rect, w, h, title = find_mozaik()

    if cmd == "screenshot":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        do_screenshot(name)
    elif cmd == "click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        desc = sys.argv[4] if len(sys.argv) > 4 else ""
        do_click(rect, x, y, desc)
    elif cmd == "dclick":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        desc = sys.argv[4] if len(sys.argv) > 4 else ""
        do_dclick(rect, x, y, desc)
    elif cmd == "drag":
        x1, y1 = int(sys.argv[2]), int(sys.argv[3])
        x2, y2 = int(sys.argv[4]), int(sys.argv[5])
        desc = sys.argv[6] if len(sys.argv) > 6 else ""
        do_drag(rect, x1, y1, x2, y2, desc)
    elif cmd == "type":
        do_type(sys.argv[2])
    elif cmd == "key":
        do_key(sys.argv[2])
    elif cmd == "info":
        do_info()
    elif cmd == "multi":
        do_multi(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
