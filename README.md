# council

A review is a claim until a check settles it.

## The rule

Every finding carries one of four states, and the verdict is a pure function of
those states:

| state | meaning |
|---|---|
| `proven` | the check ran and supported the claim — **this is the only state that fails a run** |
| `refuted` | the check ran and the claim did not hold |
| `unsettled` | no check was attempted |
| `unrunnable` | a check was attempted and could not run here |

```
any blocking finding proven        -> FAIL        exit 1
else any blocking finding open     -> INCOMPLETE  exit 2
else                               -> PASS        exit 0
```

A **start failure** is exit 3, never 2: 2 means the review ran and is missing
evidence. A start failure writes no run and sends no prompt.

## Errors and exit codes

The CLI refuses before spending a model call when the request cannot be valid:

- a run id that is not one portable path segment (separators, `..`, control
  characters, Windows-reserved characters, or more than 128 characters);
- an empty `--repo`, `--prompt`, `--sarif` or `--keep` path;
- a prompt that is missing, a directory, a FIFO, or not UTF-8;
- a `--sarif` or `--keep` path whose parent is missing, or that is a symlink,
  a directory where a file is needed, or a file where a directory is needed;
- an empty `--base`, `--profile` or `--context-url`;
- a `--plan` combined with `--sarif`, `--keep` or `--report` (a plan writes no
  run, so those flags would be silently ignored);
- a change with no reviewable text, an unknown base revision, a malformed
  `council.toml`, or a missing reviewer binary.

A missing reviewer is a start failure (exit 3), not an `INCOMPLETE` review, and
it is not retried. A file in the change that is a symlink is named and skipped;
it is never followed. Human output replaces control characters from model output
so a finding cannot drive the terminal.

`blocking` means severity `high` or `critical` — **or any severity in `security`
or `correctness`**. The model may rank a defect; it may not decide that a proven
security or correctness defect is mergeable. The boundary is tested in both
directions: a proven `low` security finding fails, a proven `low` readability
finding passes.

There is no score in this decision. A number may be reported beside a verdict as
a trend; it cannot change it.

## Commands

```sh
council review                # gate: 0 pass, 1 fail, 2 incomplete, 3 could not start
council review --plan         # units, prompt sizes and skipped files; no model call
council pr 123                # review a GitHub pull request (needs gh and its head checked out)
council ci                    # the same gate for CI: verdict.json on stdout
council doctor                # can this machine run a review? measure, don't assume
council --version             # what is installed
council review --report       # advice only: always exits 0
python3 -m pytest             # the suite
./bin/council-verify          # every claim this project makes, executed
python3 tools/mutation_check.py   # prove the suite can fail
python3 tools/differential.py     # v1.9.0's verdicts beside this rule
python3 tools/release.py check    # version, changelog and prose agree
```

`claims.toml` is the registry. Each entry is one sentence and the command that
would falsify it; the loader refuses an entry with no check, and `council-verify`
exits non-zero if any claim is false. `docs/CLAIMS.md` is generated from it
(`council-verify --write docs/CLAIMS.md`) and checked in the flake, so the page
cannot list a claim that has no check behind it.

`council ci` is `council review` for a pipeline: it always prints the verdict as
JSON and always exits with it. It deliberately does not accept `--report` — a
gate that can be told to exit 0 is not a gate.

### `council pr`

`council pr 123` asks the GitHub CLI for the pull request's base and head SHAs,
checks that the current checkout **is** that head commit with a clean worktree,
and then reviews `base..HEAD` exactly as `council review` would. It never checks
a branch out and never reviews local edits: a PR review is a review of a commit.

It needs `gh` on `PATH` and an authenticated GitHub CLI. If the checkout is at a
different commit, it says so and asks for `gh pr checkout 123`; if the worktree
is dirty, it refuses. `--plan`, `--sarif`, `--json`, `--report` and the review
flags all work; `--base` is not accepted because GitHub owns the base.
`verdict.json` records the PR's number, URL, title and both SHAs.

`council review --plan` (and `council pr N --plan`) resolves the change, builds
the context and prompt, and prints the units it would review — file ranges,
prompt bytes per unit, context depth and skipped files — **without calling the
reviewer and without writing a run directory**. `--json` gives the same as
objects. It is how a user sees why a change will be sliced or refused before
spending a model call.

## Quickstart

### The wheel — no nix on the host

