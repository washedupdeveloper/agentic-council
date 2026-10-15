# Nix

Everything that *can* be pinned is pinned in `flake.lock`; the parts that cannot are
exposed as pinned **interfaces** rather than rewritten into derivations.

## One command

There is exactly **one** app, `council`. The modules under `scripts/` are its verbs.

```bash
nix run .#council                        # lists the verbs
nix run .#council -- review <repo>       # drive a review to a verdict
nix run .#council -- gate <run-dir>      # score an existing run
nix run .#council -- doctor --repo <repo>
nix run .#council -- setup bots
nix shell .#review-council               # the command + the analyzers on PATH
```

`council <path>` is shorthand for `council review <path>`; a flag with no verb means
the same thing. An unknown first word is refused rather than guessed at — quietly
reviewing the cwd on a typo would be worse than saying so.

**On Windows the council runs in the container image.** Nix does not run on Windows,
so there is no native invocation; see `docs/CONTAINER.md`.

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
| `setup bots` | Install the reviewer and orchestrator profiles |
| `setup dispatcher` | Run the kanban dispatcher as a systemd user service |
| `setup toolchain` | Print or activate the pinned toolchain |

Four more verbs — `calibrate`, `ablate`, `golden`, `corpus` — exist only in
the **devshell**, because they are how you work *on* the framework rather than use
it. `nix develop` then `council --help` lists them; the shipped app refuses them.

`swarm`, `sample` and `merge` are **user** verbs, not dev ones, and that is deliberate:
the worker cards are executed by the dispatcher, which has no devshell and no PATH entry
for this framework, so the invocation they run must be the shipped app. `checks.commands`
enforces the split — every dev verb must be rejected by the app and accepted by the
devshell — so `audience` cannot decay into a comment.

## Why one command instead of thirteen

The modules stay separate — different arguments, tested separately — but the
**interface** is unified: thirteen top-level apps (`council-gate`, `council-doctor`,
`council-ablate`, …) made every operation look equally important, including the five a
normal user never runs. One command with verbs means one name to remember and one help
page that groups them.

## `--help` is always safe

A verb whose module parses arguments passes `--help` through and shows that module's
own help. The `setup` verbs **act** — they have no argument parsing — so the
dispatcher answers `--help` itself. Without that, `council setup bots --help` would
install the profiles rather than explain itself. A `--help` that does something is a
trap, not a help.

## What is Nix, and what is not

| Part | How | Why |
|---|---|---|
| The toolchain — 24 analyzers | `packages.toolchain` | One nixpkgs input, so the whole set moves atomically with a single lock revision. |
| The framework tree | `packages.framework` | The **shipped** tree — runtime modules, `bots/`, `skills/` — and nothing else. `packages.dev-framework` is the same tree plus the dev verbs and the suite. |
| What ships | `runtimeModules` / `devModules` | The shipping manifest, asserted against the CLI's own verb table by `checks.commands`. |
| The command surface | `apps.council` | The pinned toolchain is on PATH at exec time, so no devshell and no PATH setup. |
| The container image | `packages.container` | An OCI image, so Windows and docker-only users need nothing else. |
| The gates | `checks.*` | `nix flake check` is the one command a contributor runs before pushing. |
| The formatter | `formatter` | `nix fmt` uses the pinned `nixfmt`, so a caller never needs their own. |
| **The council loop** | a *verb*, not a derivation | It spawns non-deterministic LLM agents over the network. That is an effect, not a build; see below. |
| The scoring math | Python | Geomeans, Hill curves, floats — a build system is the wrong engine for arithmetic. |
| Corpus injection | Python | AST rewriting. |
| Resolving the toolchain | baked by the dispatcher | The launcher exports `REVIEW_COUNCIL_TOOLCHAIN`, so no runtime path has to `nix build` a flake. `council setup toolchain` still prints or activates it. |

### Why the loop is not a derivation

A council run spawns LLM agents over the network and writes into a run directory; a Nix
build is sandboxed, network-free and reproducible, and a council run is none of those
three. Modelling it as a derivation would mean an impurity escape hatch per run, which
buys nothing and costs the property that makes the rest of the flake trustworthy. So the
loop is *wrapped*: the interface is pinned — same toolchain, same modules, same store
path on every machine — while the effect stays explicit. **Pin the inputs, don't pretend
the effect is one.**

## On a darwin system

The flake declares **`aarch64-darwin`** alongside the two Linux systems, so on an Apple
Silicon Mac everything above works as written: `nix develop`, `nix build .#toolchain`,
`nix run .#council -- <verb>`, `nix flake check`.

Two things to know before you start:

