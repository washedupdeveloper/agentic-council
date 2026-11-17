# Untangle, second pass

**Status:** the four structural findings are closed for the diff parser and the run
ledger; the kernel boundary and the pure ladder are named as the remaining two,
with the reason each was not done in this pass. Comments were ruled on one by one;
tests were audited for tests that cannot fail.

The first pass (`UNTANGLE.md`) is the record of the run/prompt/artefact split. This
one starts from a fresh inventory and does not re-open what that pass settled.

## Inventory

| measure | value |
|---|---|
| tracked files | 181 |
| modules under `src/council` | 44 |
| largest modules | `cli` 484, `proofs` 372, `planning` 361, `domain/baseline` 313, `run` 292 |
| hottest files by commit count | `claims.toml` 54, `README.md` 51, `docs/CLAIMS.md` 48, `run.py` 35, `cli.py` 33, `proofs.py` 17 |
| dead definitions (named once in the whole repository) | 0 |
| dead modules (nothing imports) | 0 |
| test functions | 523 |

## Hidden links

1. **The diff grammar had five parsers.** `changes.py:68`, `:147`, `:169` each
   carried an `@@` regex; the `a/`/`b/` prefix was stripped at `:59`, `:66`, `:83`,
   `:87` and `:92`; the counter walk existed twice. A header edge case had to be
   fixed five times, and a window's line numbers came from re-parsing text the
   module had just written. **Fixed:** one `Hunk` parse with `text`, `new_range`
   and `slice()`; `change_lines` walks the same bodies; `hunk_range`, `hunk_parts`,
   `hunk_sections` and `slice_hunk` are deleted. The header line is kept verbatim
   because git appends the enclosing scope to it.
2. **"Missing evidence outranks PASS" existed three times**: `domain/adjudication.py:95`,
   `run.py:209` and `sampling.py:22`, each with its own wording. **Fixed:** `_masked`
   in `domain.adjudication` holds the rule; `verdict()` and the new
   `missing_evidence()` both call it.
3. **The verdict's unit row was built in the orchestrator.** `run.py:236` assembled
   a 19-key literal while `runstore.py:1` says the document shape is decided there.
   **Fixed:** `runstore.unit_payload`, tested against the key set.
4. **`runs` was a 5-tuple read by position.** `run[2]`, `run[4]`,
   `for unit, _, _, _, ok in runs`. **Fixed:** `runstore.UnitRun`.

## Needless links

5. **`Prepared` is a 19-field bag unpacked into 12 locals** (`planning.py:99`,
   `run.py:123`). **Left:** the locals are used once each in a 90-line function; a
   split into `Change`/`Instrument` would move the same fields behind three names
   and touch every caller. Recorded, not fixed.
6. **The kernel boundary was a list in a test, not a package.** `PURE` named
   `verdict`, `findings`, `merge`, `schema`, `prompt`, `changes`, `context`,
   `sarif` and `vocabulary` at top level while `domain/` held the rest, and
   `domain/adjudication.py:16` imported `..verdict` — the kernel reaching itself
   through the shell namespace. **Fixed in the next pass:** the nine modules moved
   into `domain/`, `PURE` is now the package, and a new test refuses a module that
   is neither kernel nor named adapter. The move cost 76 rewritten import lines, one
   `from . import findings, verdict` in `council/__init__.py` that no `from .name`
   rule matched, and six mutation anchors — which is exactly why the gate exists.
7. **`planning` is an adapter that claimed to be pure.** Its docstring said "pure
   decisions except for the injected file reader", but `build_units` builds the
   reader itself (`:153`), so the ladder cannot be tested without a checkout.
   **Docstring fixed; the split is left.** `domain/units.py` (sections + `read` +
   paths in, units out) is the move, and it should follow the kernel move so one
   commit touches the import surface once.

## Surplus

8. **`doctor._safe` was a second copy of `cli_output.safe`**, both `return
   sanitize(text)`. **Fixed:** inlined to `sanitize`.
9. **`domain/__init__.py` listed every adapter by name** — 17 of the 25 in
   `test_architecture.ADAPTERS`, already stale, in a docstring. **Fixed:** it points
   at the test that decides.
10. **`merge.py` still asserted the retracted laundering claim** (`M29.md` says a
    single relabel cannot flip the verdict: `high` blocks on severity, `low`
    `correctness` blocks on dimension). **Fixed:** the docstring states the real
    cost — one defect splitting into two rows.

## Special cases

11. **`cli._review` is a state machine over `argparse.Namespace`** — eight
    attributes mutated across a retry loop. **Left:** the behaviour is documented,
    tested, and each branch is a decision the user made. A refactor here is taste,
    not leverage.
12. **`adjudicate.py` is 25 lines whose only job is to keep `domain` from importing
    `proofs`.** It fails the deletion test and passes the dependency rule. Kept,
    and named as the seam in its docstring.

## Comments and tests

Comments were ruled on one by one. Four docstrings were rewritten because they
claimed something the code did not do; a stale adapter list and a repeated
exit-code note were removed; `doctor._safe`, a second copy of `cli_output.safe`,
was inlined. Everything else stayed, and earned it: the measured provider limit,
the bwrap overlay, the surrogateescape path rule, the indentation rule in
`present`, the CI trust boundary in `baseline.load_at`, the `@@` header scope.

Tests: 523 functions, one with no assertion (`test_pr`), six importing a private
name. The assertion-free test now proves both git calls happened. The `_claim` unit
test was deleted because `test_a_run_id_is_never_overwritten` proves the same claim
end to end — and the claim registry caught the deletion, because its check named
the removed node. A test that looks redundant may be the only evidence a claim
has; check the registry before deleting one, and re-point the claim when the proof
is stronger elsewhere. The remaining private imports are accepted with a reason:
`test_proof_params` exercises coercion rules that `run_proof` only reports as
`UNRUNNABLE`, and `_request` is the function under test in the two CLI-wiring
cases.

## Verification

- suite green; `mypy` 44 files clean; `pyright` 0; `ruff` F,E9 clean
- every claim holds, and every declared falsifier still breaks its claim
- `nix flake check` green