```sh
nix build .#wheel                 # produces council-2.0.0-py3-none-any.whl
python -m pip install council-2.0.0-py3-none-any.whl
cd path/to/repo
council doctor                    # is this machine able to review?
council review --base origin/main --samples 3
```

The wheel is pure Python (3.11+), no dependencies. `command` proofs need
`bwrap`; without it they are `UNRUNNABLE` and a run that needs one is
`INCOMPLETE`, never a pass. The flake is how the project builds its artifacts;
a user who installs the wheel never needs it.

### The image — tool and sandbox together

```sh
nix build .#image
docker load < result
docker run --rm council:2.0.0 --help
```

The image carries the tool and `bwrap`, not Hermes. Mount the repository, put a
`hermes` binary and its profile on the container's PATH, and it reviews like the
wheel does; the image is the artifact where the sandbox travels with the tool.

### The GitHub Action

The composite action installs the wheel into a private environment, runs
`council doctor`, then `council ci`, and writes `council.sarif`. It needs a
runner that has Hermes; it never installs one. The workflow in
`.github/workflows/council.yml` is the working example, including the
`upload-sarif` step that puts proven findings in code scanning.

## Configuration

A repository may narrow what proofs are allowed to do in `council.toml` at its
root:

```toml
[proofs]
allow = ["rg", "grep", "git", "jq", "test", "stat", "python3", "nix"]
timeout = 120
sandbox = true
```

The caller's policy is a ceiling: a repository can remove a tool, lower the
timeout or require the sandbox, never add a tool, raise the timeout or turn the
sandbox off. Unknown keys are refused with exit 3, so a typo cannot silently
restore a default. `command` proofs run in an overlay sandbox; `sandbox = false`
is refused when the caller requires it.

## Sandbox and cleanup

On Linux with `bwrap`, the reviewer runs in a bubblewrap sandbox: an immutable
root, a private `/tmp`, and a tmpfs overlay of `$HOME`. It can read the host and
reach the model, but every write to `$HOME` or `/tmp` lands in the overlay and
disappears with the process. `--sandbox` requires bwrap and fails without it;
`--no-sandbox` opts out; the default is **on when bwrap is on PATH**. The choice
is recorded as `reviewer_sandbox` in `verdict.json`. The Nix package puts bwrap
on the wrapper's PATH, so a Nix/NixOS install gets this by default; a bare wheel
without bubblewrap records `false` rather than pretending.

Runs are **ephemeral by default**: the run directory lives in a private
temporary tree and is removed after the verdict. `--keep DIR` copies the run
there first; `--no-ephemeral` writes `.council/runs` instead. The verdict is
printed — and a requested SARIF log is written — before the tree is removed. A
failed run removes its temporary tree too; if `--keep` cannot copy, the evidence
is left in place and its path is printed. Proof writes already run in an overlay
sandbox, so they never touch the repository. For hosts without bwrap, see
[`docs/PORTABILITY.md`](docs/PORTABILITY.md): the container is the boundary.

## Flags

Every flag the tool accepts, what it changes, and why it exists. `council <command>
--help` prints the same set from the parser; a test keeps this table and the parser in step.

### `council review`

