# Fix-round verification — 2026-10-06

**Purpose.** M5's acceptance criterion was *"on a seeded-defect fixture, the loop
drives the score up across ≥2 rounds."* The termination logic had only ever been
tested with stubs, and no run had ever applied a fix. This run closes that gap.

**Target.** A purpose-built fixture with four seeded defects, each catchable by a
deterministic probe:

| Defect | File | Probe that catches it |
|---|---|---|
| hardcoded credential | `src/bad.py:11` | `secret-grep` |
| genuine syntax error | `src/broken.py:8` | `py-compile` |
| cyclomatic complexity 19 | `src/bad.py:14` | `complexity` |
| no declared architecture rules | `.` | `declared-rules` |

**Command.**

```bash
python scripts/council_loop.py <fixture> --mode full --max-rounds 2 --timeout 1500
```

## Result

```
=== round 1/2 — review ===
  aggregate 46.07 / 80  ->  FAIL
  new findings this round: 25 (no-new streak 0/2)
=== round 1 — fix (mode: full) ===
=== round 2/2 — review ===
  aggregate 85.23 / 80  ->  FAIL
  new findings this round: 4 (no-new streak 0/2)

OUTCOME: ESCALATE
reason:  round cap reached (2) without clearing the gate
scores:  [46.07, 85.23]
```

**+39.16 points across one fix round.** The fix turn ran, edited the target, and
the re-review measured a materially higher score. The loop mechanism works.

## Per-dimension

| Dimension | R1 llm | R1 β | R1 score | R2 llm | R2 β | R2 score |
|---|---|---|---|---|---|---|
| security | 30 | 0.33 | 46.63 | 88 | 0.33 | **89.25** |
| correctness | 14 | 0.50 | 35.06 | 90 | 0.50 | **85.61** |
| readability | 34 | 0.00 | 34.00 | 74 | 0.00 | 74.00 |
| architecture | 35 | 1.00 | 58.94 | 85 | 1.00 | **84.33** |
| performance | 52 | 1.00 | 76.70 | 96 | 1.00 | **96.02** |

β is non-zero here because the fixture is a Python repo and the per-stack tables
now expect Python tools. `architecture` and `performance` reach β = 1.00 on the
built-in probes alone (`dep-graph`, `declared-rules`, `complexity`).

## What the fix turn actually did

Verified by inspecting the target, not by trusting the summary:

- `src/broken.py` — rewritten as a proper module: I/O and parsing separated into
  `_read_text` / `_parse`, full docstrings, a path-traversal guard confining reads
  to the module directory. The syntax error is gone.
- `src/bad.py` — the hardcoded credential is removed (grep for the literal returns
  nothing); the 19-complexity function was decomposed.
- `AGENTS.md` — created, declaring module boundaries and dependency direction.
- `tests/` — `test_bad.py` and `test_broken.py` added.

**No cheating:** no tests were deleted or weakened to pass, and no finding was
suppressed. The diff is a genuine repair (205 insertions, 44 deletions).

## Why it still escalated

The gate requires `aggregate ≥ threshold` **and** no open high/critical finding.
Round 2 reached 85.23 ≥ 80 but left one open HIGH:

```
[RD-0001] readability high: process() is part of the public surface
          (listed in __all__ at line 22) but its p... [missing docstring]
```

4 of 5 round-1 blockers were fixed; the fifth was not, and the round cap (2) was
reached. That is the gate working as designed — a high score does not buy a pass
while a blocking finding is open.

## Observations

1. **The fix round is real but bounded by `--max-rounds`.** One round recovered
   ~39 points and 4/5 blockers. A third round would likely have cleared the last
   one. The cap is the design's (1–2 automated); raise it for interactive runs.
2. **`readability` β stayed 0.00** — `ruff` and `mypy` are not installed on this
   host. That dimension is entirely reviewer judgement. `doctor.py --install`
   fixes it; this is the clearest remaining lever on score fidelity.
3. **The loop did not touch the run directory's target during review**, only
   during the fix turn — `git status` was clean after round 1's review and showed
   edits only after the fix turn.
4. **Runtime: ~25 minutes** for two rounds plus a fix turn, unattended.

## Status

M5's fix-round acceptance criterion is **met**: the loop drives the score up
across ≥2 rounds. Termination paths were already covered by `tests/test_council_loop.py`.
