# Changelog

All notable changes to this project are documented here.

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/). The policy — the
public surface, the definitions, and the release procedure — is
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## Unreleased

### Added

- `council evidence add` and `council evidence list` attach local screenshots to
  a kept run. Images are hash-named under `artifacts/`, recorded in a relative
  `artifacts.json` sidecar, and exposed as direct links; the reviewer never reads
  them and a moved or deleted image is reported, not treated as a failure. See
  [`docs/EVIDENCE.md`](docs/EVIDENCE.md).
- `council-mcp` and `council-acp`, optional additive adapters around the public
  CLI. MCP exposes `council_plan`, `council_review` and `council_doctor`; ACP
  exposes `/plan`, `/review`, `/verdict` and `/help`. The core package remains
  free of protocol dependencies and unchanged; evidence is retained under the
  server's own state root. See [`docs/AGENT-SERVER.md`](docs/AGENT-SERVER.md).
- Reviewer agents are now adapters. `--agent` selects one, `council agents` lists
  the build, and `council doctor` probes the selected adapter. Hermes is the only
  built-in adapter; the extension contract is
  [`docs/AGENT-ADAPTERS.md`](docs/AGENT-ADAPTERS.md). The agent name and its
  configuration identity are part of the instrument digest and the verdict.
- `council pr` accepts a pull-request number, URL or branch. `gh pr view`
  resolves the target to the same base/head pair; the checkout and clean-worktree
  checks are unchanged. The decision is [`docs/M31.md`](docs/M31.md).
- The Nix side is checked by a standard rather than by eye. `flake.nix` takes
  `rokokol/nix-best-practices-skill` as an input and exposes
  `checks.nix-lint`, which holds the flake and the scripts to twenty rules that
  rest on the parse tree, the lock file or an evaluated value. It found four
  things on adoption: the flake was not nixfmt-formatted, two assignments wanted
  `inherit`/`with pkgs`, and one list of `pkgs.*` wanted the same. The one file
  it may not touch is `fixtures/golden/target/modules/base.nix`, whose hash and
  kloc are pinned by `expect.json`; `check-nix.allow` says so in writing, which
  is the tool's own mechanism for what a repository knows and a checker cannot.
  `nix run .#nix-lint` runs the half that `--static` leaves out.
- `council.toml` can map changed paths to the documents that govern them
  (`[[rules]] glob/doc`). Each matching document reaches the prompt once, capped
  at 20,000 bytes and marked when cut, under a heading that frames it as context
  rather than instructions; the verdict records what governed the change. A rule
  whose document cannot be read is a start failure, because the alternative is a
  reviewer judging a diff against its memory of the rules — which is how a
  violation passes review. Taken from deepseek-harness's review skill.
- Proof strength is part of the verdict. Every finding records `proof_strength` —
  `executed` when the proof that held ran a command, `static` when it only quoted
  the code — and the reason names blocking findings that rest on quotation alone.
  `--require-executed-proofs` makes that the rule instead of the note. This is
  the lesson from reviewing `deepseek-harness`, where eight findings proved
  control-flow claims by quoting the defective line: a quotation is evidence the
  line exists, never that the code misbehaves.
- `verdict.json` is published atomically (staged, fsynced, renamed) and states
  `format: 1`; a consumer seeing a format it does not know must refuse rather
  than guess. A crash no longer leaves a half-written document for CI to read.
- `scope_ignored` is bounded at 200 paths with `scope_ignored_omitted` counting
  the rest. A whole-repo audit against the empty tree had produced a 3.1 MB
  verdict that was 21,629 path records and three findings.


- Large files are reviewable, by choice. A file that no budget admits — an added
  file is one hunk carrying every line, so `src/agent_loop.py`'s 38,416 lines are
  a single 1.8 MB prompt — is still refused by default, and the refusal now states
  what splitting it would cost: *N* windows, one sample each. `--window-large-files`
  splits that hunk into line windows, each its own unit at `--max-prompt-bytes`,
  sliced at depth 0 and recorded with its own range in `units[]`; `--max-windows`
  (default 200) is the ceiling. The interactive prompt gained the same choice, and
  `--plan` prints the window count and the samples it implies before anything is
  asked. Windows are disjoint: a defect spanning a boundary is missed, which is
  the price of reviewing the file at all.