| flag | default | what it does | why |
|---|---|---|---|
| `-C, --repo PATH` | `.` | the checkout to review | a review is about a repository, not a shell's idea of a directory |
| `--base REV` | `origin/HEAD`, else `HEAD~1` | where the diff starts | a wrong base still produces a confident verdict, so the default is a chain and each step is checked |
| `--samples N` | auto | samples to ask: N, or auto — 1 clean, 2 to confirm a finding, 3 to break a tie; per unit when a change is sliced | one sample is cheap; a second confirms a finding; a third only when the model disagrees with itself |
| `--profile NAME` | `council-generalist` | the Hermes profile asked | the instrument is a profile, not a string in the prompt |
| `--reviewer BIN` | `hermes` | the binary that answers a sample | the corpus harness needs a stub, and another host may need another binary |
| `--sample-timeout N` | `900` | give up on one sample after N seconds | a model that never answers must fail in bounded time, not hold the run |
| `--time-budget N` | none | stop starting units after N seconds; the unit in flight finishes | a large sliced review must end by a deadline even when the instrument is slow |
| `--reasoning LEVEL` | the profile's | reasoning effort for this review: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | the profile's level may be the wrong cost for a given run; whatever is used is recorded and hashed into the instrument |
| `--stream` / `--no-stream` | stream | read the reviewer's JSON event stream | a non-streaming call cannot tell “thinking” from “gone”; a stream can be watched; a plain-output stub needs `--no-stream` |
| `--idle-timeout N` | `120` | kill a stream with no event for N seconds | silence must cost the idle timeout, not the sample timeout |
| `--prompt PATH` | the shipped prompt | a different instrument | experiments must not edit the prompt the gate uses |
| `--sarif PATH` | off | also write proven findings as a SARIF 2.1.0 log | code scanning wants a log; `verdict.json` stays the complete evidence |
| `--plan` | off | print units, prompt bytes, depth and skipped files; no reviewer, no run | see the cost and the slicing before spending a model call |
| `--sandbox` / `--no-sandbox` | on when `bwrap` exists | run the reviewer in a bwrap sandbox: read-only root, private `/tmp`, overlay `$HOME` | writes vanish with the process; `--sandbox` fails rather than run unsandboxed |
| `--ephemeral` / `--no-ephemeral` | on | keep run state in a private temp tree and remove it after the verdict; `--no-ephemeral` writes `.council/runs` | zero-footprint by default: the verdict is the product, not the leftovers |
| `--keep DIR` | off | copy the run directory to DIR before an ephemeral removal | keep evidence deliberately, not by accident |
| `--report` | off | exit 0 whatever the verdict | advice in a hook that must not block |
| `--json` | off | print `verdict.json` | the machine-readable form, byte-identical to the artefact |
| `--run-id ID` | timestamp | name the run; refused if it exists | two runs are comparable only when they can be named |
| `--context-url URL` | none | fetch a URL as reference context (repeatable) | retrieval is context, not evidence; the caller names it, never the model |
| `--context-depth N` | `3` | `0` diff only, `1` enclosing function, `2` +one call level, `3` +two | the context is what makes a prompt large; the caller can trade depth for size |
| `--max-prompt-bytes N` | `32768` | refuse a prompt larger than N bytes | a prompt past the model's practical envelope is a hang, not a review; refusal is immediate |
| `--allow-large-prompt` | off | send an oversized prompt without asking | an autonomous caller that has measured the cost can say yes in advance |
| `--autonomous` | off | never ask: refuse an oversized prompt, exit 3 | a script running in a terminal must not block on a question |
| `-h, --help` | — | usage | — |

### When the prompt is too large

Before the reviewer is called, `council review` measures the prompt. A change
larger than one prompt is **sliced** first: whole files where they fit, hunks of
a file that does not, each reviewed within the same budget (see
[`docs/M12.md`](docs/M12.md)). The refusal below is for a single unit that
cannot fit at all, at any context depth.

Above `--max-prompt-bytes` it **stops**: nothing is sent, no run directory is written,
and it says how large the prompt is and what the limit is. By default it then
asks the person at the terminal what should happen:

| answer | effect |
|---|---|
| `allow` | send this prompt anyway; the verdict records `prompt_acknowledged: true` |
| `budget N` | change the limit to N bytes for this run and retry |
| `base REV` | review a narrower change and retry |
| `context N` | keep the diff, change the context depth to N (0–3) and retry |
| `?` | explain why the limit exists |
| `cancel`, empty line, or EOF | stop with exit 3 — silence is not consent |

`council ci` never asks: a pipeline has nobody to answer. It refuses unless
`--allow-large-prompt` is given. The same is true of `council review` with no
terminal attached, or with `--autonomous`.

The default is a starting point measured, not assumed: a 2.8 KB prompt was
answered by the reviewer, a 60 KB prompt was not, on the same profile. A run
that needs more says so before the wait rather than after it.

### `council ci`

Takes every flag in the `council review` table except `--report`, `--json` and
`--autonomous`: it prints `verdict.json` unconditionally and always exits with
the verdict (0 pass, 1 fail, 2 incomplete, 3 could not start). It exists so a
pipeline names one stable entry point instead of remembering the flags. It
refuses an oversized prompt rather than asking; `--allow-large-prompt` is the
explicit way to send one.

### `council-verify` (maintainer entry point)

Not a `council` subcommand: the registry is the project's own contract, and the
binary is installed beside `council` for whoever maintains it.

| flag | default | what it does | why |
|---|---|---|---|
| `--registry PATH` | `claims.toml` | the claims to run | the registry is the project's own contract, and a fork may carry another |
| `--list` | off | print the claims without running them | reading the contract must not execute it |
| `--write PATH` | — | render the registry as markdown | the documentation is generated, never hand-edited |
| `--check PATH` | — | fail if the file differs from the registry | a stale page is a failing check, not a review note |
| `-h, --help` | — | usage | — |

