# review-council — Milestone Plan

**Goal.** A Hermes-native system that reviews a git diff, scores it with a hybrid of deterministic
analyzer signals and LLM rubric judgement, and iterates until that score clears a threshold (or the
run stalls) — using as few moving parts as the job needs.

**Status.** Research complete (4 parallel reports, `research/`). Built, tested and verified: **M0**,
**M3**, **M4**'s deterministic gate (`scripts/score_reviews.py`), **M5** (the orchestrator sets each
round's goals and judges the round against them; the harness convenes the reviewer), **M6**
(`runs/fixture-fixround-2026-10-06.md`), **M7** (durable swarm, dispatcher, cron, PR path), **M8**,
**M8.5** (the ablation that decided the architecture), **M9**. Two parameters are recorded as ⚠️
rather than ✅, both with the measurement that justifies the state: the **threshold** is a policy
line because the classes do not separate on the hybrid scale, and the **`α_t` weights** are
immaterial because sweeping them flips no verdict. Current release **v1.5.0**. The pass threshold
is read from `scripts/calibration.json` (see `docs/CALIBRATION.md`), so the number the loop enforces
and the number the calibration recommends cannot drift.

**Architecture.** The repo ships **zero shell scripts**: every operation is a Python module under
`scripts/`, reached through one CLI, `council <verb>`. User verbs: `review`, `gate`, `doctor`,
`probes`, `swarm`, `sample`, `merge`, `baseline`, `metrics`, `goal`, `cron`, `pr`. Dev-only verbs
(devshell): `calibrate`, `ablate`, `golden`, `version`, `corpus`, `inventory`. Plus
`council setup {init|skill|bots|toolchain|dispatcher}`, once per machine. `scripts/council.py` owns
the verb table and dispatch; the flake generates one launcher, so `nix run .#council -- <verb>` is
the entry point. `council --help` is the authoritative list — `checks.commands` asserts the shipped
tree matches it.

`toolchain.py` replaced `nix-toolchain.sh` + `nix-toolchain-inner.sh`; `install_bots.py` replaced
`install-bots.sh`; `install_dispatcher.py` replaced `install-dispatcher.sh`; `sync_to_skill.py`
replaced `sync-to-skill.sh`; `inject_defects.py` replaced `inject-defects.py`; `entrypoint.py`
replaced `containers/entrypoint.sh`. The WSL bridge is gone; on Windows the council runs in the
container image. `nix flake check` is the repo's own gate — the suite, nixfmt, statix, deadnix, a
toolchain smoke test, the golden suite and a command-surface check, each able to fail. Verb and
Nix/script boundaries: `docs/NIX.md`.

**Four deviations from what this plan drew** (each a decision, not an omission; the sections below
still describe the original intent):

1. **One reviewer, not five.** M8.5 measured five isolated specialists against one generalist
   sampled five times, at equal cost: the specialists lost twice — 13/22 and 16/22 injected defects
   against 22/22. The five profiles were deleted; their rubrics remain, loaded together by one
   `council-generalist` profile.
2. **JSON files, not the YAML protocol.** M1's Pydantic layer was never built: reviewers write one
   JSON file per dimension and the gate reads them; the uniform YAML envelope remains unbuilt.
3. **The loop's own goal phase runs, not Hermes' `/goal`.** That binding is documented in
   `docs/AUTONOMY.md` but not wired; what executes is the loop's own goals → review → gate cycle.
4. **M1 and M2 are deliberately not built as drawn.** A Pydantic protocol package and a
   `src/review_council/` adapter tree would rewrite a system that works as `scripts/`; their
   deterministic tooling exists as `council probes` plus the pinned `flake.nix` toolchain.

**M9 is delivered, with one gap.** Cross-platform CI runs green on Linux, macOS and Windows for the *framework*, and the nix gate runs on Linux — checking the **darwin declaration** by *evaluation* (`nix flake check --all-systems --no-build`, proven to catch a darwin-only error) rather than by a macOS runner, which is a deliberate cost decision recorded in `docs/CI.md` and, from the user's side, in `docs/NIX.md`. The **analyzer matrix** (`checks.probes`) and the **image build** (`checks.container`) are checks rather than separate workflows, so `nix flake check` verifies both on every push, and `v1.0.0` is tagged and published in both repositories. The gap: the **analyzers are not executed on darwin or Windows** — the pinned toolchain is a nix closure, CI builds Linux only, and darwin execution is left to whoever runs the flake on a Mac (`nix flake check`, the same command). The container is attached to the release as a `docker load` tarball rather than pushed to a registry (`docs/CONTAINER.md`). **M8 is delivered**, with two parameters recorded as ⚠️ rather than ✅: the threshold and the `α_t` weights. Calibration, a labelled eval set and the golden end-to-end regression suite all exist; the A/B harness was built as M8.5; and the metrics are complete — the finding-level pair (SNR, usefulness rate) sits beside recall, and `council metrics` computes acceptance rate, addressed rate and iterations per run from the `status` field. What that verb cannot supply is the judgement itself — a human or the forge must set `status`, and until one does it reports `no data` rather than a number. The **threshold** is a policy line, not a measured boundary: five real repositories were reviewed on the hybrid scale, three pass it unchanged and two fail for verifiable reasons, but the best failing one sits 0.59 points above the known-bad fixture, so no gap exists to derive a line from (`runs/clean-baseline-evaluation-2026-10-17.md`). The **`α_t` weights** stay uncalibrated until evidence justifies reweighting, and `council calibrate --sensitivity` measures that the evidence would change no verdict on any available input, so the defaults stand as a stated policy choice. The M4 *evidence matrix* and *SNR term* are rubric-level, not code.

