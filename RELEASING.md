# Releasing

Nothing in this repository has been released. Before the first release:

1. Replace `LICENSE` with the chosen licence. Set `license` in `pyproject.toml` to the
   same identifier, and add it to `CITATION.cff` (`license:`) and `.zenodo.json`
   (`"license"`).
2. Remove the `Private :: Do Not Upload` classifier from `pyproject.toml`. PyPI refuses
   uploads while it is present, on purpose.
3. If the project is renamed, rename the import package with `git mv` in a single commit
   so that `git log --follow` keeps the history. Update the title in `README.md`,
   `CITATION.cff` and `.zenodo.json` to match.
4. Run `python -m pytest`, `python benchmarks/verification_bench.py --cases 500` and
   `gitleaks git . --redact --log-opts=--all`, and confirm all three are clean.
5. Record the release date in `README.md` (Provenance), `docs/PROVENANCE.md`,
   `CHANGELOG.md` and `CITATION.cff` (`date-released:`). Never use a date earlier than
   the day the repository actually becomes public.
6. Tag and release. If the Zenodo integration is enabled, add the DOI it mints to
   `CITATION.cff` (`doi:`) and to the README.
