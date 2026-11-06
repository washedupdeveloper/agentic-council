# Critique and restart: what this project is, what it costs, what to keep

Written after M10 was closed, with the code measured rather than remembered. Every
number below was produced by a command on `v1.9.0`; the file references are
`file:line`.

There is no M11 in `docs/MILESTONES.md` — the plan stops at M10. This document is
the proposal for what M11 should be: not another feature, a rebuild.

---

## 1. The verdict

**The idea is good. The product is three products wearing one CLI, and the
scaffolding now costs more than it returns.**

What is genuinely good, and should survive a rewrite:

- **A finding is a claim until a check settles it.** The proof vocabulary, the
  mandatory control, and "only `refuted` clears a block" is the best idea in the
  repository, and it is rare.
- **The claim ladder.** Separating "what the evidence supports" from "what the
  score says" is the right instinct, and `merge_ready` without `ci_observed` is a
  sentence worth keeping.
- **Measurement over assertion.** The repo repeatedly measured its own claims and
  published the results, including three measurements it later found wrong
  (`docs/OPTIMISATION.md` §2).

What is wrong is not the idea. It is the accumulation: a scorer, a calibration
laboratory and a packaging system, each built to its own standard, sharing a CLI
and a vocabulary that no longer agree with each other.

---

## 2. The evidence

| measure | value |
|---|---|
| `scripts/` | **17,357 lines** over **35 modules** |
| `nix/` + `flake.nix` | 1,907 lines over 6 files |
| `tests/` | **13,891 lines**, 39 files, 865 tests |
| `docs/` + README | **52,475 words** |
| `skills/` | 9,476 words |
| CLI | **24 user verbs + 5 setup + 5 dev** |
| argparse flags | **159** |
| `os.environ` reads | **54** |
| modules that mention `threshold` | **15 of 35** |
| modules that touch calibration | **11** |
| words for one judgement | **11** (`satisfied`, `not_satisfied`, `certified`, `unsatisfied`, `unprovable`, `uncalibrated`, `uncontrolled`, `proven`, `refuted`, `unsettled`, `confirmed`) |
| longest functions | `council_loop.main` 285, `calibrate.main` 222, `init.main` 181, `render_next_steps` 164, `score_reviews.evaluate` 156 |
| modules with no dedicated test file | **15** |
| property-based tests | **0** |
| commits / elapsed | 73 in 20 days |
| a review run | 5 samples × 5–8 min ≈ **25–40 min** |
| the OCI image | 99 layers, 814 MB |

Three ratios say most of it:

- **0.8** — lines of test per line of code. Unusually high, and yet two blockers
  survived the suite (see §3.6).
- **3.0** — words of documentation per line of code. The docs are a second
  codebase, and they are enforced like one.
- **15 / 35** — modules that have an opinion about the threshold.

---

## 3. What is actually wrong

### 3.1 The scoring model does not earn its complexity

The score is a weighted geometric mean over five dimensions, each a β-blend of
probe density and reviewer judgement (`score = β·det + (1−β)·llm`), renormalised
over the dimensions present, then capped by any confirmed claim (critical 30,
high 60, medium 85), compared against a threshold that is now derived per scale.

The measurement says the blend is not what separates good from bad:

- On a clean corpus the runs scored **97.83 · 97.83 · 100.00**; on the same trees
  with one seeded credential, **73.46 · 76.83 · 73.46**. The gap is produced by the
  **cap** (one confirmed medium sets a dimension to 85; one critical to 30), not by
  the curves. Remove the cap and a confirmed committed secret leaves `security` at
  det 71.75 — a number that reads like a pass.
- The first corpus could not separate at all: clean 78.37–88.81 against defective
  52.49–68.08, a 10-point band, and the repo's own conclusion was that "no cutoff
  inside a 10-point band survives another draw" (`docs/CORPUS.md`). The second
  corpus separated only because the defects were seeded to be unambiguous.
- β is a *measurement of tool presence* being used as a *weight*. When β = 1 the
  reviewer's judgement is multiplied by zero; when tools are missing the judgement
  carries the whole score. The same run therefore reports a number whose meaning
  changes with the toolchain, and the 54 `os.environ` reads are how that dependency
  gets in.

A number that is dominated by a boolean, and whose curve is decoration, is a
boolean with extra steps. The honest output of this system is the blocking set and
a list of what was proved — which it already computes.

### 3.2 Five vocabularies for one judgement

A single run can be simultaneously `satisfied` and `not certified`, `unprovable`
and `unsatisfied`, with findings that are `confirmed`, `unsettled`, `uncontrolled`
or `proven`. `score_reviews.evaluate` returns `status`, `certification`,
`score_source`, `calibration_scale`, `calibrated_for_scale`, `certification_basis`,
`reason`, `coverage_gap`, `enforced`, and a `threshold` that may be `None`.