### `council init`

| flag | default | what it does | why |
|---|---|---|---|
| `-C, --repo PATH` | `.` | the checkout to add `.council/` to | the state directory is per repository |
| `-h, --help` | — | usage | — |

### `council doctor`

Checks what a review needs on this machine and prints one line per check:
`git`, the reviewer binary, `bwrap`, and whether the profile answers a one-line
probe within `--probe-timeout`. A `fail` exits 1; a `warn` (for example, no
`bwrap`) exits 0 and says what will be `UNRUNNABLE`. `--json` prints the checks
as objects.

| flag | default | what it does | why |
|---|---|---|---|
| `--profile NAME` | `council-generalist` | the profile asked the probe | the same instrument the review will use |
| `--reviewer BIN` | `hermes` | the binary to look for and ask | a wrapper or another host may use another name |
| `--probe-timeout N` | `60` | how long the profile has to answer | a dead profile must be reported in a minute, not after a review times out |
| `--json` | off | machine-readable checks | CI can assert the machine is ready before it reviews |
| `-h, --help` | — | usage | — |

## Architecture

A pure core and an enumerated effect shell. `findings`, `verdict`, `merge`, `schema`,
`prompt` and `paths` may not import `subprocess`, `urllib`, `os`, `time`, `random`,
`shutil`, `tempfile` or `sys`, and may not call `open`, `write_text`, `write_bytes`,
`mkdir`, `unlink`, `rename`, `run`, `Popen`, `system` or `urlopen`. A test enforces it
(`tests/test_architecture.py`), because "the verdict is a pure function" is a claim about
the whole path from parsed sample to `Result`, not about one function.

Everything that acts is in a module a reader can name: `repo` (git), `proofs` and
`sandbox` (commands), `sample` and `runner` (the model), `config` (the repository's
file), `run` (writes the run), `cli` (stdout), `claims` (runs the registry). That is the
whole of the side effects.

The rebuild's acceptance criteria, every amendment to them, and the command that
decides each one: `docs/M11.md`. The time budget and the doctor checks are
decided in [`docs/M13.md`](docs/M13.md); release and adoption in
[`docs/M14.md`](docs/M14.md), with the external run written up in
[`docs/ADOPTION.md`](docs/ADOPTION.md). Every explicit and implicit state
machine, its invariants, transitions and residual races lives in
[`docs/STATE-MACHINES.md`](docs/STATE-MACHINES.md).

## Evidence

`verdict.json` records `base`, `head`, `worktree` (whether local edits were
included), `diff_sha256`, and `skipped` — every file in the change the diff could
not carry, with the reason (`too large`, `binary`, `not utf-8`, `unreadable`).
It also records `context_digest`, the spans the model was shown,
`unresolved` — calls the context could not follow — and `references`, the URLs
the caller asked for, with a digest each. A run states what it did not look at.

When the change was too large for one prompt, `verdict.json` also carries
`sliced: true` and `units[]`: each unit's files, line ranges, diff digest,
prompt size, context depth, samples, findings and its own verdict. Units whose
reviewer never answered make the run `incomplete`; a run with an unreviewed unit
can never be `pass`.

## The reviewer contract

One call, five sections (`security`, `correctness`, `readability`,
`architecture`, `performance`), one JSON object. A finding without a proof from
the closed set (`absent`, `present`, `command`, `json`, `diff`)
is refused by the parser, not by the prompt alone.

The prompt ships with the tool at `src/council/prompts/reviewer.md`; `--prompt`
names a different one. It carries the change **and the functions around it**: for
every changed Python file the enclosing function is included, then the repository
functions it calls, two levels deep. `--context-depth` is the lever on that: `0`
sends the diff alone, `1` the enclosing function, `2` one call level, `3` two (the
default). Anything the resolver could not follow is
named in the prompt rather than left out. It is deliberately **not** read from
the repository under review — otherwise the code being judged could supply a
prompt that reports nothing. Every run records a digest over the template, the
profile and the dimensions; two runs are comparable only when the digest matches.

## Container

`nix build .#image` → an OCI tarball with `council`, `git` and `bash`. It carries
the tool, not the reviewer: mount one at `/bin/hermes` or pass `--reviewer`.
Command proofs need user namespaces; a runtime that blocks them makes those
proofs `UNRUNNABLE`, never unsandboxed.

