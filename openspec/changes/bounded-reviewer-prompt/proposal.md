# Proposal

## Why

The reviewer prompt for a Python repository is dominated by deterministic probe output. Measured
on `hermes-agent`: the prompt was **518,550 bytes**, of which `probes.json` was **515,487** — and
**91.4% of that was one probe**, `ruff`: 1,013 findings over 60 files, 975 of them `low`
(603 are `UP006` alone), each carrying an absolute path twice.

The configured endpoint does not answer that request. Three runs produced no reviewer file at all:
`rc=124` at a 240 s timeout and again at 900 s, with a CloudFront 504 in the provider log, while
the same profile answers a small prompt in **20 seconds**. With no reviewer file the gate refuses
to score (correctly), so the run escalates with zero findings — the reviewer never reviewed, and
the cause was payload size rather than anything about the change under review.

## What Changes

- The reviewer prompt receives a **bounded digest** of the probe results: findings ranked by
  severity, capped per rule code and per probe, paths made repo-relative, and the long
  `claim` / `falsifiable_check` strings truncated.
- Each probe entry states `findings_total`, `findings_omitted` and `omitted_by_rule`, so the
  reviewer knows what it is not seeing and can name the rule rather than guess.
- The prompt says the probe block is summarised and that the complete record is `probes.json`.
- `probes.json` in the run directory is **unchanged**: the digest is a renderer for one consumer
  (the prompt), not a change to the record the gate and the next incremental run read.
- `AGENTS.md` stops claiming the prompt is ~400 KB, because after this it is tens of KB.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rounds`: adds the requirement that the reviewer prompt is bounded and that the run's probe
  record stays complete.

## Impact

`scripts/council_loop.py` (the digest renderer and the one call site that builds the prompt),
`tests/test_probe_digest.py`, `AGENTS.md`. No change to probing, merging, scoring, the gate,
or the CLI surface. `scripts/ablate.py` is deliberately untouched: it re-runs historical arms,
and changing its prompt would invalidate the comparison the ablation exists to make.
