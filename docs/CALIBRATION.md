# Calibration (M8)

How the framework's free parameters are set — from evidence, not intuition. Authoritative source:
`research/deterministic-quality-tooling.md` §3 and §7.

## Why this exists

The Hill curve's `d*` and `k`, the pass threshold and the per-dimension weights `α_t` used to be
guesses baked into the source:

```python
HILL_K = 5.0          # d* — the 50-point density. Never measured.
DEFAULT_THRESHOLD = 80.0   # Never calibrated.
```

§7 says to set them from a baseline scan and record the result "so a score is always reproducible
*and* its parameters are auditable". That record is `scripts/calibration.json`.

## Two defects this fixed

**1. Counts are not densities.** §3: *"Density, not raw counts. Absolute counts punish large repos;
use severity-weighted findings per KLOC."* The scorer passed a raw count to the Hill curve, so a
100-line file with 5 findings scored identically to a 10,000-line repo with 5. The term is now
findings per KLOC.

**2. `d*` was never measured.** `HILL_K = 5.0` was a guess at the density that should score 50; it is
now derived from a known-good baseline scan.

## Method (§7)

1. **Build a graded eval ladder** — this repository at HEAD is the known-good rung (level 0); each
   higher rung seeds a known number of defects from a fixed seed, so ground truth is known *by
   construction*, not by inspection.

   ```bash
   # devshell (`nix develop`): `calibrate` is a dev verb
   council calibrate --build-eval /tmp/ladder --base .
   ```

2. **Baseline scan** each rung with the full probe set; measure findings per KLOC per tool.
3. **Derive `d*` per tool** = the density observed on the known-good rung, so known-good ≈ 50 and
   known-bad lands low. A tool that finds *nothing* on clean code has `d* = 0`, which collapses the
   curve to a step at the origin; those are floored at 0.05 and marked `floored: true`.
4. **Derive the threshold** — the max-margin separator of the labelled scores, not read off the sweep
   (below).
5. **Record everything** in `scripts/calibration.json`.

## Result

| Rung | Defects | Score |
|---|---|---|
| 0 (known-good) | 0 | **94.39** |
| 1 | 1 | 79.84 |
| 2 | 2 | 67.54 |
| 4 | 4 | 40.96 |
| 8 | 8 | 32.49 |
| 16 | 16 | 25.29 |

Monotone decreasing, clean separation.

- **Recommended threshold: 87.11** — the midpoint of the plateau `(79.84, 94.39]`, which maximises
  the margin to both classes.
- **The gate ships that value**, read from `scripts/calibration.json` (`threshold.recommended`) at
  runtime, so the recommended and enforced numbers are **one value**. They used to be three literals —
  this manifest, `score_reviews.DEFAULT_THRESHOLD`, and the loop's `--threshold` default.
- **Why the midpoint, not the floor.** `80.0` was inside the plateau but only **0.16 above the best
  *bad* rung** (79.84) — one rounding step from letting a defective sample pass. The midpoint puts
  7.27 of margin on each side.
- **`--threshold` overrides it.**
- **The fallback is still `80.0`** (`DEFAULT_THRESHOLD`), used only when the manifest is missing or
  unreadable, so an uncalibrated checkout still runs.
- **`d*` anchors on `complexity` = 1.89 findings/KLOC** — the only probe with a real (non-floored)
  known-good density on this corpus.

### The aggregate curve anchors on non-floored tools only

Most probes find nothing on clean code, so their `d*` is the floor; pooling all of them makes the
median `0.05` and drags *every* dimension to ~6/100 — a real bug found by testing. The aggregate
curve therefore uses the median of tools with a real baseline reading. Floor-bound tools still score
correctly *individually* (one leaked secret should be near-fatal); they are just a bad shared
reference.

## Choosing the threshold from labels, not the sweep

The sweep evaluates candidates only **at observed scores**, so it cannot see the interior of the gap
between the best bad and the worst good. The separating interval is `(best_bad, worst_good]`, computed
from the labels; the midpoint maximizes the margin to both classes.

Reading the plateau off the sweep instead produces an artifact: a score of 79.8399 becomes a candidate
of 79.84 and thereby lands on the "bad" side of itself, so the plateau appears only by coincidence of
rounding — and collapses to a single point whenever no observed score falls in the gap.
`choose_threshold` works from labels and returns nothing when a class has no labelled point. There is
deliberately **no sweep-based fallback**: `sweep_threshold` needs both classes too, so a manifest with
no labels yields no threshold at all. A threshold derived from a one-class sweep would be a number
with no evidence behind it.

## What is NOT calibrated

