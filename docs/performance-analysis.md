# Mozaik pywinauto Performance Analysis

> Last Updated: 2026-01-27

## Problem Statement

pywinauto 0.6.9's `wrapper_object()` takes **~90 seconds per element** when searching from the root window. This makes even simple automation workflows (setting 5 form fields) take 7-8 minutes. The root cause is a full UIA (UI Automation) tree traversal on every `child_window().wrapper_object()` call.

### Measured Baseline (14coresbeast)

| Operation | Time | Notes |
|-----------|------|-------|
| Connect to Mozaik | 8.7s | One-time |
| Screenshot | 6.0s | `capture_as_image()` |
| Set room name | 94.1s | `wrapper_object()` from root |
| Set wall height | 91.3s | `wrapper_object()` from root |
| Set base depth | ~90s (est.) | `wrapper_object()` from root |
| **Total (5 fields)** | **~7-8 min** | Unacceptable for production |

### Root Cause

- pywinauto 0.6.9's `child_window().wrapper_object()` performs a full UIA tree traversal from the specified parent element
- When called from `main_window` (application root), it walks Mozaik's entire UI tree (~70+ elements, deep nesting)
- No built-in caching in pywinauto 0.6.9
- Additionally: searching for deeply nested elements (e.g., Heights sub-tab TabItem) from root can **hang the system entirely**

## Optimization Approaches

### Approach 1: Parent-Scoped Search

**Expected improvement: ~90s → ~5-10s per element**

Find the parent container first (e.g., Room tab pane), then search within its smaller subtree.

```python
# Instead of:
main_window.child_window(auto_id="RoomNameTextBox").wrapper_object()  # ~90s

# Do:
room_pane = main_window.child_window(auto_id="QRTabPage").wrapper_object()  # ~30s one-time
room_pane.child_window(auto_id="RoomNameTextBox").wrapper_object()  # ~5s
```

**Pros**: Simple change, stays within pywinauto API
**Cons**: Still uses pywinauto's tree walker, parent lookup is still slow first time

### Approach 2: Direct UIA Traversal (Depth-Limited)

**Expected improvement: ~90s → ~1-5s per element**

Use pywinauto's internal `UIAElementInfo` directly with a depth-limited manual walk.

```python
from pywinauto.uia_element_info import UIAElementInfo

root_info = UIAElementInfo(hwnd)

def find_by_auto_id(info, target_id, max_depth=6):
    for child in info.children():
        if child.automation_id == target_id:
            return child
    if max_depth > 0:
        for child in info.children():
            result = find_by_auto_id(child, target_id, max_depth - 1)
            if result:
                return result
    return None
```

**Pros**: Much faster, avoids pywinauto's overhead, configurable depth
**Cons**: Returns `UIAElementInfo` not wrapped element, need to wrap for `set_text()` etc.

### Approach 3: Batch Find (Single Pass)

**Expected improvement: ~90s × N → ~90s total (amortized)**

Walk the tree once, collect all needed elements in a single pass.

```python
target_set = {"RoomNameTextBox", "D_BaseCabsTextBox", "D_WallCabsTextBox", ...}
found = {}

for desc in main_window.descendants():
    aid = desc.element_info.automation_id
    if aid in target_set:
        found[aid] = desc
        target_set.discard(aid)
        if not target_set:
            break
```

**Pros**: Only one tree traversal regardless of element count, natural for "find all Room elements"
**Cons**: First call still takes ~90s, walks entire tree even if element is near the top

### Approach 4: Win32 COM UIAutomation

**Expected improvement: ~90s → <1s per element**

Bypass pywinauto entirely. Use Windows UIAutomation COM API directly via `comtypes`.

```python
import comtypes
from comtypes.client import CreateObject

uia = CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}",
                   interface=comtypes.gen.UIAutomationClient.IUIAutomation)
root = uia.ElementFromHandle(hwnd)
condition = uia.CreatePropertyCondition(30011, "RoomNameTextBox")  # AutomationId
el = root.FindFirst(4, condition)  # TreeScope_Descendants
```

**Pros**: Fastest possible, uses native Windows optimization, supports conditions/caching
**Cons**: Requires `comtypes`, more complex API, need to handle `IUIAutomationElement` directly

### Approach 5: Upgrade pywinauto

**Expected improvement: Unknown**

