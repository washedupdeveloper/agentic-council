# State machines

This is the state-machine map of `council` (v2): the states the CLI and run
engine can actually occupy, the invariants that must hold in each, the
transitions between them, and the invalid states/transitions that the code can
reach. It is deliberately one file: a transition that is not here is either
impossible or undocumented.

The audit was done against commit **`e567008`**, corrected against `dda59bc`
when M25–M28 changed the proof set, the unit ladder and the verdict rule; rows
those milestones changed are marked *(M28)*. Evidence is a test path or a named code path; “live” means a real CLI
process, not a monkeypatched function.

## Method

1. Read every module that owns a transition: `cli.py`, `run.py`, `sample.py`,
   `runner.py`, `adjudicate.py`, `proofs.py`, `paths.py`, `repo.py`, `pr.py`,
   `config.py`, `doctor.py`.
2. Run the suite, then probe the CLI with valid, invalid and contradictory
   arguments (see `docs/M20.md` for the error matrix).
3. Run the concurrency and retry probes below as real subprocesses.
4. Fix confirmed bugs, add a regression test per fix, and update this file.

## Inventory

| machine | owner | persisted? |
|---|---|---|
| M1 request lifecycle | `cli.main` | no |
| M2 preparation | `run._prepare` | no |
| M3 slicing | `run._build_units` / `run.plan` | plan only in memory |
| M4 sample, retry, agreement | `sample.run_sample` / `run._samples` | `sample-N.json` |
| M5 transport | `runner.hermes_runner` / `runner._read_stream` | `failures[]` |
| M6 adjudication and verdict | `adjudicate.py` / `domain/verdict.py` | `verdict.json` |
| M7 run persistence | `run.review` / `paths.py` | `.council/runs/<id>/` |
| M8 ephemeral output and cleanup | `cli._finish_ephemeral` | temp tree / `--keep` |
| M9 proof execution | `proofs.run_proof` | `verdict.json` finding states |
| M10 pull request | `pr.resolve` / `pr.verify_checkout` | none |
| M11 init and doctor | `repo.init` / `doctor.py` | `.gitignore`; stdout |
| M12 configuration and policy | `config.load` | `council.toml` |

## M1 — Request lifecycle

**States:** `START`, `PARSED`, `REFUSED`, `BOUND` (PR only), `PLANNED`,
`REVIEWING`, `OUTPUT`, `CLEANUP`, `EXIT`.

**Invariants**

- Parse and preflight happen before a run directory or a model call.
- `--plan` writes no run and refuses `--sarif`, `--keep`, `--report`.
- Exit 3 means “nothing was reviewed”; 2 means a review ran and is incomplete.
- `--report` is advice-only and exits 0. A failed SARIF or `--json` write is
  exit 3 because the requested output was not produced; a failed `--keep` copy is
  not — the evidence is left in place, its path printed, and the run keeps the
  verdict's exit code.
- `doctor` is the only command whose failed check is exit 1 by design.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| START | argv parse | valid | PARSED | none |
| START | argv parse | usage error | EXIT 3 | usage on stderr |
| PARSED | `doctor` | — | EXIT 0/1 | checks printed |
| PARSED | `init` | — | EXIT 0/3 | `.gitignore` update |
| PARSED | plan + output flag | conflict | EXIT 3 | conflict named |
| PARSED | review/ci/pr | preflight fails | EXIT 3 | no temp, no run |
| PARSED | `pr` | preflight passes | BOUND | `gh` resolved, checkout verified |
| BOUND | review/plan | — | REVIEWING/PLANNED | base is GitHub’s |
| REVIEWING | review returns | — | OUTPUT | verdict printed/written |
| REVIEWING | start failure | — | EXIT 3 | empty run dir removed |
| OUTPUT | SARIF/JSON failure | — | EXIT 3 | nothing written |
| OUTPUT | `--keep` copy fails | — | CLEANUP → verdict exit | evidence left, path printed |
| OUTPUT | normal | — | CLEANUP → EXIT 0/1/2 | evidence kept if asked |

**Invalid transitions found**

- `--plan` silently ignored `--sarif`/`--keep`/`--report`; fixed (M20).
- `--plan` accepted an invalid `--run-id`; fixed (M20).
- `pr` resolved `gh` before validating a run id; preflight now precedes bind.
- A failed SARIF write returned 3 but leaked the ephemeral tree; fixed (M20).

**Evidence:** `tests/test_cli.py::test_plan_refuses_outputs_it_cannot_write`,
`tests/test_cli.py::test_an_invalid_run_id_is_refused_before_a_run`,
`tests/test_cli.py::test_a_json_read_failure_removes_the_ephemeral_tree`.

## M2 — Preparation

**States:** `UNPREPARED`, `CONFIG_LOADED`, `REPO_RESOLVED`, `BASE_RESOLVED`,
`HEAD_RESOLVED`, `PATCH_BUILT`, `PROMPT_BUILT`, `PREPARED`.

**Invariants**