- `repro` proofs, and absence claims that carry a scope. `repro` runs one
  allowlisted command and is `PROVEN` only when the command fails, so a defect
  that can be demonstrated is settled by demonstration rather than by quoting a
  line; `contains` pins the failure to the one claimed. `absent` takes
  `within` — repository-relative POSIX globs — so a module-level absence is not
  refuted by an unrelated hit elsewhere. A scope that matches no file is
  `UNRUNNABLE`: an absence proved over nothing is not an absence.
  The proof-kind set is part of the instrument digest, so this changes every
  digest deliberately: a run under the old contract and a run under this one are
  not comparable, and the tool says so instead of averaging them.
- The instrument digest covers the reviewer profile's own configuration. The
  model, provider and reasoning default live in a Hermes profile file this tool
  does not parse, so `runner.profile_fingerprint` hashes its bytes and
  `verdict.json` records the path and the digest. A profile that cannot be read
  is recorded as unknown, never assumed unchanged.
- A licence: MIT, in `LICENSE` and in the package metadata.
- Caller-owned path scope: `--include` and `--exclude` (repeatable POSIX globs;
  `*` stays in one segment, `**` recurses, exclude wins). Dropped paths are
  named in `scope_ignored`; an include matching nothing is a start failure.
  `--staged` reviews the index against the base (`git diff --cached`), not the
  working tree, and is available on `review`/`ci` but not `pr`. See
  `docs/SCOPE.md`.
- A committed accepted-risk baseline: `council baseline create/prune`,
  `--baseline`, `--baseline-from-base`, `--baseline-strict` and
  `--allow-baseline-change`. It applies only after the evidence verdict; only
  proven blocking findings can be suppressed, never `UNRUNNABLE`, `UNSETTLED`,
  a failed sample or an unreviewed unit. `ci` and `pr` read it from the base
  revision so a PR cannot edit its own baseline; changing the baseline in the
  reviewed diff is a start failure unless explicitly allowed. Entries carry an
  owner, reason and expiry, and are fingerprinted by dimension, severity, file,
  claim and proof. `verdict.json` records both `evidence_verdict` and `verdict`.
- A pure domain kernel in `council.domain`: run-id validation, configuration
  parsing, adjudication from proof outcomes, and sandbox argv construction.
  `GLOSSARY.md` fixes the domain vocabulary; `docs/ARCHITECTURE.md` records the
  dependency rule, the SOLID scorecard and the remaining debt.
- A stronger architecture gate. It parses the imported module, checks effectful
  method calls and import direction, and fails when a new module that acts is
  not named as an adapter. The previous gate listed `paths` as pure even though
  it called `is_symlink()`.

### Changed

- The kernel is one package. `findings`, `verdict`, `merge`, `schema`, `prompt`,
  `changes`, `context`, `sarif` and `vocabulary` moved into `council.domain`, so
  the purity list in `tests/test_architecture.py` is the package rather than a
  selection from it, `domain.adjudication` no longer imports upward through the
  shell namespace, and a new test refuses a module that is neither kernel nor
  named adapter. No public name changed: `council.findings` and `council.verdict`
  still resolve, now to the kernel modules.
- The diff is parsed once. `changes.Hunk` carries the header line verbatim, the
  new-side range and `slice()`; `change_lines`, `file_sections` and the window
  slicer read the same parse, so a header edge case has one place to be fixed and
  a window's line numbers come from the code that wrote them. `hunk_range`,
  `hunk_parts`, `hunk_sections` and `slice_hunk` are gone.
- A run keeps a record per unit. `runstore.UnitRun` replaces the 5-tuple the
  loop read by position, `runstore.unit_payload` is the only place the
  `units[]` row is built, and `domain.adjudication.missing_evidence` is the only
  place a unit that never ran turns `PASS` into `INCOMPLETE`.