Upgrade from 0.6.9 (2019) to latest pywinauto (0.7.x). Newer versions may have:
- Faster UIA backend
- Better caching
- Fixed `TabControlWrapper.child_window()`

**Pros**: Upstream fixes, maintained code
**Cons**: API breaking changes (`title=` → `name=`), may break existing code, untested with Mozaik

## Recommended Strategy

1. **Immediate**: Use **Approach 3 (Batch Find)** — collect all Room tab elements in one pass on connect. Cache handles for reuse.
2. **Short-term**: Add **Approach 2 (Direct UIA)** as fallback for elements not found in batch.
3. **Medium-term**: Evaluate **Approach 4 (COM UIAutomation)** for sub-second lookups if batch isn't fast enough.
4. **Long-term**: Consider **Approach 5 (Upgrade)** when we can allocate time for regression testing.

## Benchmark Results (2026-01-27)

### Connect Strategy

| Method | Time |
|--------|------|
| `connect(title_re=...)` | 8.7s (sometimes hangs) |
| **`connect(process=PID)`** | **0.3s** |

### Element Lookup Comparison

| Approach | Time | Elements Found |
|----------|------|---------------|
| Root-scoped `wrapper_object()` (per element) | **41-94s each** | 1 per call |
| **Batch `descendants()` (single pass)** | **38.8s total** | **13/16** |
| Cached handle `set_text()` | **0.00-0.04s** | N/A |

### Batch Find Detail

Scanning 189 descendants found 13 elements simultaneously in 38.8s:
- `MainRoomComboBox`, `RmMainMenuStrip`, `LayoutTabControl`
- `RoomNameTextBox`, `SchematicCanvas`, `H_BaseCabsTextBox`, `H_WallsTextBox`
- `RoomTabButtonDrawWalls`, `RoomTabChkQuickRoom`
- `SaveButton`, `MainButtonDelete`, `SnapButton`, `ZoomExtentsButton`

**Not found** (require sub-tab selection first):
- `D_BaseCabsTextBox`, `D_WallCabsTextBox`, `D_TallCabsTextBox`

### Cached Handle Speed

Once element handles are cached from batch scan, all operations are instant:
- `set_text("Kitchen Demo")`: 0.00s
- `set_text("96")`: 0.04s
- **Total for setting 2 fields with cached handles: 0.04s**

### Recommended Architecture

```
Startup (one-time, ~39s):
  1. Connect by PID (0.3s)
  2. Batch descendants() scan → cache all visible elements (38.8s)

Per-operation (instant):
  1. Look up cached handle
  2. Call set_text() / click_input() / select() → 0.00-0.04s

Tab switch (when needed):
  1. Select new tab via TabItem.select()
  2. Re-scan descendants() for new tab's elements (~39s)
  3. Cache new handles
```

**Effective speed for room creation (5 fields): ~39s startup + <0.1s operations = ~39s total**
vs current: ~90s × 5 = ~450s (7.5 minutes)

### Live Demo Results (demo_create_room.py, 2026-01-27)

```
Room: Kitchen | Height: 96.0" | Depths: B=24.0" W=12.0" T=24.0"

  [1] Connect to Mozaik:       18.16s  (PID-based)
  [2] Batch scan descendants:  101.55s  (11/14 cached)
  [3] Screenshot (before):      6.55s
  [4] Set room name = Kitchen:  0.01s  ✓ (confirmed in screenshot)
  [5] Set wall height = 96.0:   0.06s  ✓ (confirmed in screenshot)
  [6] Set base depth:           FAILED (Depths sub-tab not active)
  [7] Set wall depth:           FAILED (Depths sub-tab not active)
  [8] Set tall depth:           FAILED (Depths sub-tab not active)
  [9] Screenshot (after):       0.17s

  Total: 126.5s
  Field operations: 0.07s for 2 fields = 0.014s/field
```

**Key finding**: Depths are on a separate sub-tab from Heights. Must click "Depths" tab first.
**Units note**: Mozaik was set to mm (not inches). Need to handle unit conversion.

## Environment

| Property | Value |
|----------|-------|
| Machine | 14coresbeast (192.168.1.103:2222) |
| OS | Windows (WSL2 SSH) |
| Python | 3.9.9 |
| pywinauto | 0.6.9 |
| Mozaik | Enterprise edition |
| UIA Elements | 70+ discovered automation IDs |
