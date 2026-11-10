# Changelog

All notable changes to this project are documented here.

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/). The policy — the
public surface, the definitions, and the release procedure — is
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## Unreleased

## [2.0.0] — 2026-11-09

The first release of the rebuilt engine: the wheel installs with no
dependencies, the image carries the tool and `bwrap`, and the CI action runs
`council doctor` before `council ci`. Adoption on `pypa/sampleproject` is
recorded in `docs/ADOPTION.md`.

### Added

- A verdict derived from evidence states: `pass`, `fail`, `incomplete`. A finding
  is a claim until a proof settles it, and only a proof that holds fails a run.
- Five proof kinds — `absent`, `present`, `command`, `json`, `diff` — each
  executed in a sandbox that overlays the repository, so a proof may write and
  the judged tree is unchanged.
- Context around the change: the enclosing function of every changed Python
  line, then the functions it calls, to a depth the caller chooses
  (`--context-depth`, 0–3).
- `council ci`: the gate for a pipeline — `verdict.json` on stdout, the verdict
  as the exit code, no advice switches.
- Slicing: a change larger than one prompt is reviewed as units — whole files
  where they fit, hunks of a file that does not — with findings merged and every
  unit's coverage recorded. An unreviewed unit makes the run `incomplete`.
- A prompt budget (`--max-prompt-bytes`, default 32 KiB). An oversized prompt is
  refused before the reviewer is called and before any run directory exists;
  an interactive `review` asks a person what to do (`allow`, `budget N`,
  `base REV`, `context N`, `?`, `cancel`), and `--autonomous` refuses without
  asking.
- Property tests for the diff parser and proof-parameter normalisation.
- A zero-dependency wheel (`pip install council-<version>-py3-none-any.whl`) and
  a container image that carries the tool, not the reviewer.
- `--sample-timeout N` (default 900 s): one sample attempt cannot outlast it.
- `--time-budget N`: a sliced run stops starting units after N seconds; the
  units it did not reach are recorded as unreviewed, so the run cannot be PASS.
- `--reasoning LEVEL`: overrides the profile's reasoning effort for the review;
  the level is recorded in `verdict.json` and hashed into the instrument digest.
- `--stream` (default) / `--no-stream`: read the reviewer as JSON events;
  `--idle-timeout N` (default 120 s) kills a stream that goes silent, and a
  silent or answerless sample fails rather than passing.
- Samples record every failed attempt in `failures`, not only the final error.
- `--version` prints the installed version; the wheel now ships `py.typed`, so
  consumers' type checkers use the package's annotations.
- `--sarif PATH` writes proven findings as SARIF 2.1.0 for code scanning;
  `verdict.json` remains the complete evidence.
- `council pr NUMBER`: resolve a GitHub pull request with `gh`, verify the
  checkout is its head commit with a clean worktree, and review it; the verdict
  records the PR's URL and SHAs. The base is GitHub's and `--base` is refused.
- `--plan` on `review` and `pr`: print units, file ranges, prompt bytes, context
  depth and skipped files without calling the reviewer or writing a run.
- README gains the `council pr` entry and the plan documentation.
- `council doctor`: measures `git`, the reviewer binary, `bwrap` and whether the
  profile answers a probe; `--json` for CI.

### Changed

- Three review verbs: `review`, `ci`, `init`; `council doctor` is a diagnostic.
  The claims registry is the maintainer entry point `council-verify`.
- A run records what it reviewed: `diff_sha256`, skipped files, context spans and
  their digest, unresolved calls, references, prompt size and limit.

### Fixed

- Every shipped text file now ends with a newline, so diffs stop reporting
  `\ No newline at end of file` for the last line.
- A run's reason names the units the time budget left unreviewed even when an
  unresolved finding already made the verdict `incomplete`.
- The changelog's duplicate `### Added` heading, literal `[Unreleased]` heading
  and "three user verbs" wording, all found by a live review of this repository.
- `tools/release.py bump` dropped the `-py3-none-any.whl` suffix from a wheel
  filename in prose; it now replaces only the version, and a test holds it.

### Removed

- The hybrid score, the threshold and the calibration laboratory. The blocking
  set is the verdict; a number may be reported beside it as a trend and cannot
  change it.
- The `http` and `dom` proof kinds. Retrieval is caller-supplied context, and a
  browser claim is a `command` proof of the repository's own test.

