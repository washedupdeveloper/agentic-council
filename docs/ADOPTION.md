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

## Results

| run | entry | reviewer | verdict | exit | evidence |
|---|---|---|---|---|---|
| `adopt-sampleproject` | `review` | `council-generalist` | `INCOMPLETE` | 2 | prompt 7,954 bytes; sample 1 failed after 2 attempts: “hermes did not answer within 90s” |
| `adopt-sampleproject-stub` | `review` | stub | `PASS` | 0 | the same diff and the same pipeline |
| `adopt-ci` | `ci` | `council-generalist` | `INCOMPLETE` | 2 | `council doctor` exit 0 (profile answered its probe in 7.0 s); `verdict.json` on stdout; same missing-sample reason |

All three run directories are preserved under
`fixtures/adoption/sampleproject-2026-11-09/{provider,stub,ci}/` (`verdict.json`
and `sample-1.json`).

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
- The CI entry (`council ci`) was exercised on the same external change:
  `council doctor` exited 0, the verdict JSON went to stdout, and the exit code
  was the verdict (2, `INCOMPLETE`).

## What this does not prove

The quality of the model's review of `pypa/sampleproject`: the provider did not
return an answer within the 90-second sample timeout on either attempt. That is
the known limit recorded in `README → Known limits`, not a property of the
adoption path. Re-run the first command on a host whose profile answers review
prompts to replace the `INCOMPLETE` with a substantive verdict; the run ID will
refuse to overwrite the old evidence until it is named differently.
