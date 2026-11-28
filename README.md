# council

**A review is a claim until a check settles it.**

`council` reviews a git change with a configured reviewer adapter, then requires a
proof before a finding can block a merge. It returns one of three verdicts:
**PASS**, **FAIL**, or **INCOMPLETE**. It is a review gate — not a linter, a
formatter, a test runner, or a code generator.

Every document in this repository is indexed in [`docs/README.md`](docs/README.md).

## What it is for

Use `council` when a change needs a repeatable review before it merges:

- **A local pre-merge check.** See what an independent reviewer finds before
  opening a pull request.
- **A CI gate.** Turn review evidence into a stable exit code and a SARIF log.
- **A pull-request review.** Review the exact commit GitHub says belongs to a
  PR, without checking out a branch yourself.
- **Team adoption.** Record accepted risks in a reviewed baseline instead of
  silently ignoring known findings.

It is designed around **one change at a time**: a base revision and its diff.
It is not a whole-repository audit tool, a static analyzer replacement, a
security certification, or an autopilot that edits your code.

The reviewer is a model; the proof is deterministic. A model's claim is not
accepted just because it sounds confident. If a blocking claim cannot be
settled, the result is **INCOMPLETE**, never a quiet pass.

## How the verdict works

A finding is one claim about the change. It has one of four states:

| state | meaning |
|---|---|
| `proven` | the proof ran and supported the claim. This is the only state that can block a merge. |
| `refuted` | the proof ran and the claim did not hold. |
| `unsettled` | no proof was attempted. |
| `unrunnable` | a proof was attempted but could not run here. |

The verdict is a pure function of those states:

```text
any blocking finding proven       -> FAIL        exit 1
else any blocking finding open    -> INCOMPLETE  exit 2
else                              -> PASS        exit 0
```

A **start failure** is exit `3`: no review ran, no run directory was written,
and no model call was made. A blocking finding is one with severity `high` or
`critical`, or any severity in the `security` or `correctness` dimension. A
proven `low` security finding still fails; a proven `low` readability finding
does not.

There is deliberately no score. A number cannot override missing evidence or a
proven blocking finding.

## Before you start

You need:

- **A git repository** with a base revision and a head. `council` reviews a diff,
  not a directory in isolation.
- **A configured reviewer.** The default is the `hermes` adapter with the
  `council-generalist` profile, plus provider credentials. `council agents` lists
  the adapters in this build, and `council doctor` checks whether the selected
  one can actually answer.
- **Python 3.11+** for the wheel, or a container runtime for the image.
- **`bwrap`** on Linux for sandboxed `command` and `repro` proofs. Without it
  those proofs are `UNRUNNABLE`, and a run that depends on one is
  `INCOMPLETE` — not a pass.
- **Network access** to the model provider. `--context-url` and `council pr`
  need network access too; proofs themselves run without it.
- **`gh`** only for `council pr`.

A source checkout's `nix develop` shell has the test tools, not an installed
`council`. Build the wheel or use the image for normal use; use the dev shell
for development.

## Install

### Wheel (recommended for local use and CI)

```sh
nix build .#wheel
python -m pip install result/council-2.0.0-py3-none-any.whl
council --version
```

The wheel is pure Python and has no runtime dependencies. If someone gives you
a wheel, install that file the same way; an installed wheel does not need Nix.
`nix build` is only how this repository produces the artifact.

To use the optional agent-server adapters, install the protocol extras:

```sh
pip install 'council[mcp,acp]'
```

`council-mcp` is for MCP hosts and `council-acp` is for ACP clients such as
Zed's Agent Panel. The core `council` command does not import either SDK. See
[`docs/AGENT-SERVER.md`](docs/AGENT-SERVER.md).

### Container

```sh
nix build .#image
docker load < result
docker run --rm council:2.0.0 --help
```

The image contains `council`, `git` and `bwrap`, but **not a reviewer agent**.
Mount the repository and make the selected adapter's binary and profile available
inside the container. The image is the portable way to carry the sandbox with the
tool; see [`docs/PORTABILITY.md`](docs/PORTABILITY.md) for host-specific details.

### Source checkout

```sh
nix develop -c python -m pytest -q -p no:cacheprovider
nix develop -c ./bin/council-verify
nix flake check
```

These are maintainer commands, not user installation commands.

## Your first review

Run these from the repository you want to review:

