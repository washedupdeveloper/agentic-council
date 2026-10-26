# Tasks

## 1. Bound the digest

- [x] 1.1 Add `probe_digest()` to `scripts/council_loop.py`: rank by severity, cap per rule code
      and per probe, relativise paths, truncate `claim` and `falsifiable_check`, report
      `findings_total` / `findings_omitted` / `omitted_by_rule`.
- [x] 1.2 Enforce a byte budget with a fallback that drops finding bodies rather than exceeding it.
- [x] 1.3 Build the prompt from the digest; state in the prompt that the block is summarised and
      that `probes.json` is the complete record.

## 2. Prove it

- [x] 2.1 `tests/test_probe_digest.py`: a 1,000-finding probe is capped, names its rule in
      `omitted_by_rule`, and renders inside the budget.
- [x] 2.2 The input list is not mutated, and `probes.json`'s writer still receives every finding.
- [x] 2.3 A `high` finding is kept ahead of `low` ones regardless of order.
- [x] 2.4 Paths under the repo are relativised; a path outside it is left alone.
- [x] 2.5 An over-tight budget degrades to counts only, and the JSON still parses.

## 3. Verify

- [x] 3.1 `nix flake check --keep-going` passes (suite, ruff, mypy, the command surface).
- [x] 3.2 A real prompt for `hermes-agent` renders inside the budget — measured, not assumed.
- [x] 3.3 `openspec validate bounded-reviewer-prompt --strict` passes.
- [x] 3.4 The full council runs on `hermes-agent` and produces readable reviewer files.