- `base` and `head` are commit ids; `base` is resolved before the diff.
- `council.toml` is loaded and validated before base resolution, the diff, the
  prompt read and any context fetch; malformed configuration cannot pay for
  expensive work.
- A change with no reviewable text is refused before the prompt is read and
  before any context URL is fetched.
- The prompt is valid UTF-8 and contains `{{base}}` and `{{diff}}`.
- A non-UTF-8 byte in a tracked diff is replaced once, not allowed to crash the
  prompt encoder.
- The repository under review cannot supply the reviewer prompt.
- Preparation writes nothing to disk.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| UNPREPARED | `repo_root` | not a worktree | REFUSED | exit 3 |
| REPO_RESOLVED | `load_config` | malformed/unknown config | REFUSED | `ConfigError`, exit 3 |
| CONFIG_LOADED | `resolve_base` | unknown rev | REFUSED | exit 3 |
| BASE_RESOLVED | `git diff` | git error/timeout | REFUSED | exit 3 |
| PATCH_BUILT | empty patch | no skipped files | REFUSED | “change is empty” |
| PATCH_BUILT | empty patch | skipped files | REFUSED | names skipped |
| PATCH_BUILT | prompt file | missing/dir/FIFO/non-UTF-8 | REFUSED | exit 3 |
| PROMPT_BUILT | `render` | missing placeholder | REFUSED | exit 3 |
| PROMPT_BUILT | — | valid | PREPARED | prompt bytes/digest |

**Invalid transitions found**

- Unknown `--base` reached a traceback because `BaseError` was a plain
  `ValueError`; now `ReviewError`, exit 3 (`test_an_unknown_base_is_refused`).
- A directory/non-UTF-8 prompt reached a traceback; now refused
  (`test_a_prompt_directory_is_refused`, `test_a_non_utf8_prompt_is_refused`).
- A custom prompt without placeholders reached `render` as a traceback; now
  `the reviewer prompt is not usable` (`test_a_prompt_without_placeholders_is_refused`).
- An empty diff was sent to the model; now refused
  (`test_an_empty_change_is_refused`).
- Non-UTF-8 tracked content crashed `prompt.encode("utf-8")`; now sanitized
  (`test_a_tracked_file_with_invalid_utf8_is_reviewable`).
- An untracked symlink was followed outside the repository; now named and
  skipped (`test_an_untracked_symlink_is_named_not_followed`).
- A malformed `council.toml` was read after git, prompt and context work; now
  loaded first (`test_malformed_config_is_found_before_the_reviewer`). A missing
  prompt or an empty change no longer triggers a context fetch
  (`test_a_missing_prompt_is_found_before_a_context_fetch`,
  `test_an_empty_change_is_found_before_a_context_fetch`).

## M3 — Slicing and units

**States:** `UNSLICED`, `SLICED`, `UNIT_FITS`, `HUNK_FITS`, `WINDOW`,
`UNIT_TOO_LARGE`, `PLANNED`.

**Invariants**

- No unit prompt exceeds `max_prompt_bytes`; if even depth 0 does not fit, the
  unit is refused with its name and its window cost, never sent — unless
  `--window-large-files` splits the hunk into line windows (M26), of which at
  most `--max-windows` are built.
- Each unit gets the deepest context depth that fits, except a line window, which
  is always built at depth 0.
- Plan and review share `_prepare` and `_build_units`, so a plan’s byte counts
  are the bytes a review would send.
- A unit that was never asked (failure or time budget) cannot produce `PASS`.
- Units are deterministic: file order, then hunk order, then unit ids.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| UNSLICED | prompt > limit | `allow_large_prompt` false | SLICED | build units |
| UNSLICED | prompt <= limit | — | UNIT_FITS | one prompt |
| SLICED | file fits | depth 3..0 | UNIT_FITS | unit added |
| SLICED | file too large | a hunk fits | HUNK_FITS | unit per hunk |
| SLICED | hunk too large | depth 0 fits nothing | WINDOW | one unit per line window |
| SLICED | hunk too large | windows off or over `--max-windows` | UNIT_TOO_LARGE | `PromptTooLarge(windows=N)` |
| SLICED | no sections | — | REFUSED | “no reviewable file section” |

**Invalid transitions found**

- A refactor moved slicing into `_prepare`; the old `slicing-disabled` mutation
  no longer changed behaviour. Retargeted (M17).
- A change with only a mode/rename/binary section can produce no units; now a
  named refusal rather than an empty review.
- A finding reported outside its unit’s ranges is attributed to the unit that
  reported it, not to a unit whose ranges happen to contain the line: `units[]`
  counts what each unit said, and the merge keeps the finding under
  place, `(file, line)`, with the most blocking dimension any sample used
  (M29). It stays visible in `findings[]` either way.

**Evidence:** `tests/test_run.py::test_a_plan_is_one_prompt_when_it_fits`,
`test_a_plan_names_the_units_and_writes_nothing`,
`test_a_unit_that_cannot_fit_at_depth_zero_is_refused_with_its_name`.

