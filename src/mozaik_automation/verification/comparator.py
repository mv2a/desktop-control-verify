"""Programmatic build verification (D9.9).

Enforces PASS/FAIL in CODE — not LLM judgment.

Pipeline:
1. An ImageAnalyzer describes each image → structured JSON
2. Python code compares the JSONs deterministically
3. ANY mismatch = FAIL, enforced by code, not overridable

Current analyzer: Claude Code (the watcher LLM reads images, provides JSON).
Future analyzer: Claude API (swap in when API key available).

The watcher calls compare_extraction_to_analysis() with structured analysis
dicts and reports the code's PASS/FAIL decision — cannot override it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class CheckResult:
    name: str
    category: str
    expected: Any
    actual: Any
    passed: bool
    detail: str = ""


@dataclass
class VerificationResult:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    failures: list[CheckResult] = field(default_factory=list)
    summary: str = ""

    @property
    def total_checks(self) -> int:
        return len(self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)


def _parse_door_count(note: str) -> int | None:
    """Extract expected door count from cabinet note."""
    note_lower = note.lower().replace("-", " ")
    if "pair door" in note_lower or "pair-door" in note_lower:
        return 2
    m = re.search(r"(\d+)\s*door", note_lower)
    if m:
        return int(m.group(1))
    if "single door" in note_lower:
        return 1
    return None


def _parse_drawer_count(note: str) -> int | None:
    """Extract expected drawer count from cabinet note."""
    note_lower = note.lower().replace("-", " ")
    m = re.search(r"(\d+)\s*drawer", note_lower)
    if m:
        return int(m.group(1))
    return None


def _has_sink_in_note(note: str) -> bool:
    return "sink" in note.lower()


def _parse_sink_bowls_from_note(note: str) -> int | None:
    """Extract expected sink bowl count from appliance note."""
    note_lower = note.lower()
    if "double" in note_lower or "2 bowl" in note_lower or "two bowl" in note_lower:
        return 2
    if "single" in note_lower or "1 bowl" in note_lower:
        return 1
    return None


def compare_extraction_to_analysis(
    extraction: dict,
    screenshot_analysis: dict,
    upload_analysis: dict,
) -> VerificationResult:
    """Deterministic comparison — pure Python, no LLM judgment.

    Args:
        extraction: The extraction JSON with parsed counts and cabinet details.
        screenshot_analysis: Structured JSON from Claude analyzing the 3D screenshot.
        upload_analysis: Structured JSON from Claude analyzing the original upload.

    Returns:
        VerificationResult with every check and deterministic PASS/FAIL.
    """
    checks: list[CheckResult] = []

    parsed = extraction.get("parsed", {})
    cabinets = extraction.get("cabinets", [])
    appliances = extraction.get("appliances", [])
    room = extraction.get("room", {})

    ss_base = screenshot_analysis.get("base_cabinets", [])
    ss_wall = screenshot_analysis.get("wall_cabinets", [])
    ss_tall = screenshot_analysis.get("tall_cabinets", [])
    ss_appliances = screenshot_analysis.get("appliances", [])
    ss_shape = screenshot_analysis.get("layout_shape", "")

    up_base = upload_analysis.get("base_cabinets", [])

    # ── Part A: Count checks ──────────────────────────────────────────

    expected_base = parsed.get("base", 0)
    actual_base = len(ss_base)
    checks.append(CheckResult(
        name="base_cabinet_count",
        category="count",
        expected=expected_base,
        actual=actual_base,
        passed=expected_base == actual_base,
        detail=f"Expected {expected_base} base cabinets, 3D shows {actual_base}",
    ))

    expected_wall = parsed.get("wall", 0)
    actual_wall = len(ss_wall)
    checks.append(CheckResult(
        name="wall_cabinet_count",
        category="count",
        expected=expected_wall,
        actual=actual_wall,
        passed=expected_wall == actual_wall,
        detail=f"Expected {expected_wall} wall cabinets, 3D shows {actual_wall}",
    ))

    expected_tall = parsed.get("tall", 0)
    actual_tall = len(ss_tall)
    checks.append(CheckResult(
        name="tall_cabinet_count",
        category="count",
        expected=expected_tall,
        actual=actual_tall,
        passed=expected_tall == actual_tall,
        detail=f"Expected {expected_tall} tall cabinets, 3D shows {actual_tall}",
    ))

    # ── Part B: Appliance checks ──────────────────────────────────────

    extraction_appliance_types = {a.get("type", "").lower() for a in appliances}
    screenshot_appliance_types = {a.get("type", "").lower() for a in ss_appliances}

    for app_type in extraction_appliance_types:
        present = app_type in screenshot_appliance_types
        checks.append(CheckResult(
            name=f"appliance_{app_type}",
            category="appliance",
            expected=True,
            actual=present,
            passed=present,
            detail=f"{app_type}: expected in 3D, {'found' if present else 'NOT found'}",
        ))

    # Phantom appliances
    phantom = screenshot_appliance_types - extraction_appliance_types
    checks.append(CheckResult(
        name="no_phantom_appliances",
        category="appliance",
        expected="none",
        actual=", ".join(sorted(phantom)) if phantom else "none",
        passed=len(phantom) == 0,
        detail=f"Phantom appliances in 3D: {sorted(phantom)}" if phantom else "No phantom appliances",
    ))

    # Sink bowl match (upload vs screenshot)
    if "sink" in extraction_appliance_types:
        # Get bowl count from upload analysis
        upload_sink = next((a for a in upload_analysis.get("appliances", [])
                           if a.get("type", "").lower() == "sink"), None)
        screenshot_sink = next((a for a in ss_appliances
                               if a.get("type", "").lower() == "sink"), None)

        if upload_sink and screenshot_sink:
            # Try extraction note first, then upload analysis
            expected_bowls = None
            for app in appliances:
                if app.get("type", "").lower() == "sink":
                    expected_bowls = _parse_sink_bowls_from_note(app.get("note", ""))
                    break
            if expected_bowls is None:
                expected_bowls = upload_sink.get("sink_bowls")
            actual_bowls = screenshot_sink.get("sink_bowls")

            if expected_bowls is not None and actual_bowls is not None:
                checks.append(CheckResult(
                    name="sink_bowl_match",
                    category="appliance",
                    expected=expected_bowls,
                    actual=actual_bowls,
                    passed=expected_bowls == actual_bowls,
                    detail=f"Sink bowls: drawing={expected_bowls}, 3D={actual_bowls}",
                ))

    # ── Part B2: Cabinet configuration checks ─────────────────────────

    # Sort extraction cabinets: base first, then wall, then tall (by sequence)
    base_cabs = [c for c in cabinets if c.get("type") == "base"]
    wall_cabs = [c for c in cabinets if c.get("type") == "wall"]
    tall_cabs_ext = [c for c in cabinets if c.get("type") == "tall"]

    for cab_list, ss_list, type_name in [
        (base_cabs, ss_base, "base"),
        (wall_cabs, ss_wall, "wall"),
        (tall_cabs_ext, ss_tall, "tall"),
    ]:
        # Find global index for naming
        for i, cab in enumerate(cab_list):
            global_idx = cabinets.index(cab)
            note = cab.get("note", "")

            if i >= len(ss_list):
                # Already caught by count check
                continue

            ss_cab = ss_list[i]
            failures = []

            # Door count check
            expected_doors = _parse_door_count(note)
            actual_doors = ss_cab.get("doors")
            if expected_doors is not None and actual_doors is not None:
                if expected_doors != actual_doors:
                    failures.append(f"doors: expected {expected_doors}, got {actual_doors}")

            # Drawer count check
            expected_drawers = _parse_drawer_count(note)
            actual_drawers = ss_cab.get("drawers")
            if expected_drawers is not None and actual_drawers is not None:
                if expected_drawers != actual_drawers:
                    failures.append(f"drawers: expected {expected_drawers}, got {actual_drawers}")

            # Sink presence check
            expected_sink = _has_sink_in_note(note)
            actual_sink = ss_cab.get("has_sink", False)
            if expected_sink != actual_sink:
                failures.append(f"sink: expected {expected_sink}, got {actual_sink}")

            checks.append(CheckResult(
                name=f"cabinet_{global_idx}_config",
                category="cabinet_config",
                expected=note,
                actual=f"doors={actual_doors}, drawers={ss_cab.get('drawers')}, sink={actual_sink}",
                passed=len(failures) == 0,
                detail="; ".join(failures) if failures else f"Cabinet #{global_idx} config matches",
            ))

    # ── Part C: Layout shape ──────────────────────────────────────────

    expected_shape = room.get("shape", "").lower()
    actual_shape = ss_shape.lower() if ss_shape else ""
    checks.append(CheckResult(
        name="layout_shape",
        category="layout",
        expected=expected_shape,
        actual=actual_shape,
        passed=expected_shape == actual_shape,
        detail=f"Layout: expected {expected_shape}, 3D shows {actual_shape}",
    ))

    # ── Part D: Cross-reference upload vs screenshot ──────────────────

    upload_base_count = len(up_base)
    checks.append(CheckResult(
        name="cross_ref_base_count",
        category="cross_reference",
        expected=upload_base_count,
        actual=actual_base,
        passed=upload_base_count == actual_base,
        detail=f"Upload shows {upload_base_count} base cabs, 3D shows {actual_base}",
    ))

    # ── Build result ──────────────────────────────────────────────────

    failures = [c for c in checks if not c.passed]
    passed = len(failures) == 0

    # Build summary
    lines = []
    lines.append(f"{'PASS' if passed else 'FAIL'} — {len(checks) - len(failures)}/{len(checks)} checks passed")
    if failures:
        lines.append("")
        lines.append("FAILURES:")
        for f in failures:
            lines.append(f"  [{f.name}] {f.detail}")

    return VerificationResult(
        passed=passed,
        checks=checks,
        failures=failures,
        summary="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# ImageAnalyzer protocol — swap implementations without changing comparison
# ---------------------------------------------------------------------------

@runtime_checkable
class ImageAnalyzer(Protocol):
    """Interface for image analysis. Current: Claude Code. Future: Claude API."""

    def analyze(self, image_path: str) -> dict:
        """Analyze an image and return structured JSON.

        Must return a dict matching the ANALYSIS_SCHEMA format.
        """
        ...


ANALYSIS_SCHEMA = {
    "base_cabinets": [
        {"position": "str", "doors": "int", "drawers": "int",
         "has_sink": "bool", "sink_bowls": "int|null"}
    ],
    "wall_cabinets": [{"position": "str", "doors": "int"}],
    "tall_cabinets": [{"position": "str", "doors": "int"}],
    "appliances": [{"type": "str", "sink_bowls": "int|null"}],
    "layout_shape": "single-wall|L-shape|U-shape|galley",
}

SCREENSHOT_ANALYSIS_PROMPT = """Analyze this 3D kitchen screenshot from Mozaik Enterprise software.
Return a JSON object with EXACTLY this structure — count and describe every visible element:

