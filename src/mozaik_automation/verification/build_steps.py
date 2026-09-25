"""Step-based build protocol (D9.10).

Converts the monolithic build into a supervised, step-by-step process
where the watcher (Claude Code) can verify each step before proceeding.

Protocol:
  Build script prints:  [STEP] <name>|<screenshot_path>|<description>
  Watcher responds:     CONTINUE  or  ABORT <reason>

The build script calls emit_step() after each major action.
The watcher reads stdout, verifies the screenshot, then responds.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

# Step name constants: the eight strategic checkpoints of the Phase 11 protocol.
STEP_CREATE_JOB = "create_job"
STEP_DRAW_WALLS = "draw_walls"
STEP_APPLIANCES = "appliances_placed"
STEP_BASE_CABS = "base_cabinets_placed"
STEP_WALL_CABS = "wall_cabinets_placed"
STEP_TALL_CABS = "tall_cabinets_placed"
STEP_SWITCH_3D = "switch_3d"
STEP_FINAL = "final_3d"

# Single per-cabinet step name from the original five-step protocol. Kept so that
# callers written against it keep working; it is not one of the eight checkpoints.
STEP_PLACE_CABINET = "place_cabinet"


@dataclass
class BuildStep:
    name: str
    screenshot_path: str
    description: str


@dataclass
class BuildStepResult:
    action: str  # "continue" or "abort"
    reason: str = ""

    @property
    def should_continue(self) -> bool:
        return self.action == "continue"

    @property
    def should_abort(self) -> bool:
        return self.action == "abort"

    @classmethod
    def from_response(cls, response: str) -> BuildStepResult:
        """Parse a watcher response line."""
        text = response.strip()
        if text.upper().startswith("ABORT"):
            reason = text[5:].strip()
            return cls(action="abort", reason=reason)
        # Default: continue (including empty/unknown responses to avoid blocking)
        return cls(action="continue")


def parse_step_event(line: str) -> BuildStep | None:
    """Parse a [STEP] event line from build output.

    Returns BuildStep if valid, None otherwise.
    """
    line = line.strip()
    if not line.startswith("[STEP] "):
        return None

    payload = line[7:]  # After "[STEP] "
    parts = payload.split("|", 2)
    if len(parts) != 3:
        return None

    name, screenshot_path, description = parts
    if not name or not screenshot_path:
        return None

    return BuildStep(name=name, screenshot_path=screenshot_path, description=description)


def format_step_event(name: str, screenshot_path: str, description: str) -> str:
    """Format a [STEP] event line for stdout."""
    return f"[STEP] {name}|{screenshot_path}|{description}"


def emit_step(name: str, screenshot_path: str, description: str,
              wait_for_response: bool = True) -> BuildStepResult:
    """Emit a step event and optionally wait for watcher response.

    Prints the step to stdout (flushed), then reads stdin for CONTINUE/ABORT.
    If wait_for_response is False, returns continue immediately (for non-critical steps).
    """
    line = format_step_event(name, screenshot_path, description)
    print(line, flush=True)

    if not wait_for_response:
        return BuildStepResult(action="continue")

    try:
        response = sys.stdin.readline()
    except (EOFError, OSError):
        response = ""

    return BuildStepResult.from_response(response)
