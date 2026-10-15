# The deployable skill is a store path, not a copy

`.#skill` is a derivation that lays out the deployment tree — `SKILL.md`,
`scripts/`, `tests/`, `assets/bots/`, `assets/rubrics/`, the two flake files — and
`programs.council.mode = "external-dirs"` points Hermes at it. The alternative was
to keep `council setup skill` as the only mechanism and make it correct.

A **store path is read-only**, and that is the whole argument. The copier's product
is a mutable tree, so it can drift and has: measured, **11 files differed from
source**, and the deployed test suite had never run at all. Managing that drift —
a `--check` flag, a byte-comparison gate in the other repository — works, but it is
work spent on a failure the store cannot have. Nothing can edit a store path in
place, so there is nothing to detect.

Two things follow that are easy to get wrong:

- **The copier is still needed.** `external-dirs` requires Nix, so the copy path
  remains the only one for a host without it. The two mechanisms coexist deliberately:
  they serve different hosts, not different versions of the same host.
- **The tree is not simply "what the framework ships".** `.#skill` must carry
  **every** script, including the four the `user` audience omits
  (`ablate`, `calibrate`, `golden`, `inject_defects`) and the two data files
  (`calibration.json`, `eval-baseline.json`). The deployed suite exercises the dev
  modules, and without the data files `score_reviews` silently falls back to the
  uncalibrated count-based curve — a deployment that scores differently from the
  checkout. Both were found by diffing the derivation against the live deployment
  file by file, which is why `checks.skill-layout` now asserts the layout.
- **The derivation's hash covers the whole tree, not just the deployed files.** A
  commit that touches only `docs/` or `.github/` still moves the framework store
  path, so `council setup skill --check` reports drift while the deployed content is
  byte-identical — measured: after a documentation-only edit the check reported drift,
  the resync changed **no file**, and the check then reported "in sync". Read a
  reported drift as "the store path moved", and confirm it with a content diff before
  chasing it; the copier is the mechanism that can actually drift.

The cost is that the deployment has a Nix dependency. That is the trade: a host
without Nix gets the copier and its drift, and a host with Nix gets a tree that
cannot drift at all.
