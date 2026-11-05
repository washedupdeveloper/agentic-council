# Claims: what a run's evidence supports

A score is not a claim about the world. "Aggregate 87, satisfied" says the reviewers and the
deterministic gate agreed about the diff. It does not say the page was loaded, that CI passed, or
that the branch may be merged — and a report that prints a clean table invites all three readings
at once.

`scripts/claims.py` replaces the invitation with a ladder. Every rung is either **allowed** (its
evidence is a file the run recorded) or **blocked**, with the reason it is not and what would open
it. Nothing is asserted; everything is projected from `meta.json`, `probes.json`, the reviewer
files, `calibration.json`, and two receipts.

```bash
council claims --run runs/<run>              # the ladder, for a human
council claims --run runs/<run> --json       # the same, for a caller
```

Exit code is 0 when nothing is blocked, 1 when something is — so a pipeline can gate on it.

## The ladder

| Rung | Opens when | Blocked reason names |
|---|---|---|
| `run_recorded` | `meta.json` records a `target_sha` | nothing to attach a claim to |
| `probes_observed` | every tool this stack expects ran **and** parsed | the tools that did not, which is exactly the beta gap |
| `runtime_observed` | *web stacks only*: the `browser` probe ran, parsed, and reported no findings | the driver, the entry point, or the runtime findings it saw |
| `council_complete` | all five dimensions reported and parsed | the missing or unparseable ones |
| `gate_recomputed` | the aggregate came out of the deterministic gate | a gate error |
| `verdict_calibrated` | the threshold came from `scripts/calibration.json` | a CLI override with no calibration behind it |
| `ci_observed` | a CI receipt exists **for this run's head SHA** and concluded `success` | the missing receipt, a different SHA, or the conclusion |
| `merge_ready` | `ci_observed` **and** a satisfied verdict | which of the two is missing |
| `published` | a publish receipt with the URL that was read back | no post, or no read-back |

Rungs are cumulative: the state is the last one reached, and the first blocked rung is the
`next_action`. A rung that does not apply (the runtime lane on a repo with no page) is listed as
`not_applicable`, not as a failure.

**`merge_ready` without `ci_observed` is the sentence the ladder exists to make impossible.** A
review that never saw CI may say "satisfied"; it may not say "merge ready".

## Determinism: the ladder is a function of the tree

The payload carries **no clock**, no set iteration order and no caller-supplied verdict, so two
builds over the same files are byte-identical. That is asserted, not assumed
(`test_two_builds_of_one_tree_are_byte_identical`).

The gate is **always re-run** inside `build()`, even when a caller passes a result. A ladder that
trusts the caller's arithmetic can be opened by handing it the right dict; here a passed result that
disagrees with the recompute is reported as a blocked `gate_recomputed` naming both numbers, and the
recomputed one is what the payload reports.

Four inputs used to be ambiguous. Each is now a named outcome rather than a silent choice:

| Input | Ambiguity | Rule |
|---|---|---|
| rounds | `round-10` sorts before `round-2` as a string | rounds sort numerically; only a round holding reviewer files is a candidate |
| two `meta.json` | which sha is the run's | a disagreement blocks `run_recorded` and prints both |
| `probes.json` | absent vs empty vs unparseable | three different blocked reasons; none of them is "clean" |
| no stacks recorded | `all([])` passes every membership test | blocks `probes_observed` — nothing was expected, so nothing is shown to have run |

Receipts are strict: a receipt that names **no** commit is not evidence for any commit, and
`record-ci` refuses a sha that is not a full lowercase 40-character id at write time rather than
storing something that can never match.

### `--require`, for a pipeline

`council claims` exits 1 when anything is blocked — strict by default, because a caller who wanted a
specific level can say so and one who did not should not read a partial ladder as a pass.

```bash
council claims --run runs/<run> --require merge_ready   # 0 only if that rung is reached
```

The exit code is the only thing YAML needs; the reasons stay in the ladder text.

## The two receipts

Both are written by the thing that observed the fact, never by hand:

```bash
# after the pipeline actually finished, for this run's commit
council claims --run runs/<run> --record-ci --sha <sha> --conclusion success --url <ci-url>

# written by `council pr` itself, after it GETs the review it just created
.review-council/published.json
```

A receipt is keyed to a SHA. A result for another commit cannot open this run's rung, and a
`success` is not inferred from absence of failure: the conclusion is recorded, or nothing is.

## Where it is enforced

- `council pr` renders a **Claims this run supports** section into every review it posts, generated
  from the ladder: the comment cannot state a claim the evidence does not support, because the text
  is produced from the ladder rather than written by hand.
- After posting, `pr` GETs the review back and writes `.review-council/published.json`. If the
  read-back fails, the receipt is not written and the `published` rung stays blocked.
- `council claims` exits 1 on any blocked rung, so CI can require the level a branch is meant to
  reach without re-deriving it in YAML.

## What it deliberately does not do

- **It does not score.** The verdict comes from `score_reviews.py`; the ladder only says what that
  verdict does and does not entitle the run to claim.
- **It does not observe CI.** It records an observation someone else made. A ladder that polled
  GitHub would be a second CI client with its own token, retries and failure modes.
- **It does not open a blocked rung to keep a pipeline green.** A blocked rung with a reason is the
  product; an inferred pass is the defect.