## M4 — Samples, retries and agreement

**States per sample:** `START`, `ATTEMPT_1`, `ATTEMPT_2`, `PARSED`, `FAILED`.
**States for auto:** `AUTO_1`, `AUTO_2`, `AUTO_3`, `AGREED`, `DISAGREED`,
`UNKNOWN`.

**Invariants**

- A sample gets at most two attempts; each failed attempt is kept in
  `failures[]`.
- `ReviewerMissing` is not retried: a missing binary cannot heal.
- Auto sampling: one clean sample; two to confirm a finding; three to break a
  tie.
- `agreement` is true or false only when every sample in the set produced an
  output; if any sample is missing, it is `null`.
- A failed sample cannot produce `PASS`; on `FAIL` it is named in `reason`.
- A retry that eventually parses keeps the first failure as evidence.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| START | runner returns valid | — | PARSED | attempts = 1 |
| START | runner raises `OSError` | attempts remain | ATTEMPT_2 | failure recorded |
| START | runner raises `ReviewerMissing` | — | FAILED (fatal) | exit 3, no retry |
| START | invalid JSON | attempts remain | ATTEMPT_2 | failure recorded |
| ATTEMPT_2 | valid | — | PARSED | attempts = 2 |
| ATTEMPT_2 | invalid/OSError | — | FAILED | `output=None` |
| AUTO_1 | no findings | — | AGREED | one sample |
| AUTO_1 | findings | — | AUTO_2 | confirm |
| AUTO_2 | blocking key equal | — | AGREED | two samples |
| AUTO_2 | differs/missing | — | AUTO_3 | tie-break |
| AUTO_3 | all present, one key | — | AGREED | three samples |
| AUTO_3 | missing/varies | — | DISAGREED/UNKNOWN | `agreement` null if missing |

**Invalid transitions found**

- Auto-sampling filtered `None` keys and could report `agreement: true` with
  only one usable sample. Fixed by setting `agreement = None` if any sample
  lacks output (`test_a_failed_sample_does_not_count_as_agreement`).
- A failed sample on a `FAIL` verdict was invisible in `reason`; fixed by
  naming it there (`test_a_missing_sample_does_not_soften_a_real_failure`).
- `ReviewerMissing` was an `OSError`, so it was retried twice and became
  `INCOMPLETE`; fixed by the fatal subclass
  (`test_a_missing_reviewer_is_not_retried`).
- Non-UTF-8 reviewer output crashed the decoder; fixed by replacement and a
  failed sample (`test_a_non_utf8_answer_is_replaced_not_a_crash`).
- A stream `result` with empty text discarded earlier `text` events; fixed
  (`test_a_stream_result_with_empty_text_falls_back_to_text_events`).

## M5 — Transport

**States:** `PLAIN_START`, `STREAM_START`, `RUNNING`, `SILENT`, `DEADLINE`,
`KILLED`, `EXITED`, `ANSWER`, `EMPTY`, `MISSING`.

**Invariants**

- CLI default is streaming; `--no-stream` is the fallback.
- No event for `idle_timeout` seconds kills the **process group**, not just the
  parent (POSIX; on Windows there is no process group and the process is killed).
- A stream with no answer or a non-zero finish is an `OSError`; the sample
  retries once.
- The prompt is written to a temp file and passed with `--query-file`; no diff
  text is shell-interpreted.
- The reviewer sandbox is read-only root + private `/tmp` + overlay `$HOME`;
  writes vanish.
- A missing binary is `ReviewerMissing`; a timeout is a failed attempt.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| PLAIN_START | process exits 0 | non-empty | ANSWER | return text |
| PLAIN_START | process exits ≠0 | — | FAILED attempt | OSError |
| PLAIN_START | missing/non-executable | — | MISSING | fatal |
| STREAM_START | JSON text events | — | RUNNING | accumulate text |
| STREAM_START | result event | text non-empty | ANSWER | final wins |
| STREAM_START | result event | text empty | ANSWER | fall back to text |
| RUNNING | no event ≥ idle | — | SILENT → KILLED | OSError, retry |
| RUNNING | process exit | — | EXITED | finish |
| RUNNING | child holds pipe | parent killed | KILLED group | reader unblocked |
| RUNNING | no answer | — | EMPTY | OSError, retry |

**Invalid transitions found**

- A wrapper’s `sleep` held the pipe after the parent died; fixed by session +
  process-group kill (earlier milestone).
- Non-UTF-8 output crashed Python’s text decoder; fixed with `errors="replace"`.
- An empty `result.text` overrode usable text events; fixed.

**Residual:** `bwrap` can disappear between preflight and the first sample; the
sample then fails as `OSError` and becomes `INCOMPLETE` rather than a start
failure. The race is narrow and recorded rather than hidden.

## M6 — Adjudication and verdict

**States:** `MERGED`, `PROOF_RUNNING`, `PROVEN`, `REFUTED`, `UNRUNNABLE`,
`RESULT_PASS`, `RESULT_FAIL`, `RESULT_INCOMPLETE`.

