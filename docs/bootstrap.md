# Bootstrap — one declaration, four paths

A fresh clone must reach a working council with one command, and the *state* it reaches
must be written down once. The declaration is in one place — `scripts/init.py` and the
`DEFAULTS` it writes — reached by four entry points, one per host:

| Host | Entry point | What reaches the declaration |
|---|---|---|
| NixOS / home-manager | import the module, then `nh os switch` | `nix/module.nix` (this repo), imported by the host flake |
| Nix, not NixOS | `nix run .#council -- setup init` | the pinned toolchain's dispatcher |
| Docker, no Nix | `docker build`, then run the image | `Dockerfile`, which builds `.#image-root` |
| Neither | `python scripts/council.py setup` | any Python ≥ 3.11 — the CLI is stdlib-only |

There is deliberately **no shell script**: every verb is a Python module reached through
`council`, and `checks.no-shell-scripts` enforces it. The non-Nix path needs no wrapper
because the CLI is already the entry point.

The one part of the declaration that can be *diffed* is the deployment:
`council setup skill --check` compares the installed skill against this tree file by
file and exits non-zero on drift.

## The Nix path is the only one where drift is impossible

`council setup skill` **copies** the repo's tree into the skill library. A copy drifts —
measured, before it was fixed: **11 files differed from source**, and the deployed suite
had never run at all, because it imported a file the copier deliberately does not ship.
See `docs/adr/0004`.

Nix removes the failure instead of managing it. `.#skill` is a derivation that *lays out
the same tree* — `SKILL.md`, `scripts/`, `tests/`, `assets/bots/`, `assets/rubrics/`,
`nix/`, `flake.nix` + `flake.lock` — as a **store path**. A store path is read-only, so:

- nothing can edit the deployed skill in place, so it cannot drift from source;
- the copier is not needed on this path at all, so it cannot be the thing that broke;
- updating is `nix flake update` + switch, atomic and pinned by `flake.lock`, like every
  other input.

This is the difference between a **reference** and a **store reference**, the distinction
`docs/adr/0004` keeps straight: a directory named in `skills.external_dirs` is merely
*readable*; a store path is *read-only*. The module takes the second. A host without Nix
takes the first — the copier copies the working tree into the directory
`skills.external_dirs` names, because there is no read-only tree to point at.

## What is deliberately NOT declarative

- **The review loop.** It spawns non-deterministic LLM agents over a network. That is an
  effect, not a build: no derivation can produce it, and pretending otherwise would put a
  network dependency inside `nix build`. The *interface* is pinned (the `council`
  launcher, the toolchain, the rubrics); the loop is invoked.
- **Profile credentials.** `council setup bots` writes a profile per member, each with
  its own `HERMES_HOME`. A key belongs in the user's secret store, not in a
  world-readable store path — so the module installs the *definition* and the first run
  authenticates. `setup init` names this as the one manual step rather than letting it
  fail at review time.

## The non-Nix path, and why it can work at all

Every script under `scripts/` is **stdlib-only**: the only non-stdlib imports are its own
sibling modules. So on a host with no Nix, the council runs on any Python ≥ 3.11 —
including Hermes' own `$HERMES_PYTHON`:

```console
$ python scripts/council.py setup
```

Never assume that interpreter is named `python3`: NixOS has none, and Windows does not
use that name. `$HERMES_PYTHON` is the reliable choice on a Hermes host.

What is lost without Nix: the pinned *analyzers*. The council's deterministic probes
shell out to the pinned binaries (`statix`, `deadnix`, `nixfmt`, `ruff`, `mypy`,
`bandit`, `osv-scanner`, `gitleaks`, `shellcheck`, `pytest`). Their absence does not stop
a review — `council doctor` reports what is missing and the rubric scores what it can
measure.

## The Docker path

`Dockerfile` exists for a host that can run docker but not nix: nix is installed *inside
the build*, never on the host, and the image root comes from the same `.#image-root`
derivation as `.#container` so the two cannot drift. Use it to **run** the council. It is
not the setup path — an image is not a permanent install, and a container that disappears
takes the deployment with it.

## Order of operations (all paths)

1. **Resolve the library.** Ask Hermes where `skills.external_dirs` points
   (`sync_to_skill.py` does this) rather than assuming a path. A mounted library is the
   source of truth; the profile-local dir is the fallback.
2. **Make the skill reachable.** Store path (Nix) or a copy into `skills.external_dirs`
   (script). Merge, never clobber: another entry may belong to someone else, and the
   comparison must use **expanded** paths, because the config may hold `~/x` while the
   script resolves an absolute path.
3. **Install the members.** One reviewer profile carrying all five rubrics, and one
   orchestrator. Definitions from the repo; credentials from the user.
4. **Verify.** `council doctor` for the toolchain, `council setup skill --check` for the
   deployment, and a real review for the whole thing. A bootstrap that has never run a
   review has verified nothing.

## A defect this work found, not fixed

**The copier's copy set depends on which audience ran it.** `sync_to_skill.py` globs
`scripts/*.py` in the tree it runs in. The `user` tree omits the four dev modules, so
`nix run .#council -- setup skill` does not merely omit them — it **prunes** them from a
deployment that has them, because they look like files the repo does not have.
Reproduced: `--check` from the user tree reports `EXTRA scripts/ablate.py (deleted in the
repo)` for a file that is in the repo.

The deployment's own test suite then cannot import what it tests — the same failure class
as the copier's self-exclusion, by a different route. Run the sync from the **devshell**
dispatcher, whose tree is complete, not from `nix run .#council`.

The fix is not to pick an audience: a copy set should not be a function of the environment
the copy ran in — the deployment is one artifact with one definition. Until then this is a
known sharp edge, and the `nix develop` invocation is the workaround, not the design.

## Verifying this document

Every claim above that can be checked mechanically is checked by
`scripts/claim-audit.py` in the `hermes-skills` repository for that repo's prose. This
document's checkable claims are the stdlib-only one and the 11-file drift figure; both
were measured, and the second is also why `docs/adr/0004` exists.