**How to read.** Each milestone has a *Goal*, *Research inputs*, *Deliverables* and *Acceptance
criteria* checkable by a command or an observable artifact. `Size` is relative effort (S/M/L);
`Depends` lists prerequisites.

---

## 0. Design pillars (fixed by research + the kickoff interview)

| Pillar | Decision | Source |
|---|---|---|
| Foundation | Hermes-native (Bots/profiles, `/loop`+`/goal`, `delegate_task`, skills, plugins, cron, kanban) | interview |
| Platform | Unix natively via the flake; **Windows via the container image**; WSL2 | interview |
| Languages | Language-agnostic framework; **Python first-class**; JS/TS, Go, Rust adapters incremental | interview |
| Satisfaction | **Hybrid**: deterministic analyzer signals + LLM rubric → weighted aggregate; terminate on threshold **and** stall | interview |
| Roster | Core five: security, performance, readability/maintainability, correctness/testing, architecture | interview |
| Autonomy | Default **fully autonomous** (auto-fix + re-review); configurable to semi / advisory | interview |
| Scope | Git diff / PR changeset only | interview |
| Protocol | One envelope for every message; **YAML** on the wire; JSON Schema as the contract | `research/inter-agent-protocol.md` |
| Anti-gaming | Hold rubric out of iterating context; execution-based checks; SNR term; oscillation detection | `research/sota-multi-agent-code-review.md` |

> **This table records the inputs, not the outcome.** Two entries were overturned: the *Roster* is
> now one generalist sampled N times, not five isolated specialists (M8.5), and `delegate_task` was
> removed from the foundation because a delegated child cannot load another profile's rubric (M4).

### 0.1 Three reconciliations the research forced (read these first)

1. **YAML vs `output_schema`.** Hermes validates `delegate_task`'s `output_schema` as **JSON only**
   (`tools/delegation_output_schema.py` calls `json.loads`). So the canonical protocol is authored in
   **Pydantic v2 → generated JSON Schema Draft 2020-12**; agents exchange **YAML files** validated
   against it; children return **JSON** (auto-validated, `schema_valid`/`schema_errors`); the
   orchestrator serializes JSON → YAML for the human/agent bus.
2. **`/loop` vs `/goal`.** `/loop` is timer-driven; its `--until` judge is **fail-open** (any error →
   continue). `/goal` is judge-driven and runs **deterministic quality gates before the judge**, plus
   completion contracts. The scored loop is evidence/judge-driven, so the primary engine is `/goal` +
   a completion contract whose `verification` encodes the score + a deterministic gate
   (`scripts/score_reviews.py`); `/loop --until "<score condition>"` is the documented alternate, and
   `/loop 10m /recap` heartbeats coexist because an active goal defers loop ticks.
3. **Determinism vs dynamism.** Performance and documentation *substance* cannot be scored
   deterministically; vulnerability/license DBs drift. Each category therefore carries a **`β`
   weight** (analyzer coverage) governing how much the deterministic vs LLM score counts.

---

## M0 — Foundations & scaffolding
**Goal.** A cross-platform repo skeleton with project context, decisions, and CI on Windows + Linux + macOS from day one. **Research inputs.** None (enabling).
**Deliverables.** Repo layout (`docs/ARCHITECTURE.md` §8): `protocol/`, `src/review_council/`, `scripts/`, `skills/`, `bots/`, `research/`, `tests/`, `.github/workflows/`; `AGENTS.md` project context (Hermes loads it in `workdir`); `pyproject.toml` (Python 3.11+ floor; 3.14 present), `ruff` + `pytest`; `LICENSE`, `.gitattributes`, `.gitignore`, `docs/DECISIONS.md`; `.github/workflows/ci.yml` — matrix `windows-latest, ubuntu-latest, macos-latest`, lint + tests.
**Acceptance.** `git clone` → `pytest` green on all three OSes; `hermes` opened in the project loads `AGENTS.md`.
**Size** S · **Depends** —

---

## M1 — The uniform YAML protocol (schema + validation)
**Goal.** One message envelope every agent can parse and iterate, versioned and testable. **Research inputs.** `inter-agent-protocol.md` (envelope fields, tri-state findings, control/termination signals, versioning).
**Deliverables.** `protocol/models.py` — Pydantic v2 `Envelope`, `Subject`, `Finding`, `Scores`, `Control`, `Error`, `Capabilities`; generated `protocol/envelope.schema.json` (Draft 2020-12) + `make schema` drift check. `schema_version: "review.msg/v1"`; `type` enum (`request|response|finding|score|vote|control|heartbeat`); `phase` enum (`intake|review|aggregate|fix|verify`); `satisfied` predicate (`aggregate >= threshold AND no open high/critical`). Golden fixtures `protocol/fixtures/valid/*.yaml` (intake, findings, score, aggregate, fix, verify, terminate) + `invalid/*.yaml`; `review-council validate <file>` CLI. Versioning policy: additive-minor, `extensions.<vendor>.*`, `additionalProperties: true` at root / `false` inside `findings[]`.
**Acceptance.** `validate` accepts every valid fixture, rejects every invalid one, exit-code correct; CI fails on `models.py`↔schema drift; JSON round-trips to YAML losslessly.
**Size** M · **Depends** M0 · **Not built** (deviations 2, 4).

