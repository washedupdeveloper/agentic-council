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

## Result so far — flake-utils: 60.86, and two real findings

| dimension | llm | det | β | score |
|---|---:|---:|---:|---:|
| security | 62.0 | 50.8 | 1.0 | 50.8 |
| correctness | 58.0 | 50.8 | 1.0 | 50.8 |
| readability | 40.0 | 65.5 | 1.0 | 65.5 |
| architecture | 78.0 | 65.5 | 1.0 | 65.5 |
| performance | 96.0 | 100.0 | 1.0 | 100.0 |

**60.86** — below the archived *bad* run's 74.00, and far below the 87.11 threshold. The
reason is not a scoring fault. The reviewer found two **blocking** findings:

1. `.github/workflows/nix.yml:9` — CI installs Nix via `NixOS/nix-installer-action@main`,
   a moving branch rather than an immutable SHA, and the workflow declares no
   `permissions:` block. Third-party code therefore executes on every push with the
   repository-default `GITHUB_TOKEN`. Pinning the action and adding
   `permissions: contents: read` is the fix.
2. `examples/check-utils/flake.nix:28-29` — the shipped `check-utils` template puts
   intentionally-failing derivations in `checks`, so `nix flake check` in that subflake
   exits 1 by construction. The rubric's zero-cap applies to that subflake, not the root
   flake.

Both are verifiable by the command each finding names. The first is a genuine
supply-chain exposure in a widely-used repository.

## What this already implies

**Reputation is not a label.** "Well-regarded and maintained" is not the same as
"defect-free", and a calibration baseline has to be the second thing. If a repository
with an unpinned CI action counts as known-good, then the threshold must sit below 60
and the gate would pass code with a real high-severity finding — which is the failure
mode the framework exists to catch.

So the honest options are:

- **keep 87.11** and record that these repositories are *not* clean baselines — they
  are well-regarded but defective, and the gate is doing its job by failing them; or
- **find genuinely defect-free baselines** and derive the threshold from those.

Lowering the threshold to accommodate them is not on the list, because it would mean
weakening the gate to match the sample rather than choosing the sample to test the gate.

**Status: 1 of 5 complete.** The remaining four are running. The table and the
derivation follow when they finish; the conclusion above does not depend on them unless
all four come back with zero blocking findings, which would make flake-utils the outlier.