- **The threshold is a decision, not a point estimate — and the band is now derived.** It
  rests on one known-good sample, so the plateau's upper edge *is* that sample's score.
  Five well-regarded repositories were then reviewed end-to-end on the **hybrid** scale
  (`runs/clean-baseline-evaluation-2026-10-17.md`): **three pass 87.1141 unchanged**
  (treefmt-nix 98.40, clan-infra 94.83, devshell 89.23) and **two fail for verifiable
  reasons** (zero-to-nix 80.63 on 45 dependency CVEs; flake-utils 60.86 on two blocking
  findings). The classes do not separate — the best failing repo (80.63) sits 0.59 above
  the golden defects fixture (80.04), so a max-margin threshold would be 80.34 with a
  margin of 0.30, which is unusable. What *is* derivable is the **equivalence band**:
  every threshold that passes all eight samples lies in **(80.63, 89.23)**, 8.60 points
  wide — but only if those scores were exact, and four repeat runs of one clean repo
  spread **3.57 points**. See "The equivalence band — and the limit it does not cover".
- **The LLM half now has measurements, not a calibration.** Five hybrid end-to-end runs
  exist (`runs/clean-baseline-evaluation-2026-10-17.md`), each n=1 at one sample and one
  round. That is enough to place every sample in a band and to show the hybrid scale does
  not separate clean from defective code, but it is not a calibration of the reviewer's
  scores: the scores themselves could move between runs. The LLM half would need repeated
  samples per repository to estimate its variance, at roughly 18 minutes a run.
- **Weights `α_t` are still the working defaults.** §7 says reweight only with evidence.
  That evidence does not exist, and the measurement below shows it would buy little
  anyway — see "How much `α_t` could move the verdict".
- **`x_bad`/`x_good` metric curves** (coverage, mutation, max-CC) are not yet wired — the probes emit
  findings densities, not scalar metrics.
- **The probe signal's half-point is not calibrated, and differs from the scorer's.** Two curves in
  the code, same *shape*, different half-points:

  | curve | used for | half-point `d*` | exponent `n` |
  |---|---|---|---|
  | `score_reviews.hill_density` | the findings term of `det` | pooled calibrated `1.8921` | `1.2` |
  | `probes.score_from_density` | every probe's own signal | `PROBE_HALF_POINT = 5.0`, uncalibrated | `1.2` |

  Measured, the two disagree by up to **26 points** across the density range, and **19 points** on a
  probe reporting one finding per KLOC — and at β = 1 the probe signal carries weight **0.7** of the
  deterministic score. It is *self-consistent*: the threshold was derived by sweeping the real gate,
  which uses the 5.0 curve, so 87.1141 is a point on the curve the score is computed from. What is
  missing is a **derivation** for 5.0 — the calibration measures a per-tool `d*` table (11 of 12
  entries floored at 0.05, one anchored at 1.8921) and the probe path does not consult it. Unifying
  them would make every probe signal stricter and lower every score, so the shipped threshold would
  need re-deriving. That is a calibration decision, not a bug fix — recorded rather than made
  silently. `PROBE_HALF_POINT` is named so the assumption is greppable.

## How much `α_t` could move the verdict

§7 says reweight only with evidence. Before hunting for that evidence, measure the
leverage — because a weighted mean of **equal** values cannot move at all, so the spread
across dimensions is a hard ceiling on anything a reweighting can achieve.

`council calibrate --sensitivity <round-dir>` sweeps each weight from **0 to 3×** its
shipped value, redistributes the others proportionally so the total stays 1, and
recomputes the aggregate with the gate's own `renormalized_aggregate`.

| input | spread | aggregate | threshold | max move from one weight | flips |
|---|---:|---:|---:|---:|---|
| `tests/golden/rounds/defects` | 19.74 | 80.04 | 87.11 | **8.63** | **no** |
| `tests/golden/rounds/clean` | 0.00 | 100.00 | 87.11 | 0.00 | no |
| a real run (`20261015-215950/round-1`) | 10.33 | 96.42 | 87.11 | 5.07 | no |

Per dimension on the defects fixture — the worst case for any weight:

| dimension | weight | aggregate at 0 | aggregate at 3× | range |
|---|---:|---:|---:|---:|
| security | 0.30 | 82.92 | 74.29 | 8.63 |
| readability | 0.20 | 78.05 | 84.03 | 5.98 |
| architecture | 0.15 | 81.46 | 77.20 | 4.26 |
| performance | 0.10 | 78.74 | 82.64 | 3.90 |
| correctness | 0.25 | 79.43 | 81.26 | 1.83 |

**Setting security's weight to zero — deleting the dimension from the aggregate entirely
— still leaves the defects fixture at 82.92, below the 87.11 threshold.** No single
weight, at any value from 0 to 3×, changes a verdict on any input measured here.

Three consequences, stated rather than implied:

1. **Calibrating `α_t` is not currently worth doing.** On every input available, the
   verdict is weight-invariant, so a "better" weight vector would change no outcome.
   This is a measurement of *these* inputs, not a proof about all inputs — a score sitting
   near 87.11 with a large spread could still be weight-sensitive, and the tool reports
   that case (`any_verdict_flips`) rather than assuming it away.
