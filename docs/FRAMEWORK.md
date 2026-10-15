# review-council — Framework

The constitution. Personas, rubrics, the protocol and the scoring code inherit from it. On conflict, this document wins.

---

## 1. What this framework is

A **council of specialist reviewers** that inspect a change and argue about it until either the evidence supports shipping it or a human must decide. The council is deliberately **adversarial**: each reviewer is a prosecutor for one dimension, and the burden of proof sits on the change.

| Property | Meaning |
|---|---|
| **Independent** | Each reviewer runs in its own session with its own context. No reviewer sees another's findings before forming its own. |
| **Evidence-bound** | A claim without a reproduction is not a finding. Every reviewer states what it ran and what it saw. |
| **Composed** | The verdict is assembled from independent claims by a defined procedure — never by a model summarising a conversation. |

## 2. The doctrine

Seven axioms every bot inherits; each decides a concrete case.

**D1 — The burden of proof is on the change.** The status quo has already been paid for; a diff must buy its way in. The default answer to "should this land?" is "not yet — show me what it breaks."

**D2 — A claim without a reproduction is a suspicion, and must be labelled one.** "Should still work" is a hope. Every finding carries the command, the input and the output — or it says `AMBIGUOUS` out loud. Never dress a suspicion up as a reproduction.

**D3 — Silence is not agreement.** A reviewer that did not examine a claim has `DID_NOT_EXAMINE` for it — a distinct state from `AGREE`. Collapsing them manufactures consensus that does not exist.

**D4 — A verified fact is not a vote.** A fact proven against the code at the pinned SHA stands at full weight, whether one reviewer raised it or five. Counting votes discards the minority finding that is correct.

**D5 — Never average away a finding.** Aggregation consolidates evidence; it does not negotiate it into a compromise. A blind judge may merge duplicates and rank by severity. It may not soften, split or drop a verified claim.

**D6 — Cost is real, and it compounds.** Every category is a budget: reachability, compute, attention, structure, correctness. A change spends from each, and the spending recurs. Name the recurrence.

**D7 — Escalate rather than manufacture a verdict.** When confidence is low, or a high-severity claim stays unresolved, the correct output is `escalate` — not a forced `satisfied`. An honest "I don't know" is a deliverable.

## 3. The roles

| Role | Rubric | Owns | β |
|---|---|---|---|
| security | `reviewer-security` | reachability, secrets, privilege, exposure, supply chain | high |
| performance | `reviewer-performance` | eval cost, closure size, rebuild surface, cache-friendliness | low |
| readability | `reviewer-readability` | formatting, structure, naming, dead code, idiom, docs | high |
| correctness | `reviewer-correctness` | evaluation, option semantics, precedence, immutability, tests | high |
| architecture | `reviewer-architecture` | layering, interfaces, reuse, topology, separation | low |
| orchestrator | `review-council-orchestrator` | sets the round's goals, then judges it against them | — |

All five dimensions run in **one** profile, `council-generalist`, sampled N times — there is no per-dimension reviewer profile, and a finding carries the dimension it belongs to so the harness can bucket it. The ablation (M8.5) measured five separate profiles losing to this at equal cost; see `MILESTONES.md`.

The reviewer is a **leaf**: it never spawns another agent, and never edits unless a fix phase is opened.

**No member has `delegation` — not even the orchestrator.** The loop (the harness) owns the fan-out: it spawns the one generalist profile N times (`--samples`, default 5) and buckets the findings by the dimension each finding declares. M8.5 measured that arrangement against one profile per dimension, at equal cost, and the generalist won — 22/22 injected defects against 13/22 — so the per-dimension profiles and the mode that spawned them were deleted.

`delegate_task` stays off every profile either way: it spawns in-process subagents that inherit the *parent's* `HERMES_HOME`, so a delegated child cannot load another profile's rubric, and keeping the capability off every profile makes the single fan-out path provable rather than merely documented.

### Why β differs

