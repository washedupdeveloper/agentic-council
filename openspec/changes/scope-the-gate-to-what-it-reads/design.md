# Design

## What was measured

Mutation campaign, same tree, same verdict:

| | Serial | Parallel |
|---|---:|---:|
| Wall clock | **1911 s** | **215 s** |
| Verdict | 72/72 caught, 80 claims | 72/72 caught, 80 claims |

Invalidation, before a check declared its inputs and after:

| Edit | Rebuilt before | Rebuilt after |
|---|---:|---:|
| `docs/M35.md` (history) | 11 of 12 | **5** |
| an OpenSpec spec | 11 of 12 | **5** |
| `CHANGELOG.md` | 11 of 12 | **5** |
| `README.md` | 11 of 12 | **6** |
| `src/council/claims.py` | 11 of 12 | 11 |

The survivors are honest. `tests`, `claims` and `differential` all execute the
suite, which reads the docs; `release` reads the changelog and the spec tree. A
source edit still rebuilds almost everything, and it must. What changed is that a
docs, spec or changelog edit no longer re-runs the 72-mutant campaign.

## Why scope first, and not a binary cache

Both were considered, and the order matters. A binary cache only helps once
derivations are stable across edits, which one shared input prevented: every push
produced new hashes for 11 of 12 checks, so a cache would have had nothing to
serve. Scoping is the precondition; a cache is a later multiplier on top of it.
Doing the cache first is the trap: it looks green locally and still rebuilds
everything on a clean runner.

## Why parallelism, and not test selection

The premium reviewer proposed selecting only the tests that touch a mutant's file.
That is unsound as usually implemented: a test that never executes the mutated
region cannot distinguish the mutant, but neither can a selector that guesses by
filename or `-k` pattern. The sound version needs a conservative coverage map plus
a documented full-suite fallback, which is a larger change than this one.

Parallelism has no such edge. The pool decides only *when* a mutant runs, never
*whether* or *against what*. The suite, the mutants and the pass condition are
byte-identical to the serial campaign, which is why the verdict reproduced exactly.

## What the scoping broke, and why that is the point

Scoping a check's input is the one change here that can make the gate lie. Three
failures occurred while landing it, each caught by the gate:

- `mutations` and `differential` were given `codeScope`, but they run pytest,
  which opens docs, `.github` and the spec tree. The baseline went red in the
  sandbox.
- `claims` was given a narrower scope, but `council-verify` runs the suite.
- `tests/test_build_scope.py` itself parses `flake.nix`, which was not in the
  scope it was checking, so it died with FileNotFoundError in the sandbox.

Each is the same defect: a check that reads a file it was not given. The guard
test now asserts the scope of every suite-running check, so the fourth instance
fails at review time instead of passing quietly.

## What is not claimed

No binary cache is added. It is the next multiplier and it is now worth something
because the derivations are stable, but it is a separate change with its own
evidence.