This is not richness; it is five layers that grew at different times:

| layer | vocabulary | introduced |
|---|---|---|
| reviewer score | `status: satisfied / not_satisfied` | M2 |
| hybrid + threshold | `certification: certified / unsatisfied / uncalibrated` | M4–M8 |
| proofs | `state: confirmed / refuted / unsettled / unrunnable` | M10 |
| claims ladder | `allowed / blocked` per rung | M10 |
| coverage | `unprovable` | M10 |

Each is defensible alone. Together they mean a reader cannot answer "did this
pass?" without knowing which field is the verdict — and the repo has shipped two
bugs of exactly that shape (`pr` publishing 80.0 while the gate used 87.33).

### 3.3 The surface is a laboratory, not a product

Thirty verbs. A user who wants "review this change" must also learn `gate`,
`adjudicate`, `claims`, `proofs`, `severity`, `doctor`, `probes`, `baseline`,
`metrics`, `goal`, `cron`, `pr`, `swarm`, `sample`, `merge`. `sample` and `merge`
are internal steps of `review`; `probes` and `severity` are explanations of the
gate; `baseline` and `metrics` are reports about the tool itself.

The five `setup` verbs are another product: `init`, `skill`, `bots`, `toolchain`,
`dispatcher`.

Every verb is a contract that must be tested, documented and kept working. Two of
them (`swarm`, `goal`) exist because a milestone promised them and a later
measurement (M8.5) made them secondary; they are maintained anyway.

### 3.4 Packaging is six artifacts with three file lists

`flake.nix` alone exposes `framework`, `container`, `image-root`, `skill`,
`devshell`, `toolchain`, `vm-test`, `council`, `image-prep-tools`. Then a
`Dockerfile`, an OCI image, a skill copy, two Hermes profiles and a systemd
dispatcher.

The failure mode is already documented: `calibration.claims.json` was added to the
**framework** list, missed by `mkSkill` and `sync_to_skill.py`, and missed by the
data-file check — so the skill shipped without it while the release notes said the
number shipped everywhere. That is not carelessness; it is three lists that must
agree and no mechanism that makes them.

### 3.5 The documentation is a second codebase

52,475 words, including `MILESTONES.md` at 7,624 and `OPTIMISATION.md` at 6,574.
The docs do not describe the system; they *are* part of it: a test enforces that a
rule is stated in exactly one place (`test_owned_rules_are_not_restated_elsewhere`),
which is a rule you need when prose is load-bearing.

The cost is real. In this session I had to correct four documents that claimed
behaviour the code did not have, and the milestone's acceptance criteria were
prose that could not be executed — which is how M10 was declared delivered while
its central criterion was false.

### 3.6 The tests are broad and shallow at the edges

865 tests, 13,891 lines, and two blockers survived:

- `_run_diff` honoured only the last hunk of a diff. Every genuine change above it
  was refuted. No test had a two-hunk diff.
- The claims threshold was loaded, printed, and never compared. No test had a run
  that cleared the blocking set but sat under the threshold.

Both are *semantic* cases, not exotic ones. The suite is strong on structure
(shapes, flags, error strings) and weak on the two questions that matter: does the
number decide anything, and does the parser handle more than one shape?

Fifteen modules have no dedicated test file, including `calibrate.py` (1,053
lines). There is no property-based testing, which is exactly what a diff parser and
a proof parser want.

### 3.7 The calibration lab is a maintainer tool wearing a product verb

`council calibrate` plans a ladder, samples it, collects it, derives a threshold,
and refuses in five ways. It is good work — it found five real defects — and it is
not a feature a user of a code-review tool wants. It also requires 25–40 minutes of
LLM time per ladder, and the runs themselves are not kept: the evidence for 87.33 is
a JSON of six scores.

Calibration belongs in `dev/`, next to the ablation, not on the surface.

### 3.8 Process: acceptance was prose, and I declared victory twice

Seventy-three commits, milestone by milestone, each "delivered" against written
criteria. Then an independent review executed those criteria and found M10 unmet:
the `diff` kind was broken, the self-test had no case for it, and the threshold was
not enforced. Before that I had reported "10/10 exercised and passed" as proof of
coverage when it was a count of cases someone had written.

The lesson is not "be more careful". It is: **an acceptance criterion that is not a
command with an exit code is a wish.** The one criterion that was executable
(`council proofs --self-test` exits 3 when a lane is unexercised) was the one that
eventually caught the problem — after it was strengthened to assert coverage rather
than count cases.