---

## M2 — Deterministic scoring engine (the anchor)
**Goal.** Reproducible 0–100 per-category scores from real analyzers, Python wired first-class. **Research inputs.** `deterministic-quality-tooling.md` (tool matrix, normalization math, determinism rules, calibration).
**Deliverables.**
- `src/review_council/platform.py` — cross-platform adapter (OS/shell detection, path normalization, native-vs-WSL execution); `src/review_council/tools/` — analyzer adapters (`detect()`, `run()`, `parse() -> findings|metrics`), Python first: semgrep, bandit, gitleaks, ruff, pylint, radon, lizard, coverage.py, pytest, mutmut, pip-audit, osv-scanner, import-linter, pydeps, interrogate, pydocstyle, reuse/scancode.
- `manifest.json` — pinned tool versions, config sha256, DB versions, KLOC (pinned LOC counter), and the manifest hash identifying a score lineage; `scores.json` with full traceability.
- `src/review_council/score/` — severity weights, severity-weighted density per KLOC, **Hill normalization**, **threshold curves**, **weighted geometric mean** within a category, hard caps/gates, KLOC-weighted cross-language aggregation, hybrid `β·score_det + (1−β)·score_llm` with bounded, evidence-logged LLM deviation; `council doctor` reports per-platform tool presence — missing tools lower `β`, never silently score 100.
**Acceptance.** Two runs on one commit produce byte-identical `scores.json` (canonical sort, no timestamps); unit tests for Hill, curves, geometric mean, caps, cross-language weighting; `doctor` degrades gracefully (β drops, run completes); Python wired, JS/TS/Go/Rust columns weight 0.
**Size** L · **Depends** M1 · **Not built as drawn** (deviation 4): the tooling exists as `council probes` + the pinned `flake.nix` toolchain.

---

## M3 — Specialist reviewer agents (the five Bots)
**Goal.** Five isolated specialists, each a narrow rubric + diversified reasoning, emitting schema-valid findings. **Research inputs.** `sota-multi-agent-code-review.md` §8.1.
**Deliverables.**
- Five Hermes profiles under `bots/` + `~/.hermes/profiles/<name>/`: `security-`, `performance-`, `readability-`, `correctness-`, `architecture-reviewer` — each a `SOUL.md` persona, per-profile model pin, `--description`; five rubric skills `skills/reviewer-*/SKILL.md` — anchored, narrow, one primary dimension per finding.
- Finding contract (§M1): `{dimension, file, line_range, evidence_span, claim, claim_type ∈ {FACT,RECOMMENDATION}, severity, calibrated confidence, falsifiable_check, suggested_fix}`.
- **Stage A verification**: each FACT checked against the pinned commit SHA (grep/ast-grep/linter), stamped `VERIFIED|REFUTED|AMBIGUOUS`; refuted findings dropped and counted against precision. Reasoning-strategy diversification (systematic enumeration for correctness, adversarial simulation for security, backward reasoning for architecture).
**Acceptance.** Each specialist runs standalone on a seeded-defect fixture and returns schema-valid findings; the rubric loads via skill and the reviewer sees only diff + rubric; REFUTED findings are excluded.
**Status.** Delivered with one change: M8.5 measured five isolated specialist profiles against one generalist sampled five times at equal cost, and the specialists lost — 13/22 and 16/22 injected defects against 22/22. The five per-dimension profiles were deleted; the five rubrics are loaded together by one `council-generalist`, sampled N times. Rubrics, finding contract and verification are as designed; only the fan-out changed.
**Size** L · **Depends** M1, M2

---

## M4 — Orchestrator, aggregation & hybrid score
**Goal.** Fan-out, aggregate with an evidence matrix, compute the hybrid score, emit the gate. **Research inputs.** `sota-multi-agent-code-review.md` §8.2–8.3; `hermes-extension-points.md` §7.3–7.4; `inter-agent-protocol.md` §2.6–2.7.
**Deliverables.**
- Orchestrator profile + `skills/review-council-orchestrator/SKILL.md`; fan-out as one `delegate_task` batch (one task per specialist) with a uniform **JSON** `output_schema`; parent reads `schema_valid`/`schema_errors`; one bounded correction retry.
- **Evidence-matrix aggregation**: dedupe by `path:line`+claim; tri-state `AGREE|DISAGREE|DID_NOT_EXAMINE` (**silence ≠ agreement**); union of `VERIFIED` facts (no voting); one bounded anonymized cross-examination round for `AMBIGUOUS`; weighted score with **minority-veto** for high-severity safety claims; the judge is **blind** and only consolidates. Hybrid score + `reviews/latest.json` and per-specialist `reviews/<specialist>.yaml`.
- `scripts/score_reviews.py` — the deterministic gate: exits 0 iff `SCORE ≥ threshold` and no open CRITICAL, printing a bounded tail as the continuation prompt. Anti-gaming: **rubric held out of the iterating context**, SNR term (penalizes "flag everything"), per-iteration finding cap.
**Acceptance.** One end-to-end round on a fixture diff yields an aggregate score + gate exit code; a verified finding from one reviewer alone still counts at full weight; a "flag everything" reviewer does not raise the aggregate (SNR works).
**Status.** Delivered with three changes: **the fan-out is not `delegate_task`** — built, found broken, removed, because a delegated child inherits the *parent's* `HERMES_HOME` and cannot load another profile's rubric, silently producing generic subagents wearing dimension labels (the harness now spawns the reviewer profile itself; no profile carries `delegation` — `docs/BOTS.md`); **the evidence matrix and SNR term are rubric-level, not code** (the orchestrator prompt directs aggregation, and `scripts/score_reviews.py` recomputes the score from the files and never trusts a number an agent asserted); and **the gate is the shipped `scripts/score_reviews.py`**, reading `<dimension>.json` rather than `reviews/latest.json`, exposed as `council gate`.
**Size** L · **Depends** M2, M3

