# Design: model routing selector

## Context

Three facts constrain the design.

1. A Hermes session's model is fixed by its profile, and `delegate_task` cannot pin a model per child. Per-task model choice therefore needs either an in-session baseline or a profile subprocess.
2. Surplus exposes four prices for the same model: list, live best offer, median offer, and seven-day realised. They can differ by more than an order of magnitude, so no single number can serve both "what can I buy now" and "what will this month cost".
3. Council's reviewer adapter is one process per sample. A text-only review does not need an agent boot, tools, a sandbox or a 120-second idle timeout.

## Three planes

- **Data plane.** A provider adapter writes a snapshot; a cron refreshes it every 12 hours. No request path performs a network scrape.
- **Decision plane.** A pure function over the task and the snapshot: `route(task, snapshot) -> {model, budget, predicate}`. No network, no LLM, no repository crawl. Target under 100 ms.
- **Work plane.** The baseline task runs in the current session. A failed predicate spawns the next tier. Council reviews run through the direct adapter.

## Baseline

Resolution order, recorded in every decision:

1. `--baseline <model-id>`.
2. `SURPLUS_BASELINE_MODEL`.
3. The active profile's `model.default`.
4. Fail with a message naming the missing input.

The baseline is the floor for this change. `--allow-downgrade` and a whitelist are the migration path to cheaper-than-baseline routing; they are not enabled here.

## Selection policy

1. Start every task at the baseline.
2. Implement in-session with a bounded attempt: implement, run the checks the agent can run, retry once.
3. Verify against the task's acceptance predicate.
4. On pass, record `passed: baseline`.
5. On repeated failure, spawn the next tier with the failed predicate and the attempts.
6. If the task has no predicate, return `needs-scoping` and make no model call.

A task is never escalated on self-reported doubt. The closed list of escalation evidence is: a failed scenario, a failing test or gate, a council `FAIL`/`INCOMPLETE` with a proven blocking finding, or two rejected patches with the same signature.

## Task taxonomy

| Type | Typical task | Predicate | Default tier | Review |
|---|---|---|---|---|
| `mechanical` | rename a field across source and tests | suite + absence check | baseline | optional |
| `docs` | update an agent guide | link check + read-through | baseline | optional |
| `test` | add a regression test | the new test passes | baseline | optional |
| `feature` | add a CLI filter | new tests + existing suite | baseline | on diff size |
| `bugfix` | fix a serializer mismatch | failing repro, then green regression | baseline, escalate on failed repro | yes |
| `refactor` | split a module without API change | full suite + public API check | baseline | yes |
| `architecture` | choose a verdict model | ADR + judge sign-off | judge decides, baseline implements | judge |
| `security` | validate a path before a sandbox mount | security tests + reviewer | baseline + mandatory reviewer | mandatory |

The type selects the benchmark basket: coding composite and DeepSWE for `feature`, `bugfix` and `refactor`; HLE-Diamond and FrontierMath for `architecture`; no benchmark for `docs`.

## Routing map

`openspec/changes/<change>/routing.yaml` is drafted by the selector and approved by the owner. A task without a type or a predicate is not routed.

```yaml
schema: 1
change: add-dimension-filter
tasks:
  "1.1":
    type: feature
    verify: ["pytest tests/test_cli_scope.py -q"]
  "1.2":
    type: test
    verify: ["pytest tests/test_prompt.py -q"]
  "2.1":
    type: architecture
    verify: ["review: docs/adr/0007-dimension-filter.md"]
```

The draft step shows a diff. Existing entries are preserved unless `--force` is passed.

## Provider registry

Each adapter declares:

- `name`
- `matches(base_url)`
- `fetch_catalog()` — models, context, modalities, list price
- `fetch_offers(model_id)` — sellers, discount, effective price, availability
- `capabilities` — whether discounts and availability are observable

Discovery order: explicit `--provider` or config, then the active profile's `base_url`, then the generic adapter. The generic adapter records that discount data is unavailable rather than inventing it.

First adapters: `surplus`, `openrouter`, `generic-openai`. Surplus is the reference implementation.

## Snapshot and freshness

