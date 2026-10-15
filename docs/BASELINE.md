# Baseline-relative review

A whole-repo review costs `samples x (time to read the repo)`, most of it re-reading files nobody
touched, whose findings are already known. This is how the framework stops paying that, without
changing what the score means.

## Why not `--scope diff`

`--scope diff` narrows what the reviewer *reads* but nothing else. The density denominator is
`kloc(repo)` — always the whole repository:

```python
# score_reviews.py
size_kloc = kloc(repo) if repo else 0.0      # the whole repo, never the diff
```

So a diff-scoped run shrinks the numerator (fewer findings, because fewer files were read) and leaves
the denominator alone: the score rises because less was reviewed. Measured on one repository with real
findings, using the scorer's own functions:

| review | findings | kloc | density | det |
|---|---:|---:|---:|---:|
| whole-repo | 4 | 1.045 | 3.83 | 69.71 |
| diff scope, whole-repo kloc | 1 | 1.045 | 0.96 | **89.61** |

89.61 clears a threshold of 87.11. Identical code, identical quality, different scope — and the run
passes. That is why `--scope` is a prompt hint rather than a scoring input, and why it must stay that
way.

Scaling the denominator to the diff is worse, not better: one finding in a 50-line diff scores 42,
because density is only meaningful when the numerator and the denominator describe the same
population.

## The design

Run the whole repository once. Keep that run's findings as a **baseline**. On later runs, read only
what changed, and carry the baseline's findings for everything else.

```bash
nix run .#council -- review <repo>                      # the baseline (whole-repo)
nix run .#council -- review <repo> --baseline auto      # incremental from here on
```

`--baseline auto` finds the newest qualifying run; an explicit run-root path works too. The default is
`off`, so nothing changes unless asked for.

What the incremental reviewer gets, and what it does not:

- **Gets**: the explicit changed-file list, the carried findings, the fresh probe results, the round's
  goals.
- **Does not get**: the unchanged files. Their content is summarised by the carried findings, the
  distilled output of a whole-repo read.

The carried findings go back into the numerator before the gate reads the files, so `carried + new`
covers the whole repository again.

## The invariants

Three, and each one is what keeps the number comparable to the baseline.

**The denominator is always the whole repo.** Never the diff, never the changed set. If this changes,
every score in the history becomes incomparable and nothing says so.

**The probes always re-run over the whole repo.** They are seconds, and they are the half of `beta`
that cannot go stale. The deterministic half is never frozen.

**The LLM self-score is carried, not re-derived.** A reviewer that saw six files cannot honestly score
a fifty-file repository, so its self-assigned number is discarded and the baseline's is carried. The
new signal is not lost — it lands in `det`, computed from the merged findings and the fresh probes.
Re-baselining is what refreshes the LLM half.

Consequence: **an incremental score is a tracking score, not a fresh score.** It answers "how is this
repository trending under incremental work", and it is comparable to its own baseline — not to a fresh
whole-repo run. `mode` is recorded in `meta.json` precisely so the two are never confused.

## What invalidates a carried finding

Two rules, both conservative.

**self** — the finding's own file is in the changed set. The code it is about was edited, so it is
re-derived rather than assumed.

**reference** — a file-like token in the finding's claim is in the changed set. This catches the
cross-cutting class: a doc, comment or ADR that asserts something about a file that has since changed.

Being conservative is deliberate, and the asymmetry is the reason. Dropping a live finding is worse
than keeping a stale one: the reviewer is no longer reading that file, so a dropped finding is gone
until the next baseline, whereas a stale one is at worst a false positive the next baseline removes.
When in doubt, carry.

That is also why the rules cannot catch everything. A finding in an unchanged file can be falsified by
a change to something *outside the repository* — an ADR about `.wslconfig`, a comment about the host's
network mode. No file-diff rule can see that. It is the argument for re-baselining on a schedule, or
when the repository has settled.

## What qualifies as a baseline

`baseline.is_baseline` requires all four, and reports which failed:

| condition | why |
|---|---|
| a completed round whose recorded scope covers the whole repo | a diff-scoped run has findings only for the diff |
| a pinned `target_sha` | without it, "unchanged" is undefined |
| all five dimension files present | a missing dimension is an uncovered dimension |
| `dropped == 0`, recorded | a baseline missing findings it never reported carries that hole forever |

The last one is why `merge_generalist_samples` records its `dropped` count in `meta.json`. Runs made
before that field existed are rejected rather than assumed complete — the validator says so, and
points at which reason applied.

An incremental run records `mode: "incremental"`, so it cannot become a baseline in turn. Carried
findings must not be carried twice; the baseline has to stay a genuine whole-repo reading.

## Cost

The saving scales with the fraction of the repository that did not change, so it is worth knowing when
this is *not* worth using.

| repository | change | saving |
|---|---|---|
| 50 files | 16 changed | small — most of the repo is still read |
| 2000 files | 5 changed | most of the sampling cost |

On a small repository the overhead of resolving the baseline and carrying the findings is comparable
to what it saves. This is a design for repositories that have outgrown whole-repo reviews, and it is
close to useless below a few hundred files.

## Inspecting it

```bash
council baseline --repo <repo> status    # the baseline and why it qualifies
council baseline --repo <repo> changed   # what changed, what it invalidates
```

`changed` is the useful one before a run: it lists the changed files and every finding the change
invalidated, with the rule that fired.

## Known conflict

`DECISIONS.md` #7 says "Git diff / PR changeset — review only what changed", and the README's first
line still describes the framework that way. The scorer has never worked that way — it normalises by
the whole repo — and #7 is not among the two decisions that note records as later overturned. This
document is the resolution: diff scope is a **reading** strategy, never a **scoring** one.
