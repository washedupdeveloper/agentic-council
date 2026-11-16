---
name: council
description: Use when a change needs a blocking-defect verdict. Runs `council review` and reports the states behind the verdict.
---

# council

`council review` diffs a change against a base, asks a Hermes profile for
findings, executes each finding's proof, and derives the verdict from the states
those proofs reached. A finding counts only once its proof holds.

## Run

    council review                        # gate: 0 pass, 1 fail, 2 incomplete, 3 could not start
    council review --plan                 # units, bytes, rules, samples: no model call, no run
    council review --include 'src/**' --exclude 'vendor/**'
    council review --samples 3            # per unit; merged by dimension, file and line
    council review --report               # advice only: always exits 0
    council ci --sarif council.sarif      # headless: JSON, exit code, SARIF
    council pr 1234                       # base and head come from `gh pr view`
    council doctor                        # can this machine produce evidence at all?

A review is **ephemeral by default**: the run directory is removed after the
verdict. Pass `--no-ephemeral` to keep `.council/runs/<id>/`, or `--keep DIR` to
copy it before the temporary tree goes.

## Read

`verdict.json` is the evidence; read `verdict`, `exit_code` and `reason` first
and do not re-derive them from `findings`.

- `format` — a consumer must refuse a format it does not know.
- `findings[]` — `id`, `dimension`, `severity`, `state`, `proof_strength`,
  `location`, `claim`, `detail` (what the proof actually found), `proof`
  (the canonical proof that was run).
- `units[]` — one row per reviewed slice, with ranges, prompt bytes, depth,
  samples and its own verdict. A windowed file appears as several units.
- `rules[]` — the repository documents that governed this change.
- `digest`, `profile_config_sha256` — the instrument. Two runs with different
  digests are not the same evidence.
- `scope_ignored[]` and `scope_ignored_omitted` — what was **not** looked at.

## Decide

- **PASS** — no blocking finding was proven. `reason` names any proven
  non-blocking finding and any that were proven by quotation only.
- **FAIL** — a blocking finding was proven: `security` or `correctness` at any
  severity, anything else at `high` or `critical`. Cite `id`, `location` and
  `claim`; the line that held is in `detail`.
- **INCOMPLETE** — the evidence did not arrive: a sample returned nothing, a
  blocking proof is `UNRUNNABLE` here, a unit was never reached, or the reviewer
  is missing. Say what is missing. Never report it as a pass.

## Rules

- A finding without a proof is not a finding; do not restate one from the output.
- `proof_strength: static` means the proof quoted code (`present`, `absent`,
  `json`, `diff`); `executed` means it ran something (`command`, `repro`). A
  quotation proves a line exists, not that the code misbehaves — say which one
  you are relying on, and prefer `repro` for a behavioural claim.
- `--require-executed-proofs` is the strict reading when a merge turns on a
  claim about behaviour.
- Do not weaken the prompt, the budget or the proof to clear a verdict; fix the
  code, add the proof, or report `INCOMPLETE` honestly.
- There is no score. Do not invent a threshold, an average, or a percentage.
- A refusal is actionable: it names the budget, the window count, or the base
  that would let the review run. Report that, not "the tool failed".
