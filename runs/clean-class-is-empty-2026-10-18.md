# The clean class is empty — 2026-10-18

**The question this answers.** The threshold needs a class of repositories with no
blocking findings, to bound it from below. Nine well-regarded Nix repositories were
examined at the shipped default (`--samples 5`). **One is clean.**

## Result

| repo | aggregate | blocking | verified? |
|---|---:|---:|---|
| treefmt-nix | **90.22** | **0** | — |
| clan-infra | 75.06 | 22 | yes |
| devshell | 61.41 | 28 | yes |
| zero-to-nix | 53.55 | 54 | yes |
| flake-utils | 48.89 | 20 | yes |
| naersk | 48.89 | 12 | yes |
| nix-direnv | 39.80 | 11 | yes |
| flake-compat | 34.50 | 3 | yes |
| disko | not reviewed | 7 high (zizmor) | — |

## Every blocking finding was read and confirmed

Not one is a false positive. Each is a supply-chain or integrity defect in code that is
otherwise carefully maintained:

- **naersk** — six actions on mutable tags, including `cachix/cachix-action@v16`, the
  action that **receives `CACHIX_AUTH_TOKEN`**. A moved tag means arbitrary code with a
  write token for the nix-community binary cache, which every consumer substitutes from.
- **nix-direnv** — `on: pull_request_target` with `contents: write`, `pull-requests: write`
  and a GitHub App token, with no author or label guard.
- **flake-compat** — `default.nix:29`, `:72`, `:82` all bind `sha256` conditionally:
  ```nix
  { url = ...; } // (if info ? narHash then { sha256 = info.narHash; } else { } )
  ```
  A lock node without `narHash` therefore reaches `fetchTarball` with **no integrity
  check**. Confirmed by reading the source, not by trusting the reviewer.
- **clan-infra** — three actions on mutable major tags in a sync workflow, a Gitea
  workflow pinned to `@pull/119`, four tracked encrypted `terraform.tfstate` files.
- **devshell / zero-to-nix / flake-utils** — `NixOS/nix-installer-action@main` and
  `DeterminateSystems/*-action@main` in jobs holding `contents: write` and
  `id-token: write`.

## What this means, and the decision it forces

**The premise of the calibration was wrong.** The threshold was to be derived from
"known-good repositories", and at this depth of review **the known-good class is
essentially empty** — one in eight. This is not a sampling problem that more repositories
would fix; unpinned actions and `pull_request_target` are normal practice in respected
projects. Collecting more candidates would keep finding the same distribution.

The framework has **two gates with different characters**, and only one of them can be
absolute:

| gate | character | evidence |
|---|---|---|
| **blocking findings** | binary, absolute | finds a real defect in 7 of 8 respected repos |
| **aggregate threshold** | numeric, absolute | cannot be calibrated: no clean class exists |

**Decision: the aggregate threshold is a regression detector, not an absolute quality
bar.** That is already what the tool is built for and what its docs say in one line — *"the
findings are the portable output; the score is a local yardstick"* — and what
`--baseline auto` implements: a run is compared against the same repository's own previous
whole-repo score. An absolute number derived from other repositories was never the right
frame, and the measurement now says so with data rather than intuition.

So **87.1141 stays**, and its role is stated correctly: it is the default bar for a
repository's *first* run and a regression line thereafter. The blocking gate is what
enforces absolute quality. Nothing about the number changes; the claim about what it
*means* does.

## What would change this

- A repository that is clean at `--samples 5` and scores **below** 87.11 would put a floor
  under the threshold. None exists in eight candidates; a ninth (disko) is untested.
- A repository clean at 5 samples scoring **above** 90.22 would raise the ceiling. Also
  none.
- If the blocking gate ever reports a false positive on a real repository, that is a
  bigger problem than the threshold and should be investigated first.
