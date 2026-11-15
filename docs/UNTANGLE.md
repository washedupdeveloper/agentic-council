# Untangle: decision log

**Status:** completed for the run/prompt/artefact and CLI boundaries; residual
debts are named at the end. This file records the problems found before any
edit, in the categories from `untangle-codebase`.

## Hidden links (pieces that must change together, but the code does not show it)

1. `run.py` was a 765-line god module owning request validation, git
   preparation, prompt fitting, unit slicing, sampling, run storage and the
   verdict document. The frequent co-changes of `run.py` and `cli.py` were the
   evidence. **Fixed:** `request.py`, `planning.py`, `sampling.py` and
   `runstore.py` now own those decisions; `run.py` composes them.
2. Request validation was copied in `cli._preflight`, `run.review` and
   `run._prepare`, with already-diverged messages. **Fixed:**
   `ReviewRequest.validate()` is the one pure validator; the shell keeps only
   file/output checks.
3. `.council` / `runs` names were repeated in `repo`, `paths` and `run`.
   **Fixed:** `paths` remains the single owner; `runstore` receives the
   resolved directory.
4. Severity and proof vocabularies were duplicated in `findings` / `schema` and
   `schema` / `proofs`. **Fixed:** `schema` re-exports `findings.SEVERITIES`;
   `proofs` asserts `EXECUTORS` and `PROOF_KINDS` are the same set at import.
5. `Finding.location` was a string parsed in four places. A path containing a
   colon was silently mis-split, dropping a finding from its unit. **Fixed:**
   `domain.location.Location`; `Finding.file` and `Finding.line` are structured,
   `location` is the derived wire form.
6. `_unit_verdict` reimplemented `judge` with different precedence. **Fixed:**
   `sampling.unit_verdict` calls `judge`; the unit and run use one rule.
7. `_preflight` and `_prepare` both validated scope and prompt. **Fixed:** the
   request owns pure validation; `_prepare` owns the single prompt read.
8. `_safe` was copied in `cli` and `doctor`, with different control-character
   rules elsewhere. **Fixed:** `domain.text.sanitize` and `printable`.
9. Baseline stale-entry policy was computed by both the gate and
   `baseline prune`. **Fixed:** `domain.baseline.stale_fingerprints`.

## Needless links (pieces tied together that change for different reasons)

1. `run._write_verdict` took 25 parameters, many derived from others. **Fixed:**
   `runstore.VerdictDocument` + `write_verdict`.
2. `ReviewRequest` exposed transport/storage fields beside review policy.
   **Partly fixed:** it is now its own module with `validate`; grouping into
   `Selection`/`Policy`/`Transport` remains a future cut because the CLI and
   tests pin the flat request shape.
3. `cli._baseline` read the argparse namespace directly. **Left:** it is a
   command handler, not a reusable domain operation; moving it would be a
   pass-through wrapper.
4. `cli` owned parser, policy, orchestration and rendering. **Fixed:** parser
   moved to `cli_parser`, renderer to `cli_output`.
5. Auto-sampling policy lived beside file/run-store code. **Fixed:**
   `sampling.samples`.
6. `prompt` imported `schema` only for vocabulary. **Left:** schema is the
   prompt's contract; the direction is stable and there is no cycle.
7. `tools/differential.py` inserts `src` on `sys.path`. **Left:** maintainer
   script; not a runtime module.

## Surplus (pieces with no reason of their own to change)

1. `proofs.py` said “six” kinds; there are five. **Fixed** in the docstring and
   guarded by the registry assertion.
2. `_belongs` re-derived unit attribution after the merge. **Moved** to
   `sampling.belongs`; the residual architectural debt (keep the mapping while
   collecting samples) is recorded in `ARCHITECTURE.md`.
3. `_write_sample` was a wrapper only translating errors. **Moved** to
   `runstore.write_sample`, where the run-store error boundary belongs.
4. `domain/proof.py` was a 13-line module with one caller. **Fixed:** inlined
   into `domain.adjudication`; deleted.
5. `test_http_is_not_a_proof_kind` and `test_dom_is_not_a_proof_kind` tested
   deleted kinds and could only fail if a kind were re-added. **Removed**; the
   generic unknown-kind test and the registry assertion remain.
6. `test_files.py` trailing-newline lint is cosmetic and duplicates formatter
   tooling. **Left:** it caught real packaging mistakes in this pass; removing it
   would not improve correctness.

## Special cases

1. `run.review` duplicated the sliced and unsliced pipelines; sliced runs lost
   the context digest. **Left as recorded debt:** unifying “whole change = one
   unit” changes the on-disk layout contract and needs its own compatibility
   test. The refactor removed the duplicated prompt assembly and verdict logic,
   not the layout.
2. `PromptTooLarge` names CLI flags from the application module. **Left:** the
   message is asserted by tests and is the operator's recovery path; a future
   `TooLarge(size, limit, unit)` error can carry the numbers and let the CLI add
   advice.
3. `reference.fetch` accepts `file:` URLs. **Left:** it is the caller's explicit
   context source; bounding it to a checkout is a security decision, not a
   structural cleanup.
4. `doctor.check_profile` accepts a probe timeout but cannot enforce it.
   **Left:** the runner owns the timeout; the parameter is reporting metadata.

## Tests and comments

- Added `tests/test_location.py` for colon paths and structured places.
- Expanded `tests/test_verdict.py` to the full dimension × severity × state
  matrix; the old severity-only matrix missed the dimension axis of `blocks`.
- Added the exit-code mapping test and a single-rule proof.
- Removed two unfalsifiable proof-kind tests.
- Kept the property tests over proof parameters: they exercise real coercion
  rules, even though they import private helpers; the public `run_proof` total
  property remains the outer guard.
- Comments that explain external constraints (bwrap, provider stalls, Windows
  paths, symlink guards, SIGKILL inheritance) were kept. The orphan prompt-limit
  comment and the duplicated workaround prose were removed.

## Verification

- `python -m pytest` — all tests pass.
- `mypy src` — clean.
- `./bin/council-verify` — 175/175 claims.
- `python tools/mutation_check.py` — 30/30 mutations caught; every declared
  falsifier breaks its claim.
