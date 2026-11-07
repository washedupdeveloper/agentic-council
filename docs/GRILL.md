# Grill — what I would change, and what is creep

**Opinion, not claims.** Nothing here is in `claims.toml`; the measurements are
from `18b7043`: 1,572 lines of source, 1,675 of tests, 0 runtime dependencies,
193 tests, 50 claims, 18 mutations.

## Verdict

The core is sound and small: one pure `judge()`, six proof kinds asserted equal
to their executors, samples merged by place, a registry that generates its own
document, and a mutation check that proves the suite can fail. That is the part
that answers the "verified, then gotcha" cycle, and it should not be touched.

The remaining defects are seams, not logic.

## Fix

1. **Git has two owners.** `run.py:77` returns a string; `base.py:16` returns a
   `CompletedProcess`; both are called `_git`, and `_diff`, `_untracked_diff`,
   `repo_root`, `state_dir_ignored` and `init` live beside the first while
   `resolve_base` lives beside the second. A quoting or `core.quotepath` fix has
   to be made twice, and the merge-base path and the diff path can drift. One
   `repo.py`, one `_git`; `run.py` becomes orchestration.

2. **`merge` depends on the runner.** `merge(results: Sequence[SampleResult])`
   imports `sample` and `schema`. Merging is a pure function of findings; taking
   `Sequence[Sequence[Finding]]` removes two imports and lets its tests run on
   literals instead of a sample double.

3. **The prompt knows the parser's field names by import.** `prompt.py` imports
   `schema` to build the digest. That is why a field rename silently changes the
   digest — the one thing the digest exists to catch. The field list belongs to
   one constant both read, not to an import edge.

4. **The version is written five times in three files** (`pyproject.toml:7`,
   `__init__.py:9`, `flake.nix:14`, `:27`, `:52`). Same class as v1's four file
   lists. Read it from the installed metadata; let the flake read `pyproject`.

## Creep

1. **`http` proof.** It is the only kind that leaves the process for the network
   (`proofs.py:223`) — the thing the sandbox otherwise removes — and it makes the
   tool a client of arbitrary URLs. "The endpoint says X" is not evidence about a
   diff; a repo that needs it has a smoke test, which is a `command` proof. The
   same argument that removed `dom`.
2. **`init` and its nag.** 30 lines plus a note printed on every run
   (`cli.py:110`) to add one line to `.gitignore`. Write the line automatically,
   or keep the note and drop the command — not both.
3. **The corpus harness.** It earned its keep — it found the truncated answer and
   the literal newline — but it is a research instrument: it needs a live model
   and produces evidence a human reads. Keep it under `tools/`, never import it
   from `src/`, never gate on it.

## Keep

Zero runtime dependencies (stdlib + `bwrap`); `judge()` without a threshold;
`PROOF_KINDS == EXECUTORS`; a failed sample carried rather than dropped; the
claims registry; the mutation check; `docs/CLAIMS.md` generated.

## The gate had one hole — closed

`ruff` was in the dev shell and not in the gate. Twelve findings: eleven were
unused mock arguments in tests, one was real (`tools/differential.py:18`). The
gate now runs `council-lint` (`ruff check --select F,E9`), and the import is gone.

## Order

1. `repo.py` (one `_git`), 2. `merge` takes findings, 3. one prompt/schema
vocabulary, 4. one version. Then the image, then the corpus on the packed binary.