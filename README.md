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

`blocking` means severity `high` or `critical` — **or any severity in `security`
or `correctness`**. The model may rank a defect; it may not decide that a proven
security or correctness defect is mergeable. The boundary is tested in both
directions: a proven `low` security finding fails, a proven `low` readability
finding passes.

There is no score in this decision. A number may be reported beside a verdict as
a trend; it cannot change it.

## Commands

```sh
council review                # gate: 0 pass, 1 fail, 2 incomplete, 3 could not start
council review --report       # advice only: always exits 0
python3 -m pytest             # the suite
./bin/council-verify          # every claim this project makes, executed
python3 tools/mutation_check.py   # prove the suite can fail
python3 tools/differential.py     # v1.9.0's verdicts beside this rule
```

`claims.toml` is the registry. Each entry is one sentence and the command that
would falsify it; the loader refuses an entry with no check, and `verify` exits
non-zero if any claim is false. `docs/CLAIMS.md` is generated from it
(`council verify --write docs/CLAIMS.md`) and checked in the flake, so the page
cannot list a claim that has no check behind it.

## The reviewer contract

One call, five sections (`security`, `correctness`, `readability`,
`architecture`, `performance`), one JSON object. A finding without a proof from
the closed set (`absent`, `present`, `command`, `json`, `http`, `diff`)
is refused by the parser, not by the prompt alone.

The prompt ships with the tool at `src/council/prompts/reviewer.md`; `--prompt`
names a different one. It is deliberately **not** read from the repository under
review — otherwise the code being judged could supply a prompt that reports
nothing. Every run records a digest over the template, the profile and the
dimensions; two runs are comparable only when the digest matches.

## Container

`nix build .#image` → an OCI tarball with `council`, `git` and `bash`. It carries
the tool, not the reviewer: mount one at `/bin/hermes` or pass `--reviewer`.
Command proofs need user namespaces; a runtime that blocks them makes those
proofs `UNRUNNABLE`, never unsandboxed.

## Layout

```
src/council/findings.py   Finding, State, Severity — the domain
src/council/verdict.py    judge() — the whole decision
src/council/base.py       which revision the diff is taken against
src/council/paths.py      where a run's artefacts live
src/council/schema.py     the reviewer's output contract
src/council/prompt.py     render the template, digest the instrument
src/council/sample.py     one sample: run, retry once, record
src/council/proofs.py     the six proof kinds
src/council/sandbox.py    bubblewrap: no network, overlay tree
src/council/claims.py     the claim registry and its runner
src/council/prompts/      the reviewer prompt, shipped with the tool
skills/council/           the agent-facing skill
fixtures/                 the six-rung corpus and the golden rounds from v1.9.0
```

## The sandbox

A `command` proof runs under `bubblewrap`: no network, a read-only root, a
private `/tmp` and `$HOME`, and a cleared environment. The repository is an
overlay — a proof may write, and the writes vanish with it. A write anywhere
else is `UNRUNNABLE`, not refuted. `[proofs] sandbox = false` opts out; without
`bwrap` on `PATH` the same proofs are `UNRUNNABLE` and never fall back to
running unsandboxed.

## What is not here

- A browser. A DOM claim is a `command` proof: the repository runs its own
  browser test, and the tool only records whether it passed.
- Calibration: there is no score, so there is nothing to calibrate.
- A replacement for v1: 1.9.0 is untouched; this is a separate checkout.