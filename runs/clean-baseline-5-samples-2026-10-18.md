# Clean baseline at the shipped default — 2026-10-18

**Why this exists.** The earlier baseline (`clean-baseline-evaluation-2026-10-17.md`) ran
`--samples 1`, but the shipped default is **5**. Sampling buys recall, so one sample misses
findings, which lowers the density term and **inflates** the score. That evaluation
therefore measured a configuration nobody runs. This one re-measures all six repositories
at `--samples 5 --min-rounds 1 --max-rounds 1 --mode advisory --scope whole-repo`.

## Result

| repo | aggregate | blocking findings | verdict |
|---|---:|---:|---|
| treefmt-nix | **90.22** | **0** | passes 87.1141 |
| clan-infra | 75.06 | 22 | fails |
| devshell | 61.41 | 28 | fails |
| zero-to-nix | 53.55 | 54 | fails |
| flake-utils | 48.89 | 20 | fails |

**Five of six well-regarded repositories have real blocking findings.** Verified by reading
them, not by trusting the count:

- **devshell** — `.github/workflows/nix.yml:17` uses `NixOS/nix-installer-action@main`, a
  moving branch, inside a job with `permissions: contents: write`. Also
  `actions/checkout@v6` on a mutable tag in the same write-capable job.
- **clan-infra** — three actions on mutable major tags in `.github/workflows/repo-sync.yml`
  (`actions/checkout@v4`, `actions/create-github-app-token`, third-party
  `repo-sync/github-sync@v2`); a Gitea workflow pinned to `@pull/119`; and four **tracked
  encrypted `terraform.tfstate` files**.
- **zero-to-nix** — `DeterminateSystems/flake-checker-action@main` and
  `determinate-nix-action@main` across three workflows, in jobs holding `contents: write`
  and `id-token: write`.
- **flake-utils** — `NixOS/nix-installer-action@main`, plus a `check-utils` template that
  cannot pass its own `nix flake check`.

Only **treefmt-nix** is clean at this depth, and it is the only one that passes.

## What this means for the threshold

The threshold's job is to separate clean from defective. At the shipped default that job
is **not** being done by the aggregate — it is being done by the **blocking-finding gate**:

- clan-infra fails at **every** threshold, including `75.05` (below its own 75.06
  aggregate), because of its open high/critical findings. Its aggregate is irrelevant to
  the verdict.
- The same is true of devshell, zero-to-nix and flake-utils.

So the aggregate threshold is only load-bearing for a repository with **no** blocking
findings. Exactly one such repository exists in the sample.

**The only constraint the data gives is an upper bound.** Verified with the shipped gate:

| threshold | treefmt-nix (90.22) |
|---:|---|
| 90.22 | **passes** |
| 90.23 | fails |
| 87.1141 (shipped) | passes |

A lower bound would need a repository with no blocking findings that *should* fail on
aggregate. None exists in the sample, so the band is `(-∞, 90.22]` — unbounded below and
therefore not a calibration. The shipped 87.1141 is consistent with the data; it is not
derived from it.

## A change I tried and reverted

The density term scores the **reviewer's** findings but its Hill anchor `d*` is calibrated
from **probe** densities — different populations (on devshell: probes under 2
findings/KLOC, reviewer 57). I added a reviewer-side anchor
(`council calibrate --from-runs`) applying §7's rule `d* = known-good density`.

**It made every score worse**, and measurement says why: §7's rule puts a *pristine*
repository at **50/100 on the density term by construction**, which caps its `det` near
0.7·95 + 0.3·50 ≈ 81. With the anchor:

| repo | shipped | with reviewer anchor |
|---|---:|---:|
| treefmt-nix | 90.22 | **75.95** |
| clan-infra | 75.06 | 48.07 |
| devshell | 61.41 | 34.40 |
| zero-to-nix | 53.55 | 35.47 |
| flake-utils | 48.89 | 36.93 |

Nothing passes at any threshold. So §7's `d*` rule is a **discrimination** rule — it makes
a curve steep enough to separate classes — not an absolute-scale rule, and applying it to
the density term forces clean code to the middle of the scale. The change is reverted
(`e2b5439`); the reasoning is recorded here so it is not re-attempted.

## Limits

- **One clean repository.** The upper bound rests on treefmt-nix alone. A second clean repo
  scoring below 90.22 would tighten it; one scoring above would raise it.
- **n=1 per repository.** The devshell repeats at one sample showed a 3.57-point spread
  (`docs/CALIBRATION.md`), so these aggregates are single samples, not means.
- **Cost:** 703s (clan-infra), 745s (treefmt-nix), 381s (flake-utils), 476s (devshell),
  909s (zero-to-nix) — 53 minutes of review time for this table.
