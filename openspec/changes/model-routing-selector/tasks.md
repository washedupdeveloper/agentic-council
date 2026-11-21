# Tasks

## 1. Selector core

- [ ] 1.1 Scaffold the `model-routing` skill with SKILL.md, a CLI entry point and a package layout.
- [ ] 1.2 Implement baseline resolution: flag, environment, active profile, explicit failure.
- [ ] 1.3 Implement the task classifier over the eight task types with a `needs-scoping` outcome.
- [ ] 1.4 Implement the routing record and the `route(task, snapshot)` function with no network and no model call.
- [ ] 1.5 Add tests for baseline resolution, classification and the no-predicate refusal.

## 2. Providers and snapshot

- [ ] 2.1 Define the provider adapter interface and the capability flags.
- [ ] 2.2 Implement the Surplus adapter: catalog, offers, realised discount, availability.
- [ ] 2.3 Implement the OpenRouter adapter and the generic OpenAI-compatible fallback.
- [ ] 2.4 Implement snapshot serialisation with provider, timestamps, capabilities and source hashes.
- [ ] 2.5 Implement `refresh` and the freshness ladder, including the 48-hour provisional and 7-day refusal.
- [ ] 2.6 Add fixture tests for parsing, stale snapshots and a provider that cannot report discounts.

## 3. Routing map

- [ ] 3.1 Generate a draft `routing.yaml` from an OpenSpec change and show a diff.
- [ ] 3.2 Preserve existing entries unless `--force` is passed.
- [ ] 3.3 Refuse to route a task with no type or no predicate.
- [ ] 3.4 Add tests for draft, merge and refusal.

## 4. Report

- [ ] 4.1 Implement the versioned JSON sidecar with generated-at, snapshot, pricing basis, roles, tasks, sources and method.
- [ ] 4.2 Implement the HTML template with freshness badge, callouts, price-basis headers and numbered sources.
- [ ] 4.3 Render both cost views: live-best headline and seven-day-realised budget.
- [ ] 4.4 Add a golden-report test against a frozen snapshot.

## 5. Calibration

- [ ] 5.1 Implement `calibrate` over `state.db` for the ambient profile and named council profiles.
- [ ] 5.2 Write `monthly_total`, `per_session.p50/p90` and `per_call.p50/p90` to `budget.yaml`.
- [ ] 5.3 Mark missing roles `uncalibrated` and fall back to the illustrative defaults.
- [ ] 5.4 Add tests with synthetic sessions, including one outlier that proves the total/percentile split.

## 6. Profiles

- [ ] 6.1 Implement the three-key patch with a comment-preserving YAML round-trip.
- [ ] 6.2 Add backup, diff and atomic write.
- [ ] 6.3 Protect the ambient profile behind `--force`.
- [ ] 6.4 Implement `--create-profiles` with the `builder-<tier>` and `council-<role>` naming.
- [ ] 6.5 Add tests that unrelated keys, comments and persona are unchanged.

## 7. Direct adapter

- [ ] 7.1 Implement the `direct` adapter module against the `AgentAdapter` protocol.
- [ ] 7.2 Resolve model, base URL and key from `COUNCIL_DIRECT_*`; never log the key.
- [ ] 7.3 Implement one request per sample and map failures to `ReviewerMissing` and `OSError`.
- [ ] 7.4 Implement the identity hash over model, base URL, prompt version and temperature.
- [ ] 7.5 Register the adapter and add the `council[direct]` extra.
- [ ] 7.6 Add protocol tests with a fake endpoint and a missing-profile case.

## 8. Validation

- [ ] 8.1 Run the shape check and `openspec validate model-routing-selector --strict`.
- [ ] 8.2 Run the selector against the 21 November snapshot and compare with the reviewed brief.
- [ ] 8.3 Record the result in the change and hand the diff to the owner.