---

## M5 — Iteration loop, termination & autonomy modes
**Goal.** The scored loop that re-runs reviewers until satisfaction, safely. **Research inputs.** `hermes-extension-points.md` §7.2; `sota-multi-agent-code-review.md` §8.4.
**Deliverables.**
- **Primary engine:** `/goal` + completion contract — `verify: scripts/score_reviews.py exits 0 reading reviews/latest.json (SCORE >= threshold and no open CRITICAL)` — plus `/goal gate add scripts/score_reviews.py`; tune `auxiliary.goal_judge.*` and `goals.max_turns`. **Alternate:** `/loop --until "<score condition>"` with its fail-open caveat, plus a `/loop 10m /recap` heartbeat.
- **Composed termination** (all must hold): no new VERIFIED findings for k=2 iterations; score ≥ threshold **and** no unresolved P0/P1; marginal improvement < ε; within round/token/time caps (1–2 automated, 3–5 interactive); score **stable** across repeated judge runs.
- **Anti-gaming:** execution-based checks (tests/build) preferred; hidden-anchor audit; invariant checks; **oscillation detection** (regression/flip → stop and escalate). **Autonomy modes:** `autonomy: full | semi | advisory` (default `full`), `semi` gating before edits and `advisory` never editing; low judge confidence or persistent high-severity disagreement → "human review recommended".
**Acceptance.** On a seeded-defect fixture the loop drives the score up across ≥2 rounds and terminates when satisfied; a stall fixture stops with `blocked`/escalate after k rounds; `goals.max_turns`/`loops.max_ticks` respected and `semi` blocks before the first edit; an agent that can see the score cannot terminate by approving everything.
**Status.** Delivered with one change: the `/goal` binding is **documented but not wired**. What runs is the loop's own goal phase — the orchestrator writes one goal per dimension, the harness hands them to the reviewer, and the orchestrator judges the round against them; the deterministic gate remains the authority, and `/goal`'s fail-open caveat is recorded in `docs/AUTONOMY.md`.
**Size** L · **Depends** M4

---

## M6 — Fix application & verification round
**Goal.** Close the loop: apply fixes, then re-review at the new commit SHA. **Research inputs.** `inter-agent-protocol.md` §2.4; `sota` §7.8 (oscillation).
**Deliverables.** Fixer agent (only in `full`/`semi`-approved mode) applies targeted fixes and produces a new commit; verification round re-reviews the **new** commit with findings `status: fixed|wontfix|open`; oscillation guard (role asymmetry — critic flags, fixer fixes — context isolation, round limits); fix ledger linking every applied fix to its finding id + verification result.
**Acceptance.** Seeded defects are fixed and independently verified `fixed`; a deliberately-oscillating fixture stops and escalates; no fix is applied in `advisory` mode.
**Size** M · **Depends** M5

---

## M7 — Durability, integrations & surfaces
**Goal.** Survive restarts and meet the user where they work. **Research inputs.** `hermes-extension-points.md` §6, §7.5, §8.
**Deliverables.** **Kanban Swarm variant** (durable, restart-safe): `hermes kanban swarm "<root>" --workers <5> --verifier score-verifier --synthesizer orchestrator`, `--goal` cards for iterate-until-done, structured `kanban_complete` handoff. **Cron** for unattended scheduled reviews (`cron.*`), noting `cron.allow_agent_scheduling: false`. **Bot-to-bot group chat** (2–6 Bots, `@mention`), documenting the string-only, fire-and-forget `message_agent` limit (structured content embedded as a fenced YAML block). **Integration target:** local CLI/desktop first, then a GitHub PR path and a CI (GitHub Actions) path.
**Acceptance.** A kanban swarm run survives a gateway restart and completes with a verified score; a cron job runs unattended and delivers the report; the GitHub PR path posts the review as PR comments (later milestone, clean path proven).
**Status.** Shipped.
- ✅ Surfaces read from `--help` before design: `hermes kanban swarm` (workers → verifier → synthesizer), the kanban board verbs, `hermes cron create`.
- ✅ The swarm verb (`scripts/swarm.py`, `council swarm`) builds the durable round from repo, round and sample count; 13 tests pin the shape — worker count, profiles, and that the **verifier is told to run the gate rather than to have an opinion**.
- ✅ A real swarm run, end to end: root → worker → verifier → synthesizer; the root wrote `goals.json`, the worker wrote `generalist-1.json` via `council sample`, and the verifier ran `merge` then `gate` and reported the gate's own numbers.
- ✅ A durable dispatcher (`council setup dispatcher`) — a systemd user unit, enabled with linger, so dispatch survives logout and reboot.
- ✅ Restart survival — M7's stated criterion: the dispatcher restarted mid-run and the round completed with a verified score (94.4 ≥ 87.1141, satisfied, β live per dimension); the in-flight worker was undisturbed (it detaches from the dispatcher's cgroup).
- ✅ **Cron** — `council cron <repo>` prints (or `--install`s) a `hermes cron create`
  job whose prompt tells the agent to **run** the council and report the gate's numbers
  verbatim, never to review the code itself: a cron agent that reviewed on its own would
  be a reviewer outside the framework, and its score would not be the score the gate
  enforces. It prints rather than installs by default, because a schedule outlives the
  session that made it; `--install` creates it and then confirms it appears in
  `hermes cron list`. `cron.allow_agent_scheduling` is false, so a reviewer cannot
  schedule its own follow-ups — only a person can. Verified: installed, listed, removed.
