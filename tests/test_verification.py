"""TDD tests for programmatic build verification (D9.9) and pre-build cross-check (D9.11).

The verification is enforced IN CODE — not by LLM judgment.
The LLM analyzes images via API → Python code compares → deterministic PASS/FAIL.
"""

import pytest
from mozaik_automation.verification.comparator import (
    CheckResult,
    VerificationResult,
    compare_extraction_to_analysis,
    pre_build_cross_check,
    _has_sink_in_note,
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


# ---------------------------------------------------------------------------
# _has_sink_in_note — must not false-positive on positional references
# ---------------------------------------------------------------------------

class TestHasSinkInNote:
    def test_sink_base_cabinet_is_true(self):
        assert _has_sink_in_note("Sink base cabinet") is True

    def test_sink_base_with_opening_is_true(self):
        assert _has_sink_in_note("Sink base cabinet with 29 7/8 inch opening") is True

    def test_above_sink_area_is_false(self):
        """Wall cab 'above sink area' is NOT a sink cabinet."""
        assert _has_sink_in_note("Pair door wall cabinet, 45 inch wide, above sink area") is False

    def test_near_sink_is_false(self):
        assert _has_sink_in_note("Single door base, near sink") is False

    def test_next_to_sink_is_false(self):
        assert _has_sink_in_note("Wall cabinet next to sink base") is False

    def test_no_sink_at_all_is_false(self):
        assert _has_sink_in_note("3-drawer base unit") is False

    def test_plain_sink_word_at_start_is_true(self):
        assert _has_sink_in_note("sink cabinet with faucet") is True

    def test_empty_note_is_false(self):
        assert _has_sink_in_note("") is False

    def test_above_sink_area_wall_cab_no_false_positive_in_verification(self):
        """Full integration: wall cab note with 'above sink area' must NOT trigger sink check fail."""
        ext = _extraction(
            base=2, wall=1, tall=0,
            cabinets=[
                {"type": "base", "width": 36, "note": "Sink base cabinet"},
                {"type": "base", "width": 24, "note": "3-drawer base"},
                {"type": "wall", "width": 45, "note": "Pair door wall cabinet, above sink area"},
            ],
            appliances=[{"type": "sink"}],
        )
        screenshot = _analysis(
            base_cabs=[
                {"position": "left", "doors": 2, "drawers": 0, "has_sink": True},
                {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
            ],
            wall_cabs=[
                {"position": "center", "doors": 2, "has_sink": False},
            ],
        )
        upload = _analysis(
            base_cabs=[
                {"position": "left", "doors": 2, "drawers": 0, "has_sink": True},
                {"position": "right", "doors": 0, "drawers": 3, "has_sink": False},
            ],
            wall_cabs=[
                {"position": "center", "doors": 2, "has_sink": False},
            ],
        )
        result = compare_extraction_to_analysis(ext, screenshot, upload)
        # The wall cab check should PASS — "above sink area" is not a sink
        wall_check = next(c for c in result.checks if c.name == "cabinet_2_config")
        assert wall_check.passed, f"Wall cab false positive: {wall_check.detail}"


# ---------------------------------------------------------------------------
# Pre-build cross-check (D9.11 / BUG-22)
# ---------------------------------------------------------------------------

class TestPreBuildCrossCheck:
    """pre_build_cross_check() compares an independent image analysis against
    the extraction BEFORE building. Catches extraction errors early."""

    def test_matching_counts_passes(self):
        """Upload analysis agrees with extraction — build should proceed."""
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}, {}],
            wall_cabs=[{}, {}],
            tall_cabs=[],
        )
        result = pre_build_cross_check(ext, upload)
        assert result.passed is True

    def test_missing_wall_cabinet_fails(self):
        """Extraction says 2W, upload image shows 3W — MUST block build."""
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}, {}],
            wall_cabs=[{}, {}, {}],  # image shows 3!
            tall_cabs=[],
        )
        result = pre_build_cross_check(ext, upload)
        assert result.passed is False
        wall_check = next(c for c in result.checks if c.name == "pre_build_wall_count")
        assert not wall_check.passed
        assert wall_check.expected == 2
        assert wall_check.actual == 3

    def test_extra_base_in_extraction_fails(self):
        """Extraction says 4B, upload shows 3B."""
        ext = _extraction(base=4, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}, {}],
            wall_cabs=[{}, {}],
        )
        result = pre_build_cross_check(ext, upload)
        assert result.passed is False
        base_check = next(c for c in result.checks if c.name == "pre_build_base_count")
        assert not base_check.passed
        assert base_check.expected == 4
        assert base_check.actual == 3

    def test_tall_mismatch_fails(self):
        """Extraction says 0T, upload shows 1T."""
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}, {}],
            wall_cabs=[{}, {}],
            tall_cabs=[{"position": "right", "doors": 2}],
        )
        result = pre_build_cross_check(ext, upload)
        assert result.passed is False
        tall_check = next(c for c in result.checks if c.name == "pre_build_tall_count")
        assert not tall_check.passed

    def test_appliance_mismatch_fails(self):
        """Extraction has sink, upload image shows sink + range."""
        ext = _extraction(appliances=[{"type": "sink"}])
        upload = _analysis(appliances=[
            {"type": "sink", "sink_bowls": 1},
            {"type": "range"},
        ])
        result = pre_build_cross_check(ext, upload)
        assert result.passed is False
        app_check = next(c for c in result.checks if c.name == "pre_build_appliance_types")
        assert not app_check.passed

    def test_appliance_match_passes(self):
        """Both extraction and upload agree on sink only."""
        ext = _extraction(appliances=[{"type": "sink"}])
        upload = _analysis(appliances=[{"type": "sink", "sink_bowls": 1}])
        result = pre_build_cross_check(ext, upload)
        app_check = next(c for c in result.checks if c.name == "pre_build_appliance_types")
        assert app_check.passed

    def test_tolerance_of_one_allowed(self):
        """Off-by-one on base count is a warning, not a failure (vision noise)."""
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}, {}, {}],  # 4 vs expected 3 — off by 1
            wall_cabs=[{}, {}],
        )
        result = pre_build_cross_check(ext, upload, tolerance=1)
        base_check = next(c for c in result.checks if c.name == "pre_build_base_count")
        assert base_check.passed  # within tolerance

    def test_tolerance_exceeded_fails(self):
        """Off-by-two exceeds tolerance=1."""
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}, {}, {}, {}],  # 5 vs expected 3 — off by 2
            wall_cabs=[{}, {}],
        )
        result = pre_build_cross_check(ext, upload, tolerance=1)
        base_check = next(c for c in result.checks if c.name == "pre_build_base_count")
        assert not base_check.passed

    def test_summary_lists_failures(self):
        """Summary string must mention every failed check."""
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(
            base_cabs=[{}, {}],         # wrong
            wall_cabs=[{}, {}, {}],     # wrong
        )
        result = pre_build_cross_check(ext, upload)
        assert result.passed is False
        assert "FAIL" in result.summary
        for f in result.failures:
            assert f.name in result.summary

    def test_result_has_check_counts(self):
        ext = _extraction(base=3, wall=2, tall=0)
        upload = _analysis(base_cabs=[{}, {}, {}], wall_cabs=[{}, {}])
        result = pre_build_cross_check(ext, upload)
        assert result.total_checks >= 4  # base, wall, tall, appliances
        assert result.pass_count == result.total_checks
        assert result.fail_count == 0
