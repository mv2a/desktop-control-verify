# desktop-control-verify (working name)

Tools for driving a Windows desktop application that has no automation interface, for
turning a drawing into a typed specification with a vision model, and for checking in
code, rather than by a model's judgement, that what was built matches what was specified.

They are the general-purpose layers of a private project that automates cabinet design
entry in Mozaik Enterprise, a Windows design-to-manufacturing application. They were
extracted from that project with their development history. The cabinetry product built
on top of them is not included.

> **Status: pre-release research software. No licence has been granted yet** (see
> [LICENSE](LICENSE)). The public name, the licence and the release date are still to be
> decided. Mozaik is a trademark of its owner. This project is not affiliated with or
> endorsed by Mozaik Software or Cyncly (see [NOTICE](NOTICE)).

## What is here

**Control layer** (`src/mozaik_automation/automation/`, `scripts/`)

- `fast_driver.py`: a cached-element driver. It walks the UI Automation tree once, records
  each element's automation id, control type and window-relative rectangle, and from then
  on clicks, types and switches tabs against those cached positions, without walking the tree.
  Input goes through pywinauto or pywin32. The target window's title and fallback
  positions are constructor arguments.
  `CachedWin32Driver` is an application-neutral alias.
- `scripts/overnight_discovery.py`: an unattended, read-only discovery harness. It runs
  16 phases with time budgets, checkpoints after each phase, reconnects after COM errors
  and uses thread-based timeouts. Its phase plan names the tabs and dialogs of the Mozaik
  Enterprise release it was written against.
- `scripts/fast_discovery.py`, `scripts/discover_mozaik_ui.py`: faster discovery through
  UI Automation COM directly, and a single-pass enumeration with a report.
- `scripts/perf_benchmark.py`: compares element-lookup strategies (root-scoped, parent-scoped,
  direct COM, cached batch). The January 2026 measurements are in
  [docs/performance-analysis.md](docs/performance-analysis.md).
- `scripts/moz_action.py`: a one-action command-line tool (screenshot, click, drag, type,
  key) for driving the application one step at a time with a screenshot after each.

**Extraction and verification layer** (`src/mozaik_automation/`)

- `models.py`: a typed specification of a room, its walls and openings, cabinets,
  appliances, finishes and trim, written in pydantic. Its JSON Schema is in
  `data/schemas/cabinet_spec.json`.
- `vision/extractor.py`: sends a drawing (image or PDF) to a vision model (Anthropic,
  OpenAI or Ollama) and returns structured JSON.
- `verification/comparator.py`: deterministic comparison. An image analyser (a model or a
  person) describes an image as structured JSON, and Python code decides PASS or FAIL. A
  pre-build gate compares the extraction with an independent reading of the source drawing
  before anything is built. A post-build check compares the extraction with readings of
  the built result and of the source. Any mismatch is a FAIL, and the code does not let
  the analyser override it.
- `verification/build_steps.py`: a step protocol. A build prints
  `[STEP] name|screenshot|description` at each of eight checkpoints and waits for a
  supervisor to answer `CONTINUE` or `ABORT <reason>`.
- `scripts/validate_annotations.py`: validates specification files against the schema.

**Benchmarks and fixtures** (`benchmarks/`, `tests/fixtures/synthetic/`). A seeded generator
builds synthetic kitchen cases from scratch, together with plan-view drawings of them. No
real drawing, customer file or third-party dataset is used. See
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

How the pieces fit is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What is not here

The following stay private. The cabinetry-specific build automation that places walls,
appliances and cabinets in the application. The element caches recorded against the
application. The trained models and adapters, with their training data and training code.
The licensing client and server, the web application, the job pipeline and the deployment
configuration. The vision evaluation set, which is derived from CubiCasa5K and licensed
CC BY-NC 4.0. Commit messages in the history sometimes describe changes to those parts.
The changes themselves are not in this repository.

## Quick start

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The tests do not need Windows. At extraction there were 294, all passing on macOS with
Python 3.13. The control layer and the discovery scripts need Windows at run time:

```bash
python -m pip install -e ".[windows]"
```

Drawing extraction needs a vision backend:

```bash
python -m pip install -e ".[vision]"
```

## Reproducing the benchmarks

```bash
# Verification layer: fault injection on synthetic cases. No network, no Windows.
python benchmarks/verification_bench.py --seed 20260925 --cases 500

# Extraction: render synthetic drawings and ground truth only.
python benchmarks/extraction_bench.py --dry-run --cases 10 --out runs/extraction

# Extraction against a model. This sends the synthetic drawings to the chosen provider.
python benchmarks/extraction_bench.py --backend ollama --model llama3.2-vision:11b --cases 50 --out runs/ollama

# Control layer: on Windows, with the target application open.
python scripts/perf_benchmark.py
python scripts/overnight_discovery.py --output runs/overnight --window-title ".*Mozaik Enterprise.*"
```

