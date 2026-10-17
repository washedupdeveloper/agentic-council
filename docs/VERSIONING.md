# Versioning

Semantic Versioning 2.0.0, applied to a tool whose interface is a CLI, a flake, a set of
file formats and a score. The policy is enforced: `council version check` runs in
`nix flake check` as `checks.version`, and in CI against the pushed tag.

## The deciding question

**Does an existing user have to change something to keep the same meaning?**

| answer | bump |
|---|---|
| yes | **major** |
| no, and there is something new | **minor** |
| nothing observable changed | **patch** |

Everything below is this question applied to a specific surface.

## What is public

| surface | where |
|---|---|
| user verbs and their flags | `council <verb>`; `scripts/council.py` `VERBS` where audience is `user` |
| setup verbs | `council setup {init,skill,bots,toolchain,dispatcher}` |
| flake outputs | `packages.*`, `apps.*`, `devShells.*`, `formatter`, `homeManagerModules.default`, `checks.*` |
| module options | `programs.council.{enable,package,skill,mode,hermesHome}` |
| run artifacts | `<dimension>.json`, `scores.json`, `goals.json`, `calibration.json` |
| finding fields | `review.msg/v1`: `dimension`, `file`, `line_range`, `evidence_span`, `claim`, `claim_type`, `severity`, `confidence`, `falsifiable_check`, `suggested_fix` |
| gate exit codes | `0` satisfied, `1` not satisfied, `2` error |
| container | `docker run --rm -v "$PWD:/repo" review-council /repo` |
| the skill | `SKILL.md` frontmatter, rubric filenames, the path `council setup skill` installs to |
| the score | the 0–100 hybrid the gate enforces |

**Not public.** Dev verbs (`calibrate`, `ablate`, `golden`, `corpus`, `version`) and their
modules, internal Python under `scripts/` that no verb names, test fixtures, the
devshell's DX tools, and the wording of any message that is not parsed by a program.
These change in patches.

## Major

- renaming or removing a user verb, a setup verb, a flag, a module option or a flake output
- removing or renaming a finding field, or changing its type or meaning
- changing what a gate exit code means
- changing the score formula or scale so that a threshold calibrated before the change
  selects different diffs, **without** a recalibrated `scripts/calibration.json` in the
  same release
- dropping a platform, or raising the Python floor (`requires-python`)

## Minor

- a new verb, flag, option, flake output or artifact field — additive, with a default
- a new probe or analyzer, **with** a recalibrated `scripts/calibration.json` and a note
  under `### Changed` saying which way scores moved
- a new rubric rule that can move a dimension score, under the same condition
- a new platform

## Patch

- a bug fix that restores documented behaviour
- documentation, comments, tests
- an internal refactor whose outputs are byte-identical
- a pin or dependency bump that changes no output

## Scores move; say so

The score is the one surface that cannot be stable by construction: it is a function of
the analyzer set, the rubrics and the calibration. So:

- scores are comparable **within a major version**, never across one
- a minor release that moves them records the movement under `### Changed` in
  `## [Unreleased]`, with the direction and the fixture it was measured on
- a release that moves them must show the shipped threshold still yields the same
  verdicts on the golden fixtures — `council golden --check` pins both. If it does not,
  the release either ships a recalibrated `scripts/calibration.json` or is **major**,
  because then the user has to recalibrate a threshold of their own

## Versions before 1.0

None. `1.0.0` was the first public release, so there is no 0.x line to reinterpret. From
here, `MAJOR.MINOR.PATCH` as above.

## The working rule

Every commit that changes a public surface writes its entry under `## [Unreleased]` in
the matching Keep a Changelog category, **in the same commit**. A release is a bump, not
an editing session: `council version bump {major|minor|patch}` moves `## [Unreleased]` to
a dated heading, updates `pyproject.toml`, and leaves an empty `## [Unreleased]` behind.

## What is checked

`council version check` fails when:

| condition | why it matters |
|---|---|
| `pyproject.toml` version is not `X.Y.Z` | the one place the version lives |
| the newest CHANGELOG release is not that version | two numbers, one truth |
| released versions are not strictly descending | the file is read top-down |
| a version appears twice | a bump that was re-run |
| a released heading has no `YYYY-MM-DD` date | when, for every release |
| `## [Unreleased]` is not the first section | where the next entry goes |

`council version check --tag vX.Y.Z` additionally requires the tag to equal the version —
CI passes the pushed tag, so a mistyped tag fails the build instead of publishing a
wrong artifact.

`council version bump` refuses when `## [Unreleased]` is empty, when `pyproject.toml` and
the newest release disagree, and when the computed version does not increase. It prints
the `git tag` command rather than running it: tagging is a publishing decision.