- ✅ **Re-claim** — the last durability branch, exercised end to end on a throwaway
  board: claim → reclaim → `ready` → re-claim as `run 2`, with `max-retries: 2` bounding
  it. The council-side half was verified too — the root card's idempotency key returns
  the *same* card id on a repeat `council swarm`, so a reclaimed dispatch cannot fork a
  second round. Record: `runs/reclaim-verification-2026-10-17.md`. Not exercised: a claim
  left to expire on its own, and a worker dying mid-`council sample`.
- ✅ **The GitHub PR path** — `council pr <run-dir> --repo owner/name --pr N` posts the
  run's verdict as a pull-request review. Every number in the body comes from
  `score_reviews.evaluate`, the same function the gate runs, so a PR comment cannot
  disagree with `council gate` about the same run. It prints the request by default and
  posts only with `--post`; the default event is `COMMENT`, which cannot block a merge,
  and `--event auto` maps a failing gate to `REQUEST_CHANGES` for teams that want the
  gate enforced on the PR. Two hazards are handled rather than left to the operator: a
  run is **never posted twice** (the body carries an HTML-comment marker naming the run
  and the PR, checked against the existing reviews first, because GitHub has no
  idempotency key), and the review is **pinned to `commit_id`** from the run's
  `meta.json` so it attaches to the commit the council actually scored rather than the
  PR's latest. The token is read from `GITHUB_TOKEN`/`GH_TOKEN` and never accepted on
  the command line. Proven: 24 tests against a stub GitHub API that records the request
  (endpoint, `Bearer` header, payload, no token in the body), the idempotency skip, the
  401/404/422 messages, and — through the real CLI — print, post, skip and refuse. Not
  proven: that github.com *accepts* the payload, which needs a token and a live PR; the
  read half was exercised against the real API unauthenticated.
**Note.** M7 adds moving parts back after M8.5's collapse, defensible only because it buys **survival**, not quality — the swarm runs the same profile and rubrics, so a swarm run scoring *better* than the plain loop would be a bug, not a result.
**Size** L · **Depends** M6

---

## M8 — Evaluation, calibration & governance
**Goal.** Prove it works and tune it on evidence, not intuition. **Research inputs.** `sota` §8.5, §6.5; `deterministic-quality-tooling.md` §7.
**Deliverables.** Labeled **eval set** (seeded defects + known-clean diffs) with ground truth; a metrics harness (precision, recall, F1, **SNR**, usefulness rate, acceptance rate, % comments addressed, avg iterations/PR); **calibration** of `d*`, `k`, `x_bad/x_good`, `α_t`, `β`, threshold, recorded in the manifest; an A/B harness for prompt/rubric/weight changes; a golden end-to-end regression suite in CI.
**Acceptance.** Metrics reported on the eval set and thresholds calibrated and stored in the manifest ✅; the regression suite catches a deliberate rubric/weight regression ✅ — demonstrated, not asserted: seven tests each break one input (a dimension weight, a severity weight, the tool table, the invocation aliases, `halflife_k`, a `d*`, the threshold) and require the suite to notice.
**Status.** Delivered, with one parameter deliberately left at its default and the reason
measured rather than asserted. Every deliverable is built: calibration of `d*`, `k` and
the threshold; the labelled eval set; the metrics harness in both halves — finding-level
(SNR, usefulness) and interactive (`council metrics`: acceptance, addressed, iterations);
the A/B harness (M8.5); the golden end-to-end suite; and `α_t` sensitivity, which shows
the weights cannot flip a verdict on any input available. What is *not* claimed: the
threshold still rests on one known-good sample, the LLM half is uncalibrated, and `α_t`
is a policy choice because a weight encodes consequence cost rather than accuracy.
- ✅ **Calibration of `d*`, `k` and the threshold** — `scripts/calibrate.py` + `scripts/calibration.json` (`docs/CALIBRATION.md`); also fixed a real defect where the findings term used a raw *count* where §3 requires a *density*.
- ✅ **Labeled eval set** — a graded defect ladder (rungs 0/1/2/4/8/16) built deterministically from a seed, so ground truth is known by construction.
- ✅ **Metrics harness, finding-level half** — `score_arm` now reports the signal-quality pair beside recall: `signal`, `noise`, **`snr`** (signal/noise over *findings*) and **`usefulness_rate`** (share of findings that describe something real), for every arm, persisted in the run's `scores.json` and printed in the `council ablate report` table. This is the reading M8.5 could not make: its rule compares `true` (distinct planted defects found), which recall can be bought for with volume — and the research names that a trust hazard (CR-Bench measured recall 27.01% → 32.76% while SNR fell 5.11 → 1.95, `sota` §3.6). Both are **floors**, not point estimates: the matcher is location-based, so a true finding pointing where the manifest names nothing counts as noise, and CR-Bench's second signal class (a valid suggestion that is not a bug) has no representation in a planted-defect manifest.
  **The rule is unchanged, deliberately.** `MARGIN` is pre-registered and editing it after a run invalidates the run, so the pair is *reported* rather than folded into the verdict. A future reader can now see whether a recall win was volume-driven; the 22-defect outcome was not re-decided.
