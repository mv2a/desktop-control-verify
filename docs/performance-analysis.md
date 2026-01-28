# Mozaik pywinauto Performance Analysis

> Last Updated: 2026-01-28

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

---

## Benchmark Results (2026-01-28)

### Overnight Discovery Results

Full UI discovery completed in **3h 8m**, cataloging **1,861 elements**:

| Tab | Elements | Sub-tabs |
|-----|----------|----------|
| Settings | 1,204 | 8 (Door/Drawer, Materials, Textures, etc.) |
| Room | 379 | 2 (Heights, Depths) |
| Order | 145 | - |
| Job | 133 | - |

Key automation IDs discovered: 60+ unique IDs including `SchematicCanvas`, `RoomNameTextBox`, `H_WallsTextBox`, `D_BaseCabsTextBox`, etc.

### Approach Comparison (2026-01-28)

| Approach | Connect | Element Lookup | Batch Scan | Tab Switch (fresh) | Tab Switch (cached) |
|----------|---------|---------------|------------|-------------------|---------------------|
| **pywinauto per-element** | 19s | 41-94s each | N/A | 30-60s | N/A |
| **pywinauto batch** | 19s | N/A | 171s (60 cached) | N/A | 2s |
| **COM UIAutomation** | 0.03s | 10-57s each | 82s (7/17) | 3s find | unstable |
| **Hybrid (win32 + UIA)** | **0.00s** | 58-67s each | N/A | 29-57s | **155-392ms** |

### Hybrid Approach Detailed Results ✓ TESTED

| Operation | First Call | Cached | Speedup |
|-----------|------------|--------|---------|
| Connect (win32gui) | **0.00s** | N/A | 19s → instant |
| Tab → Job | 57.3s | 155ms | **369x faster** |
| Tab → Settings | 29.3s | 323ms | **91x faster** |
| Tab → Room | 43.3s | 319ms | **136x faster** |
| Click element (UIA) | 58-67s | Not cached | Still slow |
| SendKeys (20 inputs) | 763ms avg | N/A | Very fast |
| Keyboard shortcuts | 275-1001ms | N/A | Fast |
| **Total dry-run** | **218.7s** | - | - |

### Key Findings

1. **UIA tree traversal is inherently slow** - Both pywinauto and direct COM UIAutomation take 10-60+ seconds per element lookup because they must walk the Windows UI Automation tree

2. **Batch scan + caching is essential** - One-time scan (~100-170s), then all operations use cached handles

3. **COM references go stale** - Direct COM approach has stability issues (COM errors after ~2-3 minutes); pywinauto handles this better with auto-reconnect

4. **Tab switches require rescan** - Each tab change invalidates cached elements for that tab's content

5. **Cached operations are fast** - Once cached, reads are <1s (337ms avg with pywinauto, instant with COM)

### Practical Workflow Timing

**Simple Room Creation (batch approach - OLD):**

| Step | Time |
|------|------|
| Connect + batch scan Room tab | ~3 min |
| Set room name, wall height (cached) | instant |
| Switch to Depths sub-tab + rescan | ~2 min |
| Set base/wall/tall depths | instant |
| Draw walls | ~30s |
| Switch to Order tab + rescan | ~2 min |
| Place cabinet | ~30s |
| **Total** | **~8-10 min** |

**Bottleneck:** Tab/subtab switches each require a fresh `descendants()` scan (~100-170s).

**Simple Room Creation (hybrid approach - NEW):**

| Step | Time (First Run) | Time (Cached) |
|------|------------------|---------------|
| Connect (win32gui) | 0.00s | 0.00s |
| Switch to Room tab | 43s | 0.3s |
| Set room name (SendKeys) | 0.8s | 0.8s |
| Set wall height (Tab + SendKeys) | 0.8s | 0.8s |
| Click Draw Walls button | 60s | ? (needs caching) |
| Draw walls (mouse) | ~30s | ~30s |
| Switch to Order tab | 57s | 0.2s |
| Place cabinet | ~30s | ~30s |
| **Total (first run)** | **~4 min** | - |
| **Total (cached)** | - | **~1 min** |

**Key insight:** With element handle caching (like tab caching), most UIA operations become sub-second.

---

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

### Approach 3: Batch Find (Single Pass) ✓ IMPLEMENTED

**Actual result: ~170s total for 60 elements**

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

**Pros**: Only one tree traversal regardless of element count
**Cons**: Still takes 100-170s per scan; must rescan after tab changes

### Approach 4: Win32 COM UIAutomation ✓ TESTED

**Actual result: Similar speed, less stable**

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

**Results:**
- COM init: 0.03s (very fast)
- Individual lookups: 10-57s (same as pywinauto - UIA tree is the bottleneck)
- Batch OR condition: 82s for 7/17 elements
- **Stability issues**: COM references go stale, causing errors after ~2-3 minutes

**Conclusion**: Not recommended - same speed, less stable than pywinauto.

### Approach 5: Upgrade pywinauto

**Status: Not tested**

Upgrade from 0.6.9 (2019) to latest pywinauto (0.7.x). May have:
- Faster UIA backend
- Better caching
- Fixed `TabControlWrapper.child_window()`