- **`x86_64-darwin` is not available.** Not an omission — nixpkgs 26.11 dropped the
  platform upstream, so the attribute cannot be declared at all. On an Intel Mac, pin
  nixpkgs to 26.05 (which still receives security fixes) or use the container.
- **The image is Linux-only.** `packages.container` and `packages.image-root` are guarded
  to Linux because `dockerTools` cannot build a Linux userspace from darwin. That is
  correct rather than a gap: on darwin you use the flake directly, and the container is
  for a host that has docker and no nix.

### What is verified, and what is not

**Verified from a Linux machine**, so it holds on yours too:

| claim | how |
|---|---|
| the flake evaluates for `aarch64-darwin` | `nix flake check --all-systems --no-build` — every declared system, evaluated, nothing built |
| every one of the 24 analyzers resolves | `nix eval .#toolchain.absent --system aarch64-darwin` → `[]` |
| the closure is mostly substitutable | `nix build .#toolchain --system aarch64-darwin --dry-run` → **239 paths fetched, 5 built**, so the first build downloads rather than compiles |

That second row is the reason to expect this to work: the toolchain is built from one
nixpkgs revision, so a package that does not exist for darwin would show up as an entry in
`absent` rather than as a failure halfway through a build.

**Not verified: that it runs on darwin.** The author has no Mac, and CI builds Linux only —
macOS minutes count tenfold, so a macOS runner is deliberately not paid for. Nothing here
asserts the darwin build executes; that claim has not been made.

**So make it, once, on your machine:**

```bash
nix flake check
```

That is the same command CI runs, and it is the whole answer — it builds the toolchain,
runs the suite, the golden suite, the analyzer matrix, the linter checks and the command
surface. If it is green, the darwin support is proven for your machine rather than
asserted by someone else's.

## The tree, and why it is shaped this way

The modules resolve their own root as `dirname(__file__)/..`, so the framework tree
mirrors the repo layout: `scripts/` beside `bots/` and `skills/`. Everything a module
reads relative to *itself* lives in `scripts/` (`calibration.json`, `eval-baseline.json`,
`probes.py`, `score_reviews.py`, `toolchain.py`). Paths that concern the repo **under
review** are never framework-relative — they arrive as `--repo` or a run directory — and
that separation is what lets the whole tree live in a read-only store path.

**The tree carries only what a review runs.** `pyproject.toml`, `README.md`, the test
suite and the flake files are not in it: nothing at review time reads them, and the
toolchain arrives as `REVIEW_COUNCIL_TOOLCHAIN` from the launcher, so the copy never has
to build *this* flake to find it. The dev verbs are not in it either — `packages.framework`
is the shipped tree, `packages.dev-framework` is what the devshell runs from.

**And a module is not a program.** Each refuses a direct invocation unless
`REVIEW_COUNCIL_DISPATCHED` is set, and only the dispatcher sets it. That is what keeps
`python3 scripts/inject_defects.py` from being a way to plant defects in a repository by
accident, and it is why the shipped app is genuinely the only interface. See
`ARCHITECTURE.md` §8.2.

## What is deliberately not here

- **No `council-test` / `council-lint` verbs.** `nix flake check` already runs the
  suite, statix, deadnix and the formatter check, and `nix develop -c pytest` runs the
  suite against *your* working tree. A third path would be redundancy, not capability.
- **No Python package.** `pyproject.toml` has no `[build-system]` on purpose: `scripts/`
  is run in place, and the only distributable artifacts are the Hermes skills.
- **No cache configuration.** The toolchain's closure is 236/238 paths already in
  `cache.nixos.org`, so there is nothing for a private cache to save and no
  substituter to configure. `docs/CI.md` has the measurement and the recipe for adding one.

## Before you run the checks

**The flake source is git-only, and the checks read the flake source.** `nix flake check`
copies `${./.}` — which for a git repo is the set of *tracked* files. A brand-new module
that is not yet `git add`ed is therefore invisible to the checks, and a verb naming it fails
with `framework is missing scripts/<name>` — an error that says the file is absent when it
is sitting right there on disk, untracked.

```bash
git add -A          # FIRST
nix flake check     # then this
```

## Adding a verb

Add one entry to `commandSpecs` (or `setupSpecs`) in `flake.nix`:

```nix
myverb = {
  script = "my_module.py";   # must exist in the framework tree
  audience = "user";         # or "dev" for devshell-only
  probe = true;              # true if the module parses --help itself
  what = "one line for the help";
};
```

It appears in `council --help`, becomes `council myverb`, joins
`packages.review-council`, and is checked by `checks.commands` — which verifies the
module exists, that the verb starts, and that a dev verb stays out of the shipped app.
Set `probe = false` if the module does not parse arguments; the dispatcher will then
answer `--help` for it. `setupSpecs` entries carry only `script` and `what`.