### 3.9 The five-dimension premise has already been refuted, and the code has not noticed

M8.5 measured one generalist with all five rubrics against five specialists and
found no difference (13/22 injected defects at equal cost). The product now runs one
profile that *loads all five rubrics*. That is the right decision, but the code still
carries five dimension weights, five per-dimension scores, five reviewer files and a
per-dimension cap — a structure that exists to keep five agents apart when there is
one agent reading five sections.

Five sections is a rubric. It does not need five files, five weights and a
geometric mean.

---

## 4. What to keep, precisely

1. **`protocol/proofs.json`** — the closed vocabulary. Seven kinds is a good number.
2. **The control requirement** and the four states; only `refuted` clears a block.
3. **The claim ladder**, as a projection of a run's files, not as a score.
4. **Deterministic probes**, as a *coverage report* ("which analyzers ran"), never as
   a weight.
5. **The file bus** — one JSON per reviewer, readable after the fact.
6. **Golden fixtures** and the replay-diff idea.
7. **Nix for the toolchain only** — pinning the analyzers is the part that pays.

Everything else is negotiable.

---

## 5. The restart: M11

Target, stated as numbers so it can be checked:

| | now | M11 |
|---|---|---|
| modules in `scripts/` | 35 | **≤ 6** |
| lines | 17,357 | **≤ 4,000** |
| user verbs | 24 | **3** (`review`, `explain`, `ci`) |
| config keys | TOML + 54 env reads | **≤ 12, one file** |
| judgement words | 11 | **2** (`verdict`, `state`) |
| shipped artifacts | 6 | **2** (CLI+toolchain, image) |
| docs | 52,475 words | **≤ 6,000** |
| tests | 13,891 lines | fewer, but with property tests for both parsers |

### 5.1 Shape

```
reviewc/
  review.py    orchestrate: sample → merge → adjudicate → verdict   ~600 lines
  proofs.py    vocabulary, executors, controls, self-test          ~700
  probes.py    deterministic checks, parsed output                 ~700
  verdict.py   the one verdict type, the blocking rule, render     ~300
  config.py    one TOML, defaults, validation                      ~200
  cli.py       3 verbs                                             ~200
dev/           calibrate, ablate, corpus — not shipped
```

One verdict object:

```python
@dataclass
class Verdict:
    verdict: Literal["pass", "fail", "incomplete"]
    findings: list[Finding]      # each with state: proven|refuted|unsettled
    reason: str                  # why, in one sentence
    proof_coverage: dict         # which kinds ran, which could not
```

No `status` *and* `certification` *and* `basis`. If a caller needs to know whether
the number is comparable, it asks the calibration module directly.

### 5.2 Scoring, if any

Keep the blocking set as the verdict. If a number is wanted for trend, publish a
**single integer 0–100 = 100 − Σ penalties**, with penalties defined in one table
and no β, no Hill curve, no geometric mean, no renormalisation. A number whose
derivation fits on one screen can be argued with; the current one cannot.

### 5.3 Milestones, each with an executable acceptance

| # | deliverable | acceptance (a command) |
|---|---|---|
| M11.0 | freeze: tag v1.9.0, keep the six-rung corpus and golden fixtures as fixtures | `pytest tests/fixtures` green |
| M11.1 | proof engine: 7 kinds, both directions, property tests for the diff parser | `reviewc proofs --self-test` prints 7×2 and exits 0; `hypothesis` finds no counterexample |
| M11.2 | review loop: sample → merge → adjudicate | one run on the golden repo produces a verdict; `reviewc review` exits 0/1 accordingly |
| M11.3 | CI surface: JSON, exit codes, receipts | `reviewc ci --json` on the corpus gives the same verdicts as v1.9.0 |
| M11.4 | delete: curves, β, lab verbs, five-file dimensions, extra docs | `git grep -c "HILL\|beta"` → 0; `wc -w docs/*` ≤ 6,000 |

### 5.4 Migration, not a big bang

Keep `review-council` v1.9.0 as the reference binary. Build `reviewc` beside it.
Run both over the same six-rung corpus and the golden fixtures; the rewrite is done
when **every rung gets the same verdict** and the rewrite's `diff` parser passes
the two-hunk case v1 failed. Delete v1 only after that.

---

## 6. The list, prioritised

**P0 — correctness and honesty (do before any rewrite)**
1. One verdict vocabulary; `pr`/`claims`/`gate` read the same field. *(done in
   v1.9.0 for the threshold; the vocabulary still has five layers.)*
2. Property tests for the two parsers (diff hunks, proof normalisation).
3. One file list for "the shipped tree"; derive `mkSkill` and the Dockerfile from it.