```sh
council agents
council doctor
council review --plan --base origin/main
council review --base origin/main --samples 3
```

If you plan to keep run artifacts, run `council init` once; it adds `.council/`
to the repository's `.gitignore`. Reviewing does not require it.

What each step does:

- **`council doctor`** checks `git`, the reviewer binary, `bwrap`, and whether
  the profile answers a short probe. With `--source DIR` it also compares the
  installed version with that source tree. Fix the reported prerequisite before
  spending a model call.
- **`council review --plan`** resolves the change and prints the units, prompt
  sizes, context depth and skipped files. It calls no reviewer and writes no run
  directory. Use it whenever a change is large or the base is uncertain.
- **`council review`** performs the review. `--base` is the revision to compare
  against; the default is `origin/HEAD`, then `HEAD~1`. Be explicit in scripts.
  The working tree is reviewed unless you use `--staged`.

A quick local check of only what your next commit would contain:

```sh
council review --staged --samples 3
```

`--staged` reviews the index against the base, not the working tree. Untracked
and unstaged edits are deliberately excluded.

## Reading the result

The human-readable report lists each finding, its dimension, severity, state,
and the proof that settled it. `--json` prints the complete `verdict.json`;
`--sarif PATH` also writes proven findings as SARIF 2.1.0.

| what you see | what it means | what to do |
|---|---|---|
| **PASS**, exit 0 | no proven blocking finding and no open blocking finding | merge when your other checks agree |
| **FAIL**, exit 1 | at least one blocking finding is proven | fix it, or explicitly accept it with a baseline |
| **INCOMPLETE**, exit 2 | at least one blocking finding is open, or a unit/sample was not reviewed | obtain the missing evidence; do not treat it as a pass |
| **start failure**, exit 3 | the review could not start; no model call and no run | read the one reported cause, usually a bad base, missing reviewer, or invalid path |

`verdict.json` is the durable record: the base and head, diff digest, skipped
files, context spans, unresolved calls, samples, findings, proof states, and
the verdict. It states what was **not** reviewed. A sliced run records each
unit and its own verdict; an unreviewed unit prevents `PASS`.

If you want advice without a blocking exit code, use `--report`. It always
exits 0. Do not use `--report` in a merge gate.

## Screenshots and run evidence

A screenshot is useful evidence for a person, but it is not a finding and the
reviewer never reads it. `council` stores screenshots beside a kept run and
prints a direct link:

```sh
council review --no-ephemeral --run-id before-fix --base origin/main
council evidence add before-fix .screens/zed-review.png --label "Zed review panel"
council evidence list before-fix
```

`evidence add` copies the file into:

```text
.council/runs/before-fix/artifacts/<sha256-prefix>-<name>.<ext>
.council/runs/before-fix/artifacts.json
```

The manifest records a **relative** path, the SHA-256, byte size, media type,
label and capture time. `evidence list` turns each path into a direct file link
and adds `[missing]` if the image was moved or deleted. A missing screenshot
does not change the verdict, fail the command, or make the run incomplete;
the screenshot is user evidence, not a proof the reviewer can settle.

Run `.council/` is gitignored by default. Runs kept by the ACP/MCP server live
under the per-user cache (`~/.cache/council/runs` on Linux, `%LOCALAPPDATA%` on
Windows), outside the reviewed repository. To attach a screenshot to one of
those runs, name the cache root explicitly:

```sh
council evidence add <run-id> path/to/shot.png \
  --state-root ~/.cache/council/runs --label "Zed Agent Panel"
```

`council evidence list <run-id> --json` emits the same links and metadata for a
tool. `council evidence` never sends the image to a model and never rewrites
the image bytes. If a run was ephemeral, its directory is already gone; use
`--no-ephemeral` or `--keep DIR` when the screenshots should persist.

## Common workflows

### Before a commit

```sh
council review --staged --samples 2
```

### Before pushing a branch

```sh
council review --base origin/main
```

### In CI

```sh
council ci --base "$BASE_SHA" --sarif council.sarif
```

`council ci` always prints `verdict.json` and always exits with its verdict. It
cannot be told to exit 0 with `--report`; a gate that can be disabled by a flag
is not a gate. `ci` reads a baseline from the base revision by default.

### A GitHub pull request

```sh
gh pr checkout 123
council pr 123
```

