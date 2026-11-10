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

## Results

| run | entry | reviewer | verdict | exit | evidence |
|---|---|---|---|---|---|
| `adopt-sampleproject` | `review` | `council-generalist` (profile `ultra`) | `INCOMPLETE` | 2 | prompt 7,954 bytes; sample 1 failed after 2 attempts: “hermes did not answer within 90s” |
| `adopt-sampleproject-stub` | `review` | stub | `PASS` | 0 | the same diff and the same pipeline |
| `adopt-ci` | `ci` | `council-generalist` (profile `ultra`) | `INCOMPLETE` | 2 | `council doctor` exit 0 (profile answered its probe in 7.0 s); `verdict.json` on stdout; same missing-sample reason |
| `adopt-substantive` | `review` | `council-generalist --reasoning none` | `PASS` | 0 | 3 samples, 155 s: sample 3 reported one low correctness finding that its own proof **refuted**; digest `7362f2c8d1801807` |
| `adopt-low` | `review` | `council-generalist --reasoning low` | `PASS` | 0 | 1 sample, 61 s, clean; digest `7344e056e4d4cf5f` |
| `adopt-low-3` | `review` | `council-generalist --reasoning low` | `PASS` | 0 | 3 samples, 600 s: samples 1–2 clean, sample 3 reported two low readability findings, both **proven**, neither blocking; digest `7344e056e4d4cf5f` |

All six run directories are preserved under
`fixtures/adoption/sampleproject-2026-11-09/{provider,stub,ci,substantive,low,low-3}/`
(`verdict.json` and the sample files).

## Why the first runs stalled, and what fixed it

The profile sets `reasoning_effort: ultra`. The same 7,954-byte prompt:

| reasoning | result |
|---|---|
| profile default (`ultra`) | no answer in 90 s, twice |
| `low`, 150 s timeout | no answer |
| `low`, 300 s timeout | **206 s** on a direct call |
| `low`, 3 samples at 300 s each | **600 s** total, `PASS` with two proven low findings |
| `minimal`, 150 s timeout | empty at the boundary |
| `none` | **21 s**, and caught a planted `AKIA…` key as `critical` in 11 s |

`--reasoning` was added to council for this; the level is recorded in
`verdict.json` and hashed into the instrument digest. The substantive `PASS` is
at `low` (`7344e056e4d4cf5f`); the `none` run is the fast path
(`7362f2c8d1801807`). Neither is passed off as the profile’s `ultra`.

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
- A **substantive external verdict** exists at `low`, the highest level that
  answers on this host: `PASS` on `pypa/sampleproject` with three samples, two
  proven low readability findings, and no blocking finding. A faster `none`
  run is kept beside it, not merged into it.
- The CI entry (`council ci`) was exercised on the same external change:
  `council doctor` exited 0, the verdict JSON went to stdout, and the exit code
  was the verdict (2, `INCOMPLETE`).

## What this does not prove

The quality of the model's review at `ultra`: that level still does not return
on this prompt. The `PASS` is from `low` — a real reasoning level, labelled with
its own digest — not from the profile default; `ultra` remains unmeasured, not
assumed equivalent. A single `low` sample was clean while the third of three
found two real issues, so the three-sample run is the one to trust.