{
  "base_cabinets": [
    {"position": "leftmost/center/rightmost", "doors": <int>, "drawers": <int>, "has_sink": <bool>, "sink_bowls": <int or null>}
  ],
  "wall_cabinets": [
    {"position": "left/center/right", "doors": <int>}
  ],
  "tall_cabinets": [
    {"position": "left/center/right", "doors": <int>}
  ],
  "appliances": [
    {"type": "sink/range/refrigerator/hood", "sink_bowls": <int or null>}
  ],
  "layout_shape": "single-wall/L-shape/U-shape/galley"
}

RULES:
- Count EVERY visible cabinet, even partially hidden ones
- For doors: count the number of door panels you can see on each cabinet
- For drawers: count horizontal drawer fronts
- has_sink: true ONLY if you see a sink/basin on that cabinet's countertop
- sink_bowls: count distinct basins (1 for single, 2 for double)
- Order cabinets left-to-right as seen in the image
- Return ONLY valid JSON, no markdown"""

UPLOAD_ANALYSIS_PROMPT = """Analyze this architectural drawing/floor plan of a kitchen.
Return a JSON object with EXACTLY this structure — describe every visible element:

{
  "base_cabinets": [
    {"position": "leftmost/center/rightmost", "doors": <int>, "drawers": <int>, "has_sink": <bool>, "sink_bowls": <int or null>}
  ],
  "wall_cabinets": [
    {"position": "left/center/right", "doors": <int>}
  ],
  "tall_cabinets": [
    {"position": "left/center/right", "doors": <int>}
  ],
  "appliances": [
    {"type": "sink/range/refrigerator/hood", "sink_bowls": <int or null>}
  ],
  "layout_shape": "single-wall/L-shape/U-shape/galley"
}