- `config.load` now only reads and delegates to the pure `domain.config.parse`.
  `version.current_version()` is the only package-metadata reader; importing
  `council` no longer performs I/O. SARIF renderers take the tool version as an
  argument.
- `paths` keeps the file-system symlink guard; the run-id *name* is validated by
  the pure `domain.run_id`.
- `sample.payload` is the pure serialisation decision; `write_sample` is the
  adapter.

### Removed

- `doctor._safe`, a second copy of `cli_output.safe`; the comments that restated
  a machine-checked list, repeated an exit-code rule, or repeated the retracted
  `merge` laundering claim; and one unit test whose claim `review` already covers
  end to end.
- `scripts/verify.sh`, `HANDOFF.md` and `docs/GRILL.md`. The script was a weaker
  copy of the gate that omitted `mypy`, `pyright`, `ruff` and the wheel build
  while the README called it "the full gate"; the handoff note duplicated a
  verified state that had already drifted (203 claims against a registry of
  211); the grill page was an opinion measured at `18b7043` whose five points
  are closed in `M29` and `M30`. A document that restates the tree is a second
  place for it to be wrong.
- The documentation index `docs/README.md` replaces the handoff note as the way
  in. It is bound: `tests/test_docs_index.py` fails when a Markdown file is not
  linked from it, or when a link on it does not resolve.

### Fixed

- A malformed `council.toml` is refused before git, context fetches, prompt
  construction or a reviewer call. A missing prompt or an empty change no longer
  triggers a context fetch.
- A `council.toml` that is a symlink is refused rather than read through the
  link; the repository config may not redirect the policy input outside the
  checkout.
- Boolean values are refused for samples, prompt budget, context depth, time
  budget and idle timeout instead of being read as `0`/`1`.

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
- The reviewer now runs in a bwrap sandbox by default where bwrap is present:
  read-only root, private `/tmp` and a tmpfs overlay of `$HOME`; the choice is
  recorded as `reviewer_sandbox`. `--no-sandbox` opts out, `--sandbox` requires it.
- Runs are **ephemeral by default**: the run directory lives in a private
  temporary tree and is removed after the verdict; `--no-ephemeral` writes
  `.council/runs`, `--keep DIR` copies the evidence first.
- `tools/sandbox.sh` runs an arbitrary command with the same boundary; it
  refuses with exit 3 when bwrap is absent.
- `Dockerfile` and `docs/PORTABILITY.md` state the non-NixOS path: a container
  (`--rm --read-only --tmpfs /tmp`) is the boundary where bwrap is unavailable.
- The CLI now refuses invalid input before a model call: non-portable run ids,
  empty paths, missing output parents, symlinks/FIFOs where a file is expected,
  unreadable or non-UTF-8 prompts, empty changes, unknown bases, malformed
  `council.toml`, and `--plan` combined with `--sarif`/`--keep`/`--report`.
- A missing reviewer is a start failure (exit 3), not an `INCOMPLETE` review,
  and is not retried. `--time-budget 0` is accepted; negative values are not.
- Untracked symlinks are named and skipped, never followed; proof parameters
  cannot crash a run; non-UTF-8 diff bytes are replaced once so the prompt is
  valid; human output strips terminal control characters.
- A run directory is claimed with `mkdir(exist_ok=False)` before evidence is
  written, so concurrent `--no-ephemeral` runs cannot share it. A start failure
  before evidence removes the empty claim.
- `--keep` refuses an existing target instead of merging into it; a copy
  failure leaves the source evidence and names both paths.
- A reviewer answer that is not UTF-8 is replaced rather than crashing the
  decoder; a stream `result` with empty text falls back to text events.
- JSON Pointer array indexes reject `-1` and leading zeros; a FIFO cannot be
  opened as a `present`/`json` proof file.
- Failed samples are named in the reason even on `FAIL`; auto-sampling returns
  `agreement: null` when any sample is missing.
- `docs/STATE-MACHINES.md` maps every explicit and implicit state machine, its
  invariants, transitions, confirmed issues and residual races.
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

