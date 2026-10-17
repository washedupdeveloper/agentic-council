# AGENTS.md

Project context for an agent working in this repository. It states the rules that are
easy to break by accident; the reasoning lives in `docs/`, linked rather than repeated.

## What this is

A Hermes-native code review system: one generalist reviewer sampled N times, a
deterministic gate that recomputes the score from the reviewer's files, and a loop that
iterates until the score clears a threshold or the run stalls. Python under `scripts/`,
Nix under `nix/`, one CLI verb per module.

## The gate

`nix flake check --keep-going` is the only gate that matters. It runs the suite, the
formatters, the linters, the toolchain smoke test, the golden suite, the command-surface
check, the version check and the container build. **All checks passed!** or it is not
done.

```bash
nix develop -c pytest tests/ -q          # the suite alone
nix develop -c ruff check scripts tests  # lint
nix develop -c mypy scripts/             # types
nix develop -c council --help            # every verb, user and dev
```

## Rules that are easy to break

**Tracked files only.** Nix cannot see an untracked file, so a new module that is not
`git add`ed is invisible to the build and the devshell breaks in a way that looks like a
code bug. Stage before you build.

**No shell scripts.** The repository ships zero `.sh` files, enforced by
`checks.no-shell-scripts`. Every operation is a Python module reached through
`council <verb>`. The one exception is the `runCommand` bodies inside `nix/`, which are
build recipes, not scripts.

**A new verb touches three places.** The module, `VERBS` in `scripts/council.py` with its
audience, and `runtimeModules` or `devModules` in `nix/builders.nix`. `checks.commands`
fails if the shipping manifest and the verb table disagree. `docs/EXTENDING.md` has the
procedure.

**User verbs ship; dev verbs do not.** The shipped tree carries only what a review runs.
A dev verb's module must not be in `runtimeModules`, and a user verb's must be. `version`
is dev, because it edits `pyproject.toml` and the shipped tree carries no build metadata.

**Prompts travel in a file, never in argv.** A reviewer prompt is ~400 KB and
`MAX_ARG_STRLEN` is 65,536 bytes. `council_loop` passes `--query-file`.

**Bundled skills are not edited here.** `skills/` in this repository is the source;
`~/.hermes/skills/` and the mirror in `hermes-skills` are generated copies. Edit the
source, then `council setup skill`.

**A review is a read.** Probing must not modify the repository under review, which is why
`_bridge` passes `--no-write-lock-file` to `nix flake` and `nix eval`.

## Versions

`docs/VERSIONING.md` is the policy and `council version check` enforces it. The deciding
question is whether an existing user must change something: yes is major, no-but-new is
minor, nothing observable is patch. Every change to a public surface writes its
`## [Unreleased]` entry **in the same commit**. A release is
`council version bump {major|minor|patch}` — never a hand edit.

## Where things are

| path | what |
|---|---|
| `scripts/` | the CLI's modules, one verb each; `_shared.py` for helpers more than one needs |
| `nix/builders.nix` | pure `pkgs -> derivation` builders, the tool lists, the VM test |
| `nix/flake-module.nix` | `perSystem` outputs: packages, apps, devShells, formatter |
| `nix/checks.nix` | this repository's gates |
| `nix/tests.nix` | the eval-tier assertions, in `lib.runTests` groups |
| `skills/` | the rubrics, and the generated council skill |
| `bots/` | the reviewer and orchestrator profiles |
| `tests/` | the suite; `tests/golden/` is fixture data that pins scores |
| `docs/` | the design, the measurements, and what they ruled out |

`tests/golden/` is data, not code: its line count is the golden suite's KLOC, so
reformatting it moves every pinned score. It is excluded from the linters for that reason.

## When a claim is uncertain

Say so. This repository prefers a stated gap to a plausible number: `docs/MILESTONES.md`
records several accepted gaps, and the unbuilt interactive metrics are unbuilt precisely
because the data does not exist. A measurement in a document names the command that
produced it, or it says it cannot be re-derived.