**Invariants**

- `PROVEN` is the only state that can fail a run.
- Any proven blocking finding → `FAIL`; otherwise any open blocking finding →
  `INCOMPLETE`; otherwise `PASS`. With `--require-executed-proofs` (M28) a
  blocking finding proven only by quotation is removed from the failing set and
  named in `reason`; it cannot turn a run `PASS` into `FAIL`.
- A `FAIL` outranks missing evidence, but missing evidence is named in
  `reason`.
- A failed sample or unreviewed unit cannot produce `PASS`.
- Multiple proofs: `PROVEN` if any proved; else `UNRUNNABLE` if any could not
  run; else `REFUTED`.
- A slice unit with `ok=False` cannot have `PASS` in `units[]`; the global
  verdict may still `FAIL` on another unit.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| MERGED | proof PROVEN | blocking | RESULT_FAIL | reason cites finding |
| MERGED | proof PROVEN | non-blocking | RESULT_PASS | counts non-blocking |
| MERGED | proof REFUTED | — | continue | not an alert |
| MERGED | proof UNRUNNABLE | blocking | RESULT_INCOMPLETE | reason cites finding |
| RESULT_PASS | failed sample | — | RESULT_INCOMPLETE | sample named |
| RESULT_FAIL | failed sample | — | RESULT_FAIL | sample appended to reason |
| RESULT_PASS | unreviewed unit | sliced | RESULT_INCOMPLETE | unit named |
| RESULT_FAIL | unreviewed unit | sliced | RESULT_FAIL | unit appended to reason |

**Invalid transitions found**

- JSON Pointer `/-1` was accepted as a list index, so a proof could be
  `PROVEN` or `REFUTED` against the wrong element; now `UNRUNNABLE`
  (`test_json_pointer_rejects_a_negative_index`). `/01` likewise
  (`test_json_pointer_rejects_a_leading_zero`).
- A failed sample on a `FAIL` was not named in `reason`; fixed.
- `adjudicate` with zero proofs would say `REFUTED`; the schema requires one
  proof, so the CLI cannot reach it. An API caller can; the state is
  documented rather than silently called “clean”.

## M7 — Run persistence

**States:** `NO_RUN`, `CLAIMED`, `SAMPLES_WRITTEN`, `VERDICT_WRITTEN`,
`PARTIAL`, `EXISTS`.

**Invariants**

- One run id maps to exactly one directory.
- The directory is claimed with `mkdir(exist_ok=False)` **before** any sample or
  verdict write; two processes cannot share it.
- A start failure before any evidence removes the empty claim.
- A failure after a sample is written keeps the evidence; a partial run is
  visible rather than deleted.
- Ephemeral runs use a private temp root; `--no-ephemeral` writes under
  `.council/runs`.
- Run ids are one portable segment: no separators, `.`, `..`, control/format
  characters, Windows-reserved characters, or >128 characters.
- `.council` and `.council/runs` must be directories, not symlinks.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| NO_RUN | `_claim` | mkdir succeeds | CLAIMED | exclusive directory |
| NO_RUN | `_claim` | exists | EXISTS | exit 3 |
| CLAIMED | sample write | — | SAMPLES_WRITTEN | `sample-N.json` |
| SAMPLES_WRITTEN | verdict write | — | VERDICT_WRITTEN | `verdict.json` |
| CLAIMED | start failure | empty | NO_RUN | `_discard_empty` |
| SAMPLES_WRITTEN | later failure | non-empty | PARTIAL | evidence kept |

**Live concurrency evidence:** two real `council review --no-ephemeral
--run-id race` processes against the same repo produced **codes 3 and 0**; the
winner’s directory held exactly one `sample-1.json` and one `verdict.json`.
Before the exclusive claim, both could pass the existence check and write into
the same directory.

**Residual:** `.council`/`--sarif`/`--keep` symlink swaps between a check and
the write are TOCTOU races (a local attacker can replace a path). The
directories are exclusive and the common accidental cases are refused, but a
fully race-free implementation needs `openat`/`O_NOFOLLOW`-style primitives.

## M8 — Ephemeral output and cleanup

**States:** `TEMP_CREATED`, `RUNNING`, `VERDICT_PRINTED`, `SARIF_WRITTEN`,
`KEPT`, `REMOVED`, `EVIDENCE_LEFT`.

**Invariants**

- The verdict is printed and SARIF written before the temp tree is removed.
- `--keep` copies the run **before** removal and refuses to merge into an
  existing target or a target inside the run.
- A failed keep leaves the evidence and prints its path; it does not delete.
- A failed SARIF/JSON read cleans the tree and exits 3.
- Cleanup failure is reported, never swallowed.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| TEMP_CREATED | review returns | — | VERDICT_PRINTED | stdout/JSON |
| VERDICT_PRINTED | `--sarif` | write ok | SARIF_WRITTEN | log |
| SARIF_WRITTEN | `--keep` | target new | KEPT | copy |
| SARIF_WRITTEN | `--keep` | target exists | EVIDENCE_LEFT | warning, no delete |
| SARIF_WRITTEN | `--keep` | inside run | EVIDENCE_LEFT | warning, no delete |
| any | no keep | — | REMOVED | `rmtree` |
| any | rmtree fails | — | EVIDENCE_LEFT | path printed |