`council pr` accepts a pull-request number, URL or branch. It asks GitHub for
the PR's base and head, checks that your checkout is the head commit with a
clean worktree, and reviews that commit. It never checks out a branch and never
reviews local edits. A PR review is a review of a commit. Use
`council pr 123 --plan` to inspect the cost first.

### Only part of a change

The caller owns the scope:

```sh
council review --include 'src/**' --exclude 'src/generated/**'
council ci --include 'src/**/*.py'
```

`*` matches within one path segment, `**` recurses, and exclude wins. An include
that matches nothing is a start failure, not a silently empty review. Dropped
paths are counted and named in `verdict.json`; they do not disappear.

### A large change

Start with the free plan:

```sh
council review --plan --base origin/main
```

`council` slices by whole file, then by hunk. It refuses before sending a prompt
that is too large. The main levers are:

- `--base REV` — review a narrower change.
- `--context-depth N` — `0` diff only, `1` enclosing function, `2` one call
  level, `3` two (default). Lower depth means a smaller prompt.
- `--max-prompt-bytes N` — raise or lower the per-unit budget.
- `--window-large-files` — split one enormous hunk into line windows, each its
  own unit. This costs one sample per window; `--max-windows N` caps it at 200
  by default.
- `--samples N` — explicit sample count; `--samples auto` asks once for a clean
  unit, twice to confirm a finding, and three times to break a tie. A count of
  1 is refused unless `--allow-single-sample` is also passed.

Windows are disjoint: a defect spanning a window boundary can be missed. That
trade-off is recorded in the run rather than hidden. `council ci` never asks an
interactive question; use `--allow-large-prompt` only when you have measured the
cost and accept it.

### Accepted risks (baselines)

A baseline is a committed list of proven blocking findings a team has explicitly
accepted. It is applied after the evidence verdict and never changes a finding's
state. Missing evidence cannot be baselined.

```sh
council review --no-ephemeral --run-id before-fix
council baseline create --from .council/runs/before-fix \
  --out council-baseline.json --owner platform-team \
  --reason "legacy, tracked" --days 90
council ci --baseline council-baseline.json
```

`ci` and `pr` read the baseline from the base revision by default, so a pull
request cannot edit the baseline to hide its own new finding. A diff that edits
the baseline is refused unless `--allow-baseline-change` is explicit. The same
rule applies to the documents listed under `[[rules]]`: a diff that edits one is
refused unless `--allow-rules-change` says the maintenance is deliberate. Entries
expire; `--baseline-strict` fails on expired or stale entries, and
`council baseline prune` reports or writes a cleaned baseline.

See [`docs/BASELINE.md`](docs/BASELINE.md) for the file format and trust rules.

## Configuration

A repository may narrow what proofs are allowed to do in `council.toml` at its
root:

```toml
[proofs]
allow = ["rg", "grep", "git", "jq", "test", "stat", "python3", "nix"]
timeout = 120
sandbox = true
```

The repository's policy is a ceiling: it can remove a tool, lower the timeout, or
require the sandbox; it cannot add a tool, raise the timeout, or turn the
sandbox off. Unknown keys are refused with exit 3, so a typo cannot silently
restore a default.

A repository can also say which document governs which paths:

```toml
[[rules]]
glob = "packages/goal/**"
doc = "docs/subsystems/goal.md"
```

Each matching document is included once, capped at 20,000 bytes and marked when
truncated. A rule naming an unreadable document stops the run. The documents are
context from the repository, not instructions from the repository.

## Flags

Run `council review --help` for the authoritative help text. This is the
complete surface at a glance.

### `council review` and `council ci`

`ci` accepts these except `--plan`, `--report`, `--json` and `--autonomous`;
it always prints JSON and exits with the verdict.

