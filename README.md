# council

A review is a claim until a check settles it.

## The rule

Every finding carries one of four states, and the verdict is a pure function of
those states:

| state | meaning |
|---|---|
| `proven` | the check ran and supported the claim — **this is the only state that fails a run** |
| `refuted` | the check ran and the claim did not hold |
| `unsettled` | no check was attempted |
| `unrunnable` | a check was attempted and could not run here |

```
any blocking finding proven        -> FAIL        exit 1
else any blocking finding open     -> INCOMPLETE  exit 2
else                               -> PASS        exit 0
```

`blocking` means severity `high` or `critical`. The boundary is tested in both
directions: a proven `medium` passes, a proven `high` fails.

There is no score in this decision. A number may be reported beside a verdict as
a trend; it cannot change it.

## Commands

```sh
python3 -m pytest            # the suite
python3 -m council.claims    # every claim this project makes, executed
```

`claims.toml` is the registry. Each entry is one sentence and the command that
would falsify it; the loader refuses an entry with no check, and `verify` exits
non-zero if any claim is false.

## Layout

```
src/council/findings.py   Finding, State, Severity — the domain
src/council/verdict.py    judge() — the whole decision
src/council/claims.py     the claim registry and its runner
fixtures/corpus           the six-rung corpus (carried over from v1.9.0)
fixtures/golden           the golden rounds and their pinned expectations
```

## What is deliberately absent

No configuration, no CLI wiring, no LLM call, no calibration, no packaging yet.
Those arrive in later milestones, and each one has to satisfy this rule and add
its claims to the registry before it exists.