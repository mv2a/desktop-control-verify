"""
Fast Mozaik Driver using Win32 + Cached Elements.

This driver avoids slow UIA tree traversals by:
1. Using Win32 API for window handles and input
2. Caching element positions after initial discovery
3. Using SendKeys for typing (instant)
4. Only using UIA for reading values when needed

Performance comparison:
- pywinauto UIA: 30-90s per element lookup
- This driver: <100ms per action (after initial cache)
"""

import ctypes
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

# Win32 constants
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5

# ctypes.windll exists only on Windows. Resolve it softly so the module (and the
# ElementCache in it) can be imported and tested on any OS; the Win32 calls below
# still require Windows at run time.
_windll = getattr(ctypes, "windll", None)
user32 = _windll.user32 if _windll else None
kernel32 = _windll.kernel32 if _windll else None


@dataclass
class CachedElement:
    """Cached UI element with position and metadata."""
    automation_id: str
    name: str
    control_type: str
    rect: Tuple[int, int, int, int]  # left, top, right, bottom
    tab: str  # Which tab this element is on
    hwnd: Optional[int] = None  # Win32 handle if available


class ElementCache:
    """Persistent cache for Mozaik UI elements."""

    def __init__(self, cache_file: str = "mozaik_element_cache.json"):
        self.cache_file = Path(cache_file)
        self.elements: Dict[str, CachedElement] = {}
        self.window_rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
        self.current_tab: str = "Room"
        self._load_cache()

    def _load_cache(self):
        """Load cache from disk if exists."""
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text())
                for aid, elem_data in data.get("elements", {}).items():
                    self.elements[aid] = CachedElement(**elem_data)
                self.window_rect = tuple(data.get("window_rect", [0, 0, 0, 0]))
                print(f"Loaded {len(self.elements)} cached elements")
            except Exception as e:
                print(f"Cache load failed: {e}")

    def save_cache(self):
        """Save cache to disk."""
        data = {
            "elements": {
                aid: {
                    "automation_id": e.automation_id,
                    "name": e.name,
                    "control_type": e.control_type,
                    "rect": e.rect,
                    "tab": e.tab,
                    "hwnd": e.hwnd,
                }
                for aid, e in self.elements.items()
            },
            "window_rect": self.window_rect,
        }
        self.cache_file.write_text(json.dumps(data, indent=2))
        print(f"Saved {len(self.elements)} elements to cache")

    def get(self, automation_id: str) -> Optional[CachedElement]:
        """Get cached element by automation ID."""
        return self.elements.get(automation_id)

    def add(self, elem: CachedElement):
        """Add element to cache."""
        self.elements[elem.automation_id] = elem

    def get_center(self, automation_id: str) -> Optional[Tuple[int, int]]:
        """Get center coordinates of cached element."""
        elem = self.get(automation_id)
        if elem:
            l, t, r, b = elem.rect
            return ((l + r) // 2, (t + b) // 2)
        return None


class FastMozaikDriver:
    """
    Fast Mozaik driver using Win32 API + caching.

    Usage:
        driver = FastMozaikDriver()
        driver.connect()

        # Fast click using cached coordinates
        driver.click("RoomNameTextBox")
        driver.type_text("Kitchen")

        # Switch tabs (instant with cache)
        driver.switch_tab("Settings")
    """

    # Pre-defined element positions (relative to window)
    # These are fallbacks if cache is empty
    DEFAULT_ELEMENTS = {
        # Tabs (relative positions)
        "Tab_Job": {"rect": (170, 163, 200, 183), "tab": "*"},
        "Tab_Settings": {"rect": (230, 163, 280, 183), "tab": "*"},
        "Tab_Room": {"rect": (295, 163, 335, 183), "tab": "*"},
        "Tab_Order": {"rect": (565, 163, 605, 183), "tab": "*"},

        # Room tab elements
        "RoomNameTextBox": {"rect": (150, 225, 280, 245), "tab": "Room"},
        "H_WallsTextBox": {"rect": (200, 298, 240, 318), "tab": "Room"},
        "RoomTabButtonDrawWalls": {"rect": (140, 217, 260, 237), "tab": "Room"},
        "RoomTabChkQuickRoom": {"rect": (140, 363, 160, 383), "tab": "Room"},
        "SchematicCanvas": {"rect": (310, 200, 850, 620), "tab": "Room"},

        # Toolbar
        "ProductsButton": {"rect": (355, 163, 400, 183), "tab": "*"},
        "3DButton": {"rect": (845, 258, 865, 278), "tab": "*"},
    }

    def __init__(
        self,
        cache_file: str = None,
        window_title: str = "Mozaik",
        default_elements: Optional[Dict[str, dict]] = None,
    ):
        """Create a driver for the first visible window whose title contains `window_title`.

        The defaults reproduce the original Mozaik V14 configuration. For any other
        application pass its title substring, and either a `default_elements` map of
        fallback positions or an empty dict to rely on the cache alone.
        """
        self.hwnd = None
        self.pid = None
        self.window_title = window_title
        self.default_elements = (
            self.DEFAULT_ELEMENTS if default_elements is None else default_elements
        )
        self.cache = ElementCache(cache_file) if cache_file else ElementCache()
        self._app = None  # pywinauto app for fallback

    def connect(self) -> bool:
        """Connect to Mozaik window using Win32 (fast)."""
        start = time.time()

        # Use win32gui directly - more reliable on Windows
        try:
            import win32gui
            import win32con

            results = []

            def find_mozaik(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if self.window_title in title:
                        results.append((hwnd, title))
                return True

            win32gui.EnumWindows(find_mozaik, None)

            if not results:
                print(f"No visible window with {self.window_title!r} in its title")
                return False

            self.hwnd, title = results[0]

            # Get window rect using win32gui
            rect = win32gui.GetWindowRect(self.hwnd)
            self.cache.window_rect = rect  # (left, top, right, bottom)

            elapsed = time.time() - start
            print(f"Connected to: {title} (hwnd={self.hwnd}) in {elapsed*1000:.1f}ms")
            return True

        except ImportError:
            print("win32gui not available - install pywin32")
            return False
        except Exception as e:
            print(f"Connect failed: {e}")
            return False

    def _get_abs_coords(self, automation_id: str) -> Optional[Tuple[int, int]]:
        """Get absolute screen coordinates for element."""
        # Try cache first
        center = self.cache.get_center(automation_id)
        if center:
            # Add window offset
            wx, wy = self.cache.window_rect[0], self.cache.window_rect[1]
            return (center[0] + wx, center[1] + wy)

        # Try default positions
        if automation_id in self.default_elements:
            elem = self.default_elements[automation_id]
            l, t, r, b = elem["rect"]
            cx, cy = (l + r) // 2, (t + b) // 2
            wx, wy = self.cache.window_rect[0], self.cache.window_rect[1]
            return (cx + wx, cy + wy)

        return None

    def click(self, automation_id: str) -> bool:
        """Click element using Win32 (instant)."""
        start = time.time()

        coords = self._get_abs_coords(automation_id)
        if not coords:
            print(f"Element not found in cache: {automation_id}")
            return False

        x, y = coords
        self._do_click(x, y)

        elapsed = time.time() - start
        print(f"Click {automation_id} at ({x}, {y}) in {elapsed*1000:.1f}ms")
        return True

    def click_coords(self, x: int, y: int) -> bool:
        """Click at coordinates relative to window."""
        start = time.time()

        # Add window offset
        wx, wy = self.cache.window_rect[0], self.cache.window_rect[1]
        abs_x, abs_y = x + wx, y + wy

        self._do_click(abs_x, abs_y)

        elapsed = time.time() - start
        print(f"Click at ({abs_x}, {abs_y}) in {elapsed*1000:.1f}ms")
        return True

    def _do_click(self, x: int, y: int):
        """Perform actual click at absolute screen coordinates."""
        try:
            # Use pywinauto's mouse module - works from WSL/remote
            from pywinauto import mouse
            mouse.click(coords=(x, y))
        except Exception as e1:
            try:
                # Fallback to win32api
                import win32api
                import win32con
                win32api.SetCursorPos((x, y))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
            except Exception as e2:
                print(f"Click failed: {e1}, {e2}")

    def type_text(self, text: str) -> bool:
        """Type text using SendKeys (instant)."""
        start = time.time()

        try:
            import pywinauto.keyboard as kbd
            kbd.send_keys(text, with_spaces=True)
            elapsed = time.time() - start
            print(f"Typed '{text}' in {elapsed*1000:.1f}ms")
            return True
        except Exception as e:
            print(f"Type failed: {e}")
            return False

    def send_keys(self, keys: str) -> bool:
        """Send special keys like {ENTER}, {ESC}, etc."""
        start = time.time()

        try:
            import pywinauto.keyboard as kbd
            kbd.send_keys(keys)
            elapsed = time.time() - start
            print(f"Sent keys '{keys}' in {elapsed*1000:.1f}ms")
            return True
        except Exception as e:
            print(f"SendKeys failed: {e}")
            return False

    def switch_tab(self, tab_name: str) -> bool:
        """Switch to tab using cached coordinates."""
        tab_key = f"Tab_{tab_name}"
        if self.click(tab_key):
            self.cache.current_tab = tab_name
            time.sleep(0.3)  # Small delay for UI to update
            return True
        return False

    def build_cache_from_uia(self):
        """
        One-time UIA scan to build element cache.
        This is slow but only needs to run once.
        """
        print("Building element cache from UIA (one-time)...")
        start = time.time()

        try:
            from pywinauto import Application

            app = Application(backend="uia").connect(handle=self.hwnd)
            main = app.window(handle=self.hwnd)

            # Get window rect
            rect = main.rectangle()
            self.cache.window_rect = (rect.left, rect.top, rect.right, rect.bottom)

            # Scan descendants
            count = 0
            for desc in main.descendants():
                try:
                    aid = desc.element_info.automation_id
                    if not aid:
                        continue

                    r = desc.rectangle()
                    elem = CachedElement(
                        automation_id=aid,
                        name=desc.element_info.name or "",
                        control_type=desc.element_info.control_type or "",
                        rect=(r.left - rect.left, r.top - rect.top,
                              r.right - rect.left, r.bottom - rect.top),
                        tab=self.cache.current_tab,
                    )
                    self.cache.add(elem)
                    count += 1
                except Exception:
                    continue

            self.cache.save_cache()
            elapsed = time.time() - start
            print(f"Cached {count} elements in {elapsed:.1f}s")

        except Exception as e:
            print(f"Cache build failed: {e}")

    def screenshot(self, filename: str = None) -> Optional[str]:
        """Capture window screenshot."""
        try:
            from PIL import ImageGrab

            rect = self.cache.window_rect
            img = ImageGrab.grab(bbox=rect)

            if filename:
                img.save(filename)
                return filename
            else:
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"screenshot_{ts}.png"
                img.save(path)
                return path
        except Exception as e:
            print(f"Screenshot failed: {e}")
            return None


# Application-neutral name for the same driver.
CachedWin32Driver = FastMozaikDriver


# Convenience function for quick testing
def demo():
    """Quick demo of fast driver."""
    driver = FastMozaikDriver()

    if not driver.connect():
        print("Failed to connect")
        return

    # Build cache if empty
    if len(driver.cache.elements) == 0:
        driver.build_cache_from_uia()

    # Demo: switch to Room tab and click canvas
    print("\n--- Demo Actions ---")
    driver.switch_tab("Room")
    time.sleep(0.5)
    driver.click_coords(400, 350)  # Click on canvas
    driver.send_keys("{ESC}")


if __name__ == "__main__":
    demo()