[docs/BENCHMARKS.md](docs/BENCHMARKS.md) says what each one measures and what it does not.

## Provenance

This repository was extracted from a private repository on **25 September 2026**. The
extraction kept the commits that touched the extracted files, with their original dates,
authors, messages and co-author trailers unchanged.

| | Date |
|---|---|
| Development of the extracted files, in private | **25 January 2026 to 5 March 2026** (26 commits) |
| Development of the wider private project | 25 January 2026 to 8 September 2026 |
| Extraction and preparation for release | from 25 September 2026 (commits after `eafb42d`) |
| First public release | **not yet released** |

The historical commits record when the work was done in private. They do not record when
it became public, which is the release date above once it exists. The extraction rewrote
commit identifiers, because git derives them from content. The mapping from each commit
here to its original, a verified archive of the original repository, and the hosting
provider's server-side push log for it are all held privately and can be produced for
verification. Commits made after the extraction are listed in
[CHANGELOG.md](CHANGELOG.md). They are not part of the historical record.

Details: [docs/PROVENANCE.md](docs/PROVENANCE.md).

## AI assistance

This software was developed with AI coding assistants. Of the 26 historical commits, 25
carry a `Co-Authored-By` trailer naming a Claude model: Claude Opus 4.5 on 14, Claude
Opus 4.6 on 10 and Claude Haiku 4.5 on 1. The commits made while preparing this release
carry one naming Claude Opus 5.5. The two author labels in the history, "Tiago Leao" and
"user", are the git configurations of the author's two machines and share one email
address.

The trailers record which commits were machine-assisted, and they measure nothing else.
Commit counts are not offered as a measure of the author's labour. The author's
contribution is the architecture; the decision to control the application through its
accessibility tree and cached positions rather than any other route; the design of the
evaluation and of the verification rules that decide PASS or FAIL; and the decisions
about what is built, tested and claimed.

## Limitations

- **One application, one version, one machine.** Every control-layer measurement was taken
  in January and February 2026 against the Mozaik Enterprise release then installed on
  one Windows machine, at one window geometry. The author's records identify that release
  as version 14; the repository itself does not record the build string. The vendor has
  since released version 15. Its marketing page describes "a rebuilt core engine, a
  modernised interface", and its support site describes version 15 as an open beta, with
  version 14 still the stable release. Nothing here has been run against version 15, so
  identifiers and positions recorded against version 14 should be assumed invalid for
  version 15 until they are rediscovered.
- **Cached positions are window-relative.** A change of resolution, DPI scaling, layout or
  window geometry requires rediscovery. The speed-ups apply only to cached operations. An
  uncached UI Automation click took 58 to 67 seconds in the January 2026 measurements.
- **Discovery is specific to the application.** The overnight harness's phases name
  Mozaik's tabs and dialogs. Another application needs its own phase plan.
- **Windows only at run time.** The tests on other systems cover the parts that do not
  touch Win32.
- **The comparator checks counts and configuration, not geometry.** It checks cabinet
  counts per category; door, drawer and sink configuration; the presence of appliances
  (including ones that should not be there); the number of sink bowls; and the layout
  shape. It does not check dimensions, positions or finishes. In the benchmark, the
  injected width error is never detected.
- **Its inputs are not deterministic.** The comparison is deterministic. The image readings
  that feed it come from a model or a person. The verification benchmark measures the
  comparison code, not how often an analyser reads an image correctly.
- **The step protocol fails open.** An empty or unrecognised supervisor response counts as
  `CONTINUE`. This was designed in March 2026 so that a build would not block forever. It
  makes the protocol a supervision aid, not an interlock.
- **The checks and prompts are specific to cabinetry.** The comparator's rules, the
  analysis prompts and the extraction prompt describe kitchens and the target
  application's conventions. The extraction prompt, for example, skips dishwashers and
  microwaves and reports any multi-wall layout as "U-shape". A different domain needs new
  rules.
- **`extract()` and `extract_to_spec()` disagree.** Since 4 March 2026, `extract()` asks the
  model for the pipeline's compact schema. That schema does not validate as the full
  `CabinetSpec` that `extract_to_spec()` expects. The `local` backend is not implemented.
- **No accuracy claim.** This repository reports no extraction accuracy. The synthetic plan
  views are simple, so results on them do not predict results on real drawings.
- **The history is sparse.** Most of the extracted code arrived in a few large commits.
  How the excluded parts evolved is not visible here.
- **Names.** The import package keeps the original project's name, `mozaik_automation`,
  so that its history reads continuously. It may be renamed before release.

## Citing

See [CITATION.cff](CITATION.cff). The software has no DOI yet.
