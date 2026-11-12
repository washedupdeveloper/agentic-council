# Architecture: a pure kernel in an effect shell

**Status:** accepted. This note records the design and its debts as of the
architecture pass after the state-machine milestone.

## Verdict

The concept is sound and the structure is now honest. The review's decisions —
what a run id is, what a configuration means, what a set of proof outcomes
settles, what an accepted risk means, and what a sandbox invocation looks like —
are pure functions in `council.domain` and the pure renderers beside it. The earlier purity claim was
false: `paths` was on the pure list while it called `is_symlink()` and
`exists()`, and the test only inspected a short list of call names. That test
could not fail for the defect it existed to prevent. It has been replaced with a
gate that parses the imported modules, checks method calls, checks import
direction, and fails when an effectful module is not explicitly named as an
adapter.

The implementation is not fully DDD or fully SOLID. `run.review` is still a
733-line application module that validates, prepares, samples, adjudicates and
serialises in one place; `proofs.py` executes checks in the same module that
defines proof semantics. Those are recorded below as debt, not relabelled as
architecture.

## Load-bearing claims and evidence

| Claim | What would make it true | Evidence |
|---|---|---|
| The domain kernel is pure | No kernel module imports an adapter, and none calls a known effectful method. | `tests/test_architecture.py` parses each imported module; `tests/test_domain_kernel.py` calls the decisions with literals. |
| Configuration parsing is a decision, not a file read | Text in, `Config` out; the path check lives in the adapter. | `domain.config.parse`; `council.config.load` only reads and delegates. |
| Adjudication does not execute proofs | Outcomes in, findings and verdict out; the executor is injected at the shell. | `domain.adjudication.decide`; `adjudicate.adjudicate(..., prove=...)`. |
| A caller cannot zip the wrong outcomes onto findings | A count mismatch is refused, not truncated. | `test_adjudication_refuses_a_mismatched_outcome_group`. |
| Sandbox argv construction does not look up or spawn anything | Resolved `bwrap`, repo and `PATH` are arguments. | `domain.sandbox.command`; `sandbox.argv` resolves and delegates. |
| Importing the package performs no metadata I/O | Importing `council` is clean; `council.__version__` resolves on access through `version.current_version`. | `test_the_package_import_reads_no_metadata`; `version.current_version`. |
| A new impure module cannot join silently | The gate classifies every effectful module as an adapter. | `test_every_module_that_acts_is_named_as_an_adapter`. |
| A cheap failure precedes an expensive one | Config, empty-change and prompt checks run before any context fetch; the reviewer is not called. | `test_malformed_config_is_found_before_the_reviewer`, `test_a_missing_prompt_is_found_before_a_context_fetch`, `test_an_empty_change_is_found_before_a_context_fetch`. |
| A boolean is not a quantity | `bool` is refused for samples, prompt budget, context depth, time budget and idle timeout. | `test_a_boolean_request_number_is_refused`. |
| A repository config cannot redirect through a link | A symlinked `council.toml` is refused before it is read. | `test_a_symlinked_config_is_refused`. |
| A baseline cannot suppress missing evidence | Only `PROVEN` blocking findings are suppressible; `UNRUNNABLE` and `UNSETTLED` stay open. | `test_an_unsettled_finding_cannot_be_suppressed`, `test_an_unrunnable_finding_cannot_be_suppressed`. |
| A baseline is a policy layer, not a verdict rewrite | `evidence_verdict` remains the finding-state result; `verdict` is the gate after matching. | `test_a_matching_proven_finding_is_suppressed_after_the_verdict`; `verdict.json` records both. |
| A PR cannot edit its own baseline | CI reads the baseline from the base revision and refuses a baseline changed in the diff. | `test_load_at_reads_the_base_revision_not_the_worktree`, `test_a_baseline_cannot_be_edited_by_the_diff_it_judges`. |
| A baseline expires and a severity escalation is new | Entries carry an expiry; severity is part of the fingerprint. | `test_an_expired_entry_does_not_suppress`, `test_a_severity_escalation_is_not_covered_by_an_old_baseline`. |
| A baselined finding is not an alert | SARIF receives only the unsuppressed findings; the evidence remains in `verdict.json`. | `test_a_baselined_finding_is_not_a_sarif_alert`. |

## Dependency rule

```
council.domain.*          pure: no imports from the shell
council.findings, verdict, merge, schema, prompt, changes, context, sarif
                          pure decisions and renderers
        ^
        | imports
council.adjudicate, run   application/orchestration; effects through calls
        ^
        | imports
council.repo, runner, proofs, pr, doctor, config, baseline, paths, sample, sandbox, cli,
council.version           effect adapters
```

The arrow points from the adapter to the decision. The kernel never imports an
adapter; `tests/test_architecture.py` enforces the direction.

## SOLID scorecard

