# Baseline-relative review

A whole-repo review costs `samples x (time to read the repo)`, most of it re-reading unchanged files
whose findings are already known. This stops that without changing what the score means.

## Why not `--scope diff`

`--scope diff` narrows what the reviewer *reads* and nothing else. The density denominator is
`kloc(repo)` — always the whole repository:

```python
# score_reviews.py
size_kloc = kloc(repo) if repo else 0.0      # the whole repo, never the diff
```

A diff-scoped run shrinks the numerator (fewer findings) and leaves the denominator alone: the score
rises because less was reviewed. Measured on one repository with real findings, using the scorer's own
functions:

| review | findings | kloc | density | det |
|---|---:|---:|---:|---:|
| whole-repo | 4 | 1.045 | 3.83 | 69.71 |
| diff scope, whole-repo kloc | 1 | 1.045 | 0.96 | **89.61** |

89.61 clears a threshold of 87.11: identical code, different scope, and the run passes. `--scope` is
therefore a prompt hint, not a scoring input.

Scaling the denominator to the diff is worse: one finding in a 50-line diff scores 42, because density
is only meaningful when numerator and denominator describe the same population.

## The design

Run the whole repository once; keep that run's findings as a **baseline**. Later runs read only what
changed and carry the baseline's findings for everything else.

```bash
nix run .#council -- review <repo>                      # the baseline (whole-repo)
nix run .#council -- review <repo> --baseline auto      # incremental from here on
```

`--baseline auto` finds the newest qualifying run; an explicit run-root path works too. Default: `off`.

- **Gets**: the changed-file list, the carried findings, the fresh probe results, the round's goals.
- **Does not get**: the unchanged files — summarised by the carried findings.

The carried findings go back into the numerator before the gate reads the files, so `carried + new`
covers the whole repository again.

## The invariants

**The denominator is always the whole repo.** Never the diff, never the changed set. If this changes,
every score in the history becomes incomparable and nothing says so.

**The probes always re-run over the whole repo.** They are seconds, and they are the half of `beta`
that cannot go stale.

**The LLM self-score is carried, not re-derived.** A reviewer that saw six files cannot honestly score
a fifty-file repository, so its self-assigned number is discarded and the baseline's is carried. The
new signal lands in `det`, computed from the merged findings and the fresh probes. Re-baselining
refreshes the LLM half.

Consequence: **an incremental score is a tracking score, not a fresh score** — comparable to its own
baseline, not to a fresh whole-repo run. `mode` is recorded in `meta.json` so the two are never
confused.

## What invalidates a carried finding

Two conservative rules.

**self** — the finding's own file is in the changed set; the code it is about was edited, so it is
re-derived.

**reference** — a file-like token in the finding's claim is in the changed set. This catches the
cross-cutting class: a doc, comment or ADR asserting something about a file that has since changed.

Conservative is deliberate: dropping a live finding is worse than keeping a stale one. The reviewer is
no longer reading that file, so a dropped finding is gone until the next baseline; a stale one is at
worst a false positive the next baseline removes. When in doubt, carry.

The rules cannot catch everything: a finding in an unchanged file can be falsified by a change
*outside the repository* — an ADR about `.wslconfig`, a comment about the host's network mode. No
file-diff rule can see that. Hence re-baselining on a schedule, or when the repository has settled.

## What qualifies as a baseline

`baseline.is_baseline` requires all four, and reports which failed:

| condition | why |
|---|---|
| a completed round whose recorded scope covers the whole repo | a diff-scoped run has findings only for the diff |
| a pinned `target_sha` | without it, "unchanged" is undefined |
| all five dimension files present | a missing dimension is an uncovered dimension |
| `dropped == 0`, recorded | a baseline missing findings it never reported carries that hole forever |

The last is why `merge_generalist_samples` records its `dropped` count in `meta.json`. Runs predating
that field are rejected rather than assumed complete; the validator names the reason.

An incremental run records `mode: "incremental"`, so it cannot become a baseline in turn. Carried
findings must not be carried twice.

## Cost

The saving scales with the fraction of the repository that did not change.

| repository | change | saving |
|---|---|---|
| 50 files | 16 changed | small — most of the repo is still read |
| 2000 files | 5 changed | most of the sampling cost |

On a small repository the overhead of resolving the baseline and carrying findings is comparable to
what it saves. The design is for repositories that have outgrown whole-repo reviews; it is close to
useless below a few hundred files.

## Inspecting it

```bash
council baseline --repo <repo> status    # the baseline and why it qualifies
council baseline --repo <repo> changed   # what changed, what it invalidates
```

`changed` is the useful one before a run: it lists the changed files and every finding the change
invalidated, with the rule that fired.

## Known conflict

`DECISIONS.md` #7 says "Git diff / PR changeset — review only what changed". The scorer has never
worked that way — it normalises by the whole repo — and #7 is not among the three decisions that note
records as later changed. Diff scope is a **reading** strategy, never a **scoring** one.
