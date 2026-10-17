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

- **The threshold is provisional.** It rests on **one** known-good sample; the plateau's upper edge
  *is* that sample's score. Add more known-good repos and re-run before treating 87.11 as settled.
- **The LLM half is not calibrated.** This measures the deterministic half only; that needs labelled
  real council runs at roughly 9 minutes each.
- **Weights `α_t` are still the working defaults.** §7 says reweight only with evidence, and none
  exists yet that any dimension's findings track real defects better than another's.
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

## A finding that reframes the question

Three council runs had escalated against the flat threshold of 80, which motivated the calibration.
The escalation was **not** threshold-driven: the round-2 fixture scored **85.23**, comfortably above
80, and still failed — because of an **open high/critical finding**, not the aggregate. The binding
constraint is the blocking-finding gate, not the threshold; raising or lowering it would not have
changed any of those outcomes.

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
