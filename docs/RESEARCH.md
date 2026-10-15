# review-council — Research Index

Four parallel research reports from kickoff, the evidence base for `MILESTONES.md` and
`ARCHITECTURE.md`. Full reports live in `research/`.

| Report | Question | File |
|---|---|---|
| Hermes extension points | How to build this **natively** in Hermes: exact commands, config keys, tool contracts | [`research/hermes-extension-points.md`](../research/hermes-extension-points.md) |
| SOTA multi-agent code review | Prior art, scoring, aggregation, termination, pitfalls | [`research/sota-multi-agent-code-review.md`](../research/sota-multi-agent-code-review.md) |
| Deterministic quality tooling | Per-category × per-language analyzers + normalization math | [`research/deterministic-quality-tooling.md`](../research/deterministic-quality-tooling.md) |
| Inter-agent protocol | Uniform YAML envelope grounded in A2A/MCP/FIPA/CloudEvents | [`research/inter-agent-protocol.md`](../research/inter-agent-protocol.md) |

---

## Findings that changed the design

1. **`delegate_task`'s `output_schema` is validated as JSON only** (`json.loads` in
   `tools/delegation_output_schema.py`). YAML payloads fail validation → the protocol is authored in
   Pydantic→JSON Schema, children return JSON, YAML is the human/agent-facing serialization.
2. **`/loop` is timer-driven; `/goal` is judge-driven with deterministic gates that run *before* the
   judge.** The scored iterate-until-satisfied loop belongs on `/goal`+gate; `/loop --until` exists
   but its judge is **fail-open**.
3. **Score thresholds are gameable, and iterating agents will game them.** Self-play drove a judge's
   pass rate 0.72→0.94 while true accuracy stayed 0.20 (arXiv:2607.05904). Mitigation: hold the rubric
   out of the iterating context, use execution-based checks, add an SNR term, cap findings, detect
   oscillation.
4. **Naive judge synthesis and majority voting are wrong for qualitative review** — position/verbosity
   bias, silence-as-consensus, minority loss. Use an **evidence matrix** with tri-state cells and
   union-of-verified-facts.
5. **Structured, evidence-grounded disagreement beats debate and naive parallelism** (AR F1 0.533 vs
   MARS 0.501 vs single 0.495) — a prompting change, not more agents.
6. **There is a hard precision/recall frontier** (recall 27→33% collapsed SNR 5.11→1.95), so **SNR and
   usefulness rate are first-class metrics**, and "flag everything" must not raise the score.
7. **Iteration converges in ~3–5 rounds**; production hard caps are 1–2 (automated) / 3–5 (interactive).
8. **Deterministic normalization is settled math**: severity-weighted density per KLOC → Hill curve;
   bounded metrics → threshold curves; within-category → weighted geometric mean; cross-language →
   KLOC-weighted; hybrid → `β·det + (1−β)·llm` with `β` = analyzer coverage.
9. **Performance and documentation *substance* cannot be scored deterministically** — low `β`, the LLM
   carries them. Architecture needs explicit rules to have any deterministic signal.
10. **Delegate children are non-durable** (restart → `unknown`, no resume) → a **Kanban Swarm** variant
    for restart-safe runs.

## Key Hermes facts (verified against source, rev `93c9360a8`)

- `/loop [interval] <prompt> [--times N] [--until <cond>]`; `loops.max_ticks` default 100 (pauses,
  recoverable); self-paced backoff 1→2→4→8→15m.
- `/goal` completion contract fields: `outcome, verification, constraints, boundaries, stop_when`;
  `/goal gate add <cmd>` runs **before** the judge; `goals.max_turns` default 20.
- `auxiliary.goal_judge.{provider,model,max_tokens,timeout}` routes the judge; fail-open; auto-pauses
  after 3 parse / 5 transport failures.
- `delegation.max_concurrent_children` default **10** (no ceiling); `max_spawn_depth` default **1**;
  `output_schema` validated with one bounded retry; a miss sets `schema_valid=false` but never fails the run.
- A Bot **is** a profile (`~/.hermes/profiles/<name>/`); `message_agent` is string-based, fire-and-forget.
- `hermes kanban swarm "<root>" --workers … --verifier … --synthesizer …` builds a durable
  root + workers + verifier + synthesizer; `--goal` cards run the same Ralph engine.

## Source URLs

Hermes docs: [loops](https://hermes-agent.nousresearch.com/docs/user-guide/features/loops) ·
[goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals) ·
[delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation) ·
[bot-mode](https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode) ·
[kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) ·
[cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) ·
[index](https://hermes-agent.nousresearch.com/docs/llms.txt).

Full citation lists are inside each report.