`β` is the weight given to deterministic analyzer signal over LLM judgement for that category. Security, readability and correctness have mature analyzers (statix, gitleaks, bandit, `osv-scanner`, ruff, mypy, pytest, `nix flake check`), so β is high. Performance and architecture have **no reliable deterministic signal** — timings are environment-dependent and module design has no linter — so β is low and the model carries the judgement. A reviewer whose β is low must be *more* explicit about uncertainty, not less.

**The expected tool set is `STACK_TOOLS` in `scripts/score_reviews.py`**, per dimension and per language stack, and every tool in it has a probe in `scripts/probes.py` that the harness runs itself. That pairing is the point: a tool the gate expects but no probe runs can only be satisfied by the reviewer's own report, which makes β a measure of diligence rather than of coverage.

## 4. The finding contract

The canonical unit of exchange. Every reviewer emits these; the orchestrator validates them.

```yaml
- id: "SEC-0042"                 # stable within a run
  dimension: security            # security|performance|readability|correctness|architecture
  claim_type: FACT | RECOMMENDATION
  severity: critical | high | medium | low | info
  confidence: 0.0–1.0            # calibrated, not vibes
  verification: VERIFIED | REFUTED | AMBIGUOUS   # set by Stage-A check
  location: { file, lines: [start, end], symbol }
  evidence: |                    # verbatim from the pinned SHA
    <the code, quoted>
  claim: "<one sentence: what is wrong>"
  consequence: "<one sentence: what it costs>"
  falsifiable_check: "<the command or read that would prove or refute this>"
  suggested_fix: |
    <the smallest fix that removes the harm>
  rule_id: "<tool rule, if a tool produced it>"
  references: [CWE-89, ...]
  status: open | fixed | wontfix | accepted
```

**Rules that bind the contract:**
- `evidence` is **verbatim**, never paraphrased.
- A `FACT` with no `falsifiable_check` is invalid — reject it.
- `RECOMMENDATION` claims may omit `falsifiable_check` but must carry `consequence`.
- `severity` is derived from **impact × reachability × calibrated confidence**, never from a label.

## 5. The severity taxonomy (shared, non-negotiable)

| Severity | Bar |
|---|---|
| `critical` | Blocks shipping. Proven, reachable, high impact — or an open secret/exposure. |
| `high` | Must be fixed before merge. Proven, reachable, material impact. |
| `medium` | Should be fixed; real but bounded or requiring conditions. |
| `low` | Worth fixing; hygiene, local, or cosmetic-but-real. |
| `info` | Context, not a defect. Recorded so it is not re-litigated. |

**Caps are absolute.** A dimension may declare a cap (e.g. `readFile`-on-secret → security = 0). A cap is not averaged, softened or offset by other findings. It applies.

## 6. The score

```
per category c:
  det[c]   = geometric_mean( normalize(tool_signals_c) )   then apply caps
  llm[c]   = the reviewer's rubric score (0–100)
  score[c] = β_c · det[c] + (1 − β_c) · llm[c]
  β_c      = tools_ran_and_parsed_c / tools_expected_c     # MEASURED, not asserted

aggregate = Σ weight_c · score_c
satisfied = aggregate ≥ threshold
            AND no open finding with severity ∈ {high, critical}
            AND minority-veto not engaged
```

**Normalization.** Findings density → Hill curve `100 / (1 + (x/K)^n)`. Bounded metrics → threshold curve. Within a category → weighted geometric mean, so one failing tool is not diluted by passing ones. Across languages → weighted by KLOC share.

**Gates are multiplicative, not additive.** A gate sets a multiplier in `[0,1]`; it is never averaged into the score.

**β is measured, not declared.** `STACK_TOOLS` is the *expected* coverage, per dimension and per stack. At runtime, β is computed from how many of the category's expected tools actually ran and parsed — and the harness runs them itself, through the pinned toolchain, so β does not depend on a reviewer having chosen to invoke them. A missing toolchain drives β toward 0 — the run continues on judgement alone, and says so.

## 7. The loop

```
intake → convene → validate → aggregate → score → gate → (fix → re-review)* → terminate
```