| Principle | What is true | Where it is weaker |
|---|---|---|
| **S**ingle responsibility | `config` splits read (`load`) from decision (`parse`); `paths` splits name validation (`domain.run_id`) from the symlink guard; `adjudicate` splits proof execution from `decide`; `baseline` splits file/git access from the pure `domain.baseline`; `sample` splits `payload` from `write_sample`; `sandbox` splits lookup from `command`; `version` is the only metadata reader. | `run.review` still orchestrates preparation, sampling, adjudication, baseline gate, persistence and serialisation. `proofs` still owns both the six executors and their parameter rules. |
| **O**pen/closed | A proof kind is a row in `EXECUTORS` plus the schema's kind set; a new kind does not add a branch to `run`. | A new **review mode** would still touch `run.review`; there is no separate application service per mode. |
| **L**iskov substitution | `ProofOutcome` is one domain value regardless of executor; `ReviewerMissing` is both a `ReviewError` and an `OSError`, so a start failure is not retried as a sample. | No subclass hierarchy beyond this; the test is behavioural, not inheritance-shaped. |
| **I**nterface segregation | `Runner` is `Callable[[str], str]`; `Prover` is the narrow proof-executor shape; callers do not receive a repository object with unrelated methods. | The CLI parser object is a large mutable namespace; it is a boundary object, not a domain interface. |
| **D**ependency inversion | `adjudicate` accepts `prove=`; `review` accepts `runner`; the domain imports no executor. | `run` constructs `load_config`, `resolve_base`, `diff` and `fetch` directly. A full port set is not added because each has one implementation and the codebase-design rule says a second implementation is what earns the seam. |

## DDD boundaries

- **Ubiquitous language:** `GLOSSARY.md`. The code uses `Finding`, `State`,
  `Verdict`, `Sample`, `Unit` and `Run` with exactly those meanings.
- **Domain service:** `decide` and `verdict`; they take values and return values.
- **Application service:** `run.review` and `run.plan`; they coordinate the
  kernel and the adapters, and they are allowed to have effects.
- **Repositories/aggregates:** deliberately absent. A `Review` is not persisted
  as one object; its evidence is a run directory with `sample-N.json` and
  `verdict.json`. Adding an aggregate and a repository for one storage mechanism
  would be a shallow adapter, not DDD.
- **Bounded context:** one context, `council`. The CLI, reviewer transport and
  GitHub integration are adapters at its edge.

## Fail fast, in the domain

| Boundary | Invalid input | Result |
|---|---|---|
| Run id | empty, `.`/`..`, separators, reserved characters, Cc/Cf/Cs/Zl/Zp, overlong | `ValueError` from `domain.run_id.validate_run_id`, before any directory |
| Configuration | malformed TOML, unknown key, wrong type, sandbox disabled by an untrusted repo | `ConfigError` from `domain.config.parse` |
| Adjudication | a different number of outcome groups and findings | `ValueError`, not a silent `zip` |
| Review request | samples < 1, bad depth, negative budget, empty profile/base, bad run id | `ReviewError`, exit 3, no run directory |
| Proof | bad params, missing regular file, unsupported kind | `UNRUNNABLE`, never `REFUTED` and never a traceback |

The distinction is deliberate: a **start failure** is exit 3 and has no
evidence; `INCOMPLETE` is exit 2 and means the review ran with missing evidence.

## Residual architecture debt

1. **`run.py` is an application god module (733 lines).** It performs request
   validation, git preparation, prompt construction, sampling, adjudication,
   payload construction and persistence. Splitting it is a larger change than
   this pass and would risk the state-machine guarantees; the next safe cut is
   `verdict_payload()` (pure) plus a `RunStore` adapter, not a speculative port
   layer.
2. **`proofs.py` mixes execution and semantics.** The `ProofOutcome` value and
   the decision moved to the kernel; the six executors, file reads and
   subprocesses remain. They are correctly an adapter, but the module is not
   shallow.
3. **`paths.state_root` remains impure on purpose.** It performs the symlink
   guard immediately before a write. Moving that guard to a pure function would
   remove the safety property; the pure part is the run-id name check.
4. **`adjudicate`'s `prove=` default is a concrete executor.** The seam is used
   by tests and by `run`; a full dependency-inversion port would be a second
   implementation with no owner.
5. **`council.__version__` is a lazy view, not a second source of truth.**
   `council.version.current_version()` resolves the installed distribution;
   importing the package reads no metadata.
6. **`_write_verdict` constructs its payload inline.** It is an adapter concern
   today; extracting the pure payload is the easiest next SRP improvement.

## What would change the verdict

- `run.py` below ~300 lines with `validate_request`, `verdict_payload` and a
  `RunStore` adapter separated, while the existing state-machine tests stay green.
- A second real implementation of a seam (for example a non-git change source)
  would justify a port; until then, adding protocols would be indirection.
- The purity gate exercised through mutation: a deliberately inserted
  `Path.read_text()` in a kernel module must make the gate fail. See
  `tools/mutation_check.py`; the architecture mutation is part of the gate.

## Verification

```sh
nix develop -c python -m pytest -q
nix develop -c mypy src
nix flake check
./bin/council-verify --check docs/CLAIMS.md
```

The architecture gate is `tests/test_architecture.py`; the kernel decisions are
tested with literals in `tests/test_domain_kernel.py`.
