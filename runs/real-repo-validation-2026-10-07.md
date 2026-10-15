# Real-repo validation — 2026-10-07

The first end-to-end run of the council against a **real repository** (rather than a
seeded fixture), after the fan-out was rebuilt to spawn reviewer profiles.

## What was run

```bash
python scripts/council_loop.py <repo> \
  --mode advisory --max-rounds 1 --scope working-tree
```

| | |
|---|---|
| Target | `review-council` itself (the working-tree diff — 5 changed files) |
| Revision | `a1e9fbf6da24f3b7e5a2403350eca3a72873be10` |
| Stacks detected | nix, python, shell |
| Probes | 12 ran (once, for the whole run) |
| Mode | advisory (review only, never edits) |
| Run dir | `.review-council/20261007-235749` (scratch, gitignored — not preserved) |

Reviewing its own diff is deliberate: I know the code, so I can **verify every
finding** instead of assuming the reviewers are right.

## The fan-out worked

```
  convening 5 reviewers in parallel…
    security       rc=0  ok
    correctness    rc=0  ok
    readability    rc=0  ok
    architecture   rc=0  ok
    performance    rc=0  ok
```

All five reviewer **profiles** spawned in parallel, each exited 0, and each wrote
its own `<dimension>.json` (1.9–6.5 KB of real content, not stubs). The harness
wrote `meta.json`. This is the behaviour the previous `delegate_task` fan-out could
not produce, because delegated children inherit the *parent's* `HERMES_HOME` and
therefore cannot load a rubric that lives in another profile.

## The verdict

| | |
|---|---|
| Aggregate | **86.04** / minimum 80 → **PASS** (satisfied) |
| Findings | 16 across the five dimensions |

Per dimension (β is the fraction of that dimension's expected tools that ran):

| Dimension | llm | det | β | score |
|---|---|---|---|---|
| security | 97.0 | 100.0 | 0.40 | 98.2 |
| correctness | 74.0 | 92.66 | 0.80 | 88.93 |
| readability | 87.0 | 92.66 | 0.50 | 89.83 |
| architecture | 80.0 | 90.83 | 1.00 | 90.83 |
| performance | 90.0 | 70.42 | 1.00 | 70.42 |

Note `correctness` and `security` have β < 1: `pytest`, `bandit`, `pip-audit` and
`shellcheck` are not installed, so those dimensions lean on reviewer judgement —
and the next-steps plan says so, ranked by how much aggregate each install would buy.

## Did the reviewers find anything real?

**Yes — and every finding I checked was true.** This is the evidence that the
rubrics are now actually applied: a generic subagent would not cross-check a prompt
against a toolset manifest.

| Finding | Claim | Verified? |
|---|---|---|
| COR-0001 | `AGGREGATE_PROMPT` tells the orchestrator it "may run ONE bounded cross-examination round … the only reason to delegate", but the orchestrator has **no `delegation` toolset** | **TRUE** — self-contradictory prompt |
| PERF-0001 | `_gate_module()` is documented as importing "once" but re-execs the module on every call, and `probe_slice_for` calls it once per dimension | **TRUE** — 5 module execs per round |
| RD-0002 / ARC-0001 | The dimension→profile→rubric→prefix mapping is copied across **three parallel dicts** that must stay in step | **TRUE** — consolidated into one `DIMENSION_SPEC` |
| RD-0003 | `probe_slice_for`'s name and docstring promise "the probes belonging to *dimension*", but on failure it returns **all** probes | **TRUE** — silently mislabels other dimensions' probes as its own |
| ARC-0003 | `docs/ARCHITECTURE.md` still describes the fan-out as a `delegate_task` batch | **TRUE** — three stale references |

Every one is now fixed.

## Bugs found by the validation itself

Comparing the loop's number with a manual re-score exposed two more defects the
reviewers did not report:

**1. The score depended on how the gate was invoked.** The loop called
`run_gate` without `--repo`, so the findings term fell back from a calibrated
*density* to a raw *count*, while a manual re-run with `--repo` used the density
curve. The same run dir scored **86.04** from the loop and **90.33** by hand.

Fixed twice over: `run_gate` now passes `--repo`, and the gate reads the repo back
out of `meta.json`, so a run dir is self-describing. Verified — the same run dir now
returns **90.35** under all three invocations (no `--repo`, `--repo .`, absolute
path). A score that changes with the invocation is not reproducible, and
reproducibility is the entire premise of the deterministic half.

**2. A termination reason contradicted its own outcome.** The run reported
`OUTCOME: SATISFIED` with `reason: round cap reached (1) without clearing the
minimum` — on a run that *did* clear it. The reason string was hardcoded. Same
class of error as the earlier "85.23 / minimum 80 (BELOW the minimum)" bug: a
reason that sends the reader to the wrong problem.

## What this does and does not establish

**Established:** the fan-out spawns real profiles, the rubrics are applied, the
findings are specific and correct, the gate scores from the reviewer files, the
handover plan is written, and the loop terminates with the right verdict.

**Not established:** *precision* — whether the reviewers report things that are not
there. Every finding above was verified TRUE, but 16 findings across 5 dimensions is
a small sample from a repo whose author was the reviewer. The false-positive rate on
unfamiliar code is still unmeasured, and that is the number that decides whether
this is usable unattended.

**Next:** run it against a repo I did not write (the Clan flake below is the
obvious candidate) and check the findings there.
