# Ablation — 10-defect injected corpus (M8.5, first run)

The first execution of the pre-registered ablation. Four arms, one corpus, one commit.

| | |
|---|---|
| Corpus | `corpus-injected` — a clean HEAD of the reference corpus + 10 injected defects |
| Revision | `6e3309b2510045b4ec73e6b95f2f8fc4e1476bcf` |
| Corpus sha256 | `6fa5d82a42c26c0a94619fa7d152bf08a4e8e666204381524afb705473e4ef97` |
| Integrity during run | **unchanged** (verified before and after) |
| Defects | 10 — 4 security, 2 correctness, 2 performance, 2 readability |
| Mode | `whole-repo`, advisory (no arm may edit) |
| Duration | 2143 s (≈36 min) |
| Run dir | `~/example-corpus/run-clean` |

## Result

| Arm | Turns | Distinct findings | True defects found | Recall | Findings not matching a defect |
|---|---:|---:|---:|---:|---:|
| `single` | 1 | 8 | 8 / 10 | 0.80 | 0 |
| `generalist-rubrics` | 5 | 42 | **10 / 10** | 1.00 | 1 |
| `generalist-bare` | 5 | 35 | 8 / 10 | 0.80 | 0 |
| `specialists` | 5 | 22 | **10 / 10** | 1.00 | 2 |

Missed by `single`: `COR-2` (/mnt no longer pruned from the locate index), `PERF-1` (dev-only
tools in `systemPackages`).
Missed by `generalist-bare`: `SEC-3` (`execWheelOnly` forced off), `PERF-1`.

**The rule says: COLLAPSE to one reviewer — 10 vs 10 true, ratio 1.00×, needs ≥1.5×.**

## That verdict is forced by the corpus, not earned by the measurement

Both equal-cost arms found **every defect**, so the ratio is pinned at 1.00 no matter how the
specialists perform. A 1.5× rule on a corpus with N defects requires the expensive arm to find more
than 1.5N; with N=10 and a cheap arm already at 10, it requires 15 — which does not exist. The
corpus decides this verdict, and it says nothing about whether five specialists are worth their cost.

The cause is difficulty, not size. Every defect in this corpus contradicts a comment beside it, so
it is findable by reading one file carefully. `single` found 8 of 10 in a **single turn**, which
leaves the 5-turn arms almost nothing to win.

## What the run does establish

- **The rubric does work, at sample count 5.** `generalist-bare` (no rubric, 5 samples) found 8/10 —
  the same as `single` (rubric, 1 sample). `generalist-rubrics` (rubric, 5 samples) found 10/10. So
  five samples without the rubric bought nothing over one sample with it, while five samples with it
  closed the corpus. The 811 lines of rubric are not decorative.
- **Finding count is not a proxy for coverage.** `generalist-rubrics` emitted 42 findings to cover 10
  defects; `specialists` emitted 22 for the same 10. The specialists were roughly twice as economical
  per defect. Neither number reflects precision, because of the limitation below.
- **The pipeline is reproducible.** Corpus hash unchanged across the run; every arm produced
  parseable output; no arm failed to write its file.

## A limitation in the precision number — read before quoting it

The "findings not matching a defect" column counts a finding as true whenever its path matches a
defect's path and its line falls within 3 lines of it. On a corpus whose defects sit in only two
files, many findings land near a defect by chance, and a finding at a defect's line that describes
something *else* still counts as true.

So the reported false-positive counts (0, 1, 0, 2) are **understated**, and 42 findings covering 10
defects is not 42 true findings. A real precision number needs the claim matched, not just the
location — which on a real repository means the operator labelling. This run does not have one, and
should not be quoted as if it did.

## What was changed as a result

The corpus was rebuilt with 22 defects and a harder class: defects that exist only as a relationship
*between* modules (a plain definition beating another module's `lib.mkDefault`; a list-typed option
merging where a restriction was intended). That is the class a specialist can catch and a single
generalist pass plausibly will not. See `docs/MILESTONES.md` M8.5.

## Bottom line

The harness works end to end and the arms behave sensibly, but **this run cannot answer the
question it was built to answer**. It is recorded as the first measurement and superseded by the
22-defect run, not as evidence for or against the architecture.
