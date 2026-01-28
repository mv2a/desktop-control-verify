"""
Fast Win32 Discovery Script - No pywinauto.

Uses pure Win32 API + UI Automation COM directly for speed.
Discovers all UI elements by navigating through tabs and capturing state.

Approach:
1. Win32 EnumChildWindows for window handles
2. UI Automation COM API directly (faster than pywinauto wrapper)
3. Fast driver for navigation (clicking tabs, opening dialogs)
4. Screenshots at each phase for visual reference

Target: ~30-60 minutes instead of 9 hours
"""

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, 'src')

import win32gui
import win32con
import win32api
from PIL import ImageGrab

# UI Automation COM imports
import comtypes
import comtypes.client
from comtypes import GUID

# Initialize UI Automation
UIAutomationClient = comtypes.client.GetModule("UIAutomationCore.dll")
uia = comtypes.client.CreateObject(
    "{ff48dba4-60ef-4201-aa87-54103eef594e}",
    interface=UIAutomationClient.IUIAutomation
)


class FastDiscovery:
    """Fast Win32 + UIA COM discovery."""

    def __init__(self, output_dir: str = "data/fast_discovery"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.hwnd = None
        self.window_rect = None
        self.elements = {}
        self.screenshots = []
        self.phase_results = {}

        # Logging
        self.log_file = self.output_dir / "discovery.log"

    def log(self, msg: str):
        """Log message with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

    def screenshot(self, name: str) -> str:
        """Capture screenshot."""
        if self.window_rect:
            img = ImageGrab.grab(bbox=self.window_rect)
        else:
            img = ImageGrab.grab()

        path = self.output_dir / f"{name}.png"
        img.save(path)
        self.screenshots.append(str(path))
        return str(path)

    def connect(self) -> bool:
        """Connect to Mozaik window."""
        self.log("Connecting to Mozaik...")
        start = time.time()

        results = []
        def find_mozaik(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "Mozaik" in title:
                    results.append((hwnd, title))
            return True

        win32gui.EnumWindows(find_mozaik, None)

        if not results:
            self.log("ERROR: Mozaik window not found")
            return False

        self.hwnd, title = results[0]
        self.window_rect = win32gui.GetWindowRect(self.hwnd)

        elapsed = (time.time() - start) * 1000
        self.log(f"Connected to: {title} (hwnd={self.hwnd}) in {elapsed:.1f}ms")
        self.log(f"Window rect: {self.window_rect}")

        return True

    def click(self, x: int, y: int):
        """Click at screen coordinates."""
        from mozaik_automation.automation.fast_driver import FastMozaikDriver
        # Use pywinauto mouse just for clicking (it's fast)
        from pywinauto import mouse
        mouse.click(coords=(x, y))
        time.sleep(0.1)

    def click_relative(self, rx: int, ry: int):
        """Click relative to window."""
        wx, wy, _, _ = self.window_rect
        self.click(wx + rx, wy + ry)

    def send_keys(self, keys: str):
        """Send keyboard input."""
        import pywinauto.keyboard as kbd
        kbd.send_keys(keys)
        time.sleep(0.1)

    def get_uia_element(self, hwnd=None):
        """Get UI Automation element for window."""
        if hwnd is None:
            hwnd = self.hwnd
        return uia.ElementFromHandle(hwnd)

    def walk_uia_tree(self, element, depth=0, max_depth=10, tab="", subtab=""):
        """Walk UI Automation tree and collect elements."""
        if depth > max_depth:
            return

        try:
            # Get element properties
            automation_id = element.CurrentAutomationId or ""
            name = element.CurrentName or ""
            control_type = element.CurrentControlType
            class_name = element.CurrentClassName or ""

            # Get bounding rectangle
            rect = element.CurrentBoundingRectangle
            rect_dict = {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom
            }

            # Store element if it has an automation ID or meaningful name
            if automation_id or (name and control_type != 50000):  # 50000 = Text
                key = automation_id or f"{name}_{control_type}"
                if key not in self.elements:
                    self.elements[key] = {
                        "automation_id": automation_id,
                        "name": name,
                        "control_type": control_type,
                        "class_name": class_name,
                        "rect": rect_dict,
                        "tab": tab,
                        "subtab": subtab,
                        "depth": depth
                    }

            # Walk children
            tree_walker = uia.ControlViewWalker
            child = tree_walker.GetFirstChildElement(element)

            while child:
                self.walk_uia_tree(child, depth + 1, max_depth, tab, subtab)
                child = tree_walker.GetNextSiblingElement(child)

        except Exception as e:
            pass  # Skip elements that cause errors

    def scan_current_view(self, label: str, tab: str = "", subtab: str = ""):
        """Scan current UI state."""
        self.log(f"Scanning: {label}...")
        start = time.time()

        before_count = len(self.elements)

        # Get root element and walk tree
        root = self.get_uia_element()
        self.walk_uia_tree(root, tab=tab, subtab=subtab)

        new_count = len(self.elements) - before_count
        elapsed = time.time() - start

        self.log(f"  Found {new_count} new elements in {elapsed:.1f}s (total: {len(self.elements)})")

        # Screenshot
        self.screenshot(label)

        return new_count

    def run_discovery(self):
        """Run full discovery."""
        self.log("=" * 60)
        self.log("FAST WIN32 DISCOVERY")
        self.log("=" * 60)

        start_time = time.time()

        # Phase 0: Connect
        if not self.connect():
            return False

        self.screenshot("00_initial")

        # Phase 1: Baseline scan
        self.log("\n--- Phase 1: Baseline Scan ---")
        self.scan_current_view("01_baseline", tab="initial")

        # Phase 2: Job Tab
        self.log("\n--- Phase 2: Job Tab ---")
        self.click_relative(62, 77)  # Job tab
        time.sleep(0.5)
        self.scan_current_view("02_job_tab", tab="Job")

        # Phase 3: Settings Tab
        self.log("\n--- Phase 3: Settings Tab ---")
        self.click_relative(143, 77)  # Settings tab
        time.sleep(0.5)
        self.scan_current_view("03_settings_tab", tab="Settings")

        # Settings sub-tabs
        settings_subtabs = [
            ("Door/Drawer Fronts", 270, 148),
            ("Drawer/Tray Boxes", 392, 148),
            ("End/Back Panels", 519, 148),
            ("Materials", 607, 148),
            ("Textures", 676, 148),
            ("Libraries", 738, 148),
            ("Misc", 792, 148),
            ("Specs", 843, 148),
        ]

        for i, (subtab_name, x, y) in enumerate(settings_subtabs):
            self.log(f"  Scanning Settings > {subtab_name}...")
            self.click_relative(x, y)
            time.sleep(0.3)
            self.scan_current_view(f"03_{i+1}_settings_{subtab_name.lower().replace('/', '_')}",
                                   tab="Settings", subtab=subtab_name)

        # Phase 4: Room Tab
        self.log("\n--- Phase 4: Room Tab ---")
        self.click_relative(231, 77)  # Room tab
        time.sleep(0.5)
        self.scan_current_view("04_room_tab", tab="Room")

        # Room sub-tabs/categories
        room_categories = [
            ("Room", 243, 119),
            ("Walls", 284, 119),
            ("Islands", 338, 119),
            ("Windows", 457, 119),
            ("Sinks", 517, 119),
            ("Fridge", 623, 119),
            ("Range", 679, 119),
            ("Hood", 731, 119),
        ]

        for i, (cat_name, x, y) in enumerate(room_categories):
            self.log(f"  Scanning Room > {cat_name}...")
            self.click_relative(x, y)
            time.sleep(0.3)
            self.scan_current_view(f"04_{i+1}_room_{cat_name.lower()}",
                                   tab="Room", subtab=cat_name)

        # Phase 5: Products Tab
        self.log("\n--- Phase 5: Products Tab ---")
        self.click_relative(313, 77)  # Products tab
        time.sleep(0.5)
        self.scan_current_view("05_products_tab", tab="Products")

        # Phase 6: Tops Tab
        self.log("\n--- Phase 6: Tops Tab ---")
        self.click_relative(405, 77)  # Tops tab
        time.sleep(0.5)
        self.scan_current_view("06_tops_tab", tab="Tops")

        # Phase 7: Molding Tab
        self.log("\n--- Phase 7: Molding Tab ---")
        self.click_relative(491, 77)  # Molding tab
        time.sleep(0.5)
        self.scan_current_view("07_molding_tab", tab="Molding")

        # Phase 8: Order Tab
        self.log("\n--- Phase 8: Order Tab ---")
        self.click_relative(590, 77)  # Order tab
        time.sleep(0.5)
        self.scan_current_view("08_order_tab", tab="Order")

        # Phase 9: Explore Menus
        self.log("\n--- Phase 9: Menu Exploration ---")

        menus = [
            ("File", 35, 47),
            ("Edit", 75, 47),
            ("View", 119, 47),
            ("Libraries", 183, 47),
            ("Tools", 244, 47),
            ("Help", 294, 47),
        ]

        for menu_name, x, y in menus:
            self.log(f"  Opening {menu_name} menu...")
            self.click_relative(x, y)
            time.sleep(0.3)
            self.scan_current_view(f"09_menu_{menu_name.lower()}", tab="Menu", subtab=menu_name)
            self.send_keys("{ESC}")
            time.sleep(0.2)

        # Phase 10: Libraries > Products Dialog
        self.log("\n--- Phase 10: Products Library Dialog ---")
        self.click_relative(183, 47)  # Libraries menu
        time.sleep(0.3)
        self.click_relative(183, 70)  # Products (first item)
        time.sleep(1)
        self.scan_current_view("10_products_dialog", tab="Dialog", subtab="Products")
        self.send_keys("{ESC}")
        time.sleep(0.3)

        # Phase 11: Final Report
        self.log("\n--- Phase 11: Generating Report ---")

        total_time = time.time() - start_time

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_time_seconds": round(total_time, 1),
            "total_elements": len(self.elements),
            "screenshots": self.screenshots,
            "elements": self.elements,
            "by_tab": {},
            "by_control_type": {},
        }

        # Group by tab
        for key, elem in self.elements.items():
            tab = elem.get("tab", "unknown")
            if tab not in report["by_tab"]:
                report["by_tab"][tab] = []
            report["by_tab"][tab].append(key)

        # Group by control type
        for key, elem in self.elements.items():
            ct = elem.get("control_type", 0)
            if ct not in report["by_control_type"]:
                report["by_control_type"][ct] = []
            report["by_control_type"][ct].append(key)

        # Save report
        report_path = self.output_dir / "discovery_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        # Save element cache for fast driver
        cache_data = {
            "elements": {},
            "window_rect": list(self.window_rect),
        }

        for key, elem in self.elements.items():
            if elem.get("automation_id"):
                rect = elem.get("rect", {})
                # Convert to relative coordinates
                wx, wy, _, _ = self.window_rect
                cache_data["elements"][elem["automation_id"]] = {
                    "automation_id": elem["automation_id"],
                    "name": elem.get("name", ""),
                    "control_type": str(elem.get("control_type", "")),
                    "rect": [
                        rect.get("left", 0) - wx,
                        rect.get("top", 0) - wy,
                        rect.get("right", 0) - wx,
                        rect.get("bottom", 0) - wy,
                    ],
                    "tab": elem.get("tab", ""),
                    "hwnd": None
                }

        cache_path = self.output_dir / "element_cache.json"
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)

        self.log("")
        self.log("=" * 60)
        self.log(f"DISCOVERY COMPLETE!")
        self.log(f"  Total time: {total_time/60:.1f} minutes")
        self.log(f"  Elements found: {len(self.elements)}")
        self.log(f"  Screenshots: {len(self.screenshots)}")
        self.log(f"  Report: {report_path}")
        self.log(f"  Cache: {cache_path}")
        self.log("=" * 60)

        return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fast Win32 Discovery")
    parser.add_argument("--output", default="data/fast_discovery", help="Output directory")
    args = parser.parse_args()

    discovery = FastDiscovery(output_dir=args.output)
    success = discovery.run_discovery()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