- ✅ **Metrics harness, the interactive half** — `council metrics` computes
  **acceptance rate**, **% comments addressed** and **iterations per run** from the
  `status` field every finding already carries (`open|accepted|fixed|wontfix|rejected`).
  It reports `null` and names what is missing whenever nobody has judged a finding,
  because no data is not a zero rate. Two corrections to what this milestone assumed:
  **iterations never needed an operator** — `outcome.json` already records one score per
  round, so its length *is* the iteration count, and that half was available all along;
  and the record the other two need was **already in the schema**, so the gap was a
  missing computation rather than a missing signal. What remains genuinely absent is the
  *source* of the judgements: a human or the forge must set `status`, and until one does
  the metrics are `no data` by construction.
- ✅ **A/B harness** — built as M8.5 (`scripts/ablate.py`): four arms at equal cost against a pre-registered rule; the answer was **collapse** (M8.5).
- ✅ **Golden end-to-end regression suite** — `scripts/golden.py` + `tests/golden/`, run by `council golden --check` and by `pytest`. Two layers, because the pipeline fails differently in each: a **round** layer (reviewer files → hybrid verdict, pinning det, β, the Hill density, the aggregate and pass/fail) and a **merge** layer (samples + probes → per-dimension files, pinning the `tools_run` union and the probe seed). `tests/test_golden.py` is the criterion executed: each test mutates one scoring input, asserts the check fails, restores it, asserts it passes. Built because the β defect shipped with **210 green tests** — every merge test supplied its own fixture and nothing asserted a number end to end, so two halves could both drop `tools_run` while the suite stayed green and the score quietly became the LLM's judgement (see M8.5).
- ⚠️ **The threshold is provisional, and the hybrid scale cannot settle it.** It rests on
  one known-good sample. Five well-regarded repositories were reviewed end-to-end on the
  hybrid scale (`runs/clean-baseline-evaluation-2026-10-17.md`): **three pass 87.1141
  unchanged** (98.40, 94.83, 89.23) and **two fail for verifiable reasons** — zero-to-nix
  at 80.63 on 45 dependency CVEs, flake-utils at 60.86 on two blocking findings. The
  classes overlap (best failing repo 80.63 vs golden defects fixture 80.04), so no
  threshold is derivable: a max-margin line would be 80.34 with a margin of 0.30. The
  shipped value is therefore a **policy line** that happens to sit above every repo in the
  sample with a real finding and below every one without. Nothing argues for moving it;
  what would is a larger sample.
- ⚠️ **`α_t` weights are uncalibrated, and measured to be immaterial.** §7 says reweight
  only with evidence. The evidence does not exist — a weight encodes *consequence cost*
  per dimension, which needs incident data, not defect labels — and
  `council calibrate --sensitivity` shows it would change nothing on any input
  available: sweeping each weight from 0 to 3× moves the defects fixture at most 8.63
  points and flips **no verdict**, and zeroing security entirely still leaves it at 82.92
  against an 87.11 threshold. So the working defaults stand as a documented policy
  choice rather than an uncalibrated guess. Recorded in `docs/CALIBRATION.md`, with the
  caveat that a score near the threshold with a large spread could still be
  weight-sensitive — which the tool reports rather than assumes away.
**Size** M · **Depends** M5, M6

---

## M8.5 — The validation gate (ablation)
**Goal.** Decide by measurement whether five isolated specialists earn their cost over one generalist given the same budget — the assumption every other milestone rests on and none tests. **Research inputs.** `sota-multi-agent-code-review.md` §8.1 — the dimension-design claim this milestone exists to falsify.
**Deliverables.**
- `scripts/ablate.py` — four arms, all through the same `run_hermes` path, `council_loop.py` untouched:

  | Arm | Profile | Rubrics | Samples | Turns |
  |---|---|---|---|---|
  | `single` | `council-generalist` | all five | 1 | 1 |
  | `generalist-rubrics` | `council-generalist` | all five | 5 | 5 |
  | `generalist-bare` | `council-generalist-bare` | none | 5 | 5 |
  | `specialists` | the five reviewer profiles | one each | 1 each | 5 |

- Ground truth without a manifest: on the seeded ladder, rung 0 is declared known-good (every finding there is a false positive) and rung N's planted defects are recovered by diffing the rungs (`ablate.py truth`). A run record in `runs/` carries the numbers, including the ones that hurt.
**The pre-registered rule** (fixed before any run, so the outcome cannot be rationalised after it): the five specialists must find at least **1.5×** the distinct TRUE defects of the best single-agent arm at equal cost, or the architecture collapses to one reviewer. `specialists` and `generalist-rubrics` both cost 5 turns, so that pair is the comparison; `generalist-bare` separates the two things the design bundles — five contexts and the 811 lines of rubric. Editing `MARGIN` after a run invalidates the run.

### What building the corpus taught (read this before trusting any verdict)
Three candidate corpora, two discarded:
- **The seeded ladder is unusable here.** Its defects are files named `seeded_secret_0.py`, which announce their own answer, so every arm found all 8 (recall 1.0, separating nothing); its apparent false positives are findings in `scripts/probe*.py` and `score_reviews.py`, because the ladder is copied from this repository, so its "clean" rung is not clean. Pipeline smoke test only.
- **A real repository cannot supply ground truth once the council has fixed it.** After eight rounds, the corpus's only remaining truth is the council's own output; scoring the council against itself proves nothing.
- **Injecting into a cleaned repository is the workable route** (`council corpus`): the base is verified clean and the manifest is independent by construction.

