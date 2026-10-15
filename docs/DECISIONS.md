# review-council — Decisions Log

Source of truth for *locked* choices (kickoff interview) and the *resolved* design points from
research. Everything below is **locked** unless listed under "Still open".

## Locked (interview, round 1)

| # | Decision | Choice |
|---|----------|--------|
| 1 | **Foundation** | **Hermes-native.** Runs inside the Hermes toolchain (Bots/profiles, `/loop`+`/goal`, `delegate_task`, skills, plugins, cron, kanban). No standalone app; no portability outside Hermes required. |
| 2 | **Cross-platform** | **Hard requirement.** Windows (native), Unix (macOS/Linux), and **WSL2**. |
| 3 | **Language coverage** | **Language-agnostic framework, Python first-class.** Python tooling wired fully first; JS/TS, Go, Rust adapters incremental. |
| 4 | **Satisfaction model** | **Hybrid signal.** Deterministic analyzers + LLM rubric → weighted aggregate; terminate on **threshold** and on **no-improvement / stall**. |
| 5 | **Reviewer roster (v1)** | **Core five:** security, performance, readability/maintainability, correctness/testing, architecture. |
| 6 | **Autonomy** | **Default fully autonomous** (auto-apply fixes + re-review). Configurable to **semi** (approve before edits) and **advisory** (never edit). |
| 7 | **Review scope** | **Git diff / PR changeset** — review only what changed. |
| 8 | **Project name** | **`review-council`** → the project's own directory (resolved from the checkout, never hardcoded). |

> **Three of these were later changed; the rows above are the record of what was decided.** Each change
> came from evidence, not preference — see `MILESTONES.md`:
>
> - **#1 Foundation** no longer includes `delegate_task`. It was the original fan-out mechanism, and it
>   was removed after a defect: a delegated child inherits the *parent's* `HERMES_HOME` and so cannot
>   load another profile's rubric, which silently ran generic subagents wearing dimension labels. No
>   profile carries `delegation` now; the harness spawns the reviewer.
> - **#2 Cross-platform** no longer means Windows *native*. nix does not run on Windows, so the
>   Windows path is the container image; the WSL bridge was deleted rather than kept as a second
>   route to maintain.
> - **#5 Reviewer roster** is no longer "core five" *profiles*. M8.5 measured five isolated specialist
>   profiles against one generalist sampled N times, at equal cost, and the specialists lost twice —
>   13/22 and 16/22 injected defects against 22/22. The five profiles were deleted; the five
>   **rubrics** remain and are loaded together by one `council-generalist`.
>
> #15 (Kanban for durability) is unstarted, not overturned — it is M7.

## Locked (interview, round 2)

| # | Decision | Choice |
|---|----------|--------|
| 16 | **Iteration engine** | **`/goal` + deterministic gate is primary**; `/loop --until` documented as the alternate. |
| 17 | **Integration target** | **Local CLI/desktop on a local git repo first**; clean path to CI / GitHub PR later. |
| 18 | **Model strategy** | **Tiered** — cheap/fast model for tool-running + aggregation; strong model for specialist judgment + the judge. |
| 19 | **Budget guardrails** | **Default** — `goals.max_turns: 20`, cap ~5 review rounds, plus a per-run token ceiling. |
| 20 | **Bot transport** | **File bus primary** — YAML messages on disk, deterministic, git-versioned; group chat as a demo surface. |

## Resolved by research

| # | Question | Resolution | Why |
|---|----------|-----------|-----|
| 9 | YAML everywhere vs Hermes' JSON-only `output_schema` | **Pydantic v2 → JSON Schema is the contract; YAML on the wire; children return JSON** | `delegation_output_schema.py` validates with `json.loads`; YAML payloads fail |
| 10 | `/loop` vs `/goal` for the scored loop | **`/goal` + completion contract + deterministic gate is primary; `/loop --until` alternate** | `/goal` gates run *before* the judge (deterministic); `/loop --until` is fail-open |
| 11 | Score aggregation method | **Evidence matrix** (tri-state, silence≠agreement, union of verified facts, minority-veto) — **not** majority voting or judge synthesis | Voting discards minority edge cases; naive judge synthesis is biased |
| 12 | Scoring math | **Hill curve** for findings density, **threshold curves** for metrics, **weighted geometric mean** within category, **KLOC-weighted** across languages, **`β·det+(1−β)·llm`** hybrid | `deterministic-quality-tooling.md` §1 |
| 13 | Termination | **Composed condition** (novelty k=2 ∧ score≥threshold ∧ no P0/P1 ∧ diminishing returns ∧ caps ∧ stability) | Single thresholds are trivially gameable |
| 14 | Anti-gaming | Rubric held out of iterating context; execution-based checks; SNR term; per-iteration finding cap; oscillation detection | Self-play gamed a judge 0.72→0.94 at 0.20 true accuracy |
| 15 | Durability | **Kanban Swarm** variant for restart-safe / cross-profile / human-in-the-loop | `delegate_task` children are non-durable |

## Resolved during research (was open)

- **`/loop --until` contract:** runs `judge_goal()` on the `goal_judge` auxiliary task once per tick;
  **fail-open** (any error → continue); a `blocked` verdict pauses the loop.
- **Bot message transport:** `message_agent` is string-based and fire-and-forget — no typed payload →
  the **file bus** is primary; group chat is a demo surface with fenced-YAML-in-string messages.
- **Aggregation:** evidence matrix, not weighted-sum-vote (see #11).
- **Cross-platform execution:** native installs with a Python `platform.py` adapter + a `doctor`
  command; missing tools lower `β` rather than failing the run.

## Ratified after measurement

- **β = 1 is the intended endpoint, not a degenerate case.** On a stack the probes cover, every
  expected tool runs, β = 1, and `score = β·det + (1−β)·llm` becomes `score = det` — the LLM's
  self-assigned number does not enter the figure the gate enforces. **Endorsed** (2026-10-11). The
  design is deterministic-first, with the LLM's judgement as the fallback for stacks the probes do not
  cover. Its *findings* still feed the density term either way; only its self-assigned score is
  ignored.
- Stated because it looks like a bug from the outside ("the LLM score is being ignored") and because
  the β defect of the same session was the opposite failure: β stuck at 0, so the deterministic half
  was ignored and the LLM's number decided everything, with nothing reporting it.

## Still open (needed at M5 / M8)

| Topic | Working default |
|-------|-----------------|
| **Per-run token/cost ceiling** (concrete number) | to set at M5 |
| **Initial `SCORE` threshold + per-category weights** | starting point now, calibrated in M8 |
| **Exact judge model** for `auxiliary.goal_judge` | pin at M5 |
