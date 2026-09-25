"""Tests for the synthetic fixtures and the verification benchmark.

The fixtures are generated from scratch by benchmarks/synthetic.py; nothing in them is
derived from a real drawing. These tests pin three things: the generator is
deterministic, a correct build passes both gates, and every fault class the comparator
covers is caught on the intended check, while the one it does not cover (dimensions) is
reported as uncaught rather than hidden.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks.extraction_bench import ground_truth, score, summarise  # noqa: E402
from benchmarks.synthetic import (  # noqa: E402
    BUILD_FAULTS,
    PREBUILD_FAULTS,
    generate,
    inject,
    render_plan,
)
from benchmarks.verification_bench import run  # noqa: E402
from mozaik_automation.models import CabinetSpec  # noqa: E402
from mozaik_automation.verification.comparator import (  # noqa: E402
    compare_extraction_to_analysis,
    pre_build_cross_check,
)

SEED = 20260925
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


@pytest.fixture(scope="module")
def cases():
    return generate(SEED, 40)


class TestGenerator:
    def test_same_seed_same_cases(self):
        assert generate(SEED, 10) == generate(SEED, 10)

    def test_different_seed_different_cases(self):
        assert generate(SEED, 10) != generate(SEED + 1, 10)

    def test_specs_validate_against_schema(self, cases):
        for case in cases:
            CabinetSpec.model_validate(case["spec"])

    def test_parsed_counts_match_cabinets(self, cases):
        for case in cases:
            ext = case["extraction"]
            for kind in ("base", "wall", "tall"):
                assert ext["parsed"][kind] == sum(1 for c in ext["cabinets"] if c["type"] == kind)

    def test_skipped_appliances_are_drawn_but_not_built(self, cases):
        for case in cases:
            drawn = {a["appliance_type"] for a in case["spec"]["appliances"]}
            built = {a["type"] for a in case["analysis"]["appliances"]}
            assert "dishwasher" not in built
            assert built <= drawn

    def test_every_case_has_a_sink(self, cases):
        for case in cases:
            assert "sink" in {a["type"] for a in case["extraction"]["appliances"]}


class TestCleanCasesPass:
    def test_build_comparison_passes(self, cases):
        for case in cases:
            result = compare_extraction_to_analysis(case["extraction"], case["analysis"], case["analysis"])
            assert result.passed, (case["id"], result.summary)

    def test_pre_build_gate_passes(self, cases):
        for case in cases:
            assert pre_build_cross_check(case["extraction"], case["analysis"]).passed


class TestBuildFaults:
    @pytest.mark.parametrize("name", [n for n, (_, t) in BUILD_FAULTS.items() if t])
    def test_covered_fault_fails_on_target_check(self, cases, name):
        fault, target = BUILD_FAULTS[name]
        applied = 0
        for k, case in enumerate(cases):
            bad = inject(case, fault, "analysis", k)
            if bad is None:
                continue
            applied += 1
            result = compare_extraction_to_analysis(case["extraction"], bad, case["analysis"])
            assert not result.passed, (name, case["id"])
            assert any(f.name == target or f.category == target for f in result.failures), (name, case["id"])
        assert applied > 0, f"no case exercised {name}"

    def test_dimensional_fault_is_not_detected(self, cases):
        """The comparator checks counts, configuration, appliances and shape, not sizes."""
        fault, target = BUILD_FAULTS["wrong_cabinet_width"]
        assert target is None
        for k, case in enumerate(cases):
            bad = inject(case, fault, "analysis", k)
            result = compare_extraction_to_analysis(case["extraction"], bad, case["analysis"])
            assert result.passed


class TestPreBuildFaults:
    def test_single_missed_cabinet_caught_at_zero_tolerance(self, cases):
        fault, _ = PREBUILD_FAULTS["extraction_missed_one_base"]
        for k, case in enumerate(cases):
            bad = inject(case, fault, "extraction", k)
            assert not pre_build_cross_check(bad, case["analysis"], tolerance=0).passed

    def test_single_missed_cabinet_allowed_at_tolerance_one(self, cases):
        fault, _ = PREBUILD_FAULTS["extraction_missed_one_base"]
        for k, case in enumerate(cases):
            bad = inject(case, fault, "extraction", k)
            assert pre_build_cross_check(bad, case["analysis"], tolerance=1).passed

    def test_two_missed_cabinets_caught_at_tolerance_one(self, cases):
        fault, _ = PREBUILD_FAULTS["extraction_missed_two_base"]
        for k, case in enumerate(cases):
            bad = inject(case, fault, "extraction", k)
            if bad is not None:
                assert not pre_build_cross_check(bad, case["analysis"], tolerance=1).passed


class TestBenchmarkReport:
    def test_small_run_is_clean_and_complete(self):
        report = run(SEED, 25)
        assert report["clean_cases_failed"] == 0
        for name, row in report["build_faults"].items():
            if row["expected_check"]:
                assert row["failed_on_target"] == row["applicable"], name
            else:
                assert row["failed"] == 0, name


class TestCommittedFixtures:
    def test_fixtures_match_the_generator(self):
        manifest = json.loads((FIXTURES / "MANIFEST.json").read_text())
        regenerated = generate(manifest["seed"], manifest["cases"])
        for case in regenerated:
            committed = json.loads((FIXTURES / f"{case['id']}.json").read_text())
            assert committed == json.loads(json.dumps(case, sort_keys=True))

    def test_every_listed_file_exists(self):
        manifest = json.loads((FIXTURES / "MANIFEST.json").read_text())
        for name in manifest["files"]:
            assert (FIXTURES / name).is_file(), name

    def test_render_plan_writes_an_image(self, tmp_path, cases):
        from PIL import Image

        path = render_plan(cases[0], tmp_path / "plan.png")
        with Image.open(path) as img:
            assert img.size[0] >= 400 and img.size[1] >= 400


class TestExtractionScoring:
    """The extraction benchmark's scorer, exercised on a hand-built model output."""

    def test_perfect_output_scores_perfectly(self, cases):
        case = cases[0]
        truth = ground_truth(case)
        output = {
            "room": {"shape": truth["shape"]},
            "parsed": dict(truth["counts"]),
            "appliances": [{"type": t} for t in truth["appliances"]],
        }
        s = score(output, truth)
        assert all(v["abs_error"] == 0 for v in s["counts"].values())
        assert s["appliances"]["exact"] and s["shape"]["match"]
        summary = summarise([{"score": s}])
        assert summary["base_count_exact_rate"] == 1.0 and summary["appliance_jaccard_mean"] == 1.0

    def test_errors_are_counted(self, cases):
        case = cases[0]
        truth = ground_truth(case)
        output = {
            "room": {"shape": "galley"},
            "parsed": {k: v + 1 for k, v in truth["counts"].items()},
            "appliances": [{"type": "microwave"}],
        }
        s = score(output, truth)
        assert all(v["abs_error"] == 1 for v in s["counts"].values())
        assert not s["appliances"]["exact"] and not s["shape"]["match"]

    def test_counts_fall_back_to_typed_cabinets(self, cases):
        truth = ground_truth(cases[0])
        output = {"cabinets": [{"type": "base"}] * truth["counts"]["base"], "appliances": [], "room": {}}
        assert score(output, truth)["counts"]["base"]["abs_error"] == 0