Two constraints on any injection, both learned by having a corpus fail them:
1. **A defect the repo's own tooling reports is not a defect the reviewers are tested on.** Formatting must be clean by the repo's formatter or the gate fails and the defect is visible to `treefmt`; no injection may trip `statix`, `deadnix`, `nil` or the rest. Check by running the repo's full gate against the corpus — with building, not `--no-build`.
2. **A defect that breaks evaluation is trivial.** A plain definition where another module already defines the option is a hard conflict error, not a silent defect; a silent override needs explicit priority. Verify by evaluating the corpus; a failure is a broken corpus.

**Satisfiability depends on difficulty, not corpus size.** If one generalist turn finds 8 of 10 defects, five samples find 9 or 10, and the specialists would need 14+ distinct defects to clear 1.5× when only 10 exist — the verdict is arithmetically forced. A corpus whose defects each contradict a comment beside them is too easy (findable by reading one file carefully); it must contain the **silent class** — nothing wrong in a file alone, the defect existing only as a relationship *between* modules (a plain definition beating another module's `lib.mkDefault`, or a list-typed option merging where a restriction was intended).
**Acceptance.** The ladder separates a clean rung from a seeded one (recall > 0 on the seeded rung; clean-rung findings counted as false positives); the rule is evaluated and printed with the losing branch stated as plainly as the winning one; corpus findings are labelled by the operator so precision on unfamiliar code is measured, not assumed.

### Outcome — COLLAPSE
`runs/ablation-10-defect-2026-10-11.md` (inconclusive — corpus too easy, verdict arithmetically forced) and `runs/ablation-22-defect-2026-10-11.md` (decisive). On the 22-defect corpus, at equal cost:

| Arm | Turns | True defects | Recall |
|---|---:|---:|---:|
| `single` | 1 | 12 / 22 | 0.545 |
| `generalist-rubrics` | 5 | **22 / 22** | **1.000** |
| `generalist-bare` | 5 | **22 / 22** | **1.000** |
| `specialists` | 5 | **13 / 22** | **0.591** |

**The five specialists found 13 of 22; one generalist with five samples found all 22 (0.59×, rule needs ≥1.5×).** The rule says collapse to a single reviewer run several times: one profile instead of six, no rubric fleet, materially higher recall here. A repeat run reached the same verdict (0.73×) and added error bars: the generalist *with* rubrics scored 22/22 twice with zero variance, while the rubric-less generalist fell from 22/22 to 17/22 — the rubrics make the generalist repeatable, and the first run's reading that they changed nothing was an artefact of measuring each arm once. Caveats: one corpus, two runs; recall is location-based so false-positive counts are a floor; the corpus and scorer were written by the same person who wrote the rule they test.

**This milestone is complete. Its result argues against the architecture the project is built on, and that is the point of running it.**

**One defect shipped with the collapse.** Collapsing to a single generalist silently disabled the deterministic half: `GENERALIST_PROMPT` never asked the reviewer to report `tools_run`, and the merge hardcoded it to `[]` — so β was 0 for every dimension and `score = β·det + (1−β)·llm` collapsed to `llm` alone; the toolchain, probes and `det` contributed nothing to the number the gate enforced, and nothing downstream said so. Found by reading a run, not by the suite (all 210 tests passed). Scope, checked: **the ablation result stands** — `score_arm` returns recall and false positives, never a hybrid score; the pre-collapse `runs/` records are untouched (they quote real β — 0.40, 0.80, 0.33 …); what was affected is the collapsed mode's own score, including the e2e PASS reported here, which was LLM judgement alone and is retracted as such. Fixed with six tests, one asserting β > 0 through `merge → deterministic_score`, with β == 0 pinned beside it as the documented failure mode.
**Size** M · **Depends** M5, M6

---

## M9 — Hardening, packaging & release
**Goal.** Ship it as a reusable, documented Hermes capability.
**Deliverables.** Full cross-platform CI (Windows/Ubuntu/macOS) incl. the analyzer matrix; docs for install, configure, run, extending a reviewer and adding a language; the orchestrator + rubrics packaged as installable Hermes **skills** (optionally a plugin exposing `/review-council`); versioning + changelog, `v1.0` tag.
**Acceptance.** Fresh machine → documented install → green end-to-end run on all three OSes; a new reviewer can be added following the docs alone.
**Status.** Delivered, with one gap that is closed and one that is accepted.
**The analyzer matrix is built**: `checks.probes` runs `council probes --all` against a fixture and asserts every analyzer that needs no fixture content actually **ran** — a tool present but broken lowers beta silently and hands the score to the LLM, which `toolchain-built` (five binaries exist) could not catch. It is a check rather than a workflow, so it runs on every system CI builds, which is Linux.
**The image is verified by the gate too**: `checks.container` builds `.#container`, so a broken image fails `nix flake check` instead of a workflow of its own. `image.yml` is now tags-only and does the one thing a check cannot — publish.
**Darwin is declared and its declaration is checked, but not built.** `systems` includes `aarch64-darwin`, and the gate evaluates every declared system with `--all-systems --no-build` — a command shown to have teeth (a canary referencing Linux-only `pkgs.systemd` made it exit 1 while a plain `nix flake check` exited 0). What is deliberately not paid for is a **macOS runner that builds the darwin toolchain**: macOS minutes count tenfold, the closure is 239 fetched paths and 5 built ones, and the author uses no Mac. So execution on darwin is left to the user, documented in `docs/NIX.md`, where one `nix flake check` settles it. `x86_64-darwin` cannot be declared at all — nixpkgs 26.11 dropped it upstream.
**The accepted gap** is that the analyzers are never *executed* on darwin or Windows: CI builds Linux, and the pinned toolchain is a nix closure, so a Windows nix job would be a second toolchain to keep working.

**What IS executed on all three OSes is the no-toolchain path**, and it is now tested
rather than asserted. `tests/test_fresh_machine.py` runs the real `probes.py` and
`doctor.py` in a subprocess with `REVIEW_COUNCIL_TOOLCHAIN` removed **and `PATH` pointing
at an empty directory** — the second half matters, because `toolchain.env()` resolves the
toolchain itself when `nix` is on PATH, so unsetting the variable alone still runs every
analyzer. Measured on that path: **6 of 20 probes run** (the stdlib set), **13 report
`ran: false` with a reason**, **zero report a signal they did not measure**, and
`doctor` reports **beta 0.32** rather than 1.00. So a machine with Python and nothing
else can still run a review, and the score degrades visibly instead of quietly becoming
the LLM's. The test has teeth: making `statix` report `ran: true` when it cannot run
fails it. It runs in the pytest matrix, so the claim is now checked on Linux, macOS and
Windows on every push — which is the part of "green on all three OSes" that was never
tested. What remains unexecuted there is the *pinned toolchain*, exactly as stated above.
`v1.0` is tagged `v1.0.0` in both repositories. The container is attached to the release as a `docker load` tarball instead of being pushed to a registry: a release asset is downloadable **anonymously** (verified 200 with no token) while an Actions artifact is not (401 unauthenticated), and a registry is a service to run and a permission to hold — see `docs/CONTAINER.md`.
**Size** M · **Depends** M8

---

## 1. Dependency graph

```
M0 ─▶ M1 ─▶ M2 ─┐
                ├─▶ M4 ─▶ M5 ─▶ M6 ─▶ M7 ─▶ M9
        M1 ─▶ M3 ┘         └─▶ M8 ──┘
```

## 2. Research → decision traceability

| Finding (source) | Applied in |
|---|---|
| `output_schema` is JSON-only (`hermes-extension-points.md` §4.3, §8.3) | §0.1(1), M1, M4 |
| `/goal` gates run before the judge; `/loop --until` is fail-open (§2.2, §1.6) | §0.1(2), M5 |
| Score gaming: judge pass-rate 0.72→0.94 while truth stayed 0.20 (`sota` §7.3) | M4, M5 anti-gaming |
| Majority voting discards minority edge cases; silence ≠ consensus (`sota` §6.3) | M4 aggregation |
| Structured evidence-grounded disagreement beats debate (`sota` §3.10) | M3, M4 |
| SNR + usefulness as first-class metrics (`sota` §3.6, §6.5) | M2, M4, M8 |
| Convergence ~3–5 rounds; hard caps 1–2/3–5 (`sota` §5.7) | M5 termination |
| Hill normalization + weighted geometric mean + β (`deterministic` §1) | M2 |
| Performance/docs can't be scored deterministically (`deterministic` §8) | M2 β, M8 |
| Envelope fields + control/termination signals (`protocol` §2) | M1, M4, M5 |
| Pydantic → JSON Schema single source of truth (`protocol` §3) | M1 |
| Delegate children non-durable → kanban for restart-safety (§4.6) | M7 |

## 3. Decisions that were open, and how they closed

Each was answered by building or measuring, not by a later conversation. The original
question is kept so a reader can see what was asked.

| # | question | resolved to |
|---|---|---|
| 1 | **Iteration engine** — `/goal`+gate, or `/loop --until`? | The loop's **own goal phase** runs: the orchestrator writes one goal per dimension, the harness hands them to the reviewer, and the orchestrator judges the round against them. `/goal` is documented, not wired (M5); `/loop --until` stays the documented alternate with its fail-open caveat. |
| 2 | **Integration target** — local, PR bot, or CI? | **Local CLI first**, and it is the only surface built. The GitHub PR path is left unbuilt rather than built and unverified (`docs/MILESTONES.md` M7). |
| 3 | **Model tiers** — cheap for tooling, strong for judgement? | Expressed as **config, not a hardcoded choice**: every member carries `model`/`provider` and `None` inherits the profile's, so a user pins tiers in `$HERMES_HOME/review-council.toml` rather than this repository picking models for them. |
| 4 | **Budget guardrails** — per-run ceiling? | `max_rounds` (default **3**), `min_rounds`, and `budget_seconds`; `council_loop.out_of_budget` enforces the wall clock and `decide_stop` the round count. |
| 5 | **Threshold + weights** | Threshold **87.1141** from `scripts/calibration.json`, weights in `score_reviews.WEIGHTS` (security .30, correctness .25, readability .20, architecture .15, performance .10). Both calibrated in M8, not guessed (`docs/CALIBRATION.md`). |
| 6 | **Bot transport** | The **file bus**: reviewers write one JSON file per dimension and the gate reads them. No group chat, no orchestrator-mediated message passing — a file is deterministic, git-versionable, and readable after the fact. |
