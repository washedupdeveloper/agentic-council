# Clean-baseline evaluation — 2026-10-17 (in progress)

**Purpose.** The threshold rested on **one** known-good sample — this repository's own
level-0 rung — so its upper plateau edge was that sample's score. M8 records this as a
provisional number. The question here is whether real, well-regarded repositories
support it, and whether they can serve as known-good baselines at all.

**Baselines.** Five repositories named by the owner as candidates:

| repo | kloc | nix files | HEAD |
|---|---:|---:|---|
| clan-infra | 6.85 | 84 | `008b3ec` |
| devshell | 1.13 | 51 | `9e29c63` |
| flake-utils | 0.62 | 13 | `b7a79d3` |
| treefmt-nix | 7.44 | 412 | `0d6d739` |
| zero-to-nix | 1.98 | 16 | `ce2725e` |

**Method — the hybrid scale, not the deterministic one.** The existing calibration
measures `score_from_densities`, but the gate enforces its threshold on the **hybrid**
aggregate. Deriving a threshold on one scale and enforcing it on another is the
mismatch this run exists to close. Each repo gets a real end-to-end review:

```bash
council review <repo> --scope whole-repo --samples 1 \
    --min-rounds 1 --max-rounds 1 --mode advisory --run-root /tmp/cal-runs/<name>
```

One sample and one round is the cheapest run that still exercises the whole pipeline:
goals → reviewer → merge → gate. Advisory mode means nothing is edited.

**Cost, measured.** flake-utils, the smallest repo at 0.62 KLOC, took **1074 s**
(18 min): 3m 5s for the orchestrator's goal phase, 7m 51s for the reviewer sample, the
rest for merge and gate. The cost is dominated by agent turns, not by repository size.

## Result — 3 of 5 complete

| repo | hybrid | blocking | verdict |
|---|---:|---:|---|
| clan-infra | **94.83** | — | passes |
| devshell | **89.23** | — | passes |
| flake-utils | **60.86** | **2** | fails |
| treefmt-nix | — | — | running |
| zero-to-nix | — | — | queued |

**The threshold is not obviously wrong.** Two of three well-regarded repositories clear
87.11 without any adjustment. The one that fails does so with two verifiable blocking
findings rather than on a marginal score — 60.86, more than 26 points below.

That changes what the calibration question is. It is not "the threshold is too strict for
real repos"; it is "one of these five repos has a genuine supply-chain finding, and the
gate caught it".

### flake-utils: 60.86, and two real findings

| dimension | llm | det | β | score |
|---|---:|---:|---:|---:|
| security | 62.0 | 50.8 | 1.0 | 50.8 |
| correctness | 58.0 | 50.8 | 1.0 | 50.8 |
| readability | 40.0 | 65.5 | 1.0 | 65.5 |
| architecture | 78.0 | 65.5 | 1.0 | 65.5 |
| performance | 96.0 | 100.0 | 1.0 | 100.0 |

1. `.github/workflows/nix.yml:9` — CI installs Nix via `NixOS/nix-installer-action@main`,
   a moving branch rather than an immutable SHA, and the workflow declares no
   `permissions:` block. Third-party code therefore executes on every push with the
   repository-default `GITHUB_TOKEN`.
2. `examples/check-utils/flake.nix:28-29` — the shipped `check-utils` template puts
   intentionally-failing derivations in `checks`, so `nix flake check` in that subflake
   exits 1 by construction.

Both are verifiable by the command each finding names. The first is a genuine
supply-chain exposure in a widely-used repository — and `zizmor` finds it mechanically in
5 findings (see below), which is why it is now a probe.

### A toolchain gap this run exposed

The first finding above is a class the deterministic half could not see: nothing in the
toolchain read `.github/`. `ipetkov/crane` lints its workflows with `zizmor`, and adding
that probe found flake-utils' unpinned `@main` action in one pass — plus 4 findings the
LLM review had not reported (`artipacked`, `excessive-permissions`,
`dependabot-cooldown`).

Adding it also reported **5 high-severity `unpinned-uses` findings against this
repository's own workflows**, which were then fixed: every action is pinned to a full
commit SHA. `docs/CI.md` had argued for major tags and its own condition for revisiting —
"the moment the repo goes public" — had already fired.

**Status: 3 of 5 complete.** treefmt-nix and zero-to-nix are still running at roughly
18 minutes each. The conclusion above does not depend on them unless both also pass, in
which case the pattern is "4 of 5 pass, 1 has real defects" and the threshold stands
unchallenged.
