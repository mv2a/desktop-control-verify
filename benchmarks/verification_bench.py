"""Fault-injection benchmark for the deterministic verification layer.

What it measures: whether `compare_extraction_to_analysis` and `pre_build_cross_check`
return FAIL, on the intended check, when a known fault is injected into otherwise
consistent synthetic inputs; whether they return PASS on the clean inputs; and how long
each comparison takes.

What it does not measure: the accuracy of any vision model, the accuracy of drawing
extraction, or whether a real build in a real application succeeds. The inputs are the
structured JSON the comparator reads, generated from scratch by `benchmarks/synthetic.py`.
A detection rate of 100% here says the comparison code is correct for that fault class;
it says nothing about how often an image analyser would report the fault in the first place.

Usage:
    python benchmarks/verification_bench.py --seed 20260925 --cases 500
    python benchmarks/verification_bench.py --seed 20260925 --cases 500 --json results.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from benchmarks.synthetic import BUILD_FAULTS, PREBUILD_FAULTS, generate, inject  # noqa: E402
from mozaik_automation.verification.comparator import (  # noqa: E402
    compare_extraction_to_analysis,
    pre_build_cross_check,
)


def _hit(result, target) -> bool:
    return any(f.name == target or f.category == target for f in result.failures)


def run(seed: int, n: int, tolerance: int = 0) -> dict:
    cases = generate(seed, n)
    timings: list[float] = []
    clean_false_fail = 0
    build = {name: {"applicable": 0, "failed": 0, "failed_on_target": 0} for name in BUILD_FAULTS}
    pre = {name: {"applicable": 0, "failed": 0, "failed_on_target": 0} for name in PREBUILD_FAULTS}

    for k, case in enumerate(cases):
        ext, ana = case["extraction"], case["analysis"]
        t0 = time.perf_counter()
        clean = compare_extraction_to_analysis(ext, ana, ana)
        timings.append(time.perf_counter() - t0)
        if not clean.passed or not pre_build_cross_check(ext, ana, tolerance).passed:
            clean_false_fail += 1

        for j, (name, (fault, target)) in enumerate(BUILD_FAULTS.items()):
            bad = inject(case, fault, "analysis", seed * 1000 + k * 37 + j)
            if bad is None:
                continue
            row = build[name]
            row["applicable"] += 1
            t0 = time.perf_counter()
            res = compare_extraction_to_analysis(ext, bad, ana)
            timings.append(time.perf_counter() - t0)
            if not res.passed:
                row["failed"] += 1
                if target and _hit(res, target):
                    row["failed_on_target"] += 1

        for j, (name, (fault, target)) in enumerate(PREBUILD_FAULTS.items()):
            bad = inject(case, fault, "extraction", seed * 1000 + k * 41 + j)
            if bad is None:
                continue
            row = pre[name]
            row["applicable"] += 1
            res = pre_build_cross_check(bad, ana, tolerance)
            if not res.passed:
                row["failed"] += 1
                if target and _hit(res, target):
                    row["failed_on_target"] += 1

    timings.sort()
    return {
        "benchmark": "verification_bench",
        "seed": seed,
        "cases": n,
        "prebuild_tolerance": tolerance,
        "clean_cases_failed": clean_false_fail,
        "build_faults": {k: {**v, "expected_check": BUILD_FAULTS[k][1]} for k, v in build.items()},
        "prebuild_faults": {k: {**v, "expected_check": PREBUILD_FAULTS[k][1]} for k, v in pre.items()},
        "comparison_seconds": {
            "n": len(timings),
            "median": statistics.median(timings),
            "p95": timings[int(0.95 * (len(timings) - 1))],
            "max": timings[-1],
        },
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }


def _print(report: dict) -> None:
    print(f"verification_bench  seed={report['seed']}  cases={report['cases']}  "
          f"pre-build tolerance={report['prebuild_tolerance']}")
    print(f"clean cases that FAILED (false alarms): {report['clean_cases_failed']} of {report['cases']}")
    for title, key in (("Build faults (screenshot analysis corrupted)", "build_faults"),
                       ("Pre-build faults (extraction corrupted)", "prebuild_faults")):
        print(f"\n{title}")
        print(f"  {'fault':32} {'applicable':>10} {'FAIL':>6} {'on target':>10}  expected check")
        for name, row in report[key].items():
            tgt = row["expected_check"] or "(not checked by design)"
            print(f"  {name:32} {row['applicable']:>10} {row['failed']:>6} {row['failed_on_target']:>10}  {tgt}")
    t = report["comparison_seconds"]
    print(f"\ncomparison time over {t['n']} calls: median {t['median'] * 1e6:.0f} us, "
          f"p95 {t['p95'] * 1e6:.0f} us, max {t['max'] * 1e6:.0f} us")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--cases", type=int, default=500)
    ap.add_argument("--tolerance", type=int, default=0, help="pre-build count tolerance")
    ap.add_argument("--json", type=Path, help="also write the full report as JSON")
    args = ap.parse_args()
    report = run(args.seed, args.cases, args.tolerance)
    _print(report)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