| flag | default | what it does |
|---|---|---|
| `-C, --repo PATH` | `.` | repository to review |
| `--base REV` | `origin/HEAD`, then `HEAD~1` | revision to diff against |
| `--staged` | off | review the index, not the working tree |
| `--include GLOB` | all paths | keep only matching paths (repeatable) |
| `--exclude GLOB` | none | drop matching paths (repeatable; exclude wins) |
| `--samples N` | auto | samples per unit: N, or auto (1/2/3 policy) |
| `--allow-single-sample` | off | allow `--samples 1`; refused without it |
| `--agent NAME` | `hermes` | reviewer adapter; `council agents` lists the build |
| `--profile NAME` | `council-generalist` | profile for adapters that use one (Hermes) |
| `--reviewer BIN` | adapter default | executable for the selected adapter |
| `--sample-timeout N` | 900 | seconds allowed for one sample |
| `--time-budget N` | 0 (none) | stop starting units after N seconds |
| `--reasoning LEVEL` | profile's | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra` |
| `--stream` / `--no-stream` | stream | read JSON events; a silent stream is killed |
| `--idle-timeout N` | 120 | seconds of stream silence before killing |
| `--sandbox` / `--no-sandbox` | on when `bwrap` exists | run the reviewer in bubblewrap |
| `--ephemeral` / `--no-ephemeral` | ephemeral | remove the run tree, or write `.council/runs` |
| `--keep DIR` | none | copy the run to DIR before ephemeral cleanup |
| `--prompt PATH` | shipped prompt | use a different reviewer prompt |
| `--sarif PATH` | none | write proven findings as SARIF 2.1.0 |
| `--run-id ID` | timestamp | name this run; duplicate ids are refused |
| `--baseline PATH` | none | accepted-risk baseline to apply |
| `--baseline-from-base` | off for review; on for ci/pr | read the baseline from the base revision |
| `--baseline-strict` | off | fail on expired or stale baseline entries |
| `--allow-baseline-change` | off | allow the reviewed diff to edit the baseline |
| `--allow-rules-change` | off | allow the reviewed diff to edit a governing rule document |
| `--context-url URL` | none | fetch reference context (repeatable; never a proof) |
| `--context-depth N` | 3 | 0 diff, 1 enclosing function, 2 +one call level, 3 +two |
| `--max-prompt-bytes N` | 32768 | refuse a larger prompt |
| `--allow-large-prompt` | off | send an oversized prompt without asking |
| `--window-large-files` | off | split an oversized hunk into line windows |
| `--max-windows N` | 200 | refuse a change needing more than N windows |
| `--require-executed-proofs` | off | quotation-only blockers make the run incomplete, never PASS |
| `--autonomous` | off | never ask; refuse an oversized prompt with exit 3 |
| `--plan` | off | show units and prompt sizes; no model call, no run |
| `--report` | off | advice only; exit 0 whatever the verdict |
| `--json` | off | print the complete `verdict.json` |
| `-h, --help` | — | usage |

### Other commands

| command | options |
|---|---|
| `council pr TARGET` | every review option except `--base` and `--staged`, plus a PR number, URL or branch |
| `council baseline create` | `--from DIR`, `--out PATH`, `--owner NAME`, `--reason TEXT`, `--days N` |
| `council baseline prune` | `--baseline PATH`, `--from DIR`, `--write` |
| `council init` | `-C, --repo PATH` |
| `council agents` | `--json` |
| `council evidence add RUN_ID IMAGE…` | `--label TEXT`, `-C, --repo PATH`, `--state-root DIR`, `--json` |
| `council evidence list RUN_ID` | `-C, --repo PATH`, `--state-root DIR`, `--json` |
| `council doctor` | `--agent NAME`, `--profile NAME`, `--reviewer BIN`, `--probe-timeout N`, `--source DIR`, `--json` |
| `council setup skill NAME…` | `--library DIR`, `--dest DIR`, `--agent NAME`, `--list`, `--force`, `--dry-run` |
| `council --version` | print the installed version |
| `council -h` / `council --help` | command overview |

## Installing skills from a library

`council setup skill` copies skills out of a *skill library* — any directory carrying
`library/contract.json` — into a directory an agent reads. It names no agent: `--dest` is
the neutral destination, and `$SKILLS_DIR` sets it once. `--agent` is convenience only, for
the conventional location of an agent that is already installed; when that directory is not
there, the verb says so instead of creating one.

Library resolution is by structure, never by name: `--library`, else `$SKILLS_LIBRARY`, else
the nearest ancestor directory holding a contract. The same verb therefore serves Hermes, a
different agent, or a directory you keep yourself, with no second code path.

```sh
council setup skill --list
council setup skill probe --dest ~/my-agent/skills
council setup skill probe --agent claude --dry-run
```

A skill is replaced only when the copy is byte-identical (reported as `unchanged`) or when
`--force` is given; otherwise the verb refuses and leaves the directory alone.

## Troubleshooting

