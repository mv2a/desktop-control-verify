# Changelog

## Unreleased: extraction, 25 September 2026

The history up to commit `eafb42d` (5 March 2026) is the historical record of the
extracted files. See [docs/PROVENANCE.md](docs/PROVENANCE.md). Everything below was done
on or after 25 September 2026 to prepare that record for release.

### Fixed
- The verification package imports. `build_steps.py` now defines the four checkpoint
  names (`STEP_APPLIANCES`, `STEP_BASE_CABS`, `STEP_WALL_CABS`, `STEP_TALL_CABS`) that the
  package has exported since 5 March 2026. Two test modules that could not be collected
  now run.
- Nothing imports modules that were not extracted, and `fast_driver.py` imports on
  systems other than Windows.

### Changed
- The cached-element driver takes the target window's title and fallback positions as
  arguments. The defaults keep the original behaviour. Added the alias `CachedWin32Driver`.
- The extractor's default Ollama endpoint is `localhost`, overridable with `OLLAMA_HOST`.

### Added
- Synthetic fixtures and three benchmarks: verification fault injection, extraction on
  synthetic plan views, and the historical control-layer benchmark scripts.
- README with provenance, AI-assistance disclosure and limitations; architecture,
  provenance and benchmark documents; CITATION.cff; .zenodo.json; a licence placeholder;
  NOTICE; packaging; CI.
