# Nix

Everything that *can* be pinned is pinned in `flake.lock`; what cannot is exposed as a pinned **interface**, not rewritten into a derivation.

## One command

One app, `council`; the modules under `scripts/` are its verbs.

```bash
nix run .#council                        # lists the verbs
nix run .#council -- review <repo>       # drive a review to a verdict
nix run .#council -- gate <run-dir>      # score an existing run
nix run .#council -- doctor --repo <repo>
nix run .#council -- setup bots
nix shell .#review-council               # the command + the analyzers on PATH
```

`council <path>` is shorthand for `council review <path>`; a flag with no verb means the same. An unknown first word is refused.

**On Windows the council runs in the container image** — Nix does not run on Windows; see `docs/CONTAINER.md`.

### Verbs

| Verb | What |
|---|---|
| `review [<repo>]` | Drive a review to a verdict (the loop) |
| `gate <run-dir>` | The deterministic gate: score a run directory |
| `doctor [--repo DIR]` | Which analyzers ran, and the β they yield |
| `probes [<name>]` | The built-in deterministic probes |
| `inventory` | The pinned tool set as JSON |
| `sample <repo> --index N` | Run ONE reviewer sample (a swarm worker's entry point) |
| `merge <run-dir>` | Bucket a round's samples into the per-dimension files |
| `swarm [<repo>]` | Build the durable council as a kanban graph |
| `baseline --repo DIR` | Report the baseline, or what changed since it |
| `metrics [<run-dir>...]` | Acceptance rate, addressed rate and iterations from judged findings |
| `goal <repo> [--json]` | Express a run as a native Hermes `/goal` + quality gate |
| `cron <repo> [--install]` | Print or install a scheduled unattended review |
| `pr <run-dir> --repo OWNER/NAME --pr N [--post]` | Post a run's verdict to a pull request |
| `setup init` | Guided first-run setup: write the config, then install |
| `setup skill` | Install the council skill into the Hermes skill library |
| `setup bots` | Install the reviewer and orchestrator profiles |
| `setup dispatcher` | Run the kanban dispatcher as a systemd user service |
| `setup toolchain` | Print or activate the pinned toolchain |

Five more verbs — `calibrate`, `ablate`, `golden`, `corpus`, `version` — exist only in the **devshell**; `nix develop` then `council --help` lists them, and the shipped app refuses them.

`swarm`, `sample` and `merge` are **user** verbs: the dispatcher executes the worker cards and has no devshell or PATH entry for this framework, so the invocation must be the shipped app. `checks.commands` enforces the split — every dev verb must be rejected by the app and accepted by the devshell.

## Why one command instead of thirteen

Thirteen top-level apps (`council-gate`, `council-doctor`, `council-ablate`, …) made every operation look equally important, including the four a normal user never runs. The modules stay separate — different arguments, tested separately — but the **interface** is unified: one name, one help page.

## `--help` is always safe

A verb whose module parses arguments passes `--help` through to that module's own help. The `setup` verbs **act** — no argument parsing — so the dispatcher answers `--help` itself; otherwise `council setup bots --help` would install the profiles rather than explain itself.

## What is Nix, and what is not

| Part | How | Why |
|---|---|---|
| The toolchain — 14 analyzers | `packages.toolchain` | One nixpkgs input, so the whole set moves atomically with a single lock revision. |
| The framework tree | `packages.framework` | The **shipped** tree — runtime modules, `bots/`, `skills/` — and nothing else. `packages.dev-framework` is the same tree plus the dev verbs and the suite. |
| What ships | `runtimeModules` / `devModules` (`nix/builders.nix`) | The shipping manifest, asserted against the CLI's own verb table by `checks.commands`. |
| The command surface | `apps.council` | The pinned toolchain is on PATH at exec time, so no devshell and no PATH setup. |
| The installable | `packages.review-council` | What `home.packages` takes. Its `bin/` carries the dispatcher **and** the toolchain, so one path is enough. `packages.default` is **not** this — it is the toolchain. |
| The deployable skill | `packages.skill` | `council-skill`, ready to drop into a skills directory without running the module. |
| The home-manager module | `homeManagerModules.default` | `programs.council.*`; deploys the skill and puts the package on PATH. |
| The container image | `packages.container` | An OCI image, so Windows and docker-only users need nothing else. |
| The gates | `checks.*` | `nix flake check` is the one command a contributor runs before pushing. Three tiers: eval (`module`, `flake` — a value in the configuration), build (`skill-layout`, `tests`, `golden`, `probes`, `commands`, … — the artifact a builder produced), and e2e (`.#vm-test` — a running machine). |
| The formatter | `formatter` | `nix fmt` uses the pinned `nixfmt`, so a caller never needs their own. |
| **The council loop** | a *verb*, not a derivation | It spawns non-deterministic LLM agents over the network. That is an effect, not a build; see below. |
| The scoring math | Python | Geomeans, Hill curves, floats — a build system is the wrong engine for arithmetic. |
| Corpus injection | Python | AST rewriting. |
| Resolving the toolchain | baked by the dispatcher | The launcher exports `REVIEW_COUNCIL_TOOLCHAIN`, so no runtime path has to `nix build` a flake. `council setup toolchain` still prints or activates it. |

### Why the loop is not a derivation

A council run spawns LLM agents over the network and writes into a run directory; a Nix build is sandboxed, network-free and reproducible, and a council run is none of those three. So the loop is *wrapped*, not derived: the interface is pinned — same toolchain, same modules, same store path on every machine — while the effect stays explicit. **Pin the inputs, don't pretend the effect is one.**

## On a darwin system

The flake declares **`aarch64-darwin`** alongside the two Linux systems, so `nix develop`, `nix build .#toolchain`, `nix run .#council -- <verb>` and `nix flake check` all work on an Apple Silicon Mac.

- **`x86_64-darwin` is not available.** nixpkgs 26.11 dropped the platform upstream, so the attribute cannot be declared at all. On an Intel Mac, pin nixpkgs to 26.05 (which still receives security fixes) or use the container.
- **The image is Linux-only.** `packages.container` and `packages.image-root` are guarded to Linux because `dockerTools` cannot build a Linux userspace from darwin; on darwin you use the flake directly.

### What is verified, and what is not

**Verified from a Linux machine:**

| claim | how |
|---|---|
| the flake evaluates for `aarch64-darwin` | `nix flake check --all-systems --no-build` — every declared system, evaluated, nothing built |
| every one of the 14 analyzers resolves | `nix eval .#toolchain.absent --system aarch64-darwin` → `[]` |
| the closure is mostly substitutable | `nix build .#toolchain --system aarch64-darwin --dry-run` → **209 paths fetched (454.3 MiB), 5 built** |

The toolchain is built from one nixpkgs revision, so a package missing for darwin shows up as an entry in `absent`, not as a failure halfway through a build.

**Not verified: that it runs on darwin.** The author has no Mac and CI builds Linux only — macOS minutes count tenfold, so a macOS runner is deliberately not paid for.

**So make it, once, on your machine:**

```bash
nix flake check
```

That is the command CI runs: it builds the toolchain and runs the suite, the golden suite, the analyzer matrix, the linter checks and the command surface.

## The tree, and why it is shaped this way

The modules resolve their own root as `dirname(__file__)/..`, so the framework tree mirrors the repo layout: `scripts/` beside `bots/` and `skills/`. Everything a module reads relative to *itself* lives in `scripts/` (`calibration.json`, `eval-baseline.json`, `probes.py`, `score_reviews.py`, `toolchain.py`). Paths that concern the repo **under review** arrive as `--repo` or a run directory, never framework-relative — that separation is what lets the whole tree live in a read-only store path.

**The tree carries only what a review runs.** `pyproject.toml`, `README.md`, the test suite and the flake files are not in it: nothing at review time reads them, and the toolchain arrives as `REVIEW_COUNCIL_TOOLCHAIN` from the launcher. The dev verbs are not in it either.

**And a module is not a program.** Each refuses a direct invocation unless `REVIEW_COUNCIL_DISPATCHED` is set, and only the dispatcher sets it — which keeps `python3 scripts/inject_defects.py` from planting defects in a repository by accident. See `ARCHITECTURE.md` §8.2.

## What is deliberately not here

- **No `council-test` / `council-lint` verbs.** `nix flake check` already runs the suite, statix, deadnix and the formatter check, and `nix develop -c pytest` runs the suite against *your* working tree.
- **No Python package.** `pyproject.toml` has no `[build-system]` on purpose: `scripts/` is run in place, and the only distributable artifacts are the Hermes skills.
- **No cache configuration.** The toolchain's closure is 236/238 paths already in `cache.nixos.org`, so there is nothing for a private cache to save. `docs/CI.md` has the measurement and the recipe for adding one.

## Before you run the checks

**The flake source is git-only, and the checks read the flake source.** `nix flake check` copies `${./.}` — for a git repo, the set of *tracked* files. A brand-new module that is not yet `git add`ed is invisible to the checks, and a verb naming it fails with `framework is missing scripts/<name>` — an error that says the file is absent when it is on disk, untracked.

```bash
git add -A          # FIRST
nix flake check     # then this
```

## Adding a verb

Add one entry to `VERBS` (or `SETUP`) in `scripts/council.py`:

```python
# name -> (module, audience, takes arguments, one-line description)
"myverb": ("my_module.py", "user", True, "one line for the help"),
```

The module must exist in the framework tree; `audience` is `"user"` (ships) or `"dev"` (devshell only); `takes arguments` false means the verb **acts**, so the dispatcher answers `--help` itself. The verb then appears in `council --help`, becomes `council myverb`, joins `packages.review-council`, and is checked by `checks.commands` — which verifies the module exists, that the verb starts, and that a dev verb stays out of the shipped app. `SETUP` entries are `name -> (module, description)`, always user-audience.
