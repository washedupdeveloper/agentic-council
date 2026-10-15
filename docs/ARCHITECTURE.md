# review-council — Architecture

Status: design. Companion to `MILESTONES.md` (the build plan) and `DECISIONS.md` (locked choices).

---

## 1. One-line summary

A Hermes-native, cross-platform system where a **reviewer** inspects a git diff, publishes findings as one JSON file per dimension, and an orchestrator iterates (via Hermes' own loop engine) until a hybrid deterministic+LLM satisfaction score clears a threshold or the run stalls. Every entry point is one CLI, `council <verb>` (`nix run .#council -- <verb>`, or the container image).

The reviewer is **one generalist carrying all five rubrics, sampled N times**. Five isolated specialist profiles used to run here; M8.5 measured the two at equal cost and the generalist won — 22/22 injected defects against 13/22 — so the five profiles, and the mode that spawned them, were deleted rather than kept as an alternative nothing installs. See `MILESTONES.md` M8.5.

## 2. The four layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. ORCHESTRATION & LOOP      /goal (+ deterministic gate) | /loop --until     │
│    - convene, bucket, aggregate, score, decide continue/stop, apply fixes    │
│    - autonomy: full (default) | semi | advisory                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. REVIEWERS                 generalist × N samples                          │
│    security · performance · readability · correctness · architecture         │
│    all five rubrics in ONE SOUL.md + profile                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. DETERMINISTIC ENGINE      analyzers → findings/metrics → 0–100 scores      │
│    bandit/gitleaks/osv-scanner/ruff/mypy/pytest/statix/deadnix/…             │
│    normalization: Hill + threshold curves + weighted geometric mean + β      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. PROTOCOL                  review.msg/v1 (YAML) ⟷ JSON Schema (contract)    │
│    Envelope · Finding · Scores · Control · Error                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. Key technical reconciliations

### 3.1 YAML everywhere, JSON where Hermes demands it

- **Designed, unbuilt (M1):** Pydantic v2 models → generated **JSON Schema Draft 2020-12** (`protocol/models.py` → `protocol/envelope.schema.json`); YAML on the wire, validated against that schema. See §5.
- **Shipped:** each dimension's findings land as **JSON** in their own file in the run directory (`round-N/<dimension>.json`). The harness buckets the one generalist's samples into those files, writes `meta.json`, and the gate reads them all.
- **Consequence:** the JSON/YAML split is an implementation detail.

### 3.2 The loop engine: `/goal` primary, `/loop` alternate

| | `/goal` (primary) | `/loop` (alternate + heartbeat) |
|---|---|---|
| Trigger | judge verdict after each turn | timer / self-paced |
| Deterministic check | **quality gates run before the judge** | none (only `--until` judge) |
| Stop | judge `done` / budget / gates | `LOOP_COMPLETE` / `--until` (fail-open) / `--times` / `max_ticks` |
| Fit | "iterate until SCORE ≥ threshold" | "re-run on a cadence" |

They coexist: an active `/goal` **defers** `/loop` ticks. Use `/goal` for the scored loop, and `/loop 10m /recap` for status heartbeats (or `/loop --until "<score condition>"` for the literal "loop until score" request, with its fail-open caveat documented).

### 3.3 The hybrid score

```
per category c:
  score_det[c] = geometric_mean_t( normalize(score_t) )        # Hill for findings, curve for metrics
                 then apply caps/gates
  score_llm[c] = rubric score from the reviewer (0–100)
  score[c]     = β_c · score_det[c] + (1 − β_c) · score_llm[c]
                 β_c = min(1, tools_ran_and_parsed_c / tools_expected_c)
aggregate = Σ_c weight_c · score[c]
satisfied = (aggregate ≥ threshold) AND (no open finding with severity ∈ {high, critical})
```

- LLM deviation from `score_det` is **bounded** unless it cites file:line evidence; every deviation logged.
- `β` is low where determinism is weak (performance, docs substance, architecture-without-rules).
- The **rubric and the deterministic score are held out of the iterating agents' context** so they optimize findings, not the number.

### 3.4 Aggregation: an evidence matrix, not a conversation

- Dedupe findings by `path:line` + functional claim; columns = reviewers; cells = `AGREE | DISAGREE | DID_NOT_EXAMINE` (**silence is never agreement**).
- `VERIFIED` FACT → **union** (any verified fact stands; no voting).
- `AMBIGUOUS` FACT → **one** bounded, anonymized cross-examination round; escalate if unresolved.
- `RECOMMENDATION` → weighted score from calibrated confidence + severity + category weight, with **minority-veto** for high-severity safety claims.
- Any judge/aggregator is **blind** and only consolidates verified findings — never negotiates or averages them away.

### 3.5 Termination: a composed condition

Terminate only when **all** hold: no new `VERIFIED` finding for k=2 iterations · `aggregate ≥ threshold` and no unresolved P0/P1 · marginal improvement < ε · within round/token/time caps · score **stable** across repeated judge runs. Escalate (don't force a verdict) on low confidence or persistent high-severity disagreement.

### 3.6 Cross-platform (Windows · Linux · macOS)

- **Language:** Python (3.11+ floor; 3.14 present) as the glue — all analyzers emit JSON/SARIF.
- **Windows runs the container image** (`scripts/entrypoint.py`); the WSL bridge is gone. Linux and macOS run natively through the flake.
- **Analyzers** are invoked as subprocesses with pinned versions; `council doctor` reports availability per platform and lowers `β` for missing tools.
- **Determinism:** pin tool + rule + DB versions; canonical sort; no timestamps/paths/hostnames in the scored payload; CI asserts `scores.json` is byte-identical across two runs on the same commit.
- **Paths:** repo-relative and forward-slashed (a Windows checkout may echo backslashes).
- **Line endings:** `.gitattributes` (LF for scripts, CRLF for `.bat`/`.ps1`).

### 3.7 Durability

In-session agents — the reviewer subprocesses the loop spawns, and `/goal` runs — are **not durable** (a restart records the attempt `unknown`). For restart-safe / cross-profile / human-in-the-loop runs, use the **Kanban Swarm** variant (`council swarm`): durable SQLite board, one worker per specialist, a verifier gated on all workers, a synthesizer, and `--goal` cards for iterate-until-done.

## 4. Data flow (one iteration)

```
git diff (pinned SHA)
   │
   ├─▶ deterministic engine ─▶ scores.json (det)  ─┐
   │                                                │
   └─▶ REVIEWERS ─▶ <dimension>.json ───────────────┤
             generalist × N samples                   │
                                                    ▼
                                      evidence-matrix aggregation
                                                    │
                                      hybrid aggregate + gate
                                                    │
                        ┌───────────────────────────┴───────────────────┐
                        ▼                                               ▼
                 satisfied → /goal done                       not satisfied → fix + re-review
                 (emit control termination=satisfied)         (emit request phase=fix)
```

## 5. Envelope (abridged — full schema in `protocol/`)

> **Designed, not built.** This is the uniform envelope M1 specified, and M1 was never implemented. What ships is one **JSON** file per dimension (`round-N/<dimension>.json`), written by the harness and read by the gate. The shape below is the intended contract if M1 is ever built; the `from:`/`to:` ids in it are illustrative agent names, not profiles that exist (there is one reviewer profile, `council-generalist`).

```yaml
schema_version: "review.msg/v1"
message_id: "01J8…"
correlation_id: null
thread_id: "rev-2026-10-05-pr1842"
from: "security-reviewer"
to: "orchestrator"
type: "finding"            # request|response|finding|score|vote|control|heartbeat
phase: "review"            # intake|review|aggregate|fix|verify
timestamp: "2026-10-05T09:14:03Z"
priority: "high"           # low|normal|high|critical
status: "ok"               # ok|partial|error|blocked|skipped
subject: { repo, commit, base_commit, files: [{path, lines}] }
subject_hash: "sha256:…"
capabilities: { languages: [...], checks: [...], produces: [...] }
findings: [ { id, category, severity, confidence, location, evidence, rule_id, suggested_fix, references, status } ]
scores: { scale, categories: {...}, aggregate, threshold, satisfied, by_agent }
metrics: {}
artifacts: []
actions: []
error: null
extensions: {}
```

## 6. Autonomy modes

| Mode | Reviews | Applies fixes | Escalates |
|---|---|---|---|
| `full` (default) | yes | yes, autonomously | only on block/escalate |
| `semi` | yes | only after approval | at threshold/stall/before edits |
| `advisory` | yes | never | always |

## 7. Integration points into Hermes (from `research/hermes-extension-points.md`)

| Concern | Hook |
|---|---|
| Iteration engine | `hermes_cli/goals.py::GoalManager.evaluate_after_turn`, `judge_goal` |
| Completion contract / score | `goals.py::GoalContract`, `parse_contract` |
| Deterministic gate | `goals.py::GoalGate`, `run_gate` (`/goal gate add`) |
| Judge model | `auxiliary.goal_judge.{provider,model,max_tokens,timeout}` |
| Budget | `goals.max_turns` |
| Convening | `council_loop.py::run_generalist_reviewers` — one profile × N samples, `ThreadPoolExecutor` |
| Concurrency | bounded by samples (5); nothing to tune |
| Reviewer personas | profiles `~/.hermes/profiles/<n>/SOUL.md` + skills |
| Timer heartbeat | `hermes_cli/loops.py::LoopManager`; `loops.*` |
| Durable swarm | `hermes kanban swarm`; `goals.py::run_kanban_goal_loop` |
| Custom command/tool | plugin `ctx.register_command` / `ctx.register_tool` |

## 8. Repository structure

Every top-level entry, what it is, and whether it **ships**. "Ships" means
`flake.nix` copies it into the framework tree, so it is inside the container image
and reachable from a review. Nothing else is: the image carries no test suite, no
documentation and no development verb.

| Path | What it is | Ships |
|---|---|---|
| `flake.nix` | The build: toolchain, framework tree, dispatcher, image, gates, devshell, formatter. `runtimeModules`/`devModules` here **are** the shipping manifest. | — |
| `flake.lock` | Pins nixpkgs. The determinism contract — the same lock gives the same store path on every machine. | — |
| `scripts/` | The implementation: one module per verb. | runtime subset |
| `skills/` | The five rubrics (`reviewer-*`) plus the council skill. Installed into Hermes by `council setup bots`. | yes |
| `bots/` | The orchestrator profile — `SOUL.md`, `bot.yaml`, `profile.yaml`. | yes |
| `tests/` | The suite, plus `golden/` (fixture data whose line count *is* the golden suite's kloc). | — |
| `docs/` | The specification: framework, architecture, decisions, milestones, and per-topic notes. | — |
| `research/` | The research record. `§` references in `docs/*` and `scripts/calibrate.py` point here. | — |
| `runs/` | Curated run reports — the evidence behind each measured claim. | — |
| `pyproject.toml` | ruff + pytest configuration. Deliberately no build backend: `scripts/` runs in place. | — |
| `README.md` · `LICENSE` · `CHANGELOG.md` | Entry point, licence, change record. | — |
| `.github/workflows/` | `ci.yml` (the suite on Linux/macOS/Windows, then the nix gate) and `image.yml` (build and publish the image). | — |
| `.gitattributes` · `.gitignore` | The LF invariant; secrets, run scratch and build output never committed. | — |

### 8.1 What is in `scripts/`, and what ships

`runtimeModules` in `flake.nix` is the shipped set; `devModules` is everything
else. The split is **enforced, not documented**: `checks.commands` reads the CLI's
own verb table (`council --verbs-json`) and fails if a user verb's module is
missing from the shipped tree, if a dev verb's module is present in it, or if the
tree carries `tests/`, `pyproject.toml`, `README.md` or the flake files — none of
which anything at review time reads.

| Module | Verb | Ships |
|---|---|---|
| `council.py` | — (the dispatcher) | yes |
| `council_loop.py` | `review` | yes |
| `score_reviews.py` | `gate` | yes |
| `doctor.py` | `doctor` | yes |
| `probes.py` | `probes` | yes |
| `swarm.py` | `swarm` | yes |
| `sample.py` | `sample` | yes |
| `merge.py` | `merge` | yes |
| `baseline.py` | `baseline` | yes |
| `toolchain.py` | `setup toolchain` | yes |
| `install_bots.py` | `setup bots` | yes |
| `install_dispatcher.py` | `setup dispatcher` | yes |
| `sync_to_skill.py` | `setup skill` | yes |
| `entrypoint.py` | — (the container ENTRYPOINT) | yes |
| `hermes_home.py` | — (shared helper) | yes |
| `calibration.json` · `eval-baseline.json` | — (data the gate and the probes read) | yes |
| `calibrate.py` | `calibrate` | dev |
| `ablate.py` | `ablate` | dev |
| `golden.py` | `golden` | dev |
| `inject_defects.py` | `corpus` | dev |

### 8.2 A module is not a program

Every module refuses a direct invocation — `python3 scripts/ablate.py` — unless
`REVIEW_COUNCIL_DISPATCHED` is set, and `scripts/council.py` sets it. Child
processes inherit it, which is how the harness still runs `probes.py` and
`score_reviews.py`. An agent turn spawned by the harness has it **removed**: a
reviewer reads untrusted repository content, and inheriting the variable would make
the guard inert exactly where the content is untrusted.

The guard is load-bearing for **accident**, not for intent. Several modules act:
`setup bots` writes into `HERMES_HOME`, `setup skill` prunes a skill deployment,
`corpus` plants defects in a repository it is pointed at, and `review`, `sample`
and `ablate` spend real agent turns over the network. Reaching them through `council`
is what puts the pinned toolchain on `PATH` and the right verb surface in front of
the caller, and the guard keeps someone exploring the tree from running one by
mistake.

**It is not a security boundary and must not be described as one.** Any caller who
can set one environment variable passes, and so can an agent with a terminal
toolset. The boundary is the sandbox and the filesystem permissions. A guard that
claimed more than this would be worse than none, because it would invite trust it
cannot hold.

`checks.commands` asserts both halves — a direct invocation must be refused, and
the same verb through the CLI must work — so it fails if the guard is dropped *or*
if it is too eager. `entrypoint.py` is the one exception to the mechanism, not to
the rule: the container's ENTRYPOINT launcher sets the same variable before
running it.

## 9. Hard limits inherited from Hermes (design around, don't fight)

1. `/goal` and `/loop` are **session-bound** (one each per session).
2. Reviewer subprocesses are **non-durable**; `/stop` or session close kills the tree. Each round re-spawns them, and a reviewer that produced no file is an ERROR (gate exit 2), never a pass.
3. `output_schema` validates **JSON only**.
4. **No profile has `delegation`** — not the reviewers and not the orchestrator. The harness is the only thing that spawns agents, so the rubric-bearing fan-out is the only fan-out.
5. The goal/`--until` judge is **fail-open**; the deterministic gate + turn budget are the real backstops.
6. Bot `message_agent` is **string-based and fire-and-forget**; no typed payload field.
7. Cron cannot recursively schedule by default; kanban is single-host.
