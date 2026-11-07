---
name: council
description: Use when reviewing a change for blocking defects. Runs `council review` and reports the verdict.
---

# council

`council review` diffs the change against a base, asks a Hermes profile for
findings, and runs each finding's proof. A finding counts only once its proof
holds.

## Run

    council review                 # gate: 0 pass, 1 fail, 2 incomplete, 3 could not start
    council review --report        # advice: always exits 0
    council review --samples 3     # merged by file and line; highest severity wins
    council review --base main --json

## Read

- **FAIL** — a proven high or critical finding. Cite `id`, `location`, `claim`.
- **INCOMPLETE** — evidence missing: a sample failed, or a proof could not run
  here. Say what is missing; never report it as a pass.
- Artefacts: `.council/runs/<id>/verdict.json`, plus one `sample-<n>.json` each.

## Rules

- A finding without a proof is not a finding; do not restate one from the output.
- Do not weaken the prompt to clear a verdict; fix the code or add the proof.
- There is no score. Do not invent a threshold.
