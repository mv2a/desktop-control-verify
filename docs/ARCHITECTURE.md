# Architecture

Two layers, extracted from a private system that turns a kitchen drawing into a finished
design inside a Windows design application. The layers are the parts of that system that
are not about cabinetry. This page describes each one, how they connect, and the boundary
with the parts that stayed private.

```
 drawing (image / PDF)
        │
        ▼
 ┌────────────────────────┐   structured JSON    ┌───────────────────────────┐
 │ vision/extractor.py    │ ───────────────────► │ verification/comparator   │
 │ DrawingExtractor       │   (extraction)       │ pre_build_cross_check()   │◄── independent reading of
 │ Anthropic/OpenAI/Ollama│                      │   PASS → build may start  │    the drawing (analyser)
 └────────────────────────┘                      └─────────────┬─────────────┘
                                                               │ PASS
                                                               ▼
                                   ┌──────────────────────────────────────────────┐
                                   │ build (private, cabinetry-specific)          │
                                   │   drives the application through the         │
                                   │   control layer; at each checkpoint prints   │
                                   │   [STEP] name|screenshot|description and     │
                                   │   waits: CONTINUE / ABORT (build_steps.py)   │
                                   └───────────────────────┬──────────────────────┘
                                                           │ screenshot of the result
                                                           ▼
                                   ┌──────────────────────────────────────────────┐
                                   │ compare_extraction_to_analysis()             │
                                   │   extraction vs reading of the result vs     │
                                   │   reading of the drawing → PASS / FAIL       │
                                   └──────────────────────────────────────────────┘

 control layer (Windows):
   discovery (once) ── UI Automation tree walk ──► element cache (id, type, rect, tab)
   driver (every action) ── window handle + cached rect ──► click / type / keys
```

## Control layer

**Problem.** The target application exposes no automation API. Its UI is reachable
through Windows UI Automation (UIA), but looking an element up through the UIA tree took
tens of seconds per element on the measured machine. A traversal from the root could
hang the session. See [performance-analysis.md](performance-analysis.md).

**Design.** Split discovery from action.

- *Discovery* walks the UIA tree once and records every element with an automation id:
  its name, control type, window-relative rectangle and the tab it lives on. The overnight
  harness (`scripts/overnight_discovery.py`) does this across tabs, sub-tabs, dialogs,
  menus, combo-box values and context menus. It runs read-only operations only, with a
  time budget and a checkpoint per phase, and it reconnects after COM errors. The
  faster variants (`fast_discovery.py`, `discover_mozaik_ui.py`) use COM directly or a
  single pass.
- *Action* never walks the tree. `fast_driver.py` finds the window through Win32
  (`EnumWindows` on a title substring), adds the window origin to a cached rectangle's
  centre, and sends mouse and keyboard input. Typing uses SendKeys.

**Consequences.** Cached actions are fast. Anything not cached is still slow. Positions
are relative to the window, so they depend on the window geometry and layout at discovery
time. A new application needs a new discovery plan. A new version of the same application
may need rediscovery. These are listed in the README's limitations.

## Extraction

`DrawingExtractor` loads an image, or the first page of a PDF, and builds a prompt that
fixes the output schema and the classification rules. It then calls the chosen backend
and parses the JSON reply, tolerating fenced code blocks. The schema the prompt asks for
is the pipeline's compact form: room shape and walls, typed cabinets with notes, a list
of appliances, and parsed counts. `models.py` holds the fuller `CabinetSpec`, and
`extract_to_spec()` validates against it. The two schemas currently disagree (see the
README's limitations).

## Verification

The central decision is that a model may *describe* an image, but only code may *judge*
it.

1. **Pre-build gate** (`pre_build_cross_check`). An independent reading of the source
   drawing is compared with the extraction: counts per cabinet category (with an optional
   tolerance) and the set of appliance types. A FAIL stops the build before anything is
   drawn.
2. **Step protocol** (`build_steps.py`). The build stops at eight named checkpoints:
   `create_job`, `draw_walls`, `appliances_placed`, `base_cabinets_placed`,
   `wall_cabinets_placed`, `tall_cabinets_placed`, `switch_3d` and `final_3d`. A supervisor
   answers on standard input. An empty or unknown answer counts as CONTINUE, so this is a
   supervision point, not an interlock.
3. **Post-build comparison** (`compare_extraction_to_analysis`). Readings of the built
   result and of the drawing are compared with the extraction. It checks counts per
   category; door, drawer and sink configuration per cabinet, parsed from the
   extraction's notes; appliance presence and phantoms; sink bowls; layout shape; and a
   cross-check of the base count between drawing and result. Every check is recorded, and
   one failure fails the whole result.

`ImageAnalyzer` is a protocol, so the reader of images can be swapped without changing
the comparison: a person, an agent in the loop, or an API call (`verify_build`).

## Boundary

| Stays private | Why |
|---|---|
| Build automation that places rooms, walls, appliances and cabinets | Cabinetry-specific product code |
| Element caches recorded against the application | The product's application-specific map |
| Trained models, adapters, training data and code | Proprietary; the evaluation data derive from a non-commercial dataset |
| Licensing client and server, web app, job pipeline, deployment | Product and operations |

Every package module imports without the private parts, on any operating system.
`tests/test_imports.py` checks that and fails if any module that was not extracted is
loaded. Two scripts, `moz_action.py` and `fast_discovery.py`, import Windows modules as
they load, so they run only on Windows.
