# Provenance of this repository

## Summary

This repository is a history-preserving extraction from a private repository, made on
25 September 2026, and first released publicly on 28 September 2026. The table below
separates the dates that matter.

| Event | Date | Evidence |
|---|---|---|
| First commit of the private project (and of this history) | 2026-01-25 21:32:48 −05:00 | commit `383364c` here |
| Last historical change to an extracted file | 2026-03-05 17:31:41 −05:00 | commit `eafb42d` here |
| Last commit of the private project | 2026-09-08 | private repository |
| Extraction | 2026-09-25 | this document; commits after `eafb42d` |
| GitHub repository created (private) | 2026-09-25 | GitHub |
| First public release | 2026-09-28 | v0.1.0; CHANGELOG.md; CITATION.cff |

## Method

1. The private repository was archived first, as a `git bundle` of all refs, and its
   SHA-256 was recorded. Its full commit log and the hosting provider's server-side push log were
   exported. The original repository was not modified in any way.
2. A fresh, non-hardlinked clone of its main branch was made (`git clone --no-local
   --single-branch`).
3. `git filter-repo` was run with a list of paths to keep and no other filter. It was
   given `--preserve-commit-hashes`, so that commit messages are left byte-identical
   rather than having old hashes rewritten into new ones, and
   `--preserve-commit-encoding`. Author and committer names, emails, dates and time zones
   are untouched. So are commit messages, including every `Co-Authored-By` trailer.
4. Commits that touched no kept path became empty and were dropped: 223 of 249. The other
   26 are the history here. One of them is a merge.
5. Every kept commit was then checked against its original: author, committer, raw
   timestamps and zones, encoding header, full message bytes, trailers, and parents
   (mapped through dropped commits). The tree had to equal the original tree restricted
   to the kept paths. No path outside the kept list appears anywhere in the history.
   Problems found: none.
6. The history was scanned for credentials with gitleaks 8.30.1 over all refs, and with a
   pattern scan of every blob, binaries included. Findings: none.

Commit identifiers here differ from the originals, because a git identifier is a hash of
the commit's content and the content changed. A private mapping from every commit here to
its original is kept with the archive.

## Reading the history

- Commit messages are verbatim. Many describe work on files that were not extracted, such
  as the web application, the job pipeline and training. They also name machines on the
  author's private network and the licence server. None of that code is in this
  repository.
- The history is sparse. Most extracted files arrived in one or two large commits, because
  development happened in larger steps inside a bigger repository.
- Commits after `eafb42d` were made on or after 25 September 2026 to prepare this
  repository for release. They are listed in CHANGELOG.md.

## Historical commits

| # | Commit | Author date | Author label | Subject |
|---|---|---|---|---|
| 1 | `383364c` | 2026-01-25 21:32:48 −05:00 | user | Initial commit: Mozaik Automation v0.2.0 |
| 2 | `b8bf096` | 2026-01-25 21:43:58 −05:00 | user | chore: add .gitignore and clean up cached files |
| 3 | `dc7986a` | 2026-01-25 23:42:25 −05:00 | user | feat: add annotation validation script |
| 4 | `61e9d17` | 2026-01-27 16:15:41 −05:00 | user | feat(mozaik): live UI discovery and smoke test validation on 14coresbeast |
| 5 | `6eb25b6` | 2026-01-27 18:53:53 −05:00 | user | docs: add performance analysis with benchmark results |
| 6 | `b27a796` | 2026-01-27 20:24:42 −05:00 | user | docs: add LLM training data plan and update perf results |
| 7 | `53a2523` | 2026-01-28 15:51:42 −05:00 | user | feat: add fast Win32 driver, training data capture, and overnight discovery |
| 8 | `7f54e5d` | 2026-01-28 16:54:02 −05:00 | Tiago Leao | Add fast Win32 discovery and kitchen workflow scripts |
| 9 | `58883a5` | 2026-01-28 19:52:24 −05:00 | user | docs: add project-specific standards, templates, and personas |
| 10 | `a5094e7` | 2026-01-28 20:37:51 −05:00 | user | feat(training): add vision training data generator |
| 11 | `c621afa` | 2026-02-03 16:31:46 −05:00 | user | feat(vision): add Ollama backend for floor plan extraction |
| 12 | `42c3931` | 2026-02-03 17:48:52 −05:00 | user | feat(portal): Phase 5 - Jobs API with Ollama vision extraction |
| 13 | `893da73` | 2026-02-03 18:15:28 −05:00 | Tiago Leao | feat(automation): E2E kitchen test with Win32 API |
| 14 | `5c24731` | 2026-02-03 20:58:03 −05:00 | Tiago Leao | Merge branch 'master' of github.com:mv2a/mozaik-automation |
| 15 | `7a7eeb4` | 2026-02-04 10:02:26 −05:00 | user | feat(web): add delete confirmation + thumbnail URL fix + infra docs |
| 16 | `e620546` | 2026-03-03 16:33:56 −05:00 | Tiago Leao | feat(Phase1): E2E poller + LLM design agent epic |
| 17 | `86c6034` | 2026-03-03 21:39:01 −05:00 | Tiago Leao | feat(extraction): Add position_along_wall precision + placement warning tracking |
| 18 | `fc6b43d` | 2026-03-03 22:38:34 −05:00 | Tiago Leao | fix(geometry): Open L-shape walls, center_x interior offset, persona gaps |
| 19 | `0f653d0` | 2026-03-04 17:42:04 −05:00 | Tiago Leao | feat(vision): Real extraction pipeline — remove mock fallback, speckit plan |
| 20 | `4e5e6ca` | 2026-03-04 17:57:40 −05:00 | Tiago Leao | test(T004-T008): Phase 2 foundational tests + verification |
| 21 | `0e63443` | 2026-03-04 20:34:46 −05:00 | Tiago Leao | fix(tests): Update prompt tests for new extraction prompt format |
| 22 | `10a14d3` | 2026-03-04 22:09:50 −05:00 | Tiago Leao | feat(e2e): Live build status in UI, claude_code vision backend, post-build verification |
| 23 | `111cd13` | 2026-03-05 13:54:02 −05:00 | Tiago Leao | feat(verification): D9.9 code-enforced build verification (20 tests) |
| 24 | `15ca62f` | 2026-03-05 13:55:54 −05:00 | Tiago Leao | feat(verification): D9.10 step-based build protocol (13 tests) |
| 25 | `70f34ad` | 2026-03-05 14:50:26 −05:00 | Tiago Leao | fix(verify): BUG-22 pre-build cross-check + _has_sink_in_note false positive |
| 26 | `eafb42d` | 2026-03-05 17:31:41 −05:00 | Tiago Leao | feat(phase11): Implement 8 strategic checkpoints for step-based build monitoring |
