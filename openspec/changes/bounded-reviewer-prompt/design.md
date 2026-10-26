# Design

## Context

See `proposal.md` — Why. Two facts shape the approach. The reviewer prompt is assembled in one
place, `generalist_prompt()` in `scripts/council_loop.py`, and `AGENTS.md` records that it travels
in a file because `MAX_ARG_STRLEN` is 65,536 bytes. The probe results are written to
`probes.json` once per run and read by the gate and by the next incremental run's diff — they are
the record, not a prompt fragment.

## Goals / Non-Goals

**Goals.** A prompt that any model in the fleet can accept, built from the same evidence, with the
omission visible to the reviewer rather than silent.

**Non-Goals.** Changing what the probes collect, how the gate scores, or what `probes.json`
contains. Re-ordering findings for the record.

## Decisions

**1. Bound by rule code, not only by count.** The payload is not 1,013 distinct observations; it is
603 `UP006` and 138 `UP045`. A per-probe cap of 25 alone would still spend the whole budget on one
linter rule, so the digest keeps at most three examples per rule and reports the remainder as
`omitted_by_rule`. The reviewer learns "603 more of this kind" — which is the fact that matters —
instead of reading a sample of 603 identical lines.

**2. Trim the fat fields before dropping findings.** `location` was 41.5% of the bytes because
every path was absolute, and `falsifiable_check` another 34.9% because it repeated the path inside
a command. Paths become repo-relative and both strings are truncated, which removes roughly
three-quarters of the size before any finding is dropped.

**3. The digest is a renderer, never a mutation.** `probe_digest()` returns a string and leaves the
probe list untouched; `probes.json` is written from the original list. A test asserts the input is
not mutated, because a digest that quietly pruned the record would corrupt the incremental diff —
the one signal that needs no file reading.

**4. A hard byte budget with a degraded fallback.** Caps are chosen so a normal repository lands
well inside the budget, but a pathological one could still exceed it, so the renderer measures its
own output and, if still over, drops finding bodies entirely and leaves the counts. A prompt that
is too big is worse than a prompt that is thin, because a thin prompt still produces a review.

**5. `ablate.py` keeps its own prompt.** It reproduces the arms the ablation measured. Bounding its
prompt would change the thing being compared, so the drift is deliberate and recorded here rather
than fixed by analogy.

## Risks / Trade-offs

- **The reviewer no longer sees every deterministic finding** → mitigated by ranking (severity
  first), by reporting the omitted counts per rule, and by the prompt saying the digest *is* the
  probe evidence. It also says not to read `probes.json` wholesale: measured, it did, and spent a
  90,906-character tool result on the same data unsummarised. The gate scores from reviewer files, not from the prompt, so a summarised
  prompt cannot change a score by itself.
- **A per-rule cap hides a rule with few but severe findings** → severity ranking runs before the
  per-rule cap, so a `high` finding is kept ahead of any number of `low` ones.
- **The budget is a constant tuned on one repository** → it is named, exported, and asserted in a
  test; the fallback makes a wrong constant degrade rather than fail.

## Migration Plan

None. The record format is unchanged and the prompt is built at run time.