**Invalid transitions found**

- `--keep` used `copytree(dirs_exist_ok=True)` and could merge two runs into one
  evidence directory; now refuses an existing target
  (`test_keep_refuses_an_existing_target`).
- `--keep` inside the run could recurse; now refused.
- A SARIF write failure returned 3 without cleanup; now cleaned (M20).

**Residual:** a copy that fails halfway can leave a partial `--keep` target; the
source evidence remains and the error names both paths.

## M9 — Proof execution

**States:** `REQUESTED`, `VALIDATED`, `RUNNING`, `PROVEN`, `REFUTED`,
`UNRUNNABLE`, `CRASH`.

**Invariants**

- Malformed params and unknown kinds are `UNRUNNABLE`, never a crash.
- A path proof must resolve inside the repository and be a regular file.
- `command` proofs name an allowlisted executable, never a path, and run in the
  sandbox when enabled.
- `absent` does not follow symlinks.
- A proof that raises is `UNRUNNABLE`; the run continues to a verdict.
- `expected exit` is `zero` or `nonzero`; no shell is involved.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| REQUESTED | unknown kind | — | UNRUNNABLE | detail names kind |
| VALIDATED | path outside repo | — | UNRUNNABLE | no read |
| VALIDATED | path not regular | — | UNRUNNABLE | no FIFO block |
| VALIDATED | command not allowed | — | UNRUNNABLE | no exec |
| RUNNING | expected outcome | — | PROVEN/REFUTED | detail |
| RUNNING | bwrap missing | — | UNRUNNABLE | install hint |
| RUNNING | exception | — | UNRUNNABLE | “crashed” detail |

**Invalid transitions found**

- `present`/`json` on a FIFO would block forever in `read_text`; `_path_param`
  now requires a regular file (`test_present_refuses_a_fifo_without_opening_it`).
- JSON Pointer negative/leading-zero indexes resolved to real elements; fixed.
- A proof exception escaped `run_proof`; now `UNRUNNABLE`
  (`test_a_proof_that_crashes_is_unrunnable`).
- `absent` followed a symlink out of the repo; now skipped
  (`test_absent_does_not_follow_a_symlink_out_of_the_repository`).

**Residual:** a catastrophic regex in `absent` has no timeout; a huge file/JSON
is read into memory; a file can be swapped to a symlink between `lstat` and
`read`. These are bounded-input/TOCTOU risks, not silent verdict changes.

## M10 — Pull request

**States:** `NO_GH`, `RESOLVED`, `VERIFIED`, `BOUND`, `REVIEWING`, `DONE`,
`FAILED`.

**Invariants**

- `council pr` never checks anything out and never reviews local edits.
- The base is GitHub’s; `--base` is refused by the parser.
- The checkout must be exactly `headRefOid` with a clean worktree.
- A failed resolve/verify writes no run.
- The PR number, URL and both SHAs are recorded in `verdict.json`.
- `--plan` resolves and verifies but writes nothing.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| NO_GH | `gh` missing | — | FAILED | exit 3 |
| NO_GH | `gh` returns JSON | valid fields | RESOLVED | PullRequest |
| RESOLVED | HEAD ≠ headRefOid | — | FAILED | `gh pr checkout N` hint |
| RESOLVED | worktree dirty | — | FAILED | no review |
| VERIFIED | review/plan | — | BOUND/REVIEWING | base set |
| REVIEWING | verdict | — | DONE | PR identity in evidence |

**Invalid transitions found**

- `gh` had no timeout and an `OSError`/timeout could traceback; now a 30 s
  timeout and `ReviewError`.
- `gh` output invalid UTF-8 now becomes a named failure.
- `pr` preflight ran after `gh`; an invalid run id could cause a network call
  before being refused. Preflight now precedes bind.

**Residual:** verify-then-review is a check, not a lock. Another process can
modify the worktree between `verify_checkout` and `_prepare`, and the review
would include that edit. The evidence records `diff_sha256` and `worktree:
true`; a fully race-free PR review would snapshot the commit into a temporary
worktree.

## M11 — Init and doctor

**States for init:** `GITIGNORE_ABSENT`, `PRESENT`, `IGNORED`, `SYMLINK`,
`FIFO`, `DIRECTORY`, `NON_UTF8`, `WRITTEN`.
**States for doctor:** `CHECKING`, `OK`, `WARN`, `FAIL`.

**Invariants**

- `init` is idempotent and never writes through a symlink.
- A `.gitignore` that is a FIFO/device/directory/non-UTF-8 is refused, not
  opened.
