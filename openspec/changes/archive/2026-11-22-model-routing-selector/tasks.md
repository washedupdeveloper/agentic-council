# Tasks

## 1. Selector core

- [x] 1.1 Scaffold the `model-routing` skill with SKILL.md, a CLI entry point and a package layout.
- [x] 1.2 Implement baseline resolution: flag, environment, active profile, explicit failure.
- [x] 1.3 Implement the task classifier over the eight task types with a `needs-scoping` outcome.
- [x] 1.4 Implement the routing record and the `route(task, snapshot)` function with no network and no model call.
- [x] 1.5 Add tests for baseline resolution, classification and the no-predicate refusal.

## 2. Providers and snapshot

- [x] 2.1 Define the provider adapter interface and the capability flags.
- [x] 2.2 Implement the Surplus adapter: catalog, offers, realised discount, availability.
- [x] 2.3 Implement the OpenRouter adapter and the generic OpenAI-compatible fallback.
- [x] 2.4 Implement snapshot serialisation with provider, timestamps, capabilities and source hashes.
- [x] 2.5 Implement `refresh` and the freshness ladder, including the 48-hour provisional and 7-day refusal.
- [x] 2.6 Add fixture tests for parsing, stale snapshots and a provider that cannot report discounts.

## 3. Routing map

- [x] 3.1 Generate a draft `routing.yaml` from an OpenSpec change and show a diff.
- [x] 3.2 Preserve existing entries unless `--force` is passed.
- [x] 3.3 Refuse to route a task with no type or no predicate.
- [x] 3.4 Add tests for draft, merge and refusal.

## 4. Report

- [x] 4.1 Implement the versioned JSON sidecar with generated-at, snapshot, pricing basis, roles, tasks, sources and method.
- [x] 4.2 Implement the HTML template with freshness badge, callouts, price-basis headers and numbered sources.
- [x] 4.3 Render both cost views: live-best headline and seven-day-realised budget.
- [x] 4.4 Add a golden-report test against a frozen snapshot.

## 5. Calibration

- [x] 5.1 Implement `calibrate` over `state.db` for the ambient profile and named council profiles.
- [x] 5.2 Write `monthly_total`, `per_session.p50/p90` and `per_call.p50/p90` to `budget.yaml`.
- [x] 5.3 Mark missing roles `uncalibrated` and fall back to the illustrative defaults.
- [x] 5.4 Add tests with synthetic sessions, including one outlier that proves the total/percentile split.

## 6. Profiles

- [x] 6.1 Implement the three-key patch with a comment-preserving YAML round-trip.
- [x] 6.2 Add backup, diff and atomic write.
- [x] 6.3 Protect the ambient profile behind `--force`.
- [x] 6.4 Implement `--create-profiles` with the `builder-<tier>` and `council-<role>` naming.
- [x] 6.5 Add tests that unrelated keys, comments and persona are unchanged.

## 7. Direct adapter

- [x] 7.1 Implement the `direct` adapter module against the `AgentAdapter` protocol.
- [x] 7.2 Resolve model, base URL and key from `COUNCIL_DIRECT_*`; never log the key.
- [x] 7.3 Implement one request per sample and map failures to `ReviewerMissing` and `OSError`.
- [x] 7.4 Implement the identity hash over model, base URL, prompt version and temperature.
- [x] 7.5 Register the adapter and add the `council[direct]` extra.
- [x] 7.6 Add protocol tests with a fake endpoint and a missing-profile case.

## 8. Validation

- [x] 8.1 Run the shape check and `openspec validate model-routing-selector --strict`.
- [x] 8.2 Run the selector against the 21 November snapshot and compare with the reviewed brief.
- [x] 8.3 Record the result in the change and hand the diff to the owner.

## Evidence

| Check | Command | Result |
|---|---|---|
| Selector suite | `nix develop ~/projects/review-council-v2 -c python -m pytest tests/unit/test_model_routing.py -q` | 82 passed, 14 subtests |
| From-scratch e2e | `nix develop ~/projects/review-council-v2 -c bash tests/e2e/run_from_scratch.sh` | `e2e ok`, $15.40 at `5978473` |
| Skill gate | `nix develop ~/projects/review-council-v2 -c python scripts/validate.py` | 0 violations |
| Direct adapter | `nix develop -c python -m pytest tests/test_direct_adapter.py -q` | 11 passed |
| OpenSpec | `nix shell nixpkgs#nodejs -c npx -y @fission-ai/openspec@1.15.0 validate model-routing-selector --strict` | valid |
| Live plan | `/tmp/envcheck-routing/report.json` | 3 models, $5.25/mo |
