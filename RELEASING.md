# Releasing

v0.1.0 was released on 28 September 2026. For a later release:

1. Run `python -m pytest`, `python benchmarks/verification_bench.py --cases 500` and
   `gitleaks git . --redact --log-opts=--all`, and confirm all three are clean.
2. Bump `version` in `pyproject.toml` and `__version__` in `src/mozaik_automation/__init__.py`.
3. Add a section to `CHANGELOG.md`, and set `version` and `date-released` in `CITATION.cff`.
   Use the day the release actually happens.
4. Tag `vX.Y.Z` and publish a GitHub release. If the Zenodo integration is enabled, add the
   DOI it mints to `CITATION.cff` (`doi:`) and to the README.
5. Only if a PyPI release is decided, remove the `Private :: Do Not Upload` classifier first.