- `doctor` exit 1 only for a failed check; `warn` (no bwrap) is exit 0.
- An empty profile probe is a failure, not success.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| GITIGNORE_ABSENT | init | — | WRITTEN | `.council/` |
| PRESENT | init | already ignored | IGNORED | no write |
| PRESENT | init | symlink/FIFO/dir | REFUSED | exit 3 |
| CHECKING | profile answers | non-empty | OK | detail |
| CHECKING | profile empty/raises | — | FAIL | exit 1 |

**Invalid transitions found**

- Symlink/FIFO/directory/non-UTF-8 `.gitignore` used to traceback; now
  `ReviewError` (tests in `test_repo.py`).
- Empty probe answer counted as OK; now `FAIL` (`test_a_profile_that_returns_nothing_is_a_failure`).

**Residual:** two concurrent `init` processes that both see an absent
`.gitignore` can append the line twice; the file remains valid and idempotent
afterwards. A lock would close it.

## M12 — Configuration and policy

**States:** `DEFAULT`, `LOADED`, `INVALID`.

**Invariants**

- Missing file means the default policy.
- Unknown top-level or `[proofs]` keys are errors; a typo cannot restore a
  default.
- A repository can narrow `allow`/`timeout`/`sandbox`, never widen them.
- `timeout` is a positive integer, not `true`/`1.5`; `sandbox` is a boolean.
- The path must be a regular UTF-8 file; a FIFO/directory/broken symlink or a
  symlink to an existing file is an error (a repository config may not point
  outside the checkout).

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| DEFAULT | no file | — | DEFAULT | policy |
| DEFAULT | file parses | valid keys | LOADED | narrowed policy |
| LOADED | unknown key/type | — | INVALID | `ConfigError` |
| INVALID | — | — | REFUSED | exit 3 before model |

**Invalid transitions found**

- Malformed TOML, a directory, non-UTF-8, and a FIFO used to traceback or block;
  now `ConfigError` (`test_malformed_toml_is_a_config_error`,
  `test_a_directory_is_a_config_error`, `test_a_non_utf8_config_is_a_config_error`).
- `timeout = true` was accepted as `1`; now refused.
- A broken symlink silently meant “missing”; now an error. A symlink to an
  existing file is refused too (`test_a_symlinked_config_is_refused`).

## M13 — Baseline and gate

**Owner:** `domain.baseline` decides; `council.baseline` reads/writes;
`run._prepare` loads the policy before expensive work; `run.review` applies it
after the evidence verdict.

**States:** `NO_BASELINE`, `LOADED`, `MATCHED`, `EXPIRED`, `STALE`, `GATED`.

**Invariants**

- A baseline entry exists only for a `PROVEN` blocking finding.
- `UNRUNNABLE`, `UNSETTLED`, a failed sample or an unreviewed unit can never be
  suppressed.
- `evidence_verdict` is never rewritten; the gate result is separate.
- CI reads the baseline from the base revision; a baseline changed in the
  reviewed diff is a start failure unless explicitly allowed.
- Entries carry an owner, reason and an expiry not before creation; severity and
  proof are part of the fingerprint.
- An incomplete run (failed sample or unreviewed unit) cannot create or prune a
  baseline; missing evidence is not a waiver.
- The baseline file is a regular UTF-8 file, not a symlink/FIFO, and at most
  1,000,000 bytes.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| NO_BASELINE | `--baseline` absent | — | NO_BASELINE | evidence verdict only |
| NO_BASELINE | `load`/`load_at` | regular valid file | LOADED | policy in memory |
| LOADED | one finding | fingerprint + severity match | MATCHED | suppress only if PROVEN blocking |
| LOADED | one finding | past expiry | EXPIRED | not suppressed; reported |
| LOADED | no finding | no fingerprint in run | STALE | reported; strict fails |
| LOADED | base revision | baseline path changed in diff | REFUSED | exit 3 unless allowed |
| MATCHED | all blocking proven suppressed | evidence not missing | GATED | exit 0, `evidence_verdict` retained |
| MATCHED | other proven/new finding | — | GATED | exit 1 |
| MATCHED | open finding/sample | — | GATED | exit 2 |

**Invalid transitions found**

- A PR could edit its own baseline and hide a new finding; now `ci`/`pr` read
  the base blob and a changed baseline is refused
  (`test_a_baseline_cannot_be_edited_by_the_diff_it_judges`).
- An expired entry still suppressed; now it is reported and does not suppress
  (`test_an_expired_entry_does_not_suppress`).
- A severity escalation kept the old fingerprint; severity is now part of it
  (`test_a_severity_escalation_is_not_covered_by_an_old_baseline`).
- Missing evidence could be mistaken for a baseline candidate; only `PROVEN`
  blocking findings are considered (`test_an_unsettled_finding_cannot_be_suppressed`,
  `test_an_unrunnable_finding_cannot_be_suppressed`).

## M14 — Scope and staged review

**Owner:** `domain.scope` decides from two pattern lists; `run._prepare` applies
the decision to the parsed diff before any prompt or context work.

**States:** `UNSCOPED`, `SCOPED`, `EMPTY_SCOPE`, `STAGED`, `WORKTREE`.

