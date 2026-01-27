"""
Performance benchmark: compare element lookup strategies in Mozaik.

Tests 3 approaches:
  1. Root-scoped wrapper_object() (current, ~90s per element)
  2. Parent-scoped: find Room tab pane first, search within it
  3. Direct Win32 API: FindWindowEx + SendMessage

Usage:
    python perf_benchmark.py
"""

import sys
import time
import ctypes
import ctypes.wintypes


def benchmark_root_scoped(main_window, auto_id: str) -> tuple[float, bool]:
    """Current approach: search from root window."""
    t0 = time.time()
    try:
        el = main_window.child_window(auto_id=auto_id).wrapper_object()
        return (time.time() - t0, True)
    except Exception:
        return (time.time() - t0, False)


def benchmark_parent_scoped(main_window, parent_id: str, auto_id: str) -> tuple[float, bool]:
    """Scoped approach: find parent pane first, then child within it."""
    t0 = time.time()
    try:
        parent = main_window.child_window(auto_id=parent_id).wrapper_object()
        el = parent.child_window(auto_id=auto_id).wrapper_object()
        return (time.time() - t0, True)
    except Exception:
        return (time.time() - t0, False)


def benchmark_win32_api(hwnd: int, auto_id: str) -> tuple[float, bool]:
    """Direct Win32 + UIA: use UIAutomation COM to find by AutomationId."""
    t0 = time.time()
    try:
        import comtypes
        from comtypes.client import CreateObject
        uia = CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}",
                          interface=comtypes.gen.UIAutomationClient.IUIAutomation)
        root = uia.ElementFromHandle(hwnd)

        # Create condition for AutomationId
        prop_id = 30011  # UIA_AutomationIdPropertyId
        condition = uia.CreatePropertyCondition(prop_id, auto_id)

        # FindFirst with Descendants scope (4)
        el = root.FindFirst(4, condition)
        found = el is not None
        return (time.time() - t0, found)
    except Exception as e:
        print(f"      Win32/UIA error: {e}")
        return (time.time() - t0, False)


def benchmark_uia_direct(hwnd: int, auto_id: str) -> tuple[float, bool]:
    """Direct UIAutomation via ctypes — no comtypes dependency."""
    t0 = time.time()
    try:
        # Use pywinauto's own UIA backend more efficiently
        from pywinauto.uia_element_info import UIAElementInfo
        from pywinauto import findwindows

        # Get element info for the main window
        root_info = UIAElementInfo(hwnd)

        # Walk children looking for matching auto_id
        def find_recursive(info, target_id, max_depth=6):
            try:
                children = info.children()
            except Exception:
                return None
            for child in children:
                try:
                    if child.automation_id == target_id:
                        return child
                except Exception:
                    continue
            # Go deeper
            if max_depth > 0:
                for child in children:
                    result = find_recursive(child, target_id, max_depth - 1)
                    if result:
                        return result
            return None

        result = find_recursive(root_info, auto_id)
        return (time.time() - t0, result is not None)
    except Exception as e:
        print(f"      UIA direct error: {e}")
        return (time.time() - t0, False)


def benchmark_cached_batch(main_window, auto_ids: list) -> tuple[float, dict]:
    """Find all elements in one pass by iterating descendants once."""
    t0 = time.time()
    found = {}
    try:
        # Get all descendants and filter by auto_id
        target_set = set(auto_ids)
        # Use print_control_identifiers-like approach but just collect
        for desc in main_window.descendants():
            try:
                aid = desc.element_info.automation_id
                if aid in target_set:
                    found[aid] = desc
                    target_set.discard(aid)
                    if not target_set:
                        break  # Found all
            except Exception:
                continue
    except Exception as e:
        print(f"      Batch error: {e}")

    return (time.time() - t0, found)


def main():
    from pywinauto import Application

    print("=== Mozaik Performance Benchmark ===\n")

    # Connect
    print("[1] Connecting to Mozaik...", flush=True)
    t0 = time.time()
    app = Application(backend="uia").connect(title_re=".*Mozaik.*", timeout=10)
    main_window = app.window(title_re=".*Mozaik.*")
    hwnd = main_window.handle
    print(f"    Connected in {time.time()-t0:.1f}s (hwnd={hwnd})\n")

    # Test elements (all on Room tab, which should be active)
    test_elements = [
        "RoomNameTextBox",
        "D_BaseCabsTextBox",
        "D_WallCabsTextBox",
    ]

    # Possible parent containers to try
    parent_candidates = [
        "LayoutTabControl",
        "QRTabPage",            # Room tab page
        "RoomTabPanel",         # Possible panel name
    ]

    # --- Approach 1: Root-scoped (baseline) ---
    print("[2] Root-scoped wrapper_object() (1 element only - baseline)")
    el_id = test_elements[0]
    elapsed, found = benchmark_root_scoped(main_window, el_id)
    print(f"    {el_id}: {'FOUND' if found else 'NOT_FOUND'} in {elapsed:.1f}s")
    print()

    # --- Approach 2: Parent-scoped ---
    print("[3] Parent-scoped search (trying parent containers)...")
    for parent_id in parent_candidates:
        print(f"    Parent: {parent_id}")
        t0 = time.time()
        try:
            parent = main_window.child_window(auto_id=parent_id).wrapper_object()
            parent_time = time.time() - t0
            print(f"      Parent found in {parent_time:.1f}s")

            # Now search within parent
            for el_id in test_elements[:2]:
                t1 = time.time()
                try:
                    el = parent.child_window(auto_id=el_id).wrapper_object()
                    el_time = time.time() - t1
                    print(f"      {el_id}: FOUND in {el_time:.1f}s (total: {parent_time + el_time:.1f}s)")
                except Exception:
                    el_time = time.time() - t1
                    print(f"      {el_id}: NOT_FOUND in {el_time:.1f}s")
            break  # Only use first working parent
        except Exception:
            elapsed = time.time() - t0
            print(f"      NOT_FOUND ({elapsed:.1f}s)")
    print()

    # --- Approach 3: UIA direct traversal (limited depth) ---
    print("[4] Direct UIA traversal (depth-limited)...")
    for el_id in test_elements[:2]:
        elapsed, found = benchmark_uia_direct(hwnd, el_id)
        print(f"    {el_id}: {'FOUND' if found else 'NOT_FOUND'} in {elapsed:.1f}s")
    print()

    # --- Approach 4: Batch find all at once ---
    print("[5] Batch find (single descendants() pass for all 3 elements)...")
    elapsed, found_map = benchmark_cached_batch(main_window, test_elements)
    print(f"    Found {len(found_map)}/{len(test_elements)} in {elapsed:.1f}s")
    for eid in test_elements:
        status = "FOUND" if eid in found_map else "NOT_FOUND"
        print(f"      {eid}: {status}")
    print()

    # --- Summary ---
    print("=== Summary ===")
    print("  Approach 1 (root-scoped):  ~90s per element (current)")
    print("  Approach 2 (parent-scoped): see above")
    print("  Approach 3 (UIA direct):    see above")
    print("  Approach 4 (batch):         see above")
    print()


if __name__ == "__main__":
    main()
