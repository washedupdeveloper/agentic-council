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
python3 -m pytest             # the suite
./bin/council-verify          # every claim this project makes, executed
python3 tools/mutation_check.py   # prove the suite can fail
```

`claims.toml` is the registry. Each entry is one sentence and the command that
would falsify it; the loader refuses an entry with no check, and `verify` exits
non-zero if any claim is false.

## The reviewer contract

One call, five sections (`security`, `correctness`, `readability`,
`architecture`, `performance`), one JSON object. A finding without a proof from
the closed set (`absent`, `present`, `command`, `json`, `http`, `dom`, `diff`)
is refused by the parser, not by the prompt alone.

The prompt is `prompts/reviewer.md` — edit it without touching code. Every run
records a digest over the template, the profile and the dimensions; two runs are
comparable only when the digest matches.

## Layout

```
src/council/findings.py   Finding, State, Severity — the domain
src/council/verdict.py    judge() — the whole decision
src/council/base.py       which revision the diff is taken against
src/council/paths.py      where a run's artefacts live
src/council/schema.py     the reviewer's output contract
src/council/prompt.py     render the template, digest the instrument
src/council/sample.py     one sample: run, retry once, record
src/council/claims.py     the claim registry and its runner
prompts/reviewer.md       the prompt you can edit
fixtures/                 the six-rung corpus and the golden rounds from v1.9.0
```

## What is deliberately absent

No CLI wiring, no proof execution, no merge of samples, no calibration, no
packaging. Those arrive in later milestones, and each one has to satisfy this
rule and add its claims to the registry before it exists.