| symptom | likely cause | fix |
|---|---|---|
| `council: command not found` | wheel is not installed in the active environment | install it with `pip`, or use `python -m council` in that environment |
| `council doctor` reports a missing reviewer | the selected adapter's executable is not on `PATH` | install it, pass `--reviewer /path/to/binary`, or select another adapter |
| doctor's agent check fails | adapter missing, profile unconfigured, or provider unreachable | configure the selected adapter and its credentials; retry `council doctor` |
| `bwrap` warning | Linux sandbox is unavailable | install bubblewrap, use the container, or accept that `command`/`repro` proofs will be `UNRUNNABLE` |
| `INCOMPLETE` | a sample failed, a proof could not run, or a unit was not reviewed | read `verdict.json`; fix the blocker and rerun; do not treat it as PASS |
| prompt is too large | the change exceeds the per-unit budget | run `--plan`; narrow `--base`, lower `--context-depth`, raise `--max-prompt-bytes`, or use `--window-large-files` |
| review is very slow | too many units or samples, or a slow provider | reduce `--samples`/`--context-depth`, use `--time-budget`, review a narrower base, or choose `--window-large-files` deliberately |
| PR review refuses the checkout | worktree is dirty or not at the PR head | run `gh pr checkout NUMBER` and clean local edits |
| baseline entry expired | the accepted risk has outlived its date | renew it, or run `council baseline prune` and review the result |

## Safety and privacy

`council` sends the reviewed diff, selected context and any caller-supplied
`--context-url` to the configured model provider. Do not review a change
containing credentials or secrets you are not allowed to send to that provider.
Keep provider keys out of the repository and out of prompts.

Proof commands run in a bubblewrap sandbox when available: no network, a
read-only root, a private `/tmp` and an overlay of `$HOME`. Writes vanish with
the process. `--no-sandbox` opts out and should be reserved for trusted
repositories. A repository's `council.toml` can only narrow the caller's proof
policy, not widen it.

Runs are ephemeral by default. `--keep DIR` is the explicit way to retain a run;
`--no-ephemeral` writes into `.council/runs`, which is ignored by git. A review
does not modify tracked files; the only repository edit the tool makes is
`council init`, which adds `.council/` to `.gitignore`.

## Documentation

- [`docs/README.md`](docs/README.md) — index of every document.
- [`docs/COMPARISON.md`](docs/COMPARISON.md) — how this review gate differs
  from coding agents, harnesses, workspaces and dedicated PR review tools.
- [`docs/FEATURES.md`](docs/FEATURES.md) — adopted, deferred and rejected
  features from those adjacent systems.
- [`docs/AGENT-SERVER.md`](docs/AGENT-SERVER.md) — the optional ACP and MCP
  adapters for Agent Panel and MCP hosts.
- [`docs/EVIDENCE.md`](docs/EVIDENCE.md) — local screenshots, direct links and
  the sidecar manifest.
- [`docs/AGENT-ADAPTERS.md`](docs/AGENT-ADAPTERS.md) — add a reviewer agent;
  Hermes is the reference adapter.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — kernel, adapters and debt.
- [`docs/STATE-MACHINES.md`](docs/STATE-MACHINES.md) — states and invariants.
- [`docs/BASELINE.md`](docs/BASELINE.md) — accepted-risk rules.
- [`docs/SCOPE.md`](docs/SCOPE.md) — include/exclude and staged review.
- [`docs/PORTABILITY.md`](docs/PORTABILITY.md) — containers and hosts without
  NixOS.
- [`docs/VERSIONING.md`](docs/VERSIONING.md) — releases and the public surface.
- [`docs/CLAIMS.md`](docs/CLAIMS.md) — the executable claims registry.
- [`skills/council/SKILL.md`](skills/council/SKILL.md) — the agent-facing skill.

## Development

```sh
nix develop -c python -m pytest -q -p no:cacheprovider
nix develop -c ./bin/council-verify
nix develop -c python tools/mutation_check.py
nix flake check
```

The mutation campaign scores every mutant against the suite: `--only NAME` narrows it to
one, `--shard I/N` takes the I-th of N interleaved slices (CI runs eight), and `--jobs N`
says how many to score at once, where 0 means one per core. `--cache PATH` reuses verdicts
already recorded for a byte-identical tree -- the key covers `src/`, `tests/`, the clock
registry, this tool and the interpreter, so a hit is the same experiment, not a guess --
and `--no-cache` scores everything from scratch.

The full gate is `nix flake check`: tests, types, claims, mutations, the
differential corpus, and the Nix sources. A green test suite alone is not a
release.
