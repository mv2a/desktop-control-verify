# Epic: Comprehensive Overnight Mozaik UI Discovery

**Status:** In Progress
**Created:** 2026-01-27
**Priority:** P0

## Context

- **14coresbeast**: Windows machine with WSL2 (SSH port 2222, IP: 192.168.1.2)
- **Mozaik Enterprise** running on Windows side
- **pywinauto 0.6.9** (uses `title=` not `name=` for `child_window()`)
- **Python 3.9.9** on Windows, invoked from WSL via `python.exe`
- **Current coverage**: 52 elements in ElementMapping, 16 in Element Knowledge Base
- **Goal**: Run ~9 hours overnight to discover ALL UI elements, dialog contents, combo values, menu structures

## Discovery Targets

| Priority | Target | Current State |
|----------|--------|---------------|
| P0 | Products Library dialog | 0% - completely unmapped |
| P0 | Settings sub-tabs (7 of 8) | 0% - only Door/Drawer Fronts explored |
| P0 | Door Style Selection dialog | 0% - dialog structure unknown |
| P1 | Order tab elements | 5% - only SplitContainer known |
| P1 | ComboBox option values | 0% - no dropdown values enumerated |
| P1 | TextBox current values | 0% - no values read from live UI |
| P1 | Room tab advanced (Thickness, Clearances) | 0% |
| P2 | All Libraries menu dialogs (13 items) | 0% |
| P2 | Tools menu dialogs | 0% |
| P2 | Right-click context menus | 0% |
| P2 | Keyboard shortcuts / access keys | 0% |

## Deliverables

### D1: `scripts/overnight_discovery.py`

Single self-contained Python file (no imports from `mozaik_automation` package). Runs standalone on 14coresbeast.

**16 phases with time budgets (total ~9 hours):**

| Phase | Name | Budget | What It Does |
|-------|------|--------|-------------|
| 0 | Connect & Metadata | 2 min | Connect via title_re, collect PID, window rect, version |
| 1 | Baseline Scan | 10 min | Full `descendants()` from Room tab, catalog all elements |
| 2 | Per-Tab Scans | 45 min | Switch to each of Job/Settings/Room/Order, `descendants()` per tab, screenshot each |
| 3 | Settings Sub-tabs | 90 min | Discover and scan all 8 Settings sub-tabs |
| 4 | Room Sub-tabs | 30 min | Heights, Depths + discover Thickness/Clearances groups |
| 5 | ComboBox Enumeration | 60 min | `.texts()` on every discovered ComboBox |
| 6 | TextBox Value Reading | 30 min | `.window_text()` on every Edit control |
| 7 | Menu Bar Exploration | 60 min | Open each top-level menu, record all MenuItems |
| 8 | Products Library Dialog | 60 min | Libraries > Products, scan dialog tree, screenshot, close |
| 9 | Door Style Dialog | 30 min | Click BaseDoorButton, scan dialog, close via Cancel |
| 10 | Other Library Dialogs | 60 min | Open each Libraries sub-menu, scan each dialog |
| 11 | Tools Menu Dialogs | 45 min | Units, Preferences, Admin Center, etc. |
| 12 | Order Tab Deep Scan | 30 min | Full descendants() with parent hierarchy tracking |
| 13 | Context Menus | 30 min | Right-click on canvas, record popup menu items |
| 14 | Keyboard Shortcuts | 15 min | Check `access_key` property on all elements |
| 15 | Final Report & Cleanup | 5 min | Merge checkpoints, write final JSON, restore Room tab |

**Key design patterns:**

1. **Phase runner with timeout**: Each phase runs in a daemon thread with hard timeout. If exceeded, moves to next phase.
2. **Checkpoint saves**: After every phase, write `checkpoint_after_{phase}.json` so partial results survive crashes.
3. **Auto-reconnect**: If COM error, retry connection 3x with 10s sleep.
4. **Safety**: READ-ONLY only. No `set_text()`, no Delete clicks. Only click menus to open/close dialogs for scanning. Cancel/Close/Escape to dismiss. Restore Room tab at end.
5. **Dialog cleanup**: At start and end of every phase, press Escape 5x and dismiss any open dialogs via Cancel/No/Close buttons.

**Element extraction** (for each discovered element):
```
automation_id, name, control_type, class_name, rectangle,
enabled, visible, tab, subtab, parent_id, depth_in_tree,
current_value (TextBox), combo_options (ComboBox), access_key
```

**Output files:**
```
data/overnight/
  overnight_discovery_report.json    # Final comprehensive report
  overnight_discovery.log            # Timestamped log
  checkpoints/                       # Per-phase JSON checkpoints
    checkpoint_after_connect_*.json
    checkpoint_after_baseline_*.json
    ...
  screenshots/
    baseline_room.png
    tab_job.png, tab_settings.png, tab_room.png, tab_order.png
    settings_subtab_*.png (8 screenshots)
    room_subtab_*.png
    dialog_products.png
    dialog_door_style.png
    dialog_libraries_*.png
    menu_*.png
    context_menu_canvas.png
```

**Report JSON structure:**
```json
{
  "metadata": { "start_time", "end_time", "duration_s", "window_title", "pid", "phases_completed" },
  "elements": { "AutomationId": { "automation_id", "name", "control_type", "class_name", "rectangle", "tab", "subtab", "enabled", "visible", "current_value", "combo_options", "parent_id", "depth" } },
  "tabs": { "Room": { "subtabs": [...], "element_count", "screenshot" } },
  "dialogs": { "Products": { "opened_via", "elements", "screenshot" } },
  "menus": { "File": { "items": [...] }, "Libraries": { "items": [...] } },
  "combobox_values": { "DoorLibSelComboBox": ["Shaker", ...] },
  "context_menus": { "canvas": { "items": [...] } },
  "errors": [...],
  "timing": { "phase_connect": 0.3, "phase_baseline": 39.0, ... }
}
```

### D2: `tests/test_overnight_discovery.py`

Unit tests for the discovery script's pure logic (no pywinauto needed):
- Report building and merging
- Checkpoint save/load
- Element data extraction formatting
- Phase timeout logic
- Tab-specific element deduplication
- Dialog close strategy ordering

### D3: Update CHANGELOG.md

Add entry for overnight discovery script under new version.

## Execution Plan

1. Create `scripts/overnight_discovery.py` with all 16 phases
2. Create `tests/test_overnight_discovery.py` with unit tests
3. Run test suite locally (must stay at 389+ passing)
4. SSH to 14coresbeast, copy script, launch overnight:
   ```bash
   ssh -p 2222 user@14coresbeast \
     "nohup python.exe /tmp/mozaik-automation/scripts/overnight_discovery.py \
       --output /tmp/mozaik-automation/data/overnight \
       > /tmp/mozaik-automation/data/overnight/overnight_discovery.log 2>&1 &"
   ```
5. Verify it started (check log tail)
6. Update CHANGELOG.md
7. Commit

## Verification

1. Local test suite passes (389+ tests)
2. Script starts successfully on 14coresbeast via SSH
3. First checkpoint file appears within 2 minutes
4. Log shows phases progressing
5. (Next morning) Review final report for discovered elements, dialog structures, combo values