`nix build .#wheel` → `council-2.0.0-py3-none-any.whl`, with no dependencies:
`pip install` it on any host with Python 3.11+. A wheel cannot carry `bwrap`, so
`command` proofs on a bare host are `UNRUNNABLE` unless bubblewrap is installed;
the image is the artifact where the sandbox travels with the tool. Nix builds
both; a user needs neither nix nor this repository to run the wheel.

## Releasing

The version lives in `pyproject.toml`, the newest heading in `CHANGELOG.md`,
and any prose that quotes it (`Current release vX.Y.Z`, or a wheel filename).
`python tools/release.py check` asserts all three agree, that `## Unreleased`
is first, and that releases are unique, dated and descending; it is a check in
the flake. `python tools/release.py bump --version X.Y.Z` moves the Unreleased
entries under a dated heading, updates every copy, and prints the `git tag`
command rather than running it — tagging is a person's decision.

The policy, the public surface and the definitions are
[`docs/VERSIONING.md`](docs/VERSIONING.md).

## Layout

```
src/council/findings.py   Finding, State, Severity — the domain
src/council/verdict.py    judge() — the whole decision
src/council/base.py       which revision the diff is taken against
src/council/paths.py      where a run's artefacts live
src/council/schema.py     the reviewer's output contract
src/council/prompt.py     render the template, digest the instrument
src/council/changes.py    the diff parser, shared by the diff proof and context
src/council/context.py    the functions around the change, and their calls
src/council/sample.py     one sample: run, retry once, record
src/council/proofs.py     the five proof kinds
src/council/sandbox.py    bubblewrap: no network, overlay tree
src/council/claims.py     the claim registry and its runner
src/council/prompts/      the reviewer prompt, shipped with the tool
skills/council/           the agent-facing skill
fixtures/                 the six-rung corpus and the golden rounds from v1.9.0
```

## The sandbox

A `command` proof runs under `bubblewrap`: no network, a read-only root, a
private `/tmp` and `$HOME`, and a cleared environment. The repository is an
overlay — a proof may write, and the writes vanish with it. A write anywhere
else is `UNRUNNABLE`, not refuted. `[proofs] sandbox = false` opts out; without
`bwrap` on `PATH` the same proofs are `UNRUNNABLE` and never fall back to
running unsandboxed.

## Known limits

The reviewer is an external process, and its speed is not the tool's. On the
provider measured on 2026-11-09: a trivial prompt answered in 11–22 s; a 2.8 KB
review (the docs commit) completed three samples; review prompts of 5.8 KB,
31 KB and 84 KB did not return within 6–10 minutes. A sliced run makes one call
per unit, so a slow provider makes a large change slow even when every unit fits.

`--sample-timeout` (default 900 s) bounds one attempt; a sample that does not
answer is a failed sample, and a run with one is `INCOMPLETE` — never a pass.
`--time-budget` stops starting units after N seconds; the units still to come are
recorded as unreviewed (`units[].error`), and the run cannot be `PASS`.
`--context-depth` and `--samples` are the cost levers, and a narrower `--base`
is the reliable one. `council doctor` reports what this machine can do before a
review depends on it.

This is a property of the instrument, not of the verdict: the tool never trades
a missing answer for a pass.

The profile on this host sets `reasoning_effort: ultra`. The same 7,954-byte
prompt answered in 84 s (plain) and 69 s (streamed), and a two-sample `ultra`
review of an external repository reached `PASS` in 239 s with five proven
findings; earlier attempts at the same level did not answer in 90 s. Usage shows
one API call, ~4.5k reasoning tokens at `ultra` and ~5.2k at `none`, and
`finish_reason=stop` when it answers: the failures were provider stalls, not
reasoning overruns. `--reasoning` still names the instrument in `verdict.json`
and in the digest, but it is not a reliability lever.

The transport is the guard: `--stream` (the default) reads the answer as JSON
events and `--idle-timeout` (default 120 s) kills a request that goes silent, so
a stalled provider costs two minutes, not the whole sample timeout. `--no-stream`
exists for a host whose Hermes has no `stream-json`. A silent or answerless
sample is still a failed sample, and a run with one is `INCOMPLETE`, never a
pass.

## What is not here

- A browser. A DOM claim is a `command` proof: the repository runs its own
  browser test, and the tool only records whether it passed.
- Calibration: there is no score, so there is nothing to calibrate.
- A replacement for v1: 1.9.0 is untouched; this is a separate checkout.