RULES:
- Count EVERY drawn cabinet, including those shown with dimensions
- For doors: count door panels drawn on each cabinet
- For drawers: count horizontal drawer lines
- has_sink: true if a sink symbol is drawn on the cabinet
- sink_bowls: 1 for single round/oval, 2 for double
- Order cabinets left-to-right as drawn
- Return ONLY valid JSON, no markdown"""


def analyze_image_with_claude(image_path: str, prompt: str, api_key: str | None = None) -> dict:
    """Call Claude API to get structured visual analysis of an image.

    Future implementation — requires ANTHROPIC_API_KEY.
    Currently the watcher (Claude Code) provides analysis directly.
    """
    import base64
    from pathlib import Path

    import anthropic

    if api_key is None:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")

    client = anthropic.Anthropic(api_key=api_key)

    img_path = Path(image_path)
    img_bytes = img_path.read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    media_type = "image/png"
    if img_path.suffix.lower() in (".jpg", ".jpeg"):
        media_type = "image/jpeg"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return json.loads(text)


def verify_build(
    upload_path: str,
    screenshot_path: str,
    extraction: dict,
    analyzer: ImageAnalyzer | None = None,
    api_key: str | None = None,
) -> VerificationResult:
    """Full verification pipeline — code-enforced PASS/FAIL.

    If analyzer is provided, uses it for both images.
    Otherwise falls back to Claude API (requires api_key).

    Current usage (Claude Code watcher):
        The watcher reads images itself, builds the analysis dicts,
        and calls compare_extraction_to_analysis() directly.

    Future usage (Claude API):
        verify_build(upload, screenshot, extraction, api_key="...")
    """
    if analyzer is not None:
        screenshot_analysis = analyzer.analyze(screenshot_path)
        upload_analysis = analyzer.analyze(upload_path)
    else:
        screenshot_analysis = analyze_image_with_claude(
            screenshot_path, SCREENSHOT_ANALYSIS_PROMPT, api_key,
        )
        upload_analysis = analyze_image_with_claude(
            upload_path, UPLOAD_ANALYSIS_PROMPT, api_key,
        )
    return compare_extraction_to_analysis(extraction, screenshot_analysis, upload_analysis)
