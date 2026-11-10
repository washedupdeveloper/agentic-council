# Adoption — `pypa/sampleproject`

A real repository, a wheel installed into a clean environment, and both the
reviewer and the pipeline asked to review the same commit.

## The target

- Repository: `https://github.com/pypa/sampleproject`
- Base: `8603eaf` (the commit before the change)
- Head: `621e4974ca25ce531773def586ba3ed8e736b3fc`, 2024-11-06,
  “pyproject: prep 4.0.0 (#219)”
- Diff: 3 files (`pyproject.toml`, `noxfile.py`, `.github/workflows/test.yml`),
  16 insertions, 19 deletions.

## The environment

`council-2.0.0-py3-none-any.whl`, built by `nix build .#wheel`, installed with
`pip install --no-index` into a fresh `python -m venv` (Python 3.14.7), no
dependencies. The repository was a clean `--depth 20` clone; `council init`
added `.council/` to its `.gitignore` before the runs.

## Commands

```sh
council init
council review --base HEAD~1 --samples 1 --context-depth 0 \
  --sample-timeout 90 --time-budget 300 --run-id adopt-sampleproject
```

and the same change with a stub reviewer, which answers immediately:

```sh
council review --base HEAD~1 --samples 1 --context-depth 0 \
  --reviewer /tmp/stub-reviewer.sh --run-id adopt-sampleproject-stub
```

and the CI entry, exactly as the composite action runs it:

```sh
council doctor --json
council ci --base HEAD~1 --samples 1 --context-depth 0 \
  --sample-timeout 90 --time-budget 300 --run-id adopt-ci
```

and the same change at `none`, the fast instrument:

```sh
council review --base HEAD~1 --samples 3 --context-depth 0 \
  --reasoning none --sample-timeout 120 --time-budget 600 \
  --run-id adopt-substantive
```

and at `low`, the substantive one — three samples, each allowed 300 s:

```sh
council review --base HEAD~1 --samples 3 --context-depth 0 \
  --reasoning low --sample-timeout 300 --time-budget 900 \
  --run-id adopt-low-3
```

and at `ultra`, the profile default, with auto-sampling:

```sh
council review --base HEAD~1 --context-depth 0 \
  --reasoning ultra --sample-timeout 300 --time-budget 900 \
  --run-id adopt-ultra
```

## Results

| run | entry | reviewer | verdict | exit | evidence |
|---|---|---|---|---|---|
| `adopt-sampleproject` | `review` | `council-generalist` (profile `ultra`) | `INCOMPLETE` | 2 | prompt 7,954 bytes; sample 1 failed after 2 attempts: “hermes did not answer within 90s” |
| `adopt-sampleproject-stub` | `review` | stub | `PASS` | 0 | the same diff and the same pipeline |
| `adopt-ci` | `ci` | `council-generalist` (profile `ultra`) | `INCOMPLETE` | 2 | `council doctor` exit 0 (profile answered its probe in 7.0 s); `verdict.json` on stdout; same missing-sample reason |
| `adopt-substantive` | `review` | `council-generalist --reasoning none` | `PASS` | 0 | 3 samples, 155 s: sample 3 reported one low correctness finding that its own proof **refuted**; digest `7362f2c8d1801807` |
| `adopt-low` | `review` | `council-generalist --reasoning low` | `PASS` | 0 | 1 sample, 61 s, clean; digest `7344e056e4d4cf5f` |
| `adopt-low-3` | `review` | `council-generalist --reasoning low` | `PASS` | 0 | 3 samples, 600 s: samples 1–2 clean, sample 3 reported two low readability findings, both **proven**, neither blocking; digest `7344e056e4d4cf5f` |
| `adopt-ultra` | `review` | `council-generalist --reasoning ultra` | `PASS` | 0 | 2 samples, 239 s, 5 proven low findings (readability/architecture), none blocking; digest `f624bb509229c8b5` |

All seven run directories are preserved under
`fixtures/adoption/sampleproject-2026-11-09/{provider,stub,ci,substantive,low,low-3,ultra}/`
(`verdict.json` and the sample files).

## Why the first runs stalled, and what it was not

The failures were not `ultra` reasoning running away. The same 7,954-byte
prompt, measured later:

| measurement | result |
|---|---|
| plain, `ultra` | 84 s, `finish_reason=stop` |
| streamed, `ultra` | 69 s, 20 events |
| `council review`, `ultra`, 2 samples | 239 s, `PASS`, 5 proven findings |
| `council review`, `low`, 3 samples | 600 s, `PASS` |
| `council review`, `none`, 3 samples | 155 s, `PASS` |
| earlier attempts, same level | no answer in 90 s or 150 s |

The usage record explains more than the level names: one API call, 14,096 input
tokens, ~4.5k reasoning tokens at `ultra` and ~5.2k at `none`, `finish_reason=stop`
when it answers. The provider's effort labels do not map cleanly to work done,
and the earlier timeouts were **provider/gateway stalls** — no tokens, no
finish — not a reasoning overrun. A warm prompt cache saves tens of seconds
(`cache_read` 0 vs 14k), not minutes.

`--reasoning` is still recorded in `verdict.json` and hashed into the instrument
digest, because it names the instrument that produced a verdict. It is not the
explanation for the stalls, and these runs do not establish that one level is
more reliable than another.

## What this proves

- The wheel installs with no network and no dependencies, and runs from a
  clean virtual environment.
- The tool operates on a repository it did not author: the clone, the base
  resolution, the diff, the run directory and the state-directory warning all
  work outside this project.
- A reviewer that does not answer is recorded as missing evidence, never as a
  pass: the provider run is `INCOMPLETE` with the exact error and attempt count.
- With an answering reviewer the same change reaches a verdict, so the
  pipeline is not the variable.
- A **substantive external verdict** exists at the profile default `ultra`:
  `PASS` on `pypa/sampleproject` with two samples, five proven low findings,
  and no blocking finding; `low` and `none` runs are kept beside it with their
  own digests, not merged into it.
- The CI entry (`council ci`) was exercised on the same external change:
  `council doctor` exited 0, the verdict JSON went to stdout, and the exit code
  was the verdict (2, `INCOMPLETE`).

## What this does not prove

The provider's reliability: a request can stall with no tokens and no finish,
and then the same prompt at the same level answers in 69–84 s. That is why the
verdict is `INCOMPLETE` when a sample does not answer, and why the sample
timeout exists. These runs do not establish a stall rate, and they do not show
that `ultra` is more or less reliable than `low` or `none`.
