# Benchmarks

Three benchmarks, each with a stated scope. None of them is a claim about how well the
system works on real drawings in a real shop. The repository makes no such claim.

## 1. Verification layer: fault injection

```bash
python benchmarks/verification_bench.py --seed 20260925 --cases 500 [--tolerance 1] [--json out.json]
```

**Inputs.** Synthetic cases from `benchmarks/synthetic.py`, generated from scratch. Each
case has a specification, the compact extraction the comparator reads, and a correct
reading of a correct build.

**Procedure.** For each case, run the comparator on the clean inputs, where PASS is
expected. Then corrupt a copy of the reading with each fault class in turn (a wrong
build, or a misreading of one), where FAIL is expected on a named check. Then corrupt the
extraction for the pre-build gate.

**Reports.** False alarms on clean cases. For each fault class: how many cases it applied
to, how many FAILed, and how many FAILed on the intended check. The time per comparison.

**Scope.** It tests the comparison code. It does not test how often a vision model or a
person reads an image correctly, which is the harder problem, and it does not test the
build. One fault class, a wrong cabinet width, is included deliberately because the
comparator does not check dimensions. It should never be detected, and the report shows
that.

The output is deterministic for a given seed, apart from timing. Verbatim output of the
command above on 2026-09-25 (Python 3.13.3, macOS 15.7.3, arm64):

```
verification_bench  seed=20260925  cases=500  pre-build tolerance=0
clean cases that FAILED (false alarms): 0 of 500

Build faults (screenshot analysis corrupted)
  fault                            applicable   FAIL  on target  expected check
  missing_base_cabinet                    500    500        500  base_cabinet_count
  extra_wall_cabinet                      500    500        500  wall_cabinet_count
  missing_tall_cabinet                    243    243        243  tall_cabinet_count
  missing_appliance                       500    500        500  appliance
  phantom_appliance                       500    500        500  no_phantom_appliances
  wrong_door_count                        443    443        443  cabinet_config
  wrong_drawer_count                      485    485        485  cabinet_config
  sink_on_wrong_cabinet                   434    434        434  cabinet_config
  wrong_sink_bowls                        500    500        500  sink_bowl_match
  wrong_layout_shape                      500    500        500  layout_shape
  wrong_cabinet_width                     500      0          0  (not checked by design)

Pre-build faults (extraction corrupted)
  fault                            applicable   FAIL  on target  expected check
  extraction_missed_one_base              500    500        500  pre_build_base_count
  extraction_missed_two_base              483    483        483  pre_build_base_count
  extraction_phantom_appliance            500    500        500  pre_build_appliance_types

comparison time over 5605 calls: median 27 us, p95 46 us, max 149 us
```

With `--tolerance 1`, `extraction_missed_one_base` is no longer caught (0 of 500), which
is what the tolerance is for; the other two pre-build faults are still caught.

Because generator changes alter the per-fault counts, rerun this block and replace it
rather than editing numbers by hand.

## 2. Extraction: synthetic plan views

```bash
python benchmarks/extraction_bench.py --dry-run --cases 10 --out runs/extraction
python benchmarks/extraction_bench.py --backend ollama --model <model> --cases 50 --out runs/<name>
python benchmarks/extraction_bench.py --backend anthropic --cases 50 --out runs/<name>   # ANTHROPIC_API_KEY
python benchmarks/extraction_bench.py --backend openai --cases 50 --out runs/<name>      # OPENAI_API_KEY
```

**Procedure.** Render a plan view for each synthetic case, send it to the backend through
`DrawingExtractor.extract()`, and score the reply against the generator's ground truth.
The score covers cabinet counts per category (exact-match rate and mean absolute error),
the appliance set (exact-match rate and mean Jaccard) and the room shape. Shape is scored
under the extraction prompt's own convention, which reports any multi-wall layout as
"U-shape". Failed calls are recorded, not dropped.

**Scope.** The drawings are clean and synthetic. A backend's score on them is an upper
bound on nothing and a prediction of nothing for real, messy drawings. The benchmark is
useful for comparing backends, or prompt changes, on identical inputs. No results are
committed. Keep the `report.json` the run writes, with the backend, model, seed and date.

## 3. Control layer: element lookup (Windows)

```bash
python scripts/perf_benchmark.py
python scripts/overnight_discovery.py --output runs/overnight --window-title ".*Mozaik Enterprise.*"
```

These need Windows and the target application, open and licensed. The January 2026
measurements, taken on one machine against the Mozaik Enterprise release then installed,
are recorded in [performance-analysis.md](performance-analysis.md). They cover discovery
of 1,861 elements in 3 h 8 min, cached tab switches between 91× and 369× faster than
uncached ones, and uncached clicks that still took 58 to 67 s. They are historical
records of that environment. They have not been reproduced since, and they have not been
re-measured against later releases of the application.
