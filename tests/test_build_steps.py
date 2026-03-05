"""TDD tests for step-based build protocol (D9.10).

The build script must yield control at each step, printing [STEP] events
and waiting for the watcher to approve before proceeding.

Protocol:
  Build prints: [STEP] <step_name>|<screenshot_path>|<description>
  Watcher reads step, verifies screenshot, writes "CONTINUE\n" or "ABORT <reason>\n" to stdin
  Build reads stdin response and proceeds or stops

This replaces the monolithic blocking build with a supervised build.
"""

import pytest
from mozaik_automation.verification.build_steps import (
    BuildStep,
    BuildStepResult,
    parse_step_event,
    format_step_event,
    STEP_CREATE_JOB,
    STEP_DRAW_WALLS,
    STEP_APPLIANCES,
    STEP_BASE_CABS,
    STEP_WALL_CABS,
    STEP_TALL_CABS,
    STEP_SWITCH_3D,
    STEP_FINAL,
)


class TestStepEventParsing:
    def test_parse_valid_step(self):
        line = "[STEP] draw_walls|data/copilot/pending/abc/step_walls.png|Walls drawn (94\" back wall)"
        step = parse_step_event(line)
        assert step is not None
        assert step.name == "draw_walls"
        assert step.screenshot_path == "data/copilot/pending/abc/step_walls.png"
        assert step.description == "Walls drawn (94\" back wall)"

    def test_parse_base_cabinet_step(self):
        line = "[STEP] base_cabinets_placed|data/copilot/pending/abc/step_cab_1.png|Base cabinets placed: 3/3 OK"
        step = parse_step_event(line)
        assert step.name == "base_cabinets_placed"
        assert "3/3" in step.description

    def test_parse_non_step_line_returns_none(self):
        assert parse_step_event("[Build] Starting...") is None
        assert parse_step_event("  Typing: jobname") is None
        assert parse_step_event("") is None

    def test_parse_step_with_missing_fields(self):
        """Malformed step line returns None."""
        assert parse_step_event("[STEP] draw_walls") is None
        assert parse_step_event("[STEP] |path|desc") is None


class TestStepEventFormatting:
    def test_format_step(self):
        result = format_step_event("draw_walls", "/path/to/img.png", "Walls drawn")
        assert result == "[STEP] draw_walls|/path/to/img.png|Walls drawn"

    def test_format_roundtrip(self):
        original = BuildStep(name="place_cabinet", screenshot_path="/p.png", description="Base #1")
        line = format_step_event(original.name, original.screenshot_path, original.description)
        parsed = parse_step_event(line)
        assert parsed.name == original.name
        assert parsed.screenshot_path == original.screenshot_path
        assert parsed.description == original.description


class TestBuildStepConstants:
    def test_step_names_are_strings(self):
        assert STEP_CREATE_JOB == "create_job"
        assert STEP_DRAW_WALLS == "draw_walls"
        assert STEP_APPLIANCES == "appliances_placed"
        assert STEP_BASE_CABS == "base_cabinets_placed"
        assert STEP_WALL_CABS == "wall_cabinets_placed"
        assert STEP_TALL_CABS == "tall_cabinets_placed"
        assert STEP_SWITCH_3D == "switch_3d"
        assert STEP_FINAL == "final_3d"

    def test_eight_strategic_checkpoints(self):
        """Verify all 8 Phase 11 strategic checkpoints are defined."""
        checkpoints = [
            STEP_CREATE_JOB, STEP_DRAW_WALLS, STEP_APPLIANCES,
            STEP_BASE_CABS, STEP_WALL_CABS, STEP_TALL_CABS,
            STEP_SWITCH_3D, STEP_FINAL
        ]
        assert len(checkpoints) == 8
        assert all(isinstance(c, str) for c in checkpoints)
        assert len(set(checkpoints)) == 8  # All unique


class TestBuildStepResult:
    def test_continue_result(self):
        r = BuildStepResult(action="continue")
        assert r.should_continue is True
        assert r.should_abort is False

    def test_abort_result(self):
        r = BuildStepResult(action="abort", reason="Cabinet count mismatch")
        assert r.should_continue is False
        assert r.should_abort is True
        assert r.reason == "Cabinet count mismatch"

    def test_parse_continue_response(self):
        r = BuildStepResult.from_response("CONTINUE\n")
        assert r.should_continue is True

    def test_parse_abort_response(self):
        r = BuildStepResult.from_response("ABORT Wrong cabinet type\n")
        assert r.should_abort is True
        assert r.reason == "Wrong cabinet type"

    def test_parse_empty_response_defaults_to_continue(self):
        """Timeout/empty response = continue (don't block forever)."""
        r = BuildStepResult.from_response("")
        assert r.should_continue is True

    def test_parse_unknown_response_defaults_to_continue(self):
        r = BuildStepResult.from_response("whatever")
        assert r.should_continue is True