Snapshot fields: `provider`, `base_url`, `fetched_at`, `capabilities`, `models[]`, `offers[]`, `source_hashes`.

| Age | Behavior |
|---|---|
| 12 hours or less | silent |
| 12 to 48 hours | one-line age note |
| 48 hours to 7 days | provisional report; profile writes refused |
| more than 7 days | ranking refused until refresh or `--accept-stale` |

Refresh is a command, scheduled every 12 hours. The first use in a session checks the age; the prompt only fires when the snapshot is stale.

## Pricing basis

- **Live best** is the headline: the cheapest offer currently on the book.
- **Seven-day realised** is the budget column: request-weighted, and it already absorbs seller failures.
- **Median** is the conservatism check.
- **List** is reference only and never enters a cost calculation.

Cost:

```
cost = input_tokens * price_in / 1e6
     + output_tokens * price_out / 1e6
     + cache_read_tokens * price_cache / 1e6
```

Every table names its basis in the header. The report never shows a bare cost.

## Calibration

`surplus-select calibrate` reads `state.db` for the ambient profile and each named `council-*` profile, aggregates input, output, cache reads, reasoning and calls, and writes `budget.yaml` with three views:

- `monthly_total` — the measured sum over the window, normalised to 30 days. This feeds the monthly cost table.
- `per_session.p50 / p90` — typical and heavy session. This feeds per-task and per-review sizing.
- `per_call.p50 / p90` — typical and heavy call. This feeds the per-call cost line.

The distinction is not cosmetic. On the measured data, multiplying the builder's P50 by its session count understated the month by 67x because one session used 66.6M input tokens. The total is a sum; percentiles are for sizing.

A role with no data is marked `uncalibrated` and falls back to the illustrative defaults, labelled as such. The report cites the sample size, window and filter.

## Profile emission

- Patch only `model.default`, the matching provider entry, and optional `model.reasoning_effort`.
- Use a comment-preserving YAML round-trip so unrelated edits do not change council's instrument hash.
- Back up, show a unified diff, write atomically.
- Never touch memories, skills, persona or state.
- The ambient profile is protected; `--force` is required.
- `--create-profiles` is the only way a missing profile is created. Naming: `builder-<tier>` and `council-<role>`.

## Direct reviewer adapter

The adapter implements the existing `AgentAdapter` protocol.

- Reads `model.default` and the matching provider entry from the selected profile.
- Resolves a literal key, `${VAR}` or `key_env`; never logs it.
- One POST to `/v1/chat/completions` per sample; returns `choices[0].message.content`.
- Missing profile or config: `ReviewerMissing`. Non-2xx, timeout or empty answer: `OSError`.
- Identity: `agent="direct"`, `profile=<name>`, `source=profiles/<name>/config.yaml`, `sha256` over model, base URL and profile bytes.
- No tools, no sandbox, no repository writes.

## Report contract

- Generated-at, ISO 8601 with timezone, in the header and JSON.
- Freshness badge: green, amber, red, with provider and age.
- Callouts: amber for a trap, blue for a recommendation, green for a value pick; one claim, evidence, source.
- Numbered sources at the bottom and a Method paragraph.
- Versioned JSON sidecar carrying the same facts; the HTML is a rendering.
- No PDF.

## Alternatives considered

- **Five dimension profiles per review.** Rejected for this change: five full-diff reviews multiply cost and latency, and each narrow reviewer still reads the whole diff.
- **LLM router.** Rejected: it adds a round-trip to every task and produces a decision that cannot be audited.
- **Automatic calibration on every run.** Rejected: the state-db schema is an internal contract; a schema change would break every run instead of one command.
- **A Surplus-specific adapter.** Rejected: the adapter reads the profile's provider, so it works for any OpenAI-compatible endpoint.

## Risks

- Provider pages change structure; the adapter needs fixture tests and a loud parse failure.
- Spot prices move; the live best is a sticker, not a guarantee, which is why the budget uses the realised average.
- The state-db schema may change; calibration is isolated behind one command and falls back to illustrative numbers.
- A profile patch changes council's instrument hash by design; the diff and backup make that visible.
