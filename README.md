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
council ci                    # the same gate for CI: verdict.json on stdout
council review --report       # advice only: always exits 0
python3 -m pytest             # the suite
./bin/council-verify          # every claim this project makes, executed
python3 tools/mutation_check.py   # prove the suite can fail
python3 tools/differential.py     # v1.9.0's verdicts beside this rule
```

`claims.toml` is the registry. Each entry is one sentence and the command that
would falsify it; the loader refuses an entry with no check, and `council-verify`
exits non-zero if any claim is false. `docs/CLAIMS.md` is generated from it
(`council-verify --write docs/CLAIMS.md`) and checked in the flake, so the page
cannot list a claim that has no check behind it.

`council ci` is `council review` for a pipeline: it always prints the verdict as
JSON and always exits with it. It deliberately does not accept `--report` — a
gate that can be told to exit 0 is not a gate.

## Flags

Every flag the tool accepts, what it changes, and why it exists. `council <command>
--help` prints the same set from the parser; a test keeps this table and the parser in step.

### `council review`

| flag | default | what it does | why |
|---|---|---|---|
| `-C, --repo PATH` | `.` | the checkout to review | a review is about a repository, not a shell's idea of a directory |
| `--base REV` | `origin/HEAD`, else `HEAD~1` | where the diff starts | a wrong base still produces a confident verdict, so the default is a chain and each step is checked |
| `--samples N` | auto | samples to ask: N, or auto — 1 clean, 2 to confirm a finding, 3 to break a tie | one sample is cheap; a second confirms a finding; a third only when the model disagrees with itself |
| `--profile NAME` | `council-generalist` | the Hermes profile asked | the instrument is a profile, not a string in the prompt |
| `--reviewer BIN` | `hermes` | the binary that answers a sample | the corpus harness needs a stub, and another host may need another binary |
| `--prompt PATH` | the shipped prompt | a different instrument | experiments must not edit the prompt the gate uses |
| `--report` | off | exit 0 whatever the verdict | advice in a hook that must not block |
| `--json` | off | print `verdict.json` | the machine-readable form, byte-identical to the artefact |
| `--run-id ID` | timestamp | name the run; refused if it exists | two runs are comparable only when they can be named |
| `--context-url URL` | none | fetch a URL as reference context (repeatable) | retrieval is context, not evidence; the caller names it, never the model |
| `-h, --help` | — | usage | — |

### `council ci`

Takes every flag in the `council review` table except `--report` and `--json`:
it prints `verdict.json` unconditionally and always exits with the verdict
(0 pass, 1 fail, 2 incomplete, 3 could not start). It exists so a pipeline names
one stable entry point instead of remembering the flags.

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

## Evidence

`verdict.json` records `base`, `head`, `worktree` (whether local edits were
included), `diff_sha256`, and `skipped` — every file in the change the diff could
not carry, with the reason (`too large`, `binary`, `not utf-8`, `unreadable`).
It also records `context_digest`, the spans the model was shown,
`unresolved` — calls the context could not follow — and `references`, the URLs
the caller asked for, with a digest each. A run states what it did not look at.

## The reviewer contract

One call, five sections (`security`, `correctness`, `readability`,
`architecture`, `performance`), one JSON object. A finding without a proof from
the closed set (`absent`, `present`, `command`, `json`, `diff`)
is refused by the parser, not by the prompt alone.

The prompt ships with the tool at `src/council/prompts/reviewer.md`; `--prompt`
names a different one. It carries the change **and the functions around it**: for
every changed Python file the enclosing function is included, then the repository
functions it calls, two levels deep. Anything the resolver could not follow is
named in the prompt rather than left out. It is deliberately **not** read from
the repository under review — otherwise the code being judged could supply a
prompt that reports nothing. Every run records a digest over the template, the
profile and the dimensions; two runs are comparable only when the digest matches.

## Container

`nix build .#image` → an OCI tarball with `council`, `git` and `bash`. It carries
the tool, not the reviewer: mount one at `/bin/hermes` or pass `--reviewer`.
Command proofs need user namespaces; a runtime that blocks them makes those
proofs `UNRUNNABLE`, never unsandboxed.

`nix build .#wheel` → `council-0.1.0-py3-none-any.whl`, with no dependencies:
`pip install` it on any host with Python 3.11+. A wheel cannot carry `bwrap`, so
`command` proofs on a bare host are `UNRUNNABLE` unless bubblewrap is installed;
the image is the artifact where the sandbox travels with the tool. Nix builds
both; a user needs neither nix nor this repository to run the wheel.

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

## What is not here

- A browser. A DOM claim is a `command` proof: the repository runs its own
  browser test, and the tool only records whether it passed.
- Calibration: there is no score, so there is nothing to calibrate.
- A replacement for v1: 1.9.0 is untouched; this is a separate checkout.