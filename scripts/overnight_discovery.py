"""
Overnight Mozaik UI Discovery Script.

Comprehensive, self-contained script that runs ~9 hours overnight to discover
ALL UI elements in Mozaik Enterprise: tabs, sub-tabs, dialogs, menus,
ComboBox values, TextBox values, context menus, and keyboard shortcuts.

Safety: READ-ONLY operations only. No set_text(), no Delete clicks.
Only opens menus/dialogs for scanning, then closes via Cancel/Escape.

16 phases with time budgets, checkpoint saves after each phase,
auto-reconnect on COM errors, and thread-based timeout protection.

Requires: pywinauto 0.6.9, pillow
Target: 14coresbeast (Windows, Python 3.9.9)

Usage:
    python overnight_discovery.py [--output data/overnight] [--window-title ".*Mozaik Enterprise.*"]
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PHASE_BUDGETS_SECONDS = {
    0: 2 * 60,       # Connect & Metadata
    1: 10 * 60,      # Baseline Scan
    2: 45 * 60,      # Per-Tab Scans
    3: 90 * 60,      # Settings Sub-tabs
    4: 30 * 60,      # Room Sub-tabs
    5: 60 * 60,      # ComboBox Enumeration
    6: 30 * 60,      # TextBox Value Reading
    7: 60 * 60,      # Menu Bar Exploration
    8: 60 * 60,      # Products Library Dialog
    9: 30 * 60,      # Door Style Dialog
    10: 60 * 60,     # Other Library Dialogs
    11: 45 * 60,     # Tools Menu Dialogs
    12: 30 * 60,     # Order Tab Deep Scan
    13: 30 * 60,     # Context Menus
    14: 15 * 60,     # Keyboard Shortcuts
    15: 5 * 60,      # Final Report & Cleanup
}

PHASE_NAMES = {
    0: "connect",
    1: "baseline",
    2: "per_tab",
    3: "settings_subtabs",
    4: "room_subtabs",
    5: "combobox_enum",
    6: "textbox_values",
    7: "menu_bar",
    8: "products_dialog",
    9: "door_style_dialog",
    10: "library_dialogs",
    11: "tools_dialogs",
    12: "order_deep_scan",
    13: "context_menus",
    14: "keyboard_shortcuts",
    15: "final_report",
}

LAYOUT_TABS = ["Job", "Settings", "Room", "Order"]

MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_SLEEP_S = 10


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredElement:
    """A single discovered UI element."""
    automation_id: str = ""
    name: str = ""
    control_type: str = ""
    class_name: str = ""
    rectangle: Optional[Dict[str, int]] = None
    enabled: bool = True
    visible: bool = True
    tab: str = ""
    subtab: str = ""
    parent_id: str = ""
    depth: int = 0
    current_value: Optional[str] = None
    combo_options: Optional[List[str]] = None
    access_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "automation_id": self.automation_id,
            "name": self.name,
            "control_type": self.control_type,
            "class_name": self.class_name,
            "enabled": self.enabled,
            "visible": self.visible,
            "tab": self.tab,
            "subtab": self.subtab,
            "depth": self.depth,
        }
        if self.rectangle:
            d["rectangle"] = self.rectangle
        if self.parent_id:
            d["parent_id"] = self.parent_id
        if self.current_value is not None:
            d["current_value"] = self.current_value
        if self.combo_options is not None:
            d["combo_options"] = self.combo_options
        if self.access_key is not None:
            d["access_key"] = self.access_key
        return d


@dataclass
class OvernightReport:
    """Comprehensive overnight discovery report."""
    metadata: Dict[str, Any] = field(default_factory=dict)
    elements: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tabs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    dialogs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    menus: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    combobox_values: Dict[str, List[str]] = field(default_factory=dict)
    context_menus: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    timing: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "elements": self.elements,
            "tabs": self.tabs,
            "dialogs": self.dialogs,
            "menus": self.menus,
            "combobox_values": self.combobox_values,
            "context_menus": self.context_menus,
            "errors": self.errors,
            "timing": self.timing,
        }

    def merge_checkpoint(self, checkpoint: Dict[str, Any]) -> None:
        """Merge a phase checkpoint into this report."""
        for key in ["elements", "tabs", "dialogs", "menus",
                     "combobox_values", "context_menus"]:
            if key in checkpoint:
                target = getattr(self, key)
                if isinstance(target, dict):
                    target.update(checkpoint[key])
        if "errors" in checkpoint:
            self.errors.extend(checkpoint["errors"])
        if "timing" in checkpoint:
            self.timing.update(checkpoint["timing"])


def build_element_key(elem: DiscoveredElement) -> str:
    """Build a unique key for deduplication. Prefer automation_id, fall back to name+type."""
    if elem.automation_id:
        return elem.automation_id
    parts = [elem.name or "(unnamed)", elem.control_type or "(unknown)"]
    if elem.tab:
        parts.append(elem.tab)
    if elem.subtab:
        parts.append(elem.subtab)
    return "|".join(parts)


def extract_element(wrapper, depth: int = 0, tab: str = "",
                    subtab: str = "", parent_id: str = "") -> Optional[DiscoveredElement]:
    """Extract element info from a pywinauto wrapper object."""
    try:
        info = wrapper.element_info
        rect = None
        try:
            r = info.rectangle
            rect = {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom}
        except Exception:
            pass

        ak = None
        try:
            ak = getattr(info, "access_key", None) or None
        except Exception:
            pass

        return DiscoveredElement(
            automation_id=getattr(info, "automation_id", "") or "",
            name=getattr(info, "name", "") or "",
            control_type=getattr(info, "control_type", "") or "",
            class_name=getattr(info, "class_name", "") or "",
            rectangle=rect,
            enabled=getattr(info, "enabled", True),
            visible=getattr(info, "visible", True),
            tab=tab,
            subtab=subtab,
            parent_id=parent_id,
            depth=depth,
            access_key=ak,
        )
    except Exception:
        return None


def save_checkpoint(data: Dict[str, Any], output_dir: Path,
                    phase_name: str) -> str:
    """Save a checkpoint JSON file. Returns the file path."""
    ckpt_dir = output_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"checkpoint_after_{phase_name}_{ts}.json"
    filepath = ckpt_dir / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return str(filepath)


def load_checkpoint(filepath: str) -> Dict[str, Any]:
    """Load a checkpoint JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def merge_elements(existing: Dict[str, Dict[str, Any]],
                   new_elements: List[DiscoveredElement]) -> Dict[str, Dict[str, Any]]:
    """Merge new elements into existing dict, deduplicating by key."""
    for elem in new_elements:
        key = build_element_key(elem)
        if key not in existing or elem.tab:
            existing[key] = elem.to_dict()
    return existing


