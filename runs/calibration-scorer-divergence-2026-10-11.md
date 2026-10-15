# The calibration scores a different function than the gate enforces

**Found** 2026-10-11, while re-deriving the threshold after the β fix (M8, priority 4).
**Status** Open. Needs a decision, not a patch.
**Evidence** `scripts/calibrate.py` vs `scripts/score_reviews.py`; re-derivation below.

---

## What was found

There are **two independent implementations of the score**.

| | Function | Maths |
|---|---|---|
| Calibration | `calibrate.score_from_densities` | geometric mean of per-tool `hill(d_t, d*_t)` — each tool against **its own** d* |
| Gate | `score_reviews.deterministic_score` | `geomean( geomean(probe signals)^0.7 , hill_density(pooled d*, findings)^0.3 )` |

They differ in three ways, not one:

1. **Per-tool vs pooled d\*.** The calibration scores each tool against its own anchor.
   The gate pools d* (the median of the tools with a real baseline reading) and applies
   that single curve to the findings density.
2. **A 0.7/0.3 blend the calibration does not have.** The gate weights probe signals at
   0.7 and the density term at 0.3. The calibration's geometric mean is unweighted.
3. **Different inputs.** The gate's density term comes from the **reviewer's**
   severity-weighted findings. The calibration's comes from the **probes'** findings —
   it has no reviewer, by design, because it must not need an LLM.

The shipped threshold is derived from the first function and enforced against the second.
**A threshold derived on one function and enforced on another is not a calibration.** It is
a number that happens to sit between two classes.

## The numbers

Re-deriving the threshold from the *same recorded measurements* in `calibration.json`,
but scoring each rung with the gate's maths:

| Rung (defects seeded) | old score | gate maths | delta |
|---:|---:|---:|---:|
| 0 (clean) | 94.3873 | **76.5580** | −17.83 |
| 1 | 79.8409 | **74.3102** | −5.53 |
| 2 | 67.5426 | 72.2082 | +4.67 |
| 4 | 40.9639 | 62.0444 | +21.08 |
| 8 | 32.4895 | 53.6068 | +21.12 |
| 16 | 25.2894 | 42.9406 | +17.65 |

| | old | gate maths |
|---|---|---|
| plateau | [79.8409, 94.3873] | [74.3102, 76.5580] |
| margin | **7.2732** | **1.1239** |
| recommended threshold | **87.1141** | **75.4341** |
| at the upper edge | tp=5, fp=0, J=1.000 | tp=5, **fp=1**, J=0.000 |

Two things follow, and the second is the more serious.

- **The shipped threshold is ~12 points above where the gate's own maths would put it**, so
  on the ladder the gate is stricter than it was calibrated to be.
- **The separation nearly disappears.** Under the gate's maths the clean baseline (76.56)
  and the one-defect rung (74.31) are 2.2 points apart, and the upper plateau edge fails
  the clean rung outright. The old scorer's clean 7.27-point margin was a property of *that
  scorer*, not of the ladder.

## Why this is not a patch

The unification itself is unambiguous — one implementation of the score, the gate's. But
making it *faithful* needs a decision I should not take alone:

**How should the gate's single pooled density be formed from the probes' findings?**

The gate sums a reviewer's severity-weighted open findings into one number and divides by
KLOC. The calibration records only per-tool **densities** (`findings / kloc`), not the
findings themselves — so the severities are gone. The re-derivation above pooled by summing
the per-tool densities, which is a **choice I made**, and it materially moves the result:
`complexity` reports many low-value items on clean code, so it dominates a plain sum.

A faithful re-derivation needs the probe findings' severities, which `measured` does not
store — so it means re-running the ladder (a toolchain sweep, minutes, not seconds).

And the outcome is a **product decision**: 87.1141 → 75.4341 makes the gate materially
weaker, and the margin collapse may mean the gate's pooled density term is itself the wrong
shape rather than the threshold being wrong.

## Candidate resolutions

1. **Unify on the gate's function and re-pin.** `calibrate.py` calls
   `score_reviews.deterministic_score`; the ladder is re-run so severities are recorded; the
   threshold is re-derived. Accepts a much narrower margin, or exposes that the gate's
   pooled density term needs rethinking.
2. **Unify on the calibration's function.** The gate adopts the calibration's per-tool
   geometric mean as its deterministic term. Cleaner maths (per-tool anchors are defensible;
   a pooled anchor mixes unrelated tools), but it changes the gate's published score model
   and invalidates every archived score in `runs/`.
3. **Split them honestly.** Keep the probe-only calibration as the *tool* calibration it
   actually is, stop calling its output "the threshold", and derive the pass threshold from
   labelled **real council runs** — which is what the manifest's own caveat already says is
   missing, and which needs the ~9-minute-per-run labelled set M8 lists as unbuilt.

## Related

The β fix (same session) closed a hole where β = 0 made the score the LLM's own judgement.
This finding is the same shape one layer up: **a number derived from one model, enforced
against another.** Both were invisible because nothing compared the two.

The golden suite (`scripts/golden.py`) pins the *gate's* function, so it would have caught a
drift *inside* the gate. It cannot see this, because `calibrate.py` is not on the gate's
path. Whatever resolution is chosen should extend the golden suite to cover it.
