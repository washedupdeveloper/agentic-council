# The corpus: what a threshold needs before it can exist

A threshold is a claim that a number separates defective code from clean code. On the claims scale
the number is derived from what the reviewer *proved*, so the claim can only be checked against runs
whose ground truth is known. That set is the corpus.

## The unit

One **adjudicated run directory** — the thing the gate scores:

| file | why the derivation needs it |
|---|---|
| `<dimension>.json` × 5 | `det` and β |
| `probes.json` | what the toolchain observed, independent of the reviewer |
| `proofs.json` | which findings are `confirmed` — the claims score and the cap |
| `meta.json` | stacks, target SHA, the enforced mode |
| **label, level, repeat** | ground truth, from the manifest |

A corpus without proofs is a reviewer's opinion with a label attached, and it calibrates nothing.

## Four steps

`calibrate` is a maintainer verb: `nix develop` exposes it (the wrapper there is built
for the dev audience), and outside the devshell `REVIEW_COUNCIL_AUDIENCE=dev` does the same.

```sh
export REVIEW_COUNCIL_AUDIENCE=dev

# 1. plan the ladder. Three runs per class is the minimum the derivation accepts,
#    so a six-level plan at the default --repeats 1 has ONE clean run and refuses.
council calibrate --plan-corpus /tmp/corpus --base <repo> --levels 0,1 --repeats 3

# 2. run every rung (the expensive half). The sampler creates <runs>/<rung id>/;
#    retries cover a provider outage rather than hiding it.
council calibrate --sample-corpus /tmp/corpus/corpus.json --runs /tmp/corpus/runs --retries 3

# 3. score every rung and record what was actually proved
council calibrate --collect-corpus /tmp/corpus/corpus.json --runs /tmp/corpus/runs

# 4. derive the threshold, or refuse
council calibrate --from-runs /tmp/corpus/corpus.json
```

`review` has no `--out`; a run's directory is the rung's `id` under `--runs`, and
`--sample-corpus` is what creates it.

The generator is `build_eval_ladder`: level 0 is the base repo untouched, every higher level seeds a
known number of defects drawn deterministically from the seed. Ground truth is known by construction
rather than by inspection, and `collect` matches confirmed claims back to the seeded defects
(file, and line when the proof records a range).

`--from-runs` writes `scripts/calibration.claims.json`, not `calibration.json`: the deterministic
threshold stays where it is, and a corpus run cannot overwrite the number the other scale depends on.

## What it refuses, and why each refusal exists

| refusal | because |
|---|---|
| a rung with no scored run | a threshold fitted to whatever finished first is fitted to the schedule, not the code |
| mixed scoring scales | a claims threshold derived from `--allow-unproven` aggregates is arithmetic on two rulers |
| a bad rung the reviewer did not detect | on the claims scale an undetected defect scores **clean**. Including it teaches the threshold that a defective repo passes — and the failure is the reviewer's, not the cutoff's |
| fewer than 3 runs per class | one draw of a stochastic reviewer is a point, not a distribution. `--allow-provisional` records that you know |
| classes that do not separate | no threshold is both precise and complete; the score lacks the signal, so the next move is the scorer |

Each refusal prints what to do next. A number that cannot be defended is worse than no number,
because it looks like one.

## The hole this closes: proving nothing

Claims scoring moves only when something is proven, so a reviewer that reports nothing scores 100
on a defective repository — and nothing blocks, because there is no claim to block on. That is
`coverage_gap` in `score_reviews`: when `probes.json` records a defect and the adjudication settled
no claim at all, the run is **`unprovable`**, not clean.

Measured on a tree holding a single README: a probe flagged one defect, the reviewer wrote nothing,
and the gate returned **100.00** with certification `unprovable`. The certification was right and
the number was meaningless — it was the score of not having answered. `collect` therefore records
no score for an `unprovable` rung, and a threshold cannot be fitted to it.

`collect` also refuses a rung scored on a different scale than the corpus declares: a corpus saying
`claims` with no claims calibration on disk silently got deterministic numbers, and recorded one as
its best rung.

Without these rules the corpus measures how quiet the model is.

## Measuring reproducibility, not just detection

`council calibrate --agreement corpus.json` reports, per rung across its repeats:

* **stable / majority / one-off** locations — how many passes reported the same finding;
* **severity disagreements** — the same location labelled differently by different passes;
* **blind spots** — a seeded defect no pass reported.