**Invariants**

- Scope is caller-owned: `--include` and `--exclude` are request fields; no
  repository configuration key can set it.
- `*` and `?` stay in one path segment; a `**` segment matches zero or more
  segments.
- An exclude wins over an include. An empty include list means every path.
- A pattern that is empty, absolute, backslash-separated or contains `.`, `..`
  or an empty segment is a start failure (exit 3).
- Every path removed by the scope is recorded: the first 200 are named in
  `scope_ignored` with their reason and, for an exclude, the matching pattern,
  and the rest are counted in `scope_ignored_omitted` (M28).
- A scope that removes every changed file is a start failure before the
  reviewer is called; it is never an empty PASS.
- `--staged` reads `git diff --cached` against the base. Untracked and unstaged
  edits are absent; `worktree` is false and `staged` is true.
- `pr` does not expose `--staged`; a pull request is a committed revision.
- The baseline-edit guard examines the unfiltered diff, so excluding the
  baseline path cannot hide an edit to it.

**Transitions**

| from | event | guard | to | side effect |
|---|---|---|---|---|
| UNSCOPED | no include/exclude | — | UNSCOPED | patch unchanged |
| UNSCOPED | valid patterns | every pattern valid | SCOPED | filter sections; name drops |
| UNSCOPED | invalid pattern | — | REFUSED | exit 3 after `repo_root`, before a prompt |
| STAGED | `--staged` | review/ci only | STAGED | `git diff --cached` |
| STAGED | `--staged` on pr | — | REFUSED | parser usage error, exit 3 |
| SCOPED | no kept section | included paths empty | EMPTY_SCOPE | exit 3; names ignored files |
| SCOPED | kept section | — | SCOPED | prompt built from filtered patch |
| SCOPED | baseline path changed | unfiltered diff | REFUSED | exit 3 unless allowed |

**Invalid transitions found**

- An include list with no match could have become an empty review; it is now a
  start failure (`test_a_scope_that_removes_everything_is_a_start_failure`).
- Filtering the patch before the baseline guard could have hidden an edit to the
  baseline; the guard now sees the unfiltered diff.
- A staged review that used the working-tree diff would include unstaged edits;
  the source is `git diff --cached` (`test_staged_diff_reads_only_the_index`).

## Confirmed issues, priority, grouping, status

Priority is impact × reachability. “Fixed” means a regression test is in the
tree; “residual” means the invalid state is documented and bounded, not
silently accepted.

