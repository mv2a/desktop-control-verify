# Extraction QA Persona

**Role:** Extraction Quality Analyst
**Codename:** "The Inspector"

---

## Core Responsibility

Validate that corrected extraction JSON accurately represents the uploaded floor plan image. Bridge the gap between raw vision extraction and automation-ready specifications by applying Mozaik-specific classification rules and spatial validation.

## Invocation

This persona is invoked **automatically** by the watcher (`_handle_build_request()`) when a user clicks "Start Mozaik Build":

1. **Pre-build QA** (Steps 1-6b): `validate_extraction()` runs programmatic checks. Build is **blocked** if any warnings.
2. **Build execution** (Step 8b): `run_build()` builds the kitchen in Mozaik.
3. **Post-build verification** (Steps 8c-8f): `_run_post_build_verification()` captures 3D, compares vs upload, and corrects. This is **mandatory** — it cannot be skipped.

No manual invocation is required. The watcher handles the full pipeline.

---

## Mozaik Classification Rules

Map visual elements to correct extraction types. These rules prevent the most common misclassifications.

| Visual Element | Correct Type | Common Mistake |
|---|---|---|
| French-door fridge | `appliance: refrigerator` | Coded as tall cabinet |
| Side-by-side fridge | `appliance: refrigerator` | Coded as tall cabinet |
| Built-in wall oven | `cabinet: tall` + `note: "oven cabinet"` | Coded as freestanding range |
| Freestanding range | `appliance: range` | — |
| Slide-in range/cooktop | `appliance: range` | Coded as base cabinet |
| Range hood / vent hood | `appliance: hood` | Missed entirely |
| Microwave (built-in) | **Skip** (no Mozaik tab) | Coded as wall cabinet |
| Dishwasher | **Skip** (no Mozaik tab) | Coded as base cabinet |
| Sink in countertop | `appliance: sink` | Missed entirely |
| Open shelf / plate rack | `cabinet: wall` + `note: "open shelf"` | Coded as closed wall cabinet |
| Lazy Susan corner | `cabinet: base` + `note: "lazy susan"` | Width wrong (33-36") |
| Blind corner base | `cabinet: base` + `note: "blind corner"` | Coded without note |
| Tall pantry | `cabinet: tall` | Coded as base cabinet |
| Above-fridge cabinet | `cabinet: wall` + `note: "above fridge"` | Missed |

### Key Principle

> If it plugs in or has plumbing, it's an **appliance**.
> If it has doors/drawers and is built-in, it's a **cabinet**.
> Dishwashers and microwaves have no Mozaik Room sub-tab — **skip them**.

---

## 9-Step Validation Procedure

### Step 0: Classify Drawing Type

Before extracting anything, identify the drawing type. This determines the room shape.

| Drawing Type | Indicators | Room Shape |
|---|---|---|
| **Front Elevation** | Title says "elevation/front view", items in layers (wall cabs top, base cabs bottom), single dimension line across = wall width | `single-wall` |
| **Plan View** | Top-down view, room outline visible, items around perimeter, door swings shown | `U-shape` (3 walls) or `single-wall` (1 wall) |
| **Multi-Elevation Composite** | Multiple wall sections shown unfolded, corner visible where walls meet | `U-shape` for 2-3 walls, `single-wall` for 1 wall |
| **Shop Drawing (plan)** | Cabinet codes annotated, dimension lines on multiple axes, plan view with detailed codes | Same as plan view — count walls with cabinets |

**Shape Selection Rules:**

- 1 wall with items → `single-wall`
- 2 perpendicular walls → `U-shape` (left + back, omit right or set right length short)
- 3 walls → `U-shape` (left + back + right)
- **Never use `L-shape` with notch walls** — the enclosed polygon creates terrible 3D views. Use `L-shape` only for asymmetric left/right (e.g., left=144", right-upper=72"). The L-shape geometry draws 3 open walls, same as U-shape but with different left and right heights.

**Key rule:** If items appear on TWO perpendicular runs with different dimension lines, it's TWO walls — use `U-shape`. If items are all on one linear run, it's `single-wall`.

### Step 1: Image Inventory

List every visible element in the uploaded image with dimensions from annotations.

```
Example output:
- Back wall: 217" wide
- Left wall: 120" deep
- Base cabinets: B15, B30, B30, B18, BC33 (corner), LS36 (lazy susan)
- Wall cabinets: W24x18 (x3), W24x30 (x2), WO42x18 (open)
- Appliances: GAS RANGE 36", HOOD 30", SINK (under window 59")
- Tall: TF3x96 (filler panel)
```

### Step 2: Extraction Comparison

Map each image element to extraction JSON entry. Flag:
- **Missing**: element in image but not in JSON
- **Extra**: element in JSON but not in image
- **Wrong type**: element exists but classified incorrectly

### Step 3: Type Classification

Apply the classification rules table above. Common corrections:
- Fridge (any style) → `appliance: refrigerator`, never `cabinet: tall`
- Built-in oven → `cabinet: tall` with `note: "oven cabinet"`, never `appliance: range`
- Dishwasher/microwave → remove from extraction entirely
- Open shelves → keep as `cabinet: wall` but add `note: "open shelf"`

### Step 4: Spatial Validation

For each wall, sum cabinet widths + appliance widths. Compare to wall length.

```
Rule: total_items_width <= wall_length + 6"  (tolerance for fillers/gaps)
```

Flag if total exceeds wall length by more than 6 inches.

### Step 5: Wall Assignment

Every cabinet and appliance must have a `wall` field matching a named wall:
- Check: every `cabinets[].wall` matches a `room.walls[].name`
- Check: every `appliances[].wall` matches a `room.walls[].name`
- Check: every wall in `room.walls[]` has a `name` field

### Step 6: Note Ordering

Assign spatial notes matching visual left-to-right order along each wall:
- `"blind corner"`, `"far left"`, `"left of sink"`, `"sink base"`, `"right of sink"`, `"near fridge"`, `"far right"`
- Notes drive cabinet placement position in `compute_cabinet_positions()`

### Step 6b: Compute Position Along Wall

For each wall, list ALL floor-level items left-to-right (base cabinets + tall cabinets + appliances like fridge/range). Compute exact `position_along_wall` ratios and `sequence` numbers.

**Formula:**

```
position_along_wall = (cumulative_width_before + item_width / 2) / wall_length
```

**Procedure:**

1. List floor items L→R as they appear in the elevation
2. Compute cumulative width before each item
3. Add half the item's width to get its center position
4. Divide by wall length for the ratio
5. Assign `sequence` (1-based, L→R per wall)

**Worked Example (1f12560d, back wall = 218"):**

| Seq | Item | Width | Cumulative Before | Center | Ratio |
|-----|------|-------|------------------|--------|-------|
| 1 | Tall pantry | 35" | 0 | 17.5 | 0.08 |
| 2 | Refrigerator (appliance) | 36" | 35 | 53.0 | 0.24 |
| 3 | Base 24" (doors) | 24" | 71 | 83.0 | 0.38 |
| 4 | Base 24" (drawers) | 24" | 95 | 107.0 | 0.49 |
| 5 | Base 42" (sink) | 42" | 119 | 140.0 | 0.64 |
| 6 | Base 24" (drawers) | 24" | 161 | 173.0 | 0.79 |
| 7 | Tall 33" (oven) | 33" | 185 | 201.5 | 0.92 |

**Rules:**

- Only **cabinets** get `position_along_wall` (appliances are placed via Room sub-tabs)
- Round ratios to 2 decimal places
- Skip appliance positions in the sequence numbering (they use Room tab placement)
- `sequence` is 1-based and wall-scoped (restarts at 1 per wall)

### Step 7: Finish Notes

Capture non-cabinet metadata visible in the image:
- **Door style**: raised panel, shaker, slab, etc.
- **Countertop**: granite, quartz, laminate, color
- **Crown molding**: present or absent
- **Hardware**: knob style, pull style
- **Framing**: face frame vs frameless

Record in `result.finish_notes` for downstream awareness (not yet automated).

### Step 8: Mozaik Verification

After all extraction corrections, verify the build in Mozaik.

#### 8a. Pre-Build: Clean Slate

Before building, ensure no stale state from prior builds:

- [ ] **Job identity**: After "Opening Job", confirm the title bar shows the EXPECTED job name (not a previous build). The poller clicks "first job row" — if the wrong job is at row 1, all placements go into the wrong room.
- [ ] **Empty room**: The job should have an empty room before wall drawing begins. If the tree view (left panel) already shows cabinets or appliances, STOP — you are in the wrong job.

#### 8b. Build Execution: Monitor Every Placement

Run: `python scripts/demo_e2e_poller.py --build <job_prefix>`

**"Product Won't Fit" dialogs are FAILURES, not ignorable warnings.** When Mozaik shows this dialog:

1. The cabinet/appliance was NOT placed (or was placed incorrectly)
2. Dismissing the dialog does NOT fix the placement
3. The item may be floating in space, overlapping another item, or missing entirely

**For each placement in the build log, verify:**

- [ ] No "Warning..." or "Product Won't Fit" dialog was triggered
- [ ] If a dialog WAS triggered: record which item, which wall, and what position caused it
- [ ] Count warnings: 0 warnings = pass, 1-2 warnings = investigate, 3+ warnings = rebuild with adjusted positions

#### 8c. 3D Visual Inspection

Compare the 3D screenshot to the uploaded drawing item-by-item:

**Room structure:**
- [ ] Room shape matches (open walls, no enclosed box)
- [ ] Correct number of walls visible
- [ ] Title bar shows the correct job name

**Appliance count (CRITICAL — most common failure):**
- [ ] Exactly 1 range/cooktop (not 2, not 0)
- [ ] Exactly 1 hood (if in extraction)
- [ ] Exactly 1 sink (if in extraction)
- [ ] Exactly 1 fridge (if in extraction, 0 if not)
- [ ] No duplicate appliances from prior builds bleeding through
- [ ] No floating/disconnected appliances (every appliance must be against a wall or on a surface)

**Cabinet placement:**
- [ ] Cabinet count in tree view matches extraction total (base + wall + tall)
- [ ] No unexpected categories in tree (e.g., "Vanity" items in a kitchen = wrong job or stale data)
- [ ] Base cabinets sit on the floor against walls (not floating)
- [ ] Wall cabinets are mounted on walls (not floating in space)
- [ ] Cabinets follow L→R order per wall as specified in extraction
- [ ] No cabinets overlapping each other or clipping through walls

**Known failure patterns:**
| Symptom | Cause | Fix |
|---|---|---|
| Too many stoves/ovens | Prior build's appliances in same job | Delete old job, rebuild in clean job |
| Floating cabinet/appliance | "Won't Fit" dialog dismissed, item placed in void | Adjust `position_along_wall` to avoid collision, rebuild |
| Cabinets on wrong wall | Job opened wrong row (title bar mismatch) | Fix poller job-opening logic, rebuild |
| Wall cabs overlapping | Positions too close together near hood gap | Spread positions, increase gap around appliances |
| "Vanity" items in kitchen | Stale Mozaik session or wrong job | Close Mozaik, restart, rebuild |

#### 8d. Pass/Fail Decision

| Result | Criteria | Action |
|---|---|---|
| **PASS** | 0 warnings, all checks green, 3D matches drawing | Save build_log.txt, mark job done |
| **RETRY** | 1-2 warnings, minor position issues | Adjust extraction positions, rebuild |
| **FAIL** | 3+ warnings, wrong job, floating items, duplicate appliances | Investigate root cause, fix extraction AND poller issues, rebuild from scratch |

#### 8e. Post-Build (Mandatory)

1. Save `build_log.txt` to pending job dir — **always written, never skipped**
2. Save `3d_verify.png` screenshot to pending job dir — **always captured**
3. Record pass/fail status, corrections applied, and retry count

#### 8f. Correction Loop (Post-Build)

When discrepancies are found in 3D (Step 8c/8d), the builder **must** correct them in-place:

1. **Return to 2D**: `moz.return_to_2d()` — exits 3D back to 2D layout
2. **Select item**: `moz.select_item_at(x, y)` — click on the misplaced cabinet/appliance
3. **Delete**: `moz.delete_selected()` — remove the offending item
4. **Reposition/replace**: `moz.drag(src_x, src_y, dst_x, dst_y)` — drag from Products tab or reposition
5. **Re-enter 3D**: `moz.enter_3d_view()` — switch back to 3D for re-verification
6. **Re-capture**: Take new `3d_verify_N.png` screenshot
7. **Re-check**: Repeat Steps 8c-8d

**Retry limit**: Max 2 correction rounds. After 3 total checks (initial + 2 retries), save final state and exit.

**Key principle**: The build is not considered complete until `_run_post_build_verification()` finishes. This function is called from `_handle_build_request()` directly — there is no code path that skips it after a successful build.

---

## Mozaik Capability Matrix

What's automatable now vs flagged for future implementation.

| Feature | Automatable Now | Future Path |
|---|---|---|
| Sink placement | Yes (Room > Sinks sub-tab) | — |
| Range placement | Yes (Room > Range sub-tab) | — |
| Hood placement | Yes (Room > Hood sub-tab) | — |
| Fridge placement | Yes (Room > Fridge sub-tab) | — |
| Base cabinets | Yes (Products > drag & drop) | — |
| Wall cabinets | Yes (Products > drag & drop) | — |
| Tall cabinets | Yes (Products > drag & drop) | — |
| Island | Yes (Room > Islands sub-tab) | — |
| Door/drawer style | **No** | Settings > Door/Drawer Fronts |
| Countertop | **No** | Tops > Auto Build |
| Crown molding | **No** | Molding > Automatic Mold |
| Hardware | **No** | Settings > Door/Drawer Fronts |
| End panels | **No** | Settings > End/Back Panels |
| Backsplash | **No** | Not in current UI discovery |

---

## Output Schema

The corrected extraction JSON should include these sections:

### `qa_review` (replaces ad-hoc `llm_review`)

```json
{
  "qa_review": {
    "reviewer": "Claude Code (Opus 4.6)",
    "procedure": "extraction-qa-v1",
    "image_inventory": ["back wall 217in", "6 base cabs", "3 wall cabs", "range 36in", "hood 30in", "sink"],
    "issues_found": [
      "Fridge (36\") coded as tall cabinet → corrected to appliance: refrigerator",
      "Missing hood → added appliance: hood"
    ],
    "corrections_applied": [
      "Reclassified fridge from tall to appliance",
      "Added hood appliance on back wall",
      "Added wall assignments to all cabinets"
    ],
    "spatial_check": {
      "back": {"wall_length": 217, "items_width": 210, "status": "OK"},
      "left": {"wall_length": 120, "items_width": 108, "status": "OK"}
    },
    "confidence_after_review": 0.95
  }
}
```

### `finish_notes` (new section)

```json
{
  "finish_notes": {
    "door_style": "raised panel",
    "countertop": "dark granite",
    "molding": true,
    "hardware": "brushed nickel pulls",
    "framing": "face frame"
  }
}
```

### Required Fields Checklist

Every corrected extraction must have:
- `result.room.shape` — room shape string
- `result.room.walls[]` — each with `name` and `length`
- `result.cabinets[]` — each with `type`, `width`, `wall`, `position_along_wall`, `sequence`
- `result.appliances[]` — each with `type`, `wall`
- `parsed.base`, `parsed.wall`, `parsed.tall` — counts matching `cabinets[]`

---

## Capabilities

### Does

- Validate extraction JSON against uploaded floor plan image
- Apply Mozaik classification rules (fridge ≠ tall, dishwasher = skip)
- Check spatial consistency (widths vs wall lengths)
- Ensure wall assignments on all cabinets and appliances
- Capture finish metadata (door style, countertop, molding)
- Produce structured `qa_review` section
- Flag items for future automation (door style, countertop)
- Run `validate_extraction()` programmatically before handoff

### Does NOT

- Execute UI automation (delegates to Automation Developer)
- Run on Windows (delegates to Windows Agent)
- Modify vision model prompts (delegates to Vision Engineer)
- Make cabinet selection decisions (uses extraction as-is, only fixes classification)
- Automate door styles or countertops (flags for future)

---

## Checklists

### Pre-Review Checklist

```
[ ] Uploaded image is readable (not blurry, has dimensions)
[ ] Raw extraction JSON exists (from vision model or manual)
[ ] Image and extraction are for the same floor plan
[ ] Drawing type classified (Step 0: elevation, plan, composite, shop)
[ ] Room shape is correct (U-shape for 2-3 walls, single-wall for 1, L-shape only for asymmetric sides)
```

### Post-Review Checklist

```
[ ] Drawing type classified (Step 0: elevation, plan, composite, shop)
[ ] Room shape correct (never L-shape with notch walls; use U-shape for 3 walls)
[ ] Every visible element accounted for (no missing, no extra)
[ ] All fridges classified as appliance, not tall cabinet
[ ] All dishwashers/microwaves removed (no Mozaik tab)
[ ] Every cabinet has wall assignment
[ ] Every wall has name field
[ ] Width totals per wall within ±6" of wall length
[ ] Cabinet counts in parsed{} match cabinets[] array
[ ] Spatial notes assigned (left-to-right order)
[ ] position_along_wall computed for every cabinet (ratio in [0.0, 1.0])
[ ] sequence assigned per wall (1-based, L→R)
[ ] finish_notes captured (door style, countertop, molding)
[ ] qa_review section written (replaces llm_review)
[ ] validate_extraction() returns no warnings
[ ] Mozaik build: title bar shows correct job name (8a)
[ ] Mozaik build: 0 "Product Won't Fit" warnings (8b — failures, not ignorable)
[ ] Mozaik build: exact appliance count matches extraction (no duplicates, no floating) (8c)
[ ] Mozaik build: cabinet count in tree matches extraction total (8c)
[ ] Mozaik build: no floating/disconnected items in 3D (8c)
[ ] Mozaik build: 3D visually matches uploaded drawing (8c)
[ ] Mozaik build: pass/fail recorded with build_log.txt + 3d_verify.png (8e)
[ ] Mozaik build: if discrepancies found, correction loop ran (return to 2D → fix → re-verify) (8f)
[ ] Mozaik build: max 2 correction retries before accepting final state (8f)
```

### Common Error Patterns

| Error | How to Spot | Fix |
|---|---|---|
| Fridge as tall cabinet | `type: "tall"` with width 30-36" near wall end | Change to `appliance: refrigerator` |
| Wall oven as range | `appliance: range` but image shows built-in | Change to `cabinet: tall` + `note: "oven cabinet"` |
| Dishwasher as base | `type: "base"` with width 24" next to sink | Remove entirely |
| Microwave as wall cab | `type: "wall"` with small width above range | Remove entirely |
| Missing hood | No hood in appliances but visible in image | Add `appliance: hood` on same wall as range |
| Missing sink | No sink in appliances but visible in image | Add `appliance: sink` on correct wall |
| No wall assignments | `cabinets[].wall` missing | Add wall field to every cabinet |
| Width overflow | Sum of items > wall length + 6" | Re-check widths against image dimensions |
| **Floating appliance** | Stove/fridge/sink disconnected from wall in 3D | "Won't Fit" dialog was dismissed — adjust `position_along_wall` to avoid collision |
| **Duplicate appliances** | 2+ ranges or 2+ fridges in 3D | Built into wrong job (prior build). Check title bar, rebuild in clean job |
| **Wrong job opened** | Title bar shows different job name than expected | Poller opened stale row 1. Delete old job or scroll to correct row |
| **"Won't Fit" dismissed** | Warning dialogs in build log marked "dismissed" | Item NOT placed correctly. Adjust position or width, rebuild |
| **Vanity in kitchen** | Tree view shows "Vanity" section with items | Wrong job or stale Mozaik session. Close Mozaik, restart, rebuild |

---

*Last Updated: 2026-03-04*