Measured on the first nine-run corpus: 10 of 16 distinct locations at level 0 appeared in exactly
one pass, and one committed credential came back `critical`, `critical`, `medium`. Both are now
fixed at the source rather than averaged away — severity is a floor set by what a tool detected
(`protocol/severity.json`), and a proof about one file cannot confirm a finding about another.

Detection is counted at the **seeded line**, not the file. Path matching scored "reported an
unrelated issue in the same file" as having found the planted defect.

## When the reviewer produces nothing

A failed sample used to leave a missing file, which `collect` called "not run" — the same thing it
says for a rung nobody attempted, and silent about a provider that refused. Now:

* `sample.py` writes `sample-<n>.status.json` beside every sample: `rc`, whether the artefact
  exists, and a **reason** — `provider_refused`, `rate_limited`, `auth`, `timeout`, `connection`,
  `unparseable`, `unknown`;
* `council calibrate --sample-corpus corpus.json --runs DIR --retries 3` runs every rung, retries a
  missing or unparseable artefact, and records **every attempt** in the manifest, so
  "never attempted" and "attempted four times and refused" are different states;
* a run that wrote valid JSON and then exited nonzero keeps its sample — the artefact is the
  evidence, the exit code is not.

The provider outage that cost three samples read `HTTP 404 — no marketplace sellers meet the
minimum 89% discount`. The next corpus needed **16 attempts to produce 9 passes**: nine attempts
left no artefact, and the ones recorded name `provider_refused` rather than "not run".

## Cost

A reviewer turn measured at 5–8 minutes; five dimensions plus merge and adjudication puts a round
at 30–40 minutes serial. Twelve runs is a long afternoon; sixty is a weekend. That is the actual
price of a threshold, and why the provisional one has survived this long.

## The verdict, and why the number is not it

Twelve runs — three on a clean tree, nine on defective ones — measured both quantities:

```text
level-0 scores   78.37 · 84.20 · 88.81     spread 10.44
level-1 scores   52.49 … 68.08             spread 15.59  (6 passes, one identical tree)
level-4 scores   60.25 · 60.83 · 64.10     spread  3.85
```

Seeded-defect detection did not move: **1/1 on every level-1 pass, 4/4 on two of three level-4
passes**. What moved was the unseeded findings — 3, 3, 3, 1, 2, 4 across six passes of the same
tree — and their severities. The aggregate is therefore a measure of how much the reviewer felt
like saying, and no cutoff inside a 10-point band survives another draw.

The verdict does not depend on it. On the claims scale a run is `certified` when nothing of high or
critical severity was confirmed, nothing blocking is unsettled — and, since the shipped threshold,
its aggregate clears the claims threshold. The blocking set is what did not vary; the aggregate is
what the second corpus made fit to enforce:

```text
the shipped ladder   good 97.83 · 97.83 · 100.00   (spread 2.17)
                     bad  73.46 · 76.83 · 73.46     (spread 3.37, detected 1/1 each)
                     threshold 87.33   plateau 76.83–97.83
```

Every clean rung sits more than ten points above every defective one, and the threshold is the
midpoint of the plateau rather than a point fitted to one draw. `tests/corpus/claims-2026-11-05.json`
records the six rungs, so `council calibrate --from-runs` on it regenerates the number.

```text
  ok   level-0-run-1        good    97.83  certified
  ok   level-0-run-2        good    97.83  certified
  ok   level-0-run-3        good   100.00  certified
  ok   level-1-run-1        bad     73.46  not certified
  ok   level-1-run-2        bad     76.83  not certified
  ok   level-1-run-3        bad     73.46  not certified
  verdicts separate every rung
```

Six for six, and the check is not vacuous: relabelling a clean rung `bad` makes it exit 1 with
`verdicts WRONG for: level-0-run-1`, and dropping a rung's certification exits 1 with
`rungs with no verdict`.

The aggregate is reported and — once a claims calibration exists — enforced: clearing the blocking
set with an aggregate under the threshold is `unsatisfied`, and the gate names the number it
compared. Before this corpus the aggregate was reported and never compared, which is why the
milestone called the threshold an open parameter.

## What this does not do

`--sample-corpus` runs the reviews, and it is the expensive half: a reviewer turn measured at 5–8
minutes, so nine passes is most of an hour before any scoring happens. `--plan-corpus`,
`--collect-corpus`, `--agreement` and `--from-runs` are deterministic and cheap.