| id | pri | invalid transition / state | impact | fix / evidence | status |
|---|---|---|---|---|---|
| SM-01 | P0 | two `--no-ephemeral` runs share one run directory | mixed samples/verdict, evidence corruption | `_claim` exclusive `mkdir`; live race 3/0; `test_a_run_id_is_never_overwritten` | fixed |
| SM-02 | P1 | `--keep` merges into an existing target | overwritten evidence, silent mix | `copytree` without `dirs_exist_ok`; `test_keep_refuses_an_existing_target` | fixed |
| SM-03 | P1 | reviewer emits non-UTF-8 bytes | traceback instead of failed sample | `errors="replace"`; `test_a_non_utf8_answer_is_replaced_not_a_crash` | fixed |
| SM-04 | P1 | JSON Pointer `/-1` or `/01` resolves an element | wrong `PROVEN`/`REFUTED` proof state | index regex; pointer tests | fixed |
| SM-05 | P2 | failed sample on `FAIL` absent from `reason` | missing evidence hidden in a failing verdict | reason suffix; `test_a_missing_sample_does_not_soften_a_real_failure` | fixed |
| SM-06 | P2 | auto-sampling `agreement: true` with a missing sample | false confidence | `agreement=None` if any output missing; `test_a_failed_sample_does_not_count_as_agreement` | fixed (prior) |
| SM-07 | P2 | stream `result.text=""` discards text events | usable answer treated as empty | fallback to text; `test_a_stream_result_with_empty_text_falls_back_to_text_events` | fixed |
| SM-08 | P2 | `present`/`json` proof on a FIFO blocks | review hangs indefinitely | `_path_param` regular-file check; FIFO test | fixed |
| SM-09 | P3 | run ids accept bidi/zero-width/line separators | spoofed path/terminal display | Unicode category check; `test_a_run_id_must_be_a_portable_segment` | fixed |
| SM-10 | P3 | start failure leaves an empty `--no-ephemeral` run dir | “no run” invariant broken | `_discard_empty`; `test_a_missing_reviewer_leaves_no_run_directory` | fixed |
| SM-11 | P3 | untracked symlink followed out of repo | secret read into prompt | `lstat` + symlink skip; repo test | fixed (prior) |
| SM-12 | P3 | proof exception escapes | traceback instead of `UNRUNNABLE` | `run_proof` catch; proof test | fixed (prior) |
| SM-13 | P3 | non-UTF-8 tracked diff crashes prompt encode | review cannot start | one replacement pass; run test | fixed (prior) |
| SM-14 | P3 | SARIF write failure leaks ephemeral tree | evidence left without cleanup | cleanup on failure; CLI test | fixed (prior) |
| SM-15 | P3 | `--plan` ignores output flags | user thinks a log was produced | conflict refusal; CLI test | fixed (prior) |
| SM-16 | P3 | `--keep` inside run recurses | runaway copy | inside-run refusal; CLI test | fixed (prior) |
| SM-17 | P4 | TOCTOU: `.council`, `--sarif`, `--keep`, untracked file swapped to symlink between check and use | writes/reads outside intended path under an active local attacker | documented in M7/M8/M9; needs `openat`/`O_NOFOLLOW` | residual |
| SM-18 | P4 | PR verify → review race: worktree changes after verify | reviewed tree is not the PR head | evidence has `worktree: true`; a commit worktree snapshot would fix | residual |
| SM-19 | P4 | sample and SARIF writes are not atomic | kill mid-write leaves partial JSON | the verdict is staged, fsynced and renamed (M28); sample and SARIF still write in place | partly fixed |
| SM-20 | P4 | partial `--keep` copy on disk-full/kill | target incomplete, source intact | error names both; no rollback | residual |
| SM-21 | P4 | concurrent `init` appends `.council/` twice | duplicate ignore line | idempotent afterwards; lock would fix | residual |
| SM-22 | P4 | catastrophic regex in `absent`; huge file/JSON | CPU/memory denial of service from model params | bounded input/timeout would fix | residual |
| SM-23 | P4 | bwrap disappears between preflight and sample | `INCOMPLETE` instead of start failure | narrow race; preflight covers the normal case | residual |
| SM-24 | P2 | malformed `council.toml` read after git, prompt and context work | every cheap failure pays for expensive work; slow start failure | config loaded first in `_prepare`; `test_malformed_config_is_found_before_the_reviewer` | fixed |
| SM-25 | P3 | boolean request number accepted as `0`/`1` | a flag silently becomes a count, budget or timeout | `_integer` rejects `bool`; `test_a_boolean_request_number_is_refused` | fixed |
| SM-26 | P2 | `council.toml` symlink to an existing file read outside the checkout | untrusted repository redirects the policy input | any symlink refused; `test_a_symlinked_config_is_refused` | fixed |
| SM-27 | P1 | a PR could edit the baseline it is judged by | new finding hidden by editing policy in the same diff | CI reads base revision; changed baseline refused; `test_a_baseline_cannot_be_edited_by_the_diff_it_judges` | fixed |
| SM-28 | P2 | baseline could suppress `UNRUNNABLE`/`UNSETTLED` evidence | missing evidence converted to a pass | only `PROVEN` blocking findings; open-evidence tests | fixed |
| SM-29 | P2 | expired baseline entry still suppressed | accepted risk outlives its stated expiry | `today > expires`; `test_an_expired_entry_does_not_suppress` | fixed |
| SM-30 | P2 | severity escalation reused an old fingerprint | high waiver hid a critical finding | severity in fingerprint; escalation test | fixed |
| SM-31 | P2 | scope dropped paths without recording them | a review could look narrower than it was | `scope_ignored` names 200 and counts the rest; `test_filter_names_every_dropped_path` | fixed |
| SM-32 | P2 | an include matching nothing could become an empty pass | a typo silently reviewed nothing | start failure before the reviewer; `test_a_scope_that_removes_everything_is_a_start_failure` | fixed |
| SM-33 | P2 | staged review could read unstaged edits | reviewed content differed from the commit under review | `git diff --cached`; `test_staged_diff_reads_only_the_index` | fixed |

## Live evidence

### Concurrency (SM-01)

Two real processes:

```
council review -C repo --base HEAD --samples 1 --reviewer slow-stub \
  --no-sandbox --no-stream --no-ephemeral --run-id race
```

Result: exit codes **3** and **0**. The loser printed
`run 'race' already exists`; the winner’s run contained exactly
`sample-1.json` and `verdict.json`, verdict `PASS`, one sample. No interleaved
evidence.

### Retry (M4)

A stub that fails its first invocation and succeeds on the second:

```
attempts=2  error=None
failures=['the reviewer could not run: flaky exited 1: first attempt failed']
verdict=pass  samples_run=1
```

A retry is recorded, not hidden; a missing binary is a different state
(`ReviewerMissing`, exit 3, no retry).

### Automated

```
nix develop -c python -m pytest -q
nix develop -c mypy src
nix develop -c pyright
nix develop -c ruff check --select F,E9 src tools tests
nix flake check
./bin/council-verify --check docs/CLAIMS.md
```

## How to keep this file current

When a transition, guard, state name or invariant changes:

1. Change the code and the regression test in the same commit.
2. Update the relevant machine’s transition table and invariant list.
3. Add or reclassify a row in the confirmed/residual table.
4. Add a claim if the behaviour is something the project promises; run
   `./bin/council-verify --write docs/CLAIMS.md`.
5. Run the gate; a state-machine change that does not update this file is
   incomplete.