DIALOG_CLOSE_BUTTONS = ["Cancel", "Close", "No", "Abort", "OK"]


def get_dialog_close_order() -> List[str]:
    """Return ordered list of button names to try when closing dialogs."""
    return list(DIALOG_CLOSE_BUTTONS)


# ---------------------------------------------------------------------------
# Phase runner with timeout
# ---------------------------------------------------------------------------

class PhaseRunner:
    """Runs a phase function with a hard timeout via daemon thread."""

    def __init__(self, phase_num: int, phase_name: str, budget_s: int,
                 logger: logging.Logger):
        self.phase_num = phase_num
        self.phase_name = phase_name
        self.budget_s = budget_s
        self.logger = logger
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.elapsed: float = 0.0

    def run(self, func, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Run func in a daemon thread with timeout. Returns result dict or None."""
        self.logger.info(
            f"=== Phase {self.phase_num}: {self.phase_name} "
            f"(budget: {self.budget_s}s) ==="
        )
        start = time.time()

        def _target():
            try:
                self.result = func(*args, **kwargs)
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                self.logger.error(f"Phase {self.phase_num} error: {self.error}")

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout=self.budget_s)
        self.elapsed = time.time() - start

        if t.is_alive():
            self.logger.warning(
                f"Phase {self.phase_num} ({self.phase_name}) timed out "
                f"after {self.elapsed:.1f}s (budget: {self.budget_s}s)"
            )
            self.error = f"Timed out after {self.elapsed:.1f}s"

        self.logger.info(
            f"Phase {self.phase_num} done in {self.elapsed:.1f}s "
            f"({'OK' if self.error is None else 'ERROR'})"
        )
        return self.result


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

class MozaikConnection:
    """Manages pywinauto connection to Mozaik with auto-reconnect."""

    def __init__(self, window_title_re: str, logger: logging.Logger):
        self.window_title_re = window_title_re
        self.logger = logger
        self.app = None
        self.main_window = None

    def connect(self) -> bool:
        """Connect to Mozaik window. Returns True on success."""
        from pywinauto import Application
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            try:
                self.logger.info(
                    f"Connecting to Mozaik (attempt {attempt}/{MAX_RECONNECT_ATTEMPTS})..."
                )
                self.app = Application(backend="uia").connect(
                    title_re=self.window_title_re, timeout=10
                )
                self.main_window = self.app.window(title_re=self.window_title_re)
                title = self.main_window.window_text()
                self.logger.info(f"Connected: {title}")
                return True
            except Exception as e:
                self.logger.warning(f"Connection attempt {attempt} failed: {e}")
                if attempt < MAX_RECONNECT_ATTEMPTS:
                    time.sleep(RECONNECT_SLEEP_S)
        return False

    def reconnect(self) -> bool:
        """Attempt to reconnect after a COM error."""
        self.logger.info("Attempting reconnect...")
        self.app = None
        self.main_window = None
        return self.connect()

    def ensure_connected(self) -> bool:
        """Verify connection is alive; reconnect if stale.

        pywinauto 0.6.9 COM connections go stale after long operations.
        This refreshes the window handle by re-connecting.
        """
        try:
            # Quick liveness check - try to read the window title
            _ = self.main_window.window_text()
            # Also refresh the window handle to prevent stale COM refs
            self.main_window = self.app.window(title_re=self.window_title_re)
            return True
        except Exception:
            self.logger.warning("Connection stale, reconnecting...")
            return self.reconnect()

    def get_metadata(self) -> Dict[str, Any]:
        """Collect window metadata."""
        meta: Dict[str, Any] = {
            "window_title": "",
            "pid": 0,
            "rectangle": None,
        }
        try:
            meta["window_title"] = self.main_window.window_text()
        except Exception:
            pass
        try:
            meta["pid"] = self.main_window.process_id()
        except Exception:
            pass
        try:
            r = self.main_window.rectangle()
            meta["rectangle"] = {
                "left": r.left, "top": r.top,
                "right": r.right, "bottom": r.bottom,
            }
        except Exception:
            pass
        return meta


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def dismiss_dialogs(main_window, logger: logging.Logger) -> int:
    """Close any open child/top-level dialogs. Returns count dismissed.

    SAFETY: Does NOT send Escape to the main window (that triggers
    Mozaik's "Save changes?" exit flow). Only closes dialogs that are
    separate top-level windows with Cancel/Close/No buttons.
    """
    dismissed = 0
    main_title = ""
    try:
        main_title = main_window.window_text()
    except Exception:
        pass

    # Strategy 1: Check for top-level dialog windows (separate from main)
    try:
        app = main_window.app
        for win in app.windows():
            try:
                win_title = win.window_text()
                # Skip the main Mozaik window itself
                if not win_title or win_title == main_title:
                    continue
                # Skip if it looks like the main window (contains "Mozaik")
                if "Mozaik" in win_title and "Enterprise" in win_title:
                    continue
                logger.info(f"Found dialog window: '{win_title}' - attempting close")
                for btn_name in get_dialog_close_order():
                    try:
                        btn = win.child_window(
                            title=btn_name, control_type="Button"
                        ).wrapper_object()
                        btn.click_input()
                        dismissed += 1
                        time.sleep(0.5)
                        break
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 2: Send Escape ONLY if we detected and closed a dialog
    # (to clean up any residual popup/menu state from the dialog)
    if dismissed:
        try:
            import pywinauto.keyboard
            pywinauto.keyboard.send_keys("{ESC}")
            time.sleep(0.2)
        except Exception:
            pass
        logger.info(f"Dismissed {dismissed} dialog(s)")

    return dismissed


def switch_tab(main_window, tab_name: str, logger: logging.Logger,
               timeout_s: int = 60, conn: Optional['MozaikConnection'] = None) -> bool:
    """Switch to a layout tab. Returns True on success.

    If conn is provided, attempts reconnect on failure.
    """
    result = [False]
    window_ref = [main_window]

    def _do():
        try:
            tab_item = window_ref[0].child_window(
                title=tab_name, control_type="TabItem"
            ).wrapper_object()
            tab_item.select()
            time.sleep(0.5)
            result[0] = True
        except Exception as e:
            logger.warning(f"Tab switch to {tab_name} failed: {e}")

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if not result[0] and t.is_alive():
        logger.warning(f"Tab switch to {tab_name} timed out after {timeout_s}s")

    # Retry with reconnect if first attempt failed
    if not result[0] and conn is not None:
        logger.info(f"Retrying tab switch to {tab_name} after reconnect...")
        if conn.ensure_connected():
            window_ref[0] = conn.main_window
            result[0] = False

            t2 = threading.Thread(target=_do, daemon=True)
            t2.start()
            t2.join(timeout=timeout_s)
            if not result[0] and t2.is_alive():
                logger.warning(f"Tab switch retry to {tab_name} also timed out")

    return result[0]


def take_screenshot(main_window, filepath: Path,
                    logger: logging.Logger) -> Optional[str]:
    """Take a screenshot. Returns path string or None."""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        img = main_window.capture_as_image()
        img.save(str(filepath))
        logger.info(f"Screenshot: {filepath}")
        return str(filepath)
    except Exception as e:
        logger.warning(f"Screenshot failed: {e}")
        return None


def scan_descendants(parent_wrapper, tab: str = "", subtab: str = "",
                     logger: Optional[logging.Logger] = None,
                     timeout_s: int = 300) -> List[DiscoveredElement]:
    """Scan all descendants of a wrapper with timeout protection."""
    elements: List[DiscoveredElement] = []
    result_holder: List[List[DiscoveredElement]] = [[]]

    def _scan():
        found = []
        try:
            for desc in parent_wrapper.descendants():
                elem = extract_element(desc, tab=tab, subtab=subtab)
                if elem is not None:
                    # Try to get parent automation_id
                    try:
                        p = desc.parent()
                        if p:
                            elem.parent_id = getattr(
                                p.element_info, "automation_id", ""
                            ) or ""
                    except Exception:
                        pass
                    # Try to get depth
                    try:
                        elem.depth = getattr(desc, "depth", 0) or 0
                    except Exception:
                        pass
                    found.append(elem)
        except Exception as e:
            if logger:
                logger.warning(f"Scan error: {e}")
        result_holder[0] = found

    t = threading.Thread(target=_scan, daemon=True)
    t.start()
    t.join(timeout=timeout_s)

    if t.is_alive():
        if logger:
            logger.warning(f"Scan timed out after {timeout_s}s")
    elements = result_holder[0]
    if logger:
        logger.info(f"Scanned {len(elements)} descendants (tab={tab}, subtab={subtab})")
    return elements


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------

def phase_connect(conn: MozaikConnection, report: OvernightReport,
                  output_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Phase 0: Connect and collect metadata."""
    if not conn.connect():
        raise ConnectionError("Could not connect to Mozaik")
    meta = conn.get_metadata()
    report.metadata.update(meta)
    return {"metadata": meta}


def phase_baseline(conn: MozaikConnection, report: OvernightReport,
                   output_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Phase 1: Full descendants() scan from Room tab."""
    conn.ensure_connected()
    main = conn.main_window
    dismiss_dialogs(main, logger)

    # Ensure we're on Room tab
    switch_tab(main, "Room", logger, conn=conn)

    # Screenshot
    ss_dir = output_dir / "screenshots"
    take_screenshot(main, ss_dir / "baseline_room.png", logger)

    # Full scan
    elements = scan_descendants(main, tab="Room", logger=logger, timeout_s=540)

    merged = merge_elements({}, elements)
    report.elements.update(merged)

    return {
        "elements": merged,
        "stats": {
            "total_elements": len(merged),
            "control_types": _count_control_types(elements),
        },
    }


def phase_per_tab(conn: MozaikConnection, report: OvernightReport,
                  output_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Phase 2: Switch to each tab, scan descendants, screenshot."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    tab_results: Dict[str, Any] = {}
    all_elements: Dict[str, Dict[str, Any]] = {}

    for tab_name in LAYOUT_TABS:
        # Refresh connection before each tab (COM can go stale)
        conn.ensure_connected()
        main = conn.main_window
        dismiss_dialogs(main, logger)
        logger.info(f"Scanning tab: {tab_name}")

        if not switch_tab(main, tab_name, logger, conn=conn):
            tab_results[tab_name] = {"error": "Could not switch to tab"}
            continue

        time.sleep(1.0)
        take_screenshot(main, ss_dir / f"tab_{tab_name.lower()}.png", logger)

        elements = scan_descendants(main, tab=tab_name, logger=logger, timeout_s=600)
        tab_merged = merge_elements({}, elements)
        all_elements.update(tab_merged)

        tab_results[tab_name] = {
            "element_count": len(tab_merged),
            "control_types": _count_control_types(elements),
            "screenshot": f"tab_{tab_name.lower()}.png",
        }

    # Return to Room tab
    conn.ensure_connected()
    switch_tab(conn.main_window, "Room", logger, conn=conn)

    report.elements.update(all_elements)
    report.tabs.update(tab_results)

    return {"elements": all_elements, "tabs": tab_results}


def phase_settings_subtabs(conn: MozaikConnection, report: OvernightReport,
                           output_dir: Path,
                           logger: logging.Logger) -> Dict[str, Any]:
    """Phase 3: Discover and scan all Settings sub-tabs."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    dismiss_dialogs(main, logger)

    if not switch_tab(main, "Settings", logger, conn=conn):
        return {"error": "Could not switch to Settings tab"}

    time.sleep(1.0)

    # Find all TabItem children within Settings
    subtab_names: List[str] = []
    subtab_data: Dict[str, Any] = {}
    all_elements: Dict[str, Dict[str, Any]] = {}

    try:
        # Discover sub-tabs by looking for TabControl children
        tab_controls = []
        for desc in main.descendants():
            try:
                info = desc.element_info
                if getattr(info, "control_type", "") == "TabItem":
                    name = getattr(info, "name", "") or ""
                    # Skip the main layout tabs
                    if name and name not in LAYOUT_TABS and name not in subtab_names:
                        subtab_names.append(name)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Error discovering Settings sub-tabs: {e}")

    logger.info(f"Found Settings sub-tabs: {subtab_names}")

    for subtab_name in subtab_names:
        dismiss_dialogs(main, logger)
        logger.info(f"Scanning Settings > {subtab_name}")

        try:
            tab_item = main.child_window(
                title=subtab_name, control_type="TabItem"
            ).wrapper_object()
            tab_item.select()
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Could not select sub-tab {subtab_name}: {e}")
            subtab_data[subtab_name] = {"error": str(e)}
            continue

        take_screenshot(
            main, ss_dir / f"settings_subtab_{subtab_name.lower().replace(' ', '_')}.png",
            logger,
        )

        elements = scan_descendants(
            main, tab="Settings", subtab=subtab_name,
            logger=logger, timeout_s=600,
        )
        sub_merged = merge_elements({}, elements)
        all_elements.update(sub_merged)

        subtab_data[subtab_name] = {
            "element_count": len(sub_merged),
            "control_types": _count_control_types(elements),
        }

    # Update report
    if "Settings" not in report.tabs:
        report.tabs["Settings"] = {}
    report.tabs["Settings"]["subtabs"] = subtab_data
    report.tabs["Settings"]["subtab_names"] = subtab_names
    report.elements.update(all_elements)

    conn.ensure_connected()
    switch_tab(conn.main_window, "Room", logger, conn=conn)

    return {"elements": all_elements, "subtabs": subtab_data}


def phase_room_subtabs(conn: MozaikConnection, report: OvernightReport,
                       output_dir: Path,
                       logger: logging.Logger) -> Dict[str, Any]:
    """Phase 4: Heights, Depths, Thickness, Clearances sub-groups."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    dismiss_dialogs(main, logger)

    if not switch_tab(main, "Room", logger, conn=conn):
        return {"error": "Could not switch to Room tab"}

    subtab_data: Dict[str, Any] = {}
    all_elements: Dict[str, Dict[str, Any]] = {}

    # Known sub-tab control
    known_subtabs = ["Heights", "Depths"]

    for subtab_name in known_subtabs:
        dismiss_dialogs(main, logger)
        logger.info(f"Scanning Room > {subtab_name}")

        try:
            # Try parent-scoped search first
            parent = main.child_window(
                auto_id="HeightsDepthsTabControl"
            ).wrapper_object()
            tab_item = parent.child_window(
                title=subtab_name, control_type="TabItem"
            ).wrapper_object()
            tab_item.select()
            time.sleep(0.5)
        except Exception:
            try:
                tab_item = main.child_window(
                    title=subtab_name, control_type="TabItem"
                ).wrapper_object()
                tab_item.select()
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not select Room > {subtab_name}: {e}")
                subtab_data[subtab_name] = {"error": str(e)}
                continue

        take_screenshot(
            main, ss_dir / f"room_subtab_{subtab_name.lower()}.png", logger,
        )

        elements = scan_descendants(
            main, tab="Room", subtab=subtab_name, logger=logger, timeout_s=300,
        )
        sub_merged = merge_elements({}, elements)
        all_elements.update(sub_merged)

        subtab_data[subtab_name] = {
            "element_count": len(sub_merged),
            "control_types": _count_control_types(elements),
        }

    # Also discover any additional group boxes (Thickness, Clearances)
    logger.info("Looking for additional Room group boxes...")
    try:
        for desc in main.descendants():
            try:
                info = desc.element_info
                ct = getattr(info, "control_type", "")
                name = getattr(info, "name", "") or ""
                if ct == "Group" and name:
                    logger.info(f"Found group box: {name}")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Error discovering groups: {e}")

    if "Room" not in report.tabs:
        report.tabs["Room"] = {}
    report.tabs["Room"]["subtabs"] = subtab_data
    report.elements.update(all_elements)

    return {"elements": all_elements, "subtabs": subtab_data}


def phase_combobox_enum(conn: MozaikConnection, report: OvernightReport,
                        output_dir: Path,
                        logger: logging.Logger) -> Dict[str, Any]:
    """Phase 5: Enumerate values for every discovered ComboBox."""
    conn.ensure_connected()
    main = conn.main_window
    combo_values: Dict[str, List[str]] = {}

    # Collect all known ComboBox automation IDs from report
    combo_ids: List[str] = []
    for key, elem_data in report.elements.items():
        if isinstance(elem_data, dict) and elem_data.get("control_type") == "ComboBox":
            aid = elem_data.get("automation_id", "")
            if aid:
                combo_ids.append(aid)
            else:
                combo_ids.append(key)

    logger.info(f"Found {len(combo_ids)} ComboBoxes to enumerate")

    # Try each tab to find and read combos
    for tab_name in LAYOUT_TABS:
        conn.ensure_connected()
        main = conn.main_window
        dismiss_dialogs(main, logger)
        switch_tab(main, tab_name, logger, conn=conn)
        time.sleep(0.5)

        # Find all ComboBox elements on this tab
        try:
            for desc in main.descendants():
                try:
                    info = desc.element_info
                    if getattr(info, "control_type", "") == "ComboBox":
                        aid = getattr(info, "automation_id", "") or ""
                        name = getattr(info, "name", "") or ""
                        key = aid or name or "(unknown)"

                        if key in combo_values:
                            continue

                        # Try .texts() to get options
                        try:
                            texts = desc.texts()
                            if texts:
                                combo_values[key] = [
                                    t for t in texts if t and t.strip()
                                ]
                                logger.info(
                                    f"ComboBox {key}: {len(combo_values[key])} values"
                                )
                        except Exception:
                            pass

                        # Fallback: try .items() or .item_texts()
                        if key not in combo_values:
                            try:
                                items = desc.item_texts()
                                if items:
                                    combo_values[key] = [
                                        t for t in items if t and t.strip()
                                    ]
                            except Exception:
                                pass

                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"ComboBox scan error on {tab_name}: {e}")

    conn.ensure_connected()
    switch_tab(conn.main_window, "Room", logger, conn=conn)

    report.combobox_values.update(combo_values)
    return {"combobox_values": combo_values}


def phase_textbox_values(conn: MozaikConnection, report: OvernightReport,
                         output_dir: Path,
                         logger: logging.Logger) -> Dict[str, Any]:
    """Phase 6: Read current values from every Edit/TextBox control."""
    conn.ensure_connected()
    main = conn.main_window
    textbox_values: Dict[str, str] = {}

    for tab_name in LAYOUT_TABS:
        conn.ensure_connected()
        main = conn.main_window
        dismiss_dialogs(main, logger)
        switch_tab(main, tab_name, logger, conn=conn)
        time.sleep(0.5)

        try:
            for desc in main.descendants():
                try:
                    info = desc.element_info
                    ct = getattr(info, "control_type", "")
                    if ct in ("Edit", "TextBox"):
                        aid = getattr(info, "automation_id", "") or ""
                        name = getattr(info, "name", "") or ""
                        key = aid or name or "(unknown)"

                        if key in textbox_values:
                            continue

                        try:
                            val = desc.window_text()
                            textbox_values[key] = val or ""
                            logger.info(f"TextBox {key}: '{val}'")
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"TextBox scan error on {tab_name}: {e}")

    conn.ensure_connected()
    switch_tab(conn.main_window, "Room", logger, conn=conn)

    # Update elements with current values
    for key, val in textbox_values.items():
        if key in report.elements:
            report.elements[key]["current_value"] = val

    return {"textbox_values": textbox_values}


def phase_menu_bar(conn: MozaikConnection, report: OvernightReport,
                   output_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Phase 7: Open each top-level menu, record all MenuItems."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    menus: Dict[str, Dict[str, Any]] = {}

    dismiss_dialogs(main, logger)

    # Find top-level menu items
    top_menu_names = ["File", "Edit", "View", "Libraries", "Tools", "Help"]

    for menu_name in top_menu_names:
        dismiss_dialogs(main, logger)
        logger.info(f"Exploring menu: {menu_name}")

        try:
            menu_item = main.child_window(
                title=menu_name, control_type="MenuItem"
            ).wrapper_object()

            # Open the menu
            try:
                menu_item.select()
            except Exception:
                menu_item.click_input()
            time.sleep(0.5)

            # Screenshot the open menu
            take_screenshot(
                main, ss_dir / f"menu_{menu_name.lower()}.png", logger,
            )

            # Collect sub-items
            sub_items: List[Dict[str, str]] = []
            try:
                for desc in menu_item.descendants():
                    try:
                        info = desc.element_info
                        if getattr(info, "control_type", "") == "MenuItem":
                            item_name = getattr(info, "name", "") or ""
                            item_aid = getattr(info, "automation_id", "") or ""
                            ak = None
                            try:
                                ak = getattr(info, "access_key", None)
                            except Exception:
                                pass
                            sub_items.append({
                                "name": item_name,
                                "automation_id": item_aid,
                                "access_key": ak or "",
                            })
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Error scanning {menu_name} sub-items: {e}")

            menus[menu_name] = {"items": sub_items}
            logger.info(f"Menu {menu_name}: {len(sub_items)} items")

            # Close the menu
            try:
                import pywinauto.keyboard
                pywinauto.keyboard.send_keys("{ESC}")
                time.sleep(0.3)
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Could not open menu {menu_name}: {e}")
            menus[menu_name] = {"error": str(e)}

    dismiss_dialogs(main, logger)
    report.menus.update(menus)
    return {"menus": menus}


def phase_products_dialog(conn: MozaikConnection, report: OvernightReport,
                          output_dir: Path,
                          logger: logging.Logger) -> Dict[str, Any]:
    """Phase 8: Libraries > Products dialog scan."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    dismiss_dialogs(main, logger)

    dialog_data: Dict[str, Any] = {"opened_via": "Libraries > Products"}

    try:
        # Open Libraries menu
        lib_menu = main.child_window(
            title="Libraries", control_type="MenuItem"
        ).wrapper_object()
        try:
            lib_menu.select()
        except Exception:
            lib_menu.click_input()
        time.sleep(0.5)

        # Click Products
        try:
            products_item = main.child_window(
                title="Products", control_type="MenuItem"
            ).wrapper_object()
            products_item.click_input()
            time.sleep(2.0)
        except Exception as e:
            logger.warning(f"Could not click Products menu item: {e}")
            dismiss_dialogs(main, logger)
            return {"error": str(e)}

        # Screenshot the dialog
        take_screenshot(main, ss_dir / "dialog_products.png", logger)

        # Scan for dialog window (might be top-level or embedded)
        dialog_elements: List[DiscoveredElement] = []

        # Try top-level windows first
        try:
            for win in conn.app.windows():
                win_title = win.window_text()
                if win_title and "product" in win_title.lower():
                    logger.info(f"Found Products dialog: {win_title}")
                    dialog_elements = scan_descendants(
                        win, tab="Dialog", subtab="Products",
                        logger=logger, timeout_s=300,
                    )
                    take_screenshot(
                        win, ss_dir / "dialog_products_window.png", logger,
                    )
                    break
        except Exception:
            pass

        # Fallback: scan main window descendants
        if not dialog_elements:
            logger.info("Scanning main window for Products dialog elements")
            dialog_elements = scan_descendants(
                main, tab="Dialog", subtab="Products",
                logger=logger, timeout_s=300,
            )

        merged = merge_elements({}, dialog_elements)
        dialog_data["elements"] = merged
        dialog_data["element_count"] = len(merged)

    except Exception as e:
        dialog_data["error"] = str(e)
        logger.error(f"Products dialog error: {e}")
    finally:
        # Close dialog
        dismiss_dialogs(main, logger)
        time.sleep(0.5)
        dismiss_dialogs(main, logger)

    report.dialogs["Products"] = dialog_data
    report.elements.update(dialog_data.get("elements", {}))
    return {"dialogs": {"Products": dialog_data}}


def phase_door_style_dialog(conn: MozaikConnection, report: OvernightReport,
                            output_dir: Path,
                            logger: logging.Logger) -> Dict[str, Any]:
    """Phase 9: Door Style Selection dialog scan."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    dismiss_dialogs(main, logger)

    dialog_data: Dict[str, Any] = {"opened_via": "Settings > BaseDoorButton"}

    try:
        # Switch to Settings tab
        if not switch_tab(main, "Settings", logger, conn=conn):
            return {"error": "Could not switch to Settings"}

        time.sleep(1.0)

        # Try to find and click the door style button
        # Common IDs: BaseDoorButton, DoorStyleButton, etc.
        door_btn_ids = [
            "BaseDoorButton", "DoorStyleButton",
            "BaseDoorStyleButton", "DoorLibButton",
        ]
        clicked = False
        for btn_id in door_btn_ids:
            try:
                btn = main.child_window(auto_id=btn_id).wrapper_object()
                btn.click_input()
                clicked = True
                logger.info(f"Clicked door style button: {btn_id}")
                time.sleep(2.0)
                break
            except Exception:
                pass

        if not clicked:
            # Try by name
            for btn_name in ["Door Style", "Base Door", "Select Door Style"]:
                try:
                    btn = main.child_window(
                        title=btn_name, control_type="Button"
                    ).wrapper_object()
                    btn.click_input()
                    clicked = True
                    logger.info(f"Clicked door style button: {btn_name}")
                    time.sleep(2.0)
                    break
                except Exception:
                    pass

        if not clicked:
            dialog_data["error"] = "Could not find door style button"
            return {"dialogs": {"DoorStyle": dialog_data}}

        take_screenshot(main, ss_dir / "dialog_door_style.png", logger)

        # Scan dialog
        dialog_elements = scan_descendants(
            main, tab="Dialog", subtab="DoorStyle",
            logger=logger, timeout_s=300,
        )
        merged = merge_elements({}, dialog_elements)
        dialog_data["elements"] = merged
        dialog_data["element_count"] = len(merged)

    except Exception as e:
        dialog_data["error"] = str(e)
    finally:
        dismiss_dialogs(main, logger)
        time.sleep(0.5)
        dismiss_dialogs(main, logger)

    report.dialogs["DoorStyle"] = dialog_data
    report.elements.update(dialog_data.get("elements", {}))
    conn.ensure_connected()
    switch_tab(conn.main_window, "Room", logger, conn=conn)
    return {"dialogs": {"DoorStyle": dialog_data}}


def phase_library_dialogs(conn: MozaikConnection, report: OvernightReport,
                          output_dir: Path,
                          logger: logging.Logger) -> Dict[str, Any]:
    """Phase 10: Open each Libraries sub-menu dialog."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    results: Dict[str, Any] = {}

    dismiss_dialogs(main, logger)

    # Get library menu items
    lib_items: List[str] = []
    try:
        lib_menu = main.child_window(
            title="Libraries", control_type="MenuItem"
        ).wrapper_object()
        try:
            lib_menu.select()
        except Exception:
            lib_menu.click_input()
        time.sleep(0.5)

        # Collect sub-menu items
        try:
            for desc in lib_menu.descendants():
                info = desc.element_info
                if getattr(info, "control_type", "") == "MenuItem":
                    name = getattr(info, "name", "") or ""
                    if name and name != "Libraries" and name != "Products":
                        lib_items.append(name)
        except Exception:
            pass

        # Close menu
        import pywinauto.keyboard
        pywinauto.keyboard.send_keys("{ESC}")
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"Could not enumerate Libraries menu: {e}")

    logger.info(f"Library menu items to scan: {lib_items}")

    # Open each library dialog
    for item_name in lib_items:
        dismiss_dialogs(main, logger)
        logger.info(f"Opening Libraries > {item_name}")

        try:
            # Re-open Libraries menu
            lib_menu = main.child_window(
                title="Libraries", control_type="MenuItem"
            ).wrapper_object()
            try:
                lib_menu.select()
            except Exception:
                lib_menu.click_input()
            time.sleep(0.5)

            # Click the specific item
            item = main.child_window(
                title=item_name, control_type="MenuItem"
            ).wrapper_object()
            item.click_input()
            time.sleep(2.0)

            # Screenshot
            safe_name = item_name.lower().replace(" ", "_").replace("/", "_")
            take_screenshot(
                main, ss_dir / f"dialog_libraries_{safe_name}.png", logger,
            )

            # Scan
            dialog_elements = scan_descendants(
                main, tab="Dialog", subtab=item_name,
                logger=logger, timeout_s=300,
            )
            merged = merge_elements({}, dialog_elements)
            results[item_name] = {
                "opened_via": f"Libraries > {item_name}",
                "elements": merged,
                "element_count": len(merged),
            }

            report.dialogs[f"Libraries_{item_name}"] = results[item_name]
            report.elements.update(merged)

        except Exception as e:
            logger.warning(f"Error with Libraries > {item_name}: {e}")
            results[item_name] = {"error": str(e)}
        finally:
            dismiss_dialogs(main, logger)
            time.sleep(0.5)

    return {"library_dialogs": results}


def phase_tools_dialogs(conn: MozaikConnection, report: OvernightReport,
                        output_dir: Path,
                        logger: logging.Logger) -> Dict[str, Any]:
    """Phase 11: Tools menu dialogs (Units, Preferences, Admin Center, etc.)."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    results: Dict[str, Any] = {}

    dismiss_dialogs(main, logger)

    # Get Tools menu items
    tool_items: List[str] = []
    try:
        tools_menu = main.child_window(
            title="Tools", control_type="MenuItem"
        ).wrapper_object()
        try:
            tools_menu.select()
        except Exception:
            tools_menu.click_input()
        time.sleep(0.5)

        try:
            for desc in tools_menu.descendants():
                info = desc.element_info
                if getattr(info, "control_type", "") == "MenuItem":
                    name = getattr(info, "name", "") or ""
                    if name and name != "Tools":
                        tool_items.append(name)
        except Exception:
            pass

        import pywinauto.keyboard
        pywinauto.keyboard.send_keys("{ESC}")
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"Could not enumerate Tools menu: {e}")

    logger.info(f"Tools menu items to scan: {tool_items}")

    for item_name in tool_items:
        dismiss_dialogs(main, logger)
        logger.info(f"Opening Tools > {item_name}")

        try:
            tools_menu = main.child_window(
                title="Tools", control_type="MenuItem"
            ).wrapper_object()
            try:
                tools_menu.select()
            except Exception:
                tools_menu.click_input()
            time.sleep(0.5)

            item = main.child_window(
                title=item_name, control_type="MenuItem"
            ).wrapper_object()
            item.click_input()
            time.sleep(2.0)

            safe_name = item_name.lower().replace(" ", "_").replace("/", "_")
            take_screenshot(
                main, ss_dir / f"dialog_tools_{safe_name}.png", logger,
            )

            dialog_elements = scan_descendants(
                main, tab="Dialog", subtab=item_name,
                logger=logger, timeout_s=300,
            )
            merged = merge_elements({}, dialog_elements)
            results[item_name] = {
                "opened_via": f"Tools > {item_name}",
                "elements": merged,
                "element_count": len(merged),
            }
            report.dialogs[f"Tools_{item_name}"] = results[item_name]
            report.elements.update(merged)

        except Exception as e:
            logger.warning(f"Error with Tools > {item_name}: {e}")
            results[item_name] = {"error": str(e)}
        finally:
            dismiss_dialogs(main, logger)
            time.sleep(0.5)

    return {"tools_dialogs": results}


def phase_order_deep_scan(conn: MozaikConnection, report: OvernightReport,
                          output_dir: Path,
                          logger: logging.Logger) -> Dict[str, Any]:
    """Phase 12: Deep scan of Order tab with parent hierarchy."""
    conn.ensure_connected()
    main = conn.main_window
    dismiss_dialogs(main, logger)

    if not switch_tab(main, "Order", logger, conn=conn):
        return {"error": "Could not switch to Order tab"}

    time.sleep(1.0)
    elements = scan_descendants(
        main, tab="Order", logger=logger, timeout_s=600,
    )

    merged = merge_elements({}, elements)
    report.elements.update(merged)

    # Track parent-child relationships
    hierarchy: Dict[str, List[str]] = {}
    for elem in elements:
        pid = elem.parent_id or "(root)"
        key = build_element_key(elem)
        hierarchy.setdefault(pid, []).append(key)

    conn.ensure_connected()
    switch_tab(conn.main_window, "Room", logger, conn=conn)

    return {
        "elements": merged,
        "hierarchy": hierarchy,
        "element_count": len(merged),
    }


def phase_context_menus(conn: MozaikConnection, report: OvernightReport,
                        output_dir: Path,
                        logger: logging.Logger) -> Dict[str, Any]:
    """Phase 13: Right-click context menus on canvas."""
    conn.ensure_connected()
    main = conn.main_window
    ss_dir = output_dir / "screenshots"
    dismiss_dialogs(main, logger)

    if not switch_tab(main, "Room", logger, conn=conn):
        return {"error": "Could not switch to Room tab"}

    context_results: Dict[str, Any] = {}

    # Right-click on SchematicCanvas
    try:
        canvas = main.child_window(auto_id="SchematicCanvas").wrapper_object()
        rect = canvas.rectangle()
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2

        canvas.right_click_input(coords=(cx - rect.left, cy - rect.top))
        time.sleep(1.0)

        take_screenshot(main, ss_dir / "context_menu_canvas.png", logger)

        # Scan for popup menu items
        menu_items: List[Dict[str, str]] = []
        try:
            for desc in main.descendants():
                info = desc.element_info
                ct = getattr(info, "control_type", "")
                if ct == "MenuItem":
                    name = getattr(info, "name", "") or ""
                    aid = getattr(info, "automation_id", "") or ""
                    # Filter to items not in main menu bar
                    if name and name not in ["File", "Edit", "View",
                                             "Libraries", "Tools", "Help"]:
                        menu_items.append({
                            "name": name,
                            "automation_id": aid,
                        })
        except Exception as e:
            logger.warning(f"Error scanning context menu: {e}")

        context_results["canvas"] = {"items": menu_items}
        logger.info(f"Context menu items: {len(menu_items)}")

        # Close context menu
        import pywinauto.keyboard
        pywinauto.keyboard.send_keys("{ESC}")
        time.sleep(0.3)

    except Exception as e:
        logger.warning(f"Context menu error: {e}")
        context_results["canvas"] = {"error": str(e)}

    report.context_menus.update(context_results)
    return {"context_menus": context_results}


def phase_keyboard_shortcuts(conn: MozaikConnection, report: OvernightReport,
                             output_dir: Path,
                             logger: logging.Logger) -> Dict[str, Any]:
    """Phase 14: Check access_key property on all elements."""
    conn.ensure_connected()
    main = conn.main_window
    dismiss_dialogs(main, logger)

    shortcuts: Dict[str, str] = {}

    try:
        for desc in main.descendants():
            try:
                info = desc.element_info
                ak = getattr(info, "access_key", None)
                if ak:
                    aid = getattr(info, "automation_id", "") or ""
                    name = getattr(info, "name", "") or ""
                    key = aid or name or "(unknown)"
                    shortcuts[key] = ak
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Keyboard shortcut scan error: {e}")

    logger.info(f"Found {len(shortcuts)} access keys")

    # Update elements with access_key info
    for key, ak in shortcuts.items():
        if key in report.elements:
            report.elements[key]["access_key"] = ak

    return {"shortcuts": shortcuts}


def phase_final_report(conn: MozaikConnection, report: OvernightReport,
                       output_dir: Path,
                       logger: logging.Logger) -> Dict[str, Any]:
    """Phase 15: Write final report, restore Room tab."""
    conn.ensure_connected()
    main = conn.main_window
    dismiss_dialogs(main, logger)

    # Restore Room tab
    switch_tab(main, "Room", logger, conn=conn)

    # Final metadata
    report.metadata["end_time"] = datetime.now().isoformat()
    start_str = report.metadata.get("start_time", "")
    if start_str:
        try:
            start_dt = datetime.fromisoformat(start_str)
            report.metadata["duration_s"] = (
                datetime.now() - start_dt
            ).total_seconds()
        except Exception:
            pass

    report.metadata["total_elements"] = len(report.elements)
    report.metadata["total_combobox_values"] = len(report.combobox_values)
    report.metadata["total_dialogs"] = len(report.dialogs)
    report.metadata["total_menus"] = len(report.menus)
    report.metadata["total_errors"] = len(report.errors)

    # Write final report
    report_path = output_dir / "overnight_discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    logger.info(f"Final report: {report_path}")

    return {"report_path": str(report_path)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_control_types(elements: List[DiscoveredElement]) -> Dict[str, int]:
    """Count elements by control type."""
    counts: Dict[str, int] = {}
    for elem in elements:
        ct = elem.control_type or "(unknown)"
        counts[ct] = counts.get(ct, 0) + 1
    return counts


def setup_logging(output_dir: Path) -> logging.Logger:
    """Configure logging to file and console."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("overnight_discovery")
    logger.setLevel(logging.DEBUG)

    # File handler
    log_path = output_dir / "overnight_discovery.log"
    fh = logging.FileHandler(str(log_path), mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(ch)

    return logger


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

PHASE_FUNCTIONS = {
    0: phase_connect,
    1: phase_baseline,
    2: phase_per_tab,
    3: phase_settings_subtabs,
    4: phase_room_subtabs,
    5: phase_combobox_enum,
    6: phase_textbox_values,
    7: phase_menu_bar,
    8: phase_products_dialog,
    9: phase_door_style_dialog,
    10: phase_library_dialogs,
    11: phase_tools_dialogs,
    12: phase_order_deep_scan,
    13: phase_context_menus,
    14: phase_keyboard_shortcuts,
    15: phase_final_report,
}


def run_overnight_discovery(
    window_title_re: str = ".*Mozaik Enterprise.*",
    output_dir: str = "data/overnight",
) -> OvernightReport:
    """Run all 16 discovery phases with checkpoint saves."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "screenshots").mkdir(parents=True, exist_ok=True)
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)

    logger = setup_logging(out)
    logger.info("=" * 60)
    logger.info("OVERNIGHT MOZAIK UI DISCOVERY")
    logger.info("=" * 60)
    logger.info(f"Window title regex: {window_title_re}")
    logger.info(f"Output directory: {out}")
    logger.info(f"Start time: {datetime.now().isoformat()}")

    report = OvernightReport()
    report.metadata["start_time"] = datetime.now().isoformat()
    report.metadata["window_title_re"] = window_title_re
    report.metadata["output_dir"] = str(out)

    conn = MozaikConnection(window_title_re, logger)
    phases_completed = 0

    for phase_num in sorted(PHASE_FUNCTIONS.keys()):
        phase_name = PHASE_NAMES[phase_num]
        budget = PHASE_BUDGETS_SECONDS[phase_num]

        runner = PhaseRunner(phase_num, phase_name, budget, logger)
        phase_func = PHASE_FUNCTIONS[phase_num]

        # Phase 0 (connect) doesn't need existing connection
        if phase_num == 0:
            result = runner.run(phase_func, conn, report, out, logger)
        else:
            # Check connection is alive
            if conn.main_window is None:
                logger.error("No connection - attempting reconnect")
                if not conn.reconnect():
                    logger.error("Reconnect failed - skipping remaining phases")
                    report.errors.append({
                        "phase": phase_num,
                        "phase_name": phase_name,
                        "error": "Connection lost, reconnect failed",
                    })
                    break

            result = runner.run(phase_func, conn, report, out, logger)

        # Record timing
        report.timing[f"phase_{phase_name}"] = runner.elapsed

        # Record errors
        if runner.error:
            report.errors.append({
                "phase": phase_num,
                "phase_name": phase_name,
                "error": runner.error,
                "elapsed_s": runner.elapsed,
            })

        # Save checkpoint
        checkpoint_data = {
            "phase": phase_num,
            "phase_name": phase_name,
            "elapsed_s": runner.elapsed,
            "error": runner.error,
            "result": result,
        }
        try:
            ckpt_path = save_checkpoint(checkpoint_data, out, phase_name)
            logger.info(f"Checkpoint saved: {ckpt_path}")
        except Exception as e:
            logger.warning(f"Checkpoint save failed: {e}")

        phases_completed += 1

        # If connect phase failed, abort
        if phase_num == 0 and runner.error:
            logger.error("Connect phase failed - aborting")
            break

    report.metadata["phases_completed"] = phases_completed
    report.metadata["phases_total"] = len(PHASE_FUNCTIONS)

    # Write final report even if phases were skipped
    try:
        report.metadata["end_time"] = datetime.now().isoformat()
        report_path = out / "overnight_discovery_report.json"
        with open(report_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        logger.info(f"Final report saved: {report_path}")
    except Exception as e:
        logger.error(f"Could not save final report: {e}")

    logger.info("=" * 60)
    logger.info(f"DISCOVERY COMPLETE: {phases_completed}/{len(PHASE_FUNCTIONS)} phases")
    logger.info(f"Elements discovered: {len(report.elements)}")
    logger.info(f"Errors: {len(report.errors)}")
    logger.info("=" * 60)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Overnight Mozaik UI Discovery Script"
    )
    parser.add_argument(
        "--output", type=str, default="data/overnight",
        help="Output directory (default: data/overnight)",
    )
    parser.add_argument(
        "--window-title", type=str, default=".*Mozaik Enterprise.*",
        help="Regex for Mozaik window title",
    )
    args = parser.parse_args()

    try:
        import pywinauto  # noqa: F401
    except ImportError:
        print("ERROR: pywinauto not installed.")
        print("Install with: pip install pywinauto==0.6.9")
        sys.exit(1)

    report = run_overnight_discovery(
        window_title_re=args.window_title,
        output_dir=args.output,
    )

    errors = len(report.errors)
    elements = len(report.elements)
    print(f"\nDone. {elements} elements, {errors} errors.")
    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
