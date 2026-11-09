# Changelog

All notable changes to this project are documented here.

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/). The policy — the
public surface, the definitions, and the release procedure — is
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## [Unreleased]

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

### Changed

- Three user verbs: `review`, `ci`, `init`. The claims registry is the
  maintainer entry point `council-verify`.
- A run records what it reviewed: `diff_sha256`, skipped files, context spans and
  their digest, unresolved calls, references, prompt size and limit.

### Fixed

- Every shipped text file now ends with a newline, so diffs stop reporting
  `\ No newline at end of file` for the last line.

### Removed

- The hybrid score, the threshold and the calibration laboratory. The blocking
  set is the verdict; a number may be reported beside it as a trend and cannot
  change it.
- The `http` and `dom` proof kinds. Retrieval is caller-supplied context, and a
  browser claim is a `command` proof of the repository's own test.