2. **`α_t` encodes importance, not accuracy.** A weight says security matters more than
   performance; that is a cost judgement about consequences, and no amount of defect
   labelling settles it. Evidence of the kind §7 asks for would have to be *incident cost
   per dimension*, which this project does not have.
3. **The golden fixtures cannot test `α_t` on their own.** `clean` is uniform at 100, so
   it is weight-invariant by construction — a reweighting is invisible there. `defects`
   is the only fixture with spread, and it is not near the threshold. A regression that
   changed the weights *and* moved a score would be caught; a change that only altered
   the weights would not be.

## A finding that reframes the question

Three council runs had escalated against the flat threshold of 80, which motivated the calibration.
The escalation was **not** threshold-driven: the round-2 fixture scored **85.23**, comfortably above
80, and still failed — because of an **open high/critical finding**, not the aggregate. The binding
constraint is the blocking-finding gate, not the threshold; raising or lowering it would not have
changed any of those outcomes.

## The equivalence band — and the limit it does not cover

"No threshold is derivable" was the conclusion from a **gap** framing — the clean and defective
classes overlap, so no midpoint separates them. That framing is right and it answers the wrong
question. A threshold does not need a gap. It needs the set of values that yield **identical
verdicts** on every sample we have, and that set *is* derivable.

Eight samples, all measured end to end on the hybrid scale:

| class | sample | score |
|---|---|---:|
| clean | treefmt-nix | 98.40 |
| clean | clan-infra | 94.83 |
| clean | devshell | 89.23 |
| defective | zero-to-nix (45 dependency CVEs) | 80.63 |
| defective | `tests/golden/rounds/defects` (round layer) | 80.04 |
| defective | archived escalated run | 74.00 |
| defective | flake-utils (2 blocking findings) | 60.86 |
| defective | end-to-end defects fixture (`council golden --check`) | 55.16 |

The two defects fixtures are different artifacts, not a contradiction: the **round layer** pins
one round's dimension scores (80.04), while the end-to-end fixture runs the whole pipeline
(55.16). The binding floor is zero-to-nix at 80.63 either way.

If those eight numbers were exact, any threshold that fails all five defective samples and passes
all three clean ones would lie in **(80.63, 89.23)** — 8.60 points wide. Both ends are open
because the gate compares `aggregate >= threshold`: measured with the shipped gate,
`--threshold 89.23` **fails** devshell (its aggregate is 89.2299…) and `--threshold 80.62`
**passes** zero-to-nix (80.6299…).

### They are not exact, and that breaks the band

Four repeat runs of **devshell** at the same settings, same commit, same toolchain:

| run | score | security findings | security `det` |
|---|---:|---:|---:|
| original | 89.23 | 3 | 85.54 |
| 1 | 88.97 | 6 | 69.58 |
| 2 | **85.66** | 7 | 68.37 |
| 3 | 88.41 | 6 | 69.58 |

mean **88.07**, standard deviation **1.64**, range **3.57 points** — and **one of the four runs
failed the 87.1141 threshold outright** (`met_minimum: false`). Treating a normal approximation as
indicative only, 87.1141 passes a clean repository about **72%** of runs.

**Why the spread is there.** `beta` was **1.0 in all four runs**, so `score = det` — the LLM's
self-assigned score never entered. But `det` is a Hill curve over **severity-weighted findings
density**, and the findings are the reviewer's own output. So the deterministic half is a
deterministic *formula over a non-deterministic input*: "β = 1 means deterministic" is true of the
arithmetic and false of the number. The original 89.23 came from the run that reported the fewest
security findings; the three repeats reported 6–7 and scored 68–70 on that dimension.

That also means the band's **ceiling was set by the luckiest of four runs.** The band is not a
property of the threshold — it is a property of the threshold *at a given sample count*, and the
calibration runs used `--samples 1` while the shipped default is **5**.

### What follows

At one sample the noise (3.57) is comparable to the distance between the classes (5.03), so the
threshold cannot be made reliable by moving it: any value low enough to pass devshell reliably is
close enough to zero-to-nix to risk passing it. The lever is the sample count, not the threshold —
which is what the 5-sample measurement below exists to settle.

## Reproducing

```bash
# Rebuild the eval ladder (devshell — `calibrate` is a dev verb)
council calibrate --build-eval /tmp/ladder --base .

# Re-measure and re-derive (the measurement is the slow half)
council calibrate --good <known-good> --bad <known-bad> --out calibration.json
```

The ladder is measured once and then re-tuned for free:

```sh
# Measure every rung (the slow half) and keep the raw points
council calibrate --ladder /tmp/ladder/manifest.json --out calibration.json

# Re-derive d*, the sweep and the threshold from those points alone
council calibrate --recalibrate calibration.json --k 1.4 --out retuned.json
```

`--recalibrate` reads the `measured` points a calibration already recorded, so `k` and the selection
rule can be re-tuned without paying for the toolchain sweep again. A manifest with no `ladder` key is
refused by name, as is a ladder handed to `--recalibrate`.
