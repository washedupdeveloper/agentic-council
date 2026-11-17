# Versioning and releasing

This project follows [Semantic Versioning](https://semver.org/) with the policy
written down here, a changelog in the repository, and a gate that fails when the
three copies of the version disagree.

## The deciding question

**Does an existing user have to change something to keep the same meaning?**

| answer | bump |
|---|---|
| yes | **major** |
| no, and there is something new | **minor** |
| nothing observable changed | **patch** |

## The public surface

Enumerated from the tool, not from memory (`council --help`, `council review
--help`, `council ci --help`, `council init --help`; `nix flake show`):

- subcommands `review`, `ci`, `init`, `pr`, `baseline` and `doctor`, their flags,
  and the optional console scripts `council-mcp` and `council-acp`;
- exit codes: `0` pass, `1` fail, `2` incomplete, `3` could not start;
- `verdict.json` and its fields, including `format`, `verdict`, `findings[].state`,
  `findings[].proof_strength`, `scope_ignored_omitted`, `rules[].glob/doc/paths/truncated`,
  `prompt_bytes`, `prompt_limit`, `prompt_acknowledged`, `context_depth`,
  `diff_sha256`, `skipped`, `context`, `unresolved`, `references`, `sliced` and
  `units[]` (each unit's files, ranges, digest, prompt size, depth, whether it is a
  window, and verdict); and the `--plan` fields `windows` and
  `estimated_samples`;
- the shipped reviewer prompt's contract: one JSON object with five sections,
  and the closed proof-kind set (`absent`, `present`, `command`, `repro`,
  `json`, `diff`);
- the wheel (`council-<version>-py3-none-any.whl`) and the OCI image
  (`council:<version>`, entrypoint `/bin/council`);
- the configuration file `council.toml` and its keys.

**Not public** — changing these is not a version event: `tools/` (maintainer
scripts), `claims.toml` and the claim ids, `fixtures/`, internal modules that no
entry point reaches, and the wording of messages no program parses.

## Definitions

**Major** — renaming or removing a subcommand, flag or configuration key;
removing or retyping a `verdict.json` field; changing what an exit code means;
removing a proof kind; dropping a platform; raising the Python floor.

**Minor** — a new subcommand, flag, configuration key, verdict field or proof
kind with a default; a new artifact; a new platform.

**Patch** — a bug fix that restores documented behaviour; docs, comments, tests;
an internal refactor whose outputs are byte-identical.

There is no computed score or threshold to recalibrate, so the calibration
clause of the general policy does not apply here. If one is ever reintroduced,
its movement and fixture must be recorded in the same release.

## Where the version lives

Three copies, and they must agree:

1. `pyproject.toml` — `[project] version`, the build metadata;
2. `CHANGELOG.md` — the newest `## [X.Y.Z] — YYYY-MM-DD` heading;
3. prose claims of the shape `Current release vX.Y.Z` in `README.md` and
   `docs/**` (excluding `CHANGELOG.md` and run records, which are history).

`python tools/release.py check` verifies all three, plus: `## Unreleased` is
the first section, released versions are strictly descending, no version
appears twice, and every release heading carries a valid date. `--tag vX.Y.Z`
checks a pushed tag against the build metadata without asking git.

Before the first release the changelog has only `## [Unreleased]`; the check
passes and says no version has been released yet.

## Cutting a release

1. Every public change already has its line under `## [Unreleased]`.
2. `python tools/release.py bump --version X.Y.Z` moves those entries under a
   dated heading, updates `pyproject.toml`, rewrites every prose claim, leaves
   an empty `## [Unreleased]`, and **prints** the `git tag` command. It refuses
   an empty Unreleased section, a malformed version, or a version that does not
   increase. `--dry-run` shows the diff without writing.
3. Commit the bump. The gate runs `python tools/release.py check`.
4. Tag the commit the check passed on — tagging publishes, so it is a person's
   decision, never a script's.
5. Build the artifacts from the tag's tree, never from the working branch:
   `git show <tag>:pyproject.toml` must carry the version, and the wheel and
   image must be built at that commit.

Never tag a red gate. Never move a published tag over product code; a follow-up
commit is honest, a moved tag is not.
