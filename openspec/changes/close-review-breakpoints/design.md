# Design

## Context

See `proposal.md` for the motivation. The current review path is one reviewer
instrument, sampled by `sampling.samples`, merged by `domain.merge`, adjudicated
from proof outcomes, and published as `verdict.json`. The remaining risk is not
a missing feature; it is a verdict that can be quieter than the evidence.

## Goals / Non-Goals

**Goals:**

- No silent PASS when a blocking claim is ambiguous, malformed or only quoted.
- No finding is erased by a merge with another finding at the same place.
- A clean result is not based on one sample.
- Every merged claim, proof and evidence path remains visible.

**Non-Goals:**

- No panel, debate, consensus or multi-agent roster.
- No anomaly heuristic, semantic deduplication or model-based adjudication.
- No cross-platform or multi-model claim from this change.
- No automatic fix, merge or model selection.

## Decisions

### D1. One claim is one finding

Key the merge by `(file, line, normalized_claim)`. Normalization only collapses
case and whitespace; paraphrases remain separate. The most blocking dimension
and highest severity across the same claim still win, and every proof and
evidence path is retained.

Why: the place-only key treats two distinct defects on one line as one defect.
That is a reporting loss even when the verdict is conservative. A semantic
merge would require a model and would make the merge non-deterministic; exact
normalization is the smallest deterministic rule that stops erasing distinct
claims. The cost is more rows for paraphrases; the verdict remains complete.

### D2. Two clean samples before PASS

In auto mode, a clean first sample asks for a second. Two clean samples produce
PASS; a second sample with findings asks for a third. A failed sample anywhere
makes the run INCOMPLETE. Fixed `--samples N` remains an explicit caller choice.

Why: one clean sample cannot distinguish a clean change from one missed defect;
absence is the weakest evidence. Two independent clean samples reduce that
failure mode for one extra sample per clean unit. Always requiring three would
be safer but would make the default materially more expensive; two is the
smallest useful confirmation.

### D3. Strict proof mode fails closed

With `--require-executed-proofs`, a blocking finding that is PROVEN but static
(quotation only) is treated as not settled: the run is INCOMPLETE and names the
finding. An executed blocking finding still fails. Static non-blocking findings
remain notes and do not block.

Why: the current strict mode removes the quotation-only finding from the
failing set and can leave an otherwise clean PASS. That is a false green.
INCOMPLETE is the honest state: the claim may be real, but the selected proof
did not demonstrate behaviour. This can increase incomplete runs; that is the
price of never certifying an unexecuted blocking claim.

### D4. Malformed output is a failed sample

Unknown dimensions are a schema error. A missing proof is a schema error. An
empty proof outcome is UNSETTLED, not REFUTED. Nothing is guessed or silently
dropped.

Why: every one of those conditions previously had a path to a clean-looking
verdict. Failing the sample keeps the failure local and makes the run
INCOMPLETE or FAIL, never PASS.

### D5. Preserve all merged wording

`Finding.claims` carries every distinct wording; `claim` remains the first for
existing consumers. `verdict.json` emits `claims` beside `claim`.

Why: merge already kept every wording internally; dropping all but the first at
the verdict boundary made the artifact less informative than the merge. This is
additive and does not change the verdict.

### D6. The build requirement is satisfiable by the lock
`pyproject.toml` requires `setuptools>=83`; the locked nixpkgs provides 83.0.0.
Dependabot had raised the floor to 84.2.1, which no revision in this lock
provides, so `nix build .#council-acp` failed before a test could run. A build
constraint the flake cannot satisfy is a start failure, not a version
preference.

### D7. Support is what the sandbox can run on
The flake declares `x86_64-linux` and `aarch64-linux`. The Darwin entries were
removed: the app wraps `bubblewrap`, which is Linux-only, so a Darwin evaluation
was a guaranteed failure disguised as a supported platform. CI proves x86_64;
aarch64 shares the Linux sandbox but is not claimed by this gate.

### D8. Deployment limits are not code claims

The installed `council` on PATH is a separate build. The source listing and the
installed listing can diverge; users must run the source/devshell build when
using the direct adapter. This change records that as a deployment precondition,
not as a code guarantee. The runtime app also stops installing `council-verify`:
its checks run pytest and the claim registry, neither of which is a runtime
dependency, and shipping the plain wrapper made every claim fail outside the
devshell. Cross-system flake coverage remains host-dependent; this change makes
no claim about systems the gate did not run on.

## Trade-off verdict

The three code choices all trade tidy output or latency for a stronger verdict:

| Choice | Cost | Benefit | Verdict |
|---|---|---|---|
| Claim-level merge | More rows when samples paraphrase | No distinct finding is erased | Adopt |
| Build on the locked setuptools | None beyond the lock | The Nix app can be built and installed | Adopt |
| Linux-only systems | No Darwin package | No guaranteed Darwin evaluation failure | Adopt |
| Two clean samples | One extra sample on clean units | No PASS from a single clean sample | Adopt |
| Strict mode fails closed | More INCOMPLETE results | No blocking quotation-only finding passes | Adopt |
| Semantic merge | Model dependency, non-determinism | Fewer paraphrase rows | Reject |
| Always three samples | Higher default cost | Slightly stronger clean evidence | Reject as default |
| Ignore quotation-only findings | Cheap | False green | Reject |

"Zero failure points" is treated as **zero silent failure paths**, not a claim
that no process can ever fail. Reviewer absence is exit 3; missing or malformed
evidence is INCOMPLETE; a proven executed blocker is FAIL; only a complete
non-blocking evidence set is PASS.

## Risks / Trade-offs

- More findings may appear for paraphrased samples; evidence makes the
  relationship explicit. Mitigation: display grouping by location, not a merge.
- A clean unit costs one extra sample. Mitigation: fixed N remains available for
  callers who deliberately choose a cheaper review.
- Strict mode can return more INCOMPLETE results. Mitigation: the reason names
  the static finding and the mode; the operator can rerun with an executed proof
  or accept the default lenient policy.
- Claim normalization can merge case/whitespace variants only; true paraphrases
  remain separate by design.
- This change does not make cross-platform or installed-build claims.

## Migration Plan

Existing verdict format stays `1`; `claims` is additive. A baseline fingerprint
uses the representative `claim`, so existing single-wording findings behave as
before. Runs with multiple wordings may produce additional rows and are a new
evidence shape, not a silent change to an old one.

## Open Questions

None that change the contracts above.
