"""TDD tests for programmatic build verification (D9.9).

The verification is enforced IN CODE — not by LLM judgment.
The LLM analyzes images via API → Python code compares → deterministic PASS/FAIL.
"""

import pytest
from mozaik_automation.verification.comparator import (
    CheckResult,
    VerificationResult,
    compare_extraction_to_analysis,
)


# ---------------------------------------------------------------------------
# Helpers to build test data
# ---------------------------------------------------------------------------

def _extraction(
    base=3, wall=2, tall=0,
    cabinets=None, appliances=None, shape="single-wall",
):
    if cabinets is None:
        cabinets = [
            {"type": "base", "width": 36, "note": "2-door base cabinet"},
            {"type": "base", "width": 30, "note": "sink base cabinet"},
            {"type": "base", "width": 24, "note": "3-drawer base cabinet"},
            {"type": "wall", "width": 15, "note": "single-door wall cabinet"},
            {"type": "wall", "width": 45, "note": "pair-door wall cabinet"},
        ]
    if appliances is None:
        appliances = [{"type": "sink", "note": "single-bowl sink"}]
    return {
        "room": {"shape": shape},
        "cabinets": cabinets,
        "appliances": appliances,
        "parsed": {"base": base, "wall": wall, "tall": tall},
    }


def _analysis(
    base_cabs=None, wall_cabs=None, tall_cabs=None,
    appliances=None, layout_shape="single-wall",
):
    """Simulates the structured JSON a vision API call would return."""
    if base_cabs is None:
        base_cabs = [
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": False},
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
            {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
        ]
    if wall_cabs is None:
        wall_cabs = [
            {"position": "left", "doors": 1},
            {"position": "right", "doors": 2},
        ]
    if tall_cabs is None:
        tall_cabs = []
    if appliances is None:
        appliances = [{"type": "sink", "sink_bowls": 1}]
    return {
        "base_cabinets": base_cabs,
        "wall_cabinets": wall_cabs,
        "tall_cabinets": tall_cabs,
        "appliances": appliances,
        "layout_shape": layout_shape,
    }


# ---------------------------------------------------------------------------
# Part A: Count checks
# ---------------------------------------------------------------------------

class TestCountChecks:
    def test_matching_counts_passes(self):
        result = compare_extraction_to_analysis(
            _extraction(base=3, wall=2, tall=0),
            _analysis(),
            _analysis(),  # upload analysis (same for this test)
        )
        count_checks = [c for c in result.checks if c.category == "count"]
        assert all(c.passed for c in count_checks)

    def test_base_count_mismatch_fails(self):
        """3D shows 4 base cabs, extraction says 3."""
        screenshot = _analysis(base_cabs=[
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": False},
            {"position": "center-left", "doors": 1, "drawers": 0, "has_sink": False},
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
            {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
        ])
        result = compare_extraction_to_analysis(
            _extraction(base=3), screenshot, _analysis(),
        )
        base_check = next(c for c in result.checks if c.name == "base_cabinet_count")
        assert not base_check.passed
        assert base_check.expected == 3
        assert base_check.actual == 4

    def test_wall_count_mismatch_fails(self):
        screenshot = _analysis(wall_cabs=[
            {"position": "left", "doors": 1},
        ])
        result = compare_extraction_to_analysis(
            _extraction(wall=2), screenshot, _analysis(),
        )
        wall_check = next(c for c in result.checks if c.name == "wall_cabinet_count")
        assert not wall_check.passed

    def test_tall_count_mismatch_fails(self):
        screenshot = _analysis(tall_cabs=[
            {"position": "left", "doors": 2},
        ])
        result = compare_extraction_to_analysis(
            _extraction(tall=0), screenshot, _analysis(),
        )
        tall_check = next(c for c in result.checks if c.name == "tall_cabinet_count")
        assert not tall_check.passed


# ---------------------------------------------------------------------------
# Part B: Appliance checks
# ---------------------------------------------------------------------------

class TestApplianceChecks:
    def test_sink_present_passes(self):
        result = compare_extraction_to_analysis(
            _extraction(appliances=[{"type": "sink", "note": "single-bowl"}]),
            _analysis(appliances=[{"type": "sink", "sink_bowls": 1}]),
            _analysis(appliances=[{"type": "sink", "sink_bowls": 1}]),
        )
        sink_check = next(c for c in result.checks if c.name == "appliance_sink")
        assert sink_check.passed

    def test_missing_appliance_fails(self):
        """Extraction has sink, 3D shows no sink."""
        result = compare_extraction_to_analysis(
            _extraction(appliances=[{"type": "sink", "note": "single-bowl"}]),
            _analysis(appliances=[]),
            _analysis(appliances=[{"type": "sink", "sink_bowls": 1}]),
        )
        sink_check = next(c for c in result.checks if c.name == "appliance_sink")
        assert not sink_check.passed

    def test_phantom_appliance_fails(self):
        """3D shows range, extraction has no range."""
        result = compare_extraction_to_analysis(
            _extraction(appliances=[{"type": "sink", "note": "single-bowl"}]),
            _analysis(appliances=[
                {"type": "sink", "sink_bowls": 1},
                {"type": "range"},
            ]),
            _analysis(appliances=[{"type": "sink", "sink_bowls": 1}]),
        )
        phantom_check = next(c for c in result.checks if c.name == "no_phantom_appliances")
        assert not phantom_check.passed

    def test_sink_bowl_mismatch_fails(self):
        """Drawing shows single-bowl, 3D shows double-bowl."""
        result = compare_extraction_to_analysis(
            _extraction(appliances=[{"type": "sink", "note": "single-bowl"}]),
            _analysis(appliances=[{"type": "sink", "sink_bowls": 2}]),
            _analysis(appliances=[{"type": "sink", "sink_bowls": 1}]),
        )
        bowl_check = next(c for c in result.checks if c.name == "sink_bowl_match")
        assert not bowl_check.passed
        assert bowl_check.expected == 1
        assert bowl_check.actual == 2


# ---------------------------------------------------------------------------
# Part B2: Cabinet configuration checks
# ---------------------------------------------------------------------------

class TestCabinetConfigChecks:
    def test_door_count_match_passes(self):
        result = compare_extraction_to_analysis(
            _extraction(), _analysis(), _analysis(),
        )
        config_checks = [c for c in result.checks if c.category == "cabinet_config"]
        assert all(c.passed for c in config_checks)

    def test_door_count_mismatch_fails(self):
        """Extraction says 2-door, 3D shows 1 door."""
        screenshot = _analysis(base_cabs=[
            {"position": "left", "doors": 1, "drawers": 0, "has_sink": False},  # wrong!
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
            {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
        ])
        result = compare_extraction_to_analysis(
            _extraction(), screenshot, _analysis(),
        )
        cab0_check = next(c for c in result.checks if c.name == "cabinet_0_config")
        assert not cab0_check.passed

    def test_drawer_count_mismatch_fails(self):
        """Extraction says 3-drawer, 3D shows 2 drawers."""
        screenshot = _analysis(base_cabs=[
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": False},
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
            {"position": "right", "doors": 0, "drawers": 2, "has_sink": False},  # wrong!
        ])
        result = compare_extraction_to_analysis(
            _extraction(), screenshot, _analysis(),
        )
        cab2_check = next(c for c in result.checks if c.name == "cabinet_2_config")
        assert not cab2_check.passed

    def test_sink_on_wrong_cabinet_fails(self):
        """Extraction says sink on cabinet #2, 3D shows sink on cabinet #1."""
        screenshot = _analysis(base_cabs=[
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},  # wrong cab
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": False, "sink_bowls": 0},
            {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
        ])
        result = compare_extraction_to_analysis(
            _extraction(), screenshot, _analysis(),
        )
        cab1_check = next(c for c in result.checks if c.name == "cabinet_1_config")
        assert not cab1_check.passed


# ---------------------------------------------------------------------------
# Part C: Layout shape
# ---------------------------------------------------------------------------

class TestLayoutChecks:
    def test_matching_shape_passes(self):
        result = compare_extraction_to_analysis(
            _extraction(shape="single-wall"),
            _analysis(layout_shape="single-wall"),
            _analysis(layout_shape="single-wall"),
        )
        shape_check = next(c for c in result.checks if c.name == "layout_shape")
        assert shape_check.passed

    def test_shape_mismatch_fails(self):
        result = compare_extraction_to_analysis(
            _extraction(shape="single-wall"),
            _analysis(layout_shape="L-shape"),
            _analysis(layout_shape="single-wall"),
        )
        shape_check = next(c for c in result.checks if c.name == "layout_shape")
        assert not shape_check.passed


# ---------------------------------------------------------------------------
# Part D: Upload-vs-screenshot cross-reference
# ---------------------------------------------------------------------------

class TestCrossReference:
    def test_upload_screenshot_count_mismatch_fails(self):
        """Upload shows 3 base, screenshot shows 2 — even if extraction says 3."""
        upload = _analysis(base_cabs=[
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": False},
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
            {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
        ])
        screenshot = _analysis(base_cabs=[
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": False},
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
        ])
        result = compare_extraction_to_analysis(
            _extraction(base=3), screenshot, upload,
        )
        cross_check = next(c for c in result.checks if c.name == "cross_ref_base_count")
        assert not cross_check.passed


# ---------------------------------------------------------------------------
# Overall result
# ---------------------------------------------------------------------------

class TestOverallResult:
    def test_all_pass_means_overall_pass(self):
        result = compare_extraction_to_analysis(
            _extraction(), _analysis(), _analysis(),
        )
        assert result.passed is True
        assert len(result.failures) == 0

    def test_any_single_failure_means_overall_fail(self):
        """Even if 14/15 pass, 1 fail = overall FAIL."""
        screenshot = _analysis(base_cabs=[
            {"position": "left", "doors": 2, "drawers": 0, "has_sink": False},
            {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 1},
            {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
            {"position": "extra", "doors": 1, "drawers": 0, "has_sink": False},  # phantom
        ])
        result = compare_extraction_to_analysis(
            _extraction(base=3), screenshot, _analysis(),
        )
        assert result.passed is False
        assert len(result.failures) >= 1

    def test_summary_lists_all_failures(self):
        """Summary string must mention every failed check."""
        screenshot = _analysis(
            base_cabs=[
                {"position": "left", "doors": 1, "drawers": 0, "has_sink": False},  # wrong doors
                {"position": "center", "doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": 2},  # wrong bowls
                {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
            ],
            layout_shape="L-shape",  # wrong shape
        )
        result = compare_extraction_to_analysis(
            _extraction(), screenshot,
            _analysis(appliances=[{"type": "sink", "sink_bowls": 1}]),
        )
        assert result.passed is False
        assert "FAIL" in result.summary
        # Every failure must be mentioned
        for f in result.failures:
            assert f.name in result.summary


class TestVerificationResultProperties:
    def test_result_has_check_count(self):
        result = compare_extraction_to_analysis(
            _extraction(), _analysis(), _analysis(),
        )
        assert result.total_checks > 0
        assert result.pass_count == result.total_checks
        assert result.fail_count == 0

    def test_failed_result_counts(self):
        screenshot = _analysis(layout_shape="L-shape")
        result = compare_extraction_to_analysis(
            _extraction(shape="single-wall"), screenshot, _analysis(),
        )
        assert result.fail_count >= 1
        assert result.pass_count == result.total_checks - result.fail_count