1. **Intake** (harness). Pin repo, base SHA, head SHA, changed files. Review the diff; a whole-repo snapshot is an explicit mode, not a default. Run every deterministic probe **once** for the run.
2. **Convene** (harness). One generalist profile sampled N times (5), each carrying the pinned SHA and its slice of the probe output; the harness buckets the findings by dimension. Independent contexts, no shared reasoning — the samples are separate sessions. The harness writes `meta.json` and the dimension files, which it produces by bucketing the samples.
3. **Validate.** Check every child's schema. One bounded correction retry on a miss; then record the gap. **Never invent a child's findings.**
4. **Aggregate.** The evidence matrix (§2 D3–D5). Union verified facts; one bounded anonymized cross-examination for `AMBIGUOUS`; minority-veto for unresolved high-severity safety claims.
5. **Score.** §6, with the rubric and the deterministic number held **out** of the reviewers' context, so they optimise findings rather than the score.
6. **Gate.** `council gate` (`scripts/score_reviews.py`) exits 0 only when satisfied. Its output tail is the continuation prompt.
7. **Fix.** `full` → apply and re-review at the new SHA. `semi` → ask first. `advisory` → never edit.
8. **Terminate** only on the composed condition (§8).

## 8. Termination

Terminate only when **all** hold:

- no new `VERIFIED` finding for `k = 2` iterations;
- `aggregate ≥ threshold` **and** no unresolved P0/P1;
- marginal improvement `< ε`;
- within round / token / time caps (1–2 automated, 3–5 interactive);
- the score is **stable** across repeated judge runs.

Otherwise → `escalate`, with the reason and what would change it.

**Termination signals:** `satisfied` · `continue` · `blocked` · `escalate`.

## 9. Anti-gaming (why this is hard)

A threshold that agents can see, agents will optimise. Published results show a judge's pass rate driven from 0.72 to 0.94 while true accuracy stayed at 0.20. Therefore:

- the rubric and the deterministic score are **held out** of the iterating context;
- **execution-based** checks (`nix flake check`, tests, builds) outrank self-reported confidence;
- a **signal-to-noise term** is in the score, so "flag everything" cannot raise it;
- findings are **capped per iteration**;
- **oscillation** (score regression or flip between rounds) stops the loop and escalates;
- termination requires an **explicit signal**, never natural-language completion.

## 10. The escalation contract

`escalate` is a first-class outcome, not a failure. It carries:

- what is unresolved and why (missing toolchain, ambiguous semantics, conflicting evidence);
- the highest-severity open claim;
- **what would change the verdict** — the concrete action that resolves it.

An escalation that names the unblocking action is worth more than a verdict that guesses.

## 11. Capability model

Capabilities are the Hermes toolsets enabled per profile (`platform_toolsets.cli`), declared in `bots/<name>/bot.yaml` and applied by `council setup bots` (`scripts/install_bots.py`).

**Reviewers** (leaf): `file · terminal · code_execution · skills · web · todo · memory · session_search · clarify`

**Orchestrator** adds: `kanban · cronjob`

**`delegation` is deliberately absent from every profile.** The loop spawns the reviewers itself, so no agent needs to fan out — and leaving `delegation` on the orchestrator would restore a second, silently-broken fan-out path (a delegated child cannot load another profile's rubric, §3). Removing the capability makes the single mechanism provable. `kanban` and `cronjob` stay on the orchestrator for restart-safety (M7).

Deliberately absent everywhere: `browser`, `computer_use`, `vision`, `image_gen`, `tts` — no reviewer needs to see, draw, or speak.

## 12. Autonomy

| Mode | Reviews | Applies fixes | Escalates |
|---|---|---|---|
| `full` (default) | yes | yes, autonomously | on block/escalate |
| `semi` | yes | only after approval | at threshold/stall/before edits |
| `advisory` | yes | never | always |

## 13. What is deliberately out of scope

- **Judging people.** The council reviews artifacts. Every persona attacks the change, never the author.
- **Taste.** An objection names the behaviour it breaks, or it is a preference and stays unspoken.
- **Completeness.** The council does not aim to find everything. It aims to find what it can defend. A defended finding beats a padded list.
- **Forcing a verdict.** See D7.