**Pros**: Upstream fixes, maintained code
**Cons**: API breaking changes (`title=` → `name=`), may break existing code

### Approach 6: SendKeys / Keyboard Navigation ⭐ NEW

**Expected improvement: Significant**

Bypass UIA entirely for input. Use keyboard shortcuts and Tab navigation.

```python
import win32gui
import win32con
from pywinauto.keyboard import send_keys

# Focus window
hwnd = win32gui.FindWindow(None, "Mozaik Enterprise (Job:u)")
win32gui.SetForegroundWindow(hwnd)

# Use keyboard navigation
send_keys("{TAB}")  # Move to next field
send_keys("Kitchen Demo")  # Type text
send_keys("{TAB}")  # Next field
send_keys("96")  # Type value
```

**Pros**: No UIA tree traversal needed, instant input
**Cons**: Fragile (depends on tab order), can't read values, no element verification

### Approach 7: Mozaik API / File Format ⭐ NEW

**Expected improvement: 10-100x faster**

Investigate if Mozaik has:
1. **Scripting API** - COM automation interface, VBA macros
2. **Command-line interface** - Batch processing
3. **File format** - Direct .mzk file generation/modification

**Investigation needed:**
- Check Mozaik documentation for API
- Analyze .mzk file format (likely XML or proprietary binary)
- Look for plugin/extension system

### Approach 8: Hybrid - UIA for Navigation, SendKeys for Input ✓ TESTED

**Actual result: Significant improvement for cached operations**

Use win32gui for:
- Window connection (instant vs 19s)
- Window focus

Use UIA only for:
- Finding and clicking buttons/tabs (cache the handles!)
- Verifying element state

Use SendKeys for:
- All text input (frequent)
- Keyboard shortcuts

```python
import win32gui
from pywinauto import Application
from pywinauto.keyboard import send_keys

# Instant connect via win32gui
def find_mozaik(hwnd, results):
    if win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd)
        if "Mozaik Enterprise" in title:
            results.append((hwnd, title))
    return True

results = []
win32gui.EnumWindows(find_mozaik, results)
hwnd = results[0][0]  # Connect: 0.00s!

# UIA for tabs (cache the handles)
app = Application(backend="uia").connect(handle=hwnd)
main = app.window(handle=hwnd)
tab = main.child_window(title="Room", control_type="TabItem").wrapper_object()
_tab_cache["Room"] = tab  # Cache for next time
tab.select()  # First: 43s, Cached: 319ms

# Fast: Use keyboard for all input
send_keys("^a")  # Select all
send_keys("Kitchen Demo")  # 763ms avg
send_keys("{TAB}")
send_keys("96")  # Wall height
```

**Key findings:**
- win32gui connect is **instant** (0.00s vs 19s with pure pywinauto)
- Cached tab switches are **100-400x faster** (155-392ms vs 29-57s)
- SendKeys typing is **very fast** (763ms avg for complex input)
- **Remaining bottleneck**: Element clicking still uses UIA (58-67s per click)

**Next optimization**: Cache element handles like tabs to eliminate click latency.

---

## Recommended Strategy (Updated 2026-01-28)

### Immediate (Current) ✓ VALIDATED
Use **Approach 8 (Hybrid)** - win32gui + cached UIA + SendKeys:
- win32gui for instant window connect
- UIA for tab/button clicks (cache handles after first lookup)
- SendKeys for all text input

**Projected workflow timing with full caching:**

| Step | Time (Hybrid + Cache) |
|------|----------------------|
| Connect | 0.00s |
| Tab switches (4x cached) | ~1.2s |
| Click elements (if cached) | ~0.5s each |
| SendKeys inputs (10x) | ~8s |
| **Total (estimated)** | **~15-30s per room** |

vs. current batch approach: **8-10 min per room**

### Short-term
1. ✓ ~~Test Approach 8 (Hybrid)~~ - **DONE, validated**
2. Implement element handle caching (like tab caching)
3. Pre-cache all tabs + common elements at startup

### Medium-term
1. Investigate **Approach 7 (Mozaik API/File Format)**
2. If API exists, switch entirely to API-based automation

### Long-term
1. Consider **Approach 5 (Upgrade pywinauto)** if 0.7.x has significant improvements
2. Evaluate alternative automation frameworks (FlaUI, etc.)

---

## Scripts

| Script | Purpose | Location |
|--------|---------|----------|
| `automation_hybrid.py` | **Recommended** - win32gui + UIA + SendKeys | `scripts/` |
| `automation_batch.py` | Batch scan + cached operations | `scripts/` |
| `automation_com.py` | Direct COM UIAutomation test | `scripts/` |
| `automation_dry_run.py` | Basic dry-run test | `scripts/` |
| `overnight_discovery.py` | Full UI element discovery | `scripts/` |

---

## Environment

| Property | Value |
|----------|-------|
| Machine | 14coresbeast (192.168.1.103:2222) |
| OS | Windows (WSL2 SSH) |
| Python | 3.9.9 |
| pywinauto | 0.6.9 |
| Mozaik | Enterprise edition |
| UIA Elements | 1,861 discovered (60 with automation IDs) |
