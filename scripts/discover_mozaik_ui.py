"""
Mozaik UI Element Discovery Script.

Connects to a running Mozaik instance via pywinauto and enumerates all UI
elements recursively. Outputs a structured JSON report and takes a screenshot.

Compares discovered elements against our ElementMapping defaults and reports
matches/misses.

Usage:
    python discover_mozaik_ui.py [--max-depth 8] [--output-dir data]

Requires: pywinauto, pillow (install via setup_14coresbeast.ps1)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data structures for discovery results
# ---------------------------------------------------------------------------

@dataclass
class UIElement:
    """Represents a single discovered UI element."""

    name: str = ""
    automation_id: str = ""
    control_type: str = ""
    class_name: str = ""
    rectangle: Optional[dict[str, int]] = None
    depth: int = 0
    children_count: int = 0
    is_enabled: bool = True
    is_visible: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "automation_id": self.automation_id,
            "control_type": self.control_type,
            "class_name": self.class_name,
            "depth": self.depth,
            "children_count": self.children_count,
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
        }
        if self.rectangle:
            d["rectangle"] = self.rectangle
        return d


@dataclass
class MappingMatch:
    """Result of comparing an ElementMapping entry against discovered UI."""

    element_name: str
    expected_name: Optional[str] = None
    expected_automation_id: Optional[str] = None
    expected_control_type: Optional[str] = None
    expected_title: Optional[str] = None
    status: str = "NOT_FOUND"  # FOUND / NOT_FOUND / ERROR
    matched_element: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "element_name": self.element_name,
            "status": self.status,
        }
        if self.expected_name:
            d["expected_name"] = self.expected_name
        if self.expected_automation_id:
            d["expected_automation_id"] = self.expected_automation_id
        if self.expected_control_type:
            d["expected_control_type"] = self.expected_control_type
        if self.expected_title:
            d["expected_title"] = self.expected_title
        if self.matched_element:
            d["matched_element"] = self.matched_element
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class DiscoveryReport:
    """Full discovery report."""

    timestamp: str = ""
    mozaik_window_title: str = ""
    mozaik_process_id: int = 0
    window_rectangle: Optional[dict[str, int]] = None
    total_elements: int = 0
    max_depth_reached: int = 0
    elements: list[dict] = field(default_factory=list)
    mapping_results: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "mozaik_window_title": self.mozaik_window_title,
            "mozaik_process_id": self.mozaik_process_id,
            "window_rectangle": self.window_rectangle,
            "total_elements": self.total_elements,
            "max_depth_reached": self.max_depth_reached,
            "elements": self.elements,
            "mapping_results": self.mapping_results,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Default ElementMapping (mirrors mozaik_driver.py)
# ---------------------------------------------------------------------------

DEFAULT_ELEMENT_MAPPING: dict[str, dict[str, Optional[str]]] = {
    # Menu items (matched by accessible name)
    "file_menu": {"name": "File", "control_type": "MenuItem"},
    "file_new": {"name": "New", "control_type": "MenuItem"},
    "libraries_menu": {"name": "Libraries", "control_type": "MenuItem"},
    # Layout
    "menu_bar": {"automation_id": "RmMainMenuStrip"},
    "layout_tab_control": {"automation_id": "LayoutTabControl"},
    "room_combo": {"automation_id": "MainRoomComboBox"},
    # Room tab
    "room_name_input": {"automation_id": "RoomNameTextBox"},
    "design_canvas": {"automation_id": "SchematicCanvas"},
    "draw_walls_button": {"automation_id": "RoomTabButtonDrawWalls"},
    "quick_room_checkbox": {"automation_id": "RoomTabChkQuickRoom"},
    # Heights
    "height_walls": {"automation_id": "H_WallsTextBox"},
    "height_base_cabs": {"automation_id": "H_BaseCabsTextBox"},
    "height_wall_cabs": {"automation_id": "H_WallCabsTextBox"},
    # Depths
    "depth_base_cabs": {"automation_id": "D_BaseCabsTextBox"},
    "depth_wall_cabs": {"automation_id": "D_WallCabsTextBox"},
    "depth_tall_cabs": {"automation_id": "D_TallCabsTextBox"},
    # Toolbar
    "save_button": {"automation_id": "SaveButton"},
    "delete_button": {"automation_id": "MainButtonDelete"},
    "zoom_extents_button": {"automation_id": "ZoomExtentsButton"},
    "snap_button": {"automation_id": "SnapButton"},
    # Job tab
    "job_combo": {"automation_id": "JobComboBox"},
    "new_job_button": {"automation_id": "NewJobButton"},
    # Settings > Door/Drawer Fronts
    "door_library_combo": {"automation_id": "DoorLibSelComboBox"},
    "base_handle_combo": {"automation_id": "BasePullComboBox"},
}


# ---------------------------------------------------------------------------
# Discovery logic
# ---------------------------------------------------------------------------

def enumerate_elements(
    wrapper,
    max_depth: int = 8,
    current_depth: int = 0,
) -> list[UIElement]:
    """
    Recursively enumerate UI elements from a pywinauto wrapper.

    Args:
        wrapper: pywinauto WindowSpecification or wrapper element
        max_depth: Maximum recursion depth to prevent hanging
        current_depth: Current recursion depth

    Returns:
        Flat list of UIElement objects found
    """
    results: list[UIElement] = []

    if current_depth > max_depth:
        return results

    try:
        children = wrapper.children()
    except Exception:
        return results

    for child in children:
        elem = _extract_element_info(child, current_depth)
        if elem is not None:
            # Count direct children for reference
            try:
                sub_children = child.children()
                elem.children_count = len(sub_children)
            except Exception:
                elem.children_count = 0

            results.append(elem)

            # Recurse
            if current_depth < max_depth:
                sub_results = enumerate_elements(child, max_depth, current_depth + 1)
                results.extend(sub_results)

    return results


def _extract_element_info(wrapper, depth: int) -> Optional[UIElement]:
    """Extract UIElement info from a pywinauto wrapper, safely."""
    try:
        info = wrapper.element_info
        rect = None
        try:
            r = info.rectangle
            rect = {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom}
        except Exception:
            pass

        return UIElement(
            name=getattr(info, "name", "") or "",
            automation_id=getattr(info, "automation_id", "") or "",
            control_type=getattr(info, "control_type", "") or "",
            class_name=getattr(info, "class_name", "") or "",
            rectangle=rect,
            depth=depth,
            is_enabled=getattr(info, "enabled", True),
            is_visible=getattr(info, "visible", True),
        )
    except Exception:
        return None


def compare_mapping(
    elements: list[UIElement],
    mapping: dict[str, dict[str, Optional[str]]],
) -> list[MappingMatch]:
    """
    Compare discovered elements against expected ElementMapping entries.

    For each mapping entry, search through discovered elements for a match.
    Matching logic:
    - automation_id: exact match
    - name + control_type: both must match
    - title: matches against element name (window/dialog titles appear as name)
    """
    results: list[MappingMatch] = []

    for elem_name, criteria in mapping.items():
        match = MappingMatch(
            element_name=elem_name,
            expected_name=criteria.get("name"),
            expected_automation_id=criteria.get("automation_id"),
            expected_control_type=criteria.get("control_type"),
            expected_title=criteria.get("title"),
        )

        try:
            found = _find_matching_element(elements, criteria)
            if found is not None:
                match.status = "FOUND"
                match.matched_element = found.to_dict()
            else:
                match.status = "NOT_FOUND"
        except Exception as e:
            match.status = "ERROR"
            match.error = str(e)

        results.append(match)

    return results


def _find_matching_element(
    elements: list[UIElement],
    criteria: dict[str, Optional[str]],
) -> Optional[UIElement]:
    """Find first element matching the given criteria."""
    automation_id = criteria.get("automation_id")
    name = criteria.get("name")
    control_type = criteria.get("control_type")
    title = criteria.get("title")

    for elem in elements:
        # Match by automation_id (strongest)
        if automation_id and elem.automation_id == automation_id:
            # If control_type is also specified, it must match too
            if control_type and elem.control_type != control_type:
                continue
            return elem

        # Match by name + control_type
        if name and control_type:
            if elem.name == name and elem.control_type == control_type:
                return elem

        # Match by title (check against element name, which is how dialogs appear)
        if title and not automation_id and not name:
            if elem.name == title:
                return elem

    return None


def build_report(
    window_title: str,
    process_id: int,
    window_rect: Optional[dict],
    elements: list[UIElement],
    mapping_results: list[MappingMatch],
) -> DiscoveryReport:
    """Build the final discovery report."""
    max_depth = max((e.depth for e in elements), default=0)

    found_count = sum(1 for m in mapping_results if m.status == "FOUND")
    not_found_count = sum(1 for m in mapping_results if m.status == "NOT_FOUND")
    error_count = sum(1 for m in mapping_results if m.status == "ERROR")

    # Collect unique control types
    control_types: dict[str, int] = {}
    for e in elements:
        ct = e.control_type or "(unknown)"
        control_types[ct] = control_types.get(ct, 0) + 1

    return DiscoveryReport(
        timestamp=datetime.now().isoformat(),
        mozaik_window_title=window_title,
        mozaik_process_id=process_id,
        window_rectangle=window_rect,
        total_elements=len(elements),
        max_depth_reached=max_depth,
        elements=[e.to_dict() for e in elements],
        mapping_results=[m.to_dict() for m in mapping_results],
        summary={
            "total_elements": len(elements),
            "max_depth": max_depth,
            "control_type_counts": control_types,
            "mapping_found": found_count,
            "mapping_not_found": not_found_count,
            "mapping_errors": error_count,
            "mapping_total": len(mapping_results),
        },
    )


# ---------------------------------------------------------------------------
# Main entry point (runs on Windows with pywinauto)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Discover Mozaik UI elements")
    parser.add_argument(
        "--max-depth", type=int, default=8,
        help="Maximum depth for UI tree traversal (default: 8)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="data",
        help="Directory for output files (default: data)",
    )
    parser.add_argument(
        "--window-title", type=str, default=".*Mozaik Enterprise.*",
        help="Regex for Mozaik window title (default: .*Mozaik.*)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Mozaik UI Discovery ===")
    print(f"Max depth: {args.max_depth}")
    print(f"Output dir: {output_dir}")
    print()

    # Import pywinauto (Windows only)
    try:
        from pywinauto import Application
    except ImportError:
        print("ERROR: pywinauto not installed. Run setup_14coresbeast.ps1 first.")
        sys.exit(1)

    # Connect to Mozaik
    print("[1/5] Connecting to Mozaik...")
    try:
        app = Application(backend="uia").connect(title_re=args.window_title, timeout=10)
    except Exception as e:
        print(f"ERROR: Could not connect to Mozaik: {e}")
        sys.exit(1)

    main_window = app.window(title_re=args.window_title)
    window_title = main_window.window_text()
    print(f"  Connected: {window_title}")

    # Get process info
    process_id = 0
    try:
        process_id = main_window.process_id()
    except Exception:
        pass

    # Get window rectangle
    window_rect = None
    try:
        r = main_window.rectangle()
        window_rect = {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom}
    except Exception:
        pass

    # Take screenshot
    print("[2/5] Taking screenshot...")
    screenshot_path = output_dir / "mozaik_screenshot.png"
    try:
        img = main_window.capture_as_image()
        img.save(str(screenshot_path))
        print(f"  Saved: {screenshot_path}")
    except Exception as e:
        print(f"  WARNING: Screenshot failed: {e}")

    # Enumerate elements
    print(f"[3/5] Enumerating UI elements (max depth={args.max_depth})...")
    start_time = time.time()
    elements = enumerate_elements(main_window, max_depth=args.max_depth)
    elapsed = time.time() - start_time
    print(f"  Found {len(elements)} elements in {elapsed:.1f}s")

    # Compare against ElementMapping
    print("[4/5] Comparing against ElementMapping defaults...")
    mapping_results = compare_mapping(elements, DEFAULT_ELEMENT_MAPPING)

    found = sum(1 for m in mapping_results if m.status == "FOUND")
    not_found = sum(1 for m in mapping_results if m.status == "NOT_FOUND")
    errors = sum(1 for m in mapping_results if m.status == "ERROR")
    print(f"  FOUND: {found}  NOT_FOUND: {not_found}  ERROR: {errors}")

    for m in mapping_results:
        icon = {"FOUND": "+", "NOT_FOUND": "-", "ERROR": "!"}[m.status]
        print(f"  [{icon}] {m.element_name}: {m.status}")

    # Build and save report
    print("[5/5] Saving report...")
    report = build_report(window_title, process_id, window_rect, elements, mapping_results)
    report_path = output_dir / "mozaik_ui_elements.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"  Saved: {report_path}")

    print()
    print("=== Discovery Complete ===")
    print(f"Total elements: {report.total_elements}")
    print(f"Mapping match rate: {found}/{len(mapping_results)}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
