"""Extraction benchmark: run a vision backend over synthetic plan views and score it.

Renders synthetic plan-view drawings from `benchmarks/synthetic.py` (generated from
scratch; no real drawings), sends each to `DrawingExtractor.extract()` with the chosen
backend, and scores the returned JSON against the generator's ground truth:

- cabinet counts (base, wall, tall) from the output's `parsed` block: exact-match rate
  and mean absolute error per category;
- the appliance set, excluding the types the extraction rules skip: exact-match rate
  and mean Jaccard similarity;
- the room shape, against the convention the extraction prompt itself imposes
  (two or more walls are reported as "U-shape"; see `_build_extraction_prompt`).

This command calls an external model unless `--dry-run` is given. It sends the rendered
synthetic images to the provider selected by `--backend`. No results are committed with
the repository; run it and keep the JSON it writes.

Usage:
    python benchmarks/extraction_bench.py --dry-run --cases 10 --out runs/extraction
    python benchmarks/extraction_bench.py --backend ollama --model llama3.2-vision:11b --cases 50 --out runs/ollama
    ANTHROPIC_API_KEY=... python benchmarks/extraction_bench.py --backend anthropic --cases 50 --out runs/anthropic
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from benchmarks.synthetic import generate, render_plan  # noqa: E402

PROMPT_SHAPE = {"single-wall": "single-wall", "L-shape": "U-shape", "U-shape": "U-shape", "galley": "U-shape"}


def ground_truth(case: dict) -> dict:
    ext = case["extraction"]
    return {
        "counts": {k: ext["parsed"].get(k, 0) for k in ("base", "wall", "tall")},
        "appliances": sorted({a["type"] for a in ext["appliances"]}),
        "shape": PROMPT_SHAPE[ext["room"]["shape"]],
    }


def score(output: dict, truth: dict) -> dict:
    parsed = output.get("parsed") or {}
    counts = {}
    for k in ("base", "wall", "tall"):
        got = parsed.get(k)
        if got is None:  # fall back to counting typed cabinets
            got = sum(1 for c in output.get("cabinets", []) if str(c.get("type", "")).lower() == k)
        counts[k] = {"expected": truth["counts"][k], "got": got, "abs_error": abs(int(got) - truth["counts"][k])}
    got_apps = {str(a.get("type", "")).lower() for a in output.get("appliances", []) if isinstance(a, dict)}
    exp_apps = set(truth["appliances"])
    union = got_apps | exp_apps
    shape = str((output.get("room") or {}).get("shape", "")).strip()
    return {
        "counts": counts,
        "appliances": {"expected": sorted(exp_apps), "got": sorted(got_apps),
                       "exact": got_apps == exp_apps,
                       "jaccard": (len(got_apps & exp_apps) / len(union)) if union else 1.0},
        "shape": {"expected": truth["shape"], "got": shape, "match": shape.lower() == truth["shape"].lower()},
    }


def summarise(rows: list[dict]) -> dict:
    ok = [r for r in rows if "score" in r]
    n = len(ok)
    out = {"scored": n, "errors": len(rows) - n}
    if not n:
        return out
    for k in ("base", "wall", "tall"):
        errs = [r["score"]["counts"][k]["abs_error"] for r in ok]
        out[f"{k}_count_exact_rate"] = sum(e == 0 for e in errs) / n
        out[f"{k}_count_mae"] = sum(errs) / n
    out["appliance_set_exact_rate"] = sum(r["score"]["appliances"]["exact"] for r in ok) / n
    out["appliance_jaccard_mean"] = sum(r["score"]["appliances"]["jaccard"] for r in ok) / n
    out["shape_match_rate"] = sum(r["score"]["shape"]["match"] for r in ok) / n
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", choices=["anthropic", "openai", "ollama"], default="ollama")
    ap.add_argument("--model", help="model id; the extractor's default for the backend if omitted")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--cases", type=int, default=20)
    ap.add_argument("--out", type=Path, required=True, help="directory for drawings, raw outputs and the report")
    ap.add_argument("--dry-run", action="store_true", help="render drawings and ground truth only; call no model")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    extractor = None
    if not args.dry_run:
        from mozaik_automation.vision.extractor import DrawingExtractor
        extractor = DrawingExtractor(backend=args.backend, model=args.model)

    rows = []
    for case in generate(args.seed, args.cases):
        png = render_plan(case, args.out / f"{case['id']}.png")
        truth = ground_truth(case)
        row = {"id": case["id"], "drawing": png.name, "truth": truth}
        if extractor is not None:
            t0 = time.perf_counter()
            try:
                output = extractor.extract(png)
                row["seconds"] = time.perf_counter() - t0
                (args.out / f"{case['id']}.output.json").write_text(json.dumps(output, indent=2))
                row["score"] = score(output, truth)
            except Exception as e:  # record and continue; a failed call is a result too
                row["seconds"] = time.perf_counter() - t0
                row["error"] = f"{type(e).__name__}: {e}"
        rows.append(row)

    report = {
        "benchmark": "extraction_bench",
        "backend": None if args.dry_run else args.backend,
        "model": None if args.dry_run else (args.model or extractor.model),
        "seed": args.seed,
        "cases": args.cases,
        "summary": summarise(rows) if not args.dry_run else {"dry_run": True},
        "rows": rows,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    print(f"report: {args.out / 'report.json'}")


if __name__ == "__main__":
    main()