**P1 — cut the surface**
4. Three verbs; move `sample`, `merge`, `probes`, `severity`, `doctor`, `baseline`,
   `metrics` behind `explain` or `dev/`.
5. Move `calibrate`, `ablate`, `corpus`, `golden` to `dev/` — not shipped, not
   documented as user features.
6. Decide `swarm` and `goal`: keep one orchestration path, delete the other.

**P2 — cut the model**
7. Delete β, the Hill curves and renormalisation; one penalty table, one integer.
8. Collapse five dimension files to five sections in one review file.
9. Calibration becomes a maintainer script that reads a corpus and prints a number;
   it stops being a CLI verb.

**P3 — cut the prose and the packaging**
10. Four documents (README, ARCHITECTURE ≤ 1 page, OPERATIONS, DECISIONS log);
    delete `MILESTONES.md` prose into a changelog, `OPTIMISATION.md` into
    `DECISIONS`.
11. One container path (flake), one skill generated from it, no Dockerfile — or a
    Dockerfile that is ten lines around the flake output.
12. Then M11.1–M11.4 as above.

---

## 7. What would make me wrong

- If a real user needs the per-dimension scores to decide something, the five
  dimensions earn their files. No evidence of that exists in the repo.
- If the aggregate is used as a trend across months, the curves may earn their
  keep. The repo's own data says the unseeded findings move the number more than
  the code does — a trend of reviewer mood.
- If the calibration lab is used by someone other than the maintainer, it should
  stay a verb. At present the only consumer is the maintainer, and its output is a
  file the build copies.

If none of those hold, the rewrite is a deletion exercise with a proof engine left
standing — which is the right shape for a tool whose value is "I can show you why
this finding is true".

---

## Appendix A — the feature ledger, M0–M11

Every milestone as it stands in the code today, not as it was described when it
shipped. "Keep" means the capability is load-bearing; "merge" means it exists but
should not be its own thing; "cut" means delete or move to `dev/`.

| # | what it was | what exists now | verdict |
|---|---|---|---|
| M0 | foundations, config, CLI | `council.py` dispatch table, `council_config.py`, 28 modules sharing one dispatcher boilerplate | **regenerate** — the table is good, the boilerplate is not |
| M1 | "uniform YAML protocol (schema + validation)" | **no YAML anywhere** (`import yaml` count: 0); reviewer files are JSON with a `schema_version` field; the protocol directory holds `proofs.json` and `severity.json` | **cut the claim** — the milestone text describes a format that no longer exists |
| M2 | deterministic scoring engine | `score_reviews.py`, 1,543 lines: five dimensions, β, Hill curves, geometric mean, renormalisation | **cut the model**, keep the gate |
| M3 | five specialist agents | one profile (`council-generalist`) that loads **all five rubrics** as core skills; `bots/` holds two members | **merge** — five sections, not five agents |
| M4 | orchestrator, aggregation, hybrid score | `council_loop` aggregation, `evaluate`, the caps | **keep**, collapse to one verdict |
| M5 | loop, termination, autonomy modes | `council_loop.py`, 2,417 lines, `main()` 285 lines: goals, rounds, budget, modes, rendering | **keep and shrink** — the loop is the product; it should not also be the renderer and the config reader |
| M6 | fix application and verification | folded into the loop (`fix_plan`, `apply_carry`), no separate module | **keep** |
| M7 | durability, integrations, surfaces | `swarm.py`, `cron.py`, `pr.py`, `install_dispatcher.py`, kanban | **cut `swarm`+`goal`** (one orchestration path), keep `pr` |
| M8 | evaluation, calibration, governance | `calibrate.py` 1,053 lines, `ablate.py` 832, `corpus.py` 585, three calibration JSONs | **move to `dev/`** |
| M8.5 | the ablation that refuted M3 | `ablate.py`, four arms, measured | **keep in `dev/`** — it is the most honest artefact in the repo |
| M9 | hardening, packaging, release | flake (7 outputs), Dockerfile, OCI image, skill copy, profiles, dispatcher, 39 test files | **collapse to two artifacts** |
| M10 | the proof ladder | `proofs.py` 965 lines, `adjudicate.py`, `claims.py`, `protocol/proofs.json`, 18-case self-test | **keep — this is the reason the project exists** |
| M11 | — | does not exist in `docs/MILESTONES.md` (0 mentions) | **this document proposes it** |

Two rows are the most useful in the table. **M1** is a milestone whose deliverable
has been quietly replaced and whose text still says otherwise — exactly the failure
mode that made M10's acceptance untestable. **M8.5** is a milestone that disproved
its predecessor and was then treated as a footnote: the product collapsed to one
reviewer, but the code kept five of everything.
