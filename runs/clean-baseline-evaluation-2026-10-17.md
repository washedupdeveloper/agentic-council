# Clean-baseline evaluation — 2026-10-17

> **CORRECTION (later the same day).** This evaluation ran at `--samples 1`, and that
> under-samples: the reviewer finds fewer findings per sample, so the density term scores
> higher and the aggregate is **inflated**. Re-running devshell at the shipped default
> (`--samples 5`) gave **61.41**, not 89.23 — and it found a **real blocking finding** that
> one sample missed: `.github/workflows/nix.yml:17` uses `NixOS/nix-installer-action@main`,
> a moving branch, inside a job holding `permissions: contents: write`. So **devshell was
> never clean**, and the "three pass" result below is an artifact of the sample count. The
> table below is kept as the record of what was measured, not as a conclusion.

**Purpose.** The threshold rested on **one** known-good sample — this repository's own
level-0 rung — so its upper plateau edge was that sample's score. M8 records that as
provisional. The question here is whether real, well-regarded repositories support it,
and whether the hybrid scale separates clean code from defective code at all.

**Baselines.** Five repositories named by the owner:

| repo | kloc | nix files | HEAD |
|---|---:|---:|---|
| clan-infra | 6.85 | 84 | `008b3ec` |
| devshell | 1.13 | 51 | `9e29c63` |
| flake-utils | 0.62 | 13 | `b7a79d3` |
| treefmt-nix | 7.44 | 412 | `0d6d739` |
| zero-to-nix | 1.98 | 16 | `ce2725e` |

**Method — the hybrid scale, not the deterministic one.** The existing calibration
measured `score_from_densities`, but the gate enforces its threshold on the **hybrid**
aggregate. Deriving a threshold on one scale and enforcing it on another is the mismatch
this run exists to close. Each repo got a real end-to-end review:

```bash
council review <repo> --scope whole-repo --samples 1 \
    --min-rounds 1 --max-rounds 1 --mode advisory --run-root /tmp/cal-runs/<name>
```

One sample, one round: the cheapest run that still exercises the whole pipeline —
goals → reviewer → merge → gate. Advisory, so nothing was edited.

**Cost, measured — and it does not track repository size.** Exact elapsed times per run:

| repo | kloc | elapsed |
|---|---:|---:|
| clan-infra | 6.85 | 28.6 min |
| zero-to-nix | 1.98 | 20.8 min |
| flake-utils | 0.62 | 17.9 min |
| devshell | 1.13 | 17.6 min |
| treefmt-nix | 7.44 | 12.7 min |
| **total** | | **97.6 min (1.63 h)**, mean 19.5 |

The **smallest** repository (flake-utils, 0.62 KLOC) took **1.4× longer** than the
**largest** (treefmt-nix, 7.44 KLOC) — 17.9 against 12.7 minutes. Cost is dominated by
agent turns and how many findings there are to describe, not by how much code there is.
The 5.6× spread (12.7–28.6 min) is why the estimate of "about an hour" was wrong: the
real figure is 1.63 hours for five repositories.

## Result

| repo | hybrid | β | blocking | verdict |
|---|---:|---:|---:|---|
| treefmt-nix | **98.40** | 0.61 | 0 | passes |
| clan-infra | **94.83** | 1.00 | 0 | passes |
| devshell | **89.23** | 1.00 | 0 | passes |
| zero-to-nix | **80.63** | 0.80 | 0 | fails |
| flake-utils | **60.86** | 1.00 | 2 | fails |

**Three of five pass 87.1141 unchanged.** The two that fail do so for verifiable reasons,
not on a scoring artefact.

The loop's own `outcome` agrees with the gate in every case: three `SATISFIED` (round cap
reached with the minimum met), two `ESCALATE` — and both escalations give the reason
`advisory mode: report only, no fixes applied`, which is the loop correctly declining to
edit code it was told not to edit rather than a separate judgement.

### flake-utils: 60.86, two blocking findings

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

### zero-to-nix: 80.63, no blocking findings

| dimension | llm | det | β | score | missing |
|---|---:|---:|---:|---:|---|
| security | 74.0 | **58.84** | 1.00 | 58.84 | — |
| correctness | 88.0 | 89.08 | 0.57 | 88.62 | jest, tsc, pytest |
| readability | 90.0 | 89.08 | 0.75 | 89.31 | eslint, prettier |
| architecture | 88.0 | 94.57 | 1.00 | 94.57 | — |
| performance | 85.0 | 89.08 | 0.67 | 87.72 | bundle-size |

Every dimension sits at 87–94 except security, which is dragged down by **45 dependency
CVEs** from `osv-scanner` — `golang.org/x/crypto 0.52.0` (GO-2026-5932) among them. No
single finding is high enough to block; the density is what fails the run.

## The classes do not separate on the hybrid scale

| | score |
|---|---:|
| worst **passing** repo (devshell) | 89.23 |
| best **failing** repo (zero-to-nix) | 80.63 |
| known-bad: golden defects fixture | 80.04 |

`zero-to-nix` at 80.63 sits **0.59 points above** the golden defects fixture at 80.04. A
max-margin threshold over these two classes would be **80.34, margin 0.30** — a line that
puts a repository with 45 dependency CVEs within a rounding step of passing.

**So no threshold is derivable from this data.** The reason is structural, not
statistical: both classes contain imperfect code. A well-regarded repository is not
defect-free, so "known-good" and "known-bad" differ in *density*, not in kind, and the
hybrid score is a weighted mean of quality — it reflects density. There is no gap to find.

That makes 87.1141 a **policy line rather than a measured boundary**, and it is a
defensible one: it sits above every repository in this sample that has a real finding and
below every one that does not. **Nothing in this run argues for moving it.**

## What this run did change

Three things, none of them the threshold:

1. **`d*` was anchored on one repo, with 11 of 12 entries floored.** Rebuilt from six
   known-good baselines: `calibrate --good` is repeatable, and `d*` anchors on the *worst*
   density per tool across the set (v1.3.3). Anchoring on the tidiest repo would mark every
   other clean repo as failing.
2. **A probe bug hid the measurement.** `run_probes` treated any non-JSON answer as "no
   probes", so a calibration invoked as a library measured zero points and reported "no
   labels" (v1.3.3).
3. **A toolchain gap.** Nothing read `.github/`, which is why flake-utils' unpinned action
   went unseen by the deterministic half. `zizmor` is now a probe (v1.4.0), and it
   immediately reported **5 high-severity unpinned actions in this repository's own
   workflows**, since fixed (v1.4.1).

## What is still not known

- **n=1 per repo.** One sample, one round. M8.5 showed sampling buys recall, so a
  five-sample run could move these scores; nothing here estimates by how much.
- **β varies with what a repository contains** (0.61 for treefmt-nix, 1.00 for two
  others), so the scores are comparable as the gate's *verdicts* — which is what they are
  — but not as measurements of code quality.
- **Two of the five are small** (0.62 and 1.13 KLOC), where one finding moves the density
  a lot. KLOC normalisation is weak at that size.
- **Five hand-picked repositories is not a sample.** The threshold's position relative to
  the distribution of real repositories is unknown.
