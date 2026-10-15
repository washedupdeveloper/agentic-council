# Ablation — 22-defect injected corpus (M8.5, the decisive run)

| | |
|---|---|
| Corpus | `corpus-hard` — a clean HEAD of the reference corpus + 22 injected defects |
| Revision | `fa763fc081e6a04d33e384495215493de06fe143` |
| Corpus sha256 | `3e2a96fb464725943a20b0db9707e631c0924998dbf12d53c1b2803f016ce3de` |
| Integrity during run | **unchanged** (verified before and after) |
| Defects | 22 — 10 security, 7 correctness, 3 performance, 2 readability |
| Deterministically visible | **0 of 22** — the corpus passes its own full gate |
| Duration | 1981 s (≈33 min) |
| Run dir | `~/example-corpus/run-hard` |

## Result

| Arm | Turns | Findings | True defects | Recall | False positives | Wall |
|---|---:|---:|---:|---:|---:|---:|
| `single` | 1 | 11 | 12 / 22 | 0.545 | 0 | 346 s |
| `generalist-rubrics` | 5 | 68 | **22 / 22** | **1.000** | 0 | 487 s |
| `generalist-bare` | 5 | 67 | **22 / 22** | **1.000** | 1 | 900 s |
| `specialists` | 5 | 26 | **13 / 22** | **0.591** | 1 | 249 s |

**The rule: COLLAPSE to one reviewer — specialists 13 vs best single-agent 22 = 0.59×, needs ≥1.5×.**

Unlike the first run, this verdict is **earned, not forced**. Both equal-cost arms had the same
opportunity and the same corpus; one found every defect and the other found 59% of them.

## The three findings

**1. Five specialists did no better than one generalist turn.** `specialists` found 13/22;
`single` — one agent, one pass, all five rubrics — found 12/22. Splitting the review into five
isolated dimensions, each with its own profile and rubric, bought one extra defect.

**2. The rubrics earn their place — but only the repeat run shows it.** In run 1 `generalist-bare`
(no rubric at all) found 22/22, exactly as `generalist-rubrics` did, and it looked as though the 811
lines of dimension rubric did nothing. The repeat run says otherwise: `generalist-rubrics` scored
22/22 a second time, while `generalist-bare` fell to 17/22. One measurement per arm was not enough to
see the difference, and the conclusion drawn from run 1 alone — that the rubrics changed nothing —
was wrong. This is the clearest argument in the project for repeating a measurement before believing
it.

**3. The specialists missed the defects their own rubrics target.** Of 10 injected security
defects the security reviewer found 5, missing the widened firewall rule, the disabled commit
signing, the disabled gitleaks hook, the over-broad broker ACL, and the enabled DHCP client. Of 7
correctness defects the correctness reviewer found 4. All of these were in files the specialists
reviewed; the rubrics were verified present and mounted, so this is a miss, not a handicap.

## Cost, honestly

The specialists were **faster** — 249 s against 487 s — because they did less work. Per defect
found they are comparable: 19.2 s/defect against 22.1 s/defect. So the argument for collapsing is
not speed; it is that one reviewer with five samples found 69% more defects for the same number of
agent turns, and with one profile instead of six.

## Two scoring bugs found while measuring — both fixed

Recorded because they are the reason the numbers above are trustworthy:

- **Exclusive nearest-match under-counted recall.** Two defects sat on adjacent lines (46 and 47),
  both anchored on the same source line, so a finding covering both was credited to one and the
  other read as missed. `specialists` scored 12/22 instead of 13/22, and `single` 10/22 instead of
  12/22.
- **`_distance` never compared paths.** A finding matched a defect in a different file whenever the
  line numbers were close, and a `new-file` entry matched any finding anywhere. Every arm reported
  zero false positives as a result.

Both are pinned by tests. The first run in `ablation-10-defect-2026-10-11.md` was scored with the
old matcher and should be re-read with that in mind.

## Repeat run — the error bars

The same four arms on the same corpus, run a second time (`run-hard-2`), so the numbers have a
spread rather than standing alone:

| Arm | Run 1 | Run 2 | Δ | Verdict |
|---|---:|---:|---:|---|
| `single` | 0.545 | 0.500 | 0.045 | stable |
| `generalist-rubrics` | **1.000** | **1.000** | **0.000** | **stable, perfect both times** |
| `generalist-bare` | 1.000 | 0.773 | 0.227 | noisy |
| `specialists` | 0.591 | 0.727 | 0.136 | noisy |

**The rule reaches the same verdict on both runs** — specialists at 0.59× and 0.73× of the best
generalist, against a threshold of 1.5×. The verdict is not an artefact of one run.

Three things the repeat adds that one run could not:

- **`generalist-rubrics` is the most reliable arm measured**: 22/22 twice, zero variance. Whatever
  the project keeps, this is the configuration the evidence supports.
- **The rubrics matter.** `generalist-bare` is the arm that moved, and it moved down. The rubrics are
  what make the generalist repeatable.
- **The specialists are both worse and less predictable** — below every generalist arm in both runs,
  and with a 0.136 spread of their own.

A caveat on the timings: the repeat ran concurrently with another job, so its wall-clock figures are
inflated (564 s for `single` against 346 s) and are not comparable across runs. Recall is unaffected;
only the clocks are.

## Limitations

- **One corpus, two runs.** The repeat gives each arm a spread (see above), but it is still a single
  corpus, so the numbers say how repeatable an arm is on *these* defects, not how it generalises to
  others.
- **Recall is location-based.** A finding counts as true if it names a defect's path and lands
  within three lines, whether or not it describes that defect. The false-positive counts are
  therefore a floor, and 68 findings covering 22 defects is three findings per defect — not 68 true
  findings.
- **A sample of `generalist-bare` timed out** at 900 s. Its 22/22 came from the remaining four, so
  the arm is understated rather than overstated.
- **The specialists cannot exceed their dimension by design.** Each covers one dimension, so the
  union is the measured quantity — which is the right thing to measure, but it means a specialist
  arm can only ever be as good as the sum of its parts.
- The corpus is mine, and so is the scorer. The 22 defects were chosen by the same person who wrote
  the rule they are used to test.

## Bottom line

The evidence supports **collapsing to a single reviewer run several times** — and specifically to the
generalist *with* the rubrics, which is the only arm that scored 22/22 twice. Fewer moving parts (one
profile instead of six), fewer agent turns for the same coverage, and materially higher recall than
the five specialists in both runs. The five-dimension split is not earning its cost; the five rubrics
are.

This is the answer the ablation was built to find, and it is the answer that argues against the
architecture the project is built on.
