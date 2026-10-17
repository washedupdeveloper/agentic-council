# Contributing

One gate decides whether a change is done:

```bash
nix flake check --keep-going     # "all checks passed!" or it is not done
```

`nix develop` first, or let direnv do it (`.envrc`). The suite alone is
`nix develop -c pytest tests/ -q`.

## Before your first change

| read | why |
|---|---|
| [`AGENTS.md`](AGENTS.md) | the rules that are easy to break by accident, and the reasoning |
| [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) | what the product does and how a run works |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | adding a verb, a rubric or a probe |
| [`docs/VERSIONING.md`](docs/VERSIONING.md) | what counts as major, minor and patch |

`AGENTS.md` is written for an agent and is the most complete statement of the
constraints; nothing here repeats it.

## The three that catch everyone

1. **`git add` before you build.** Nix cannot see an untracked file, so a new module is
   invisible to the build and the failure looks like a code bug.
2. **No shell scripts.** Zero `.sh` files, enforced by `checks.no-shell-scripts`.
   Operations are Python modules reached through `council <verb>`.
3. **A new verb touches three places** — the module, `VERBS` in `scripts/council.py`,
   and `runtimeModules` or `devModules` in `nix/builders.nix`. `checks.commands` fails
   if they disagree.

## Every public change writes its changelog entry in the same commit

`CHANGELOG.md` under `## [Unreleased]`, using `### Added` / `### Changed` / `### Fixed`.
A release is `council version bump {major|minor|patch}`, never a hand edit — the verb
refuses an empty `[Unreleased]`, which is what keeps the entry from being forgotten.

## Using the council on your own repository

```bash
nix flake init -t github:washedupdeveloper/agentic-council
```

That writes a working `flake.nix` importing the council's packages, formatter and app.
`#home-manager` writes a module instead. `checks.templates` keeps both honest.
