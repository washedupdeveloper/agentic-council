# Adjudication — the orchestrator asks for proof, and writes down what it could not settle

A finding is a claim. `protocol/proofs.json` defines what a checkable claim looks like; this is where
the orchestrator runs those checks over a round's findings and records a state for every one of them.

```bash
council adjudicate runs/<run>                      # the most recent round
council adjudicate runs/<run>/round-3 --json
council adjudicate runs/<run> --fail-on-unproven    # exit 1 if a blocking claim is unsettled
council review .                                    # enforcement is the default
council review . --allow-unproven                    # the pre-proof rule, to reproduce a score
```

## Four states, and only one of them is a pass

| state | meaning | blocks certification |
|---|---|---|
| `confirmed` | the proof reproduced **and** its control failed as required | **yes** — this is a real defect |
| `refuted` | the proof did not reproduce | no — there is nothing to answer |
| `unsettled` | no proof, an uncontrolled proof, or a control that also passed | **yes** — nobody knows |
| `unrunnable` | the check could not run here (no browser, no server, wrong params) | **yes** — nobody knows |

The asymmetry is deliberate and it is the whole point: **`refuted` is the only state that clears a
blocking finding.** A claim is treated as outstanding until its proof fails. A confirmed defect and
an unsettled claim both stop a merge, for opposite reasons, and the report says which — one is a
thing to fix, the other is a thing to settle.

A blocking finding with no structured proof lands in `unsettled`. The reviewer's
`falsifiable_check` is preserved in the record as `candidate`, because it is usually the raw material
for a proof — but prose the orchestrator cannot run is not a check.

## Two modes, and the strict one is the default

The adjudication report is always written. Whether it *decides* anything:

| mode | how you get it | gate behaviour | field |
|---|---|---|---|
| **enforcing** | the default | a blocking finding counts only if its proof was **refuted** | `enforced: true` |
| advisory | `--allow-unproven` | the pre-proof rule: the score and the raw blocking list decide | `enforced: false` |

The opt-out is named for what it does, not for what it wants: a default that requires an argument to
be strict is a default that is lax. `--allow-unproven` exists to reproduce an old score, and a run
that uses it says so in `meta.json` and in its own result.

In enforcing mode the verdict has four states, checked in this order:

| certification | meaning |
|---|---|
| `unsatisfied` | a confirmed defect, or the score is short — something to fix |
| `unprovable` | nothing proven wrong, and something blocking could not be settled |
| `uncalibrated` | nothing blocks, but the number cannot be compared to the threshold |
| `certified` | threshold met, nothing blocking, every blocking claim refuted |

`unsatisfied` and `unprovable` are different answers and both are failures to certify. They are kept
apart because the next action differs: fix a defect, versus settle a claim (add a proof, install the
tool, or waive it in writing).

## The score, and its scale

The number is no longer the reviewer's opinion of its own dimension. With adjudication in force,
each dimension is scored from the claims that were **proven** — severity-weighted density of
`confirmed` findings through the same Hill curve the deterministic half uses, then blended with the
tool signal by β as before. A dimension with nothing proven scores 100, because nothing was shown
wrong in it; `unsettled`, `refuted` and `unrunnable` claims leave the number alone (they are not
known defects — they block by their own route).

That makes the number *earned*, and it also makes it a **different scale** from the one the
repository's threshold was derived on. But a blend alone cannot carry it: on a fully-probed run
every dimension has β = 1.00, so `score = det` and the claims term is multiplied by zero. Measured
on a real round: a confirmed committed credential left security at det 71.75 under *either* scoring
mode — the reviewer's own 0.00 and the claims-derived 33.06 both landed in a term weighted zero. So
a proven defect also **caps** its dimension:

| confirmed severity | cap |
|---|---|
| `critical` | 30 |
| `high` | 60 |
| `medium` | 85 |
| `low`, `info` | none |

The same mechanism the gate already uses for an observed runtime failure, for the same reason: it
cannot be diluted by a tool that happened to be quiet. On that round the cap moved security
71.75 → 30.00 and the aggregate 89.73 → **77.21**, under the threshold — the number now fails a run
the tools alone were willing to pass.

So every result carries both the scale and the source:

| field | values |
|---|---|
| `score_source` | `claims` (adjudicated, enforcement on) or `reviewer` (no proofs, or `--allow-unproven`) |
| `calibration_scale` | the `scale` field of `scripts/calibration.json` |
| `calibrated_for_scale` | whether those two agree |

When they disagree the run is `uncalibrated`: the score is still reported, and nothing is certified.
Comparing a claims-scale number to a reviewer-scale threshold would be arithmetic on two different
rulers, and the failure would be invisible — the threshold looks the same either way. `council
calibrate` has to derive the new one; until it does, claims-scored runs say so on every report.

The mode is recorded in `meta.json` by the harness and read back by the gate and the claim ladder, so
a re-run recomputes with the same rule the run used. A report and a verdict cannot disagree about
what was enforced.

## The rule that decides what blocks

Security and correctness block at `high`; the other dimensions only at `critical`; a closed finding
never blocks. This is `score_reviews.BLOCKING_SEVERITIES`, **imported, not restated** — a second copy
would drift the first time either changed.

Two refinements came out of the twelve-run corpus:

**Blocking keeps the asserted severity.** A block that should not have been raised is visible in the
report and can be argued; a block that was never raised is invisible. So an uncorroborated claim
still blocks.

**The cap uses the corroborated severity.** A confirmed claim caps its dimension at 30/60/85 for
critical/high/medium — and an *uncorroborated* severity may not impose the hardest cap. Measured: a
formatting finding asserted `critical` and proved by a linter scored 52.49, the lowest in the corpus,
and produced a 15.59-point spread across six passes of one identical tree. Held at `high`, the same
pass scores 58.72 and the spread falls to 9.36.

Corroboration is recorded per claim: `severity_corroborated` is true when the evidence implies at
least the severity carried; `severity_scored` is what the cap uses. The asserted severity stays in
`severity` — nothing is hidden, it is just not allowed to set a ceiling on its own word.

Content rules (`protocol/severity.json` → `excerpt_matches`) apply only to proofs that **cite a
line**. Measured: `ruff format --check` echoed the secret it was reformatting, and the
`credential-literal` rule stamped a formatting finding `critical` — the rule matched the tool's
output, not the finding's subject. A citation has a subject; a command's stdout is whatever the tool
happened to print.

## What is in the report

```text
adjudication — round-7  (/repo)
  findings   : 7  (confirmed 4, refuted 0, unsettled 3, unrunnable 0)
  blocking   : 2  (confirmed 2, unsettled 0)
  enforced   : no — this report does not change the verdict
  verdict    : NOT certifiable as it stands — 2 claim(s) block it (2 confirmed, 0 unsettled):
    - [confirmed] security critical app.py:3 — proof reproduced, control failed as required —
      `gitleaks detect --no-git --source . --redact --exit-code 1` exited 1 (expected nonzero)
    - [confirmed] security high app.py:6 — proof reproduced, control failed as required —
      `bandit -r ./app.py` exited 1 (expected nonzero)
```

That is a real reviewer turn, not a fixture: the two defects it found were proven by running the
analyzer the toolchain pins, with a control that failed as required. The three `unsettled` findings
are the info/low ones where it offered prose and no proof — reported, not blocking.

`proofs.json` is written beside the round, is deterministic (no clock, sorted by source then id), and
is excluded from the reviewer files it reads — an adjudication that re-adjudicated its own output
would grow without ever changing.