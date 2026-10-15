# review-council

An autonomous code-review council. One reviewer agent, sampled N times, judged
against pinned deterministic analyzers, iterating until a hybrid score clears a
threshold — or until it stops improving and hands you a plan.

## Run it

```bash
curl -L -O https://github.com/washedupdeveloper/agentic-council/releases/latest/download/review-council.tar.gz
docker load -i review-council.tar.gz          # -> review-council:latest

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo" \
  -v "$HOME/.hermes:/home/council/.hermes" \
  -v "$(dirname "$(command -v hermes)")/..:/opt/hermes:ro" \
  review-council /repo
```

The tarball is a release asset on a tag, so the URL above keeps working across
versions and needs no registry account. A nix host needs no download:
`nix build github:washedupdeveloper/agentic-council#container`.

`--user` is not optional in practice: the image runs as uid 1000, so a repository
mounted from any other account is read-only to it. Run it as yourself and the
output belongs to you.

Everything after the image name goes to the harness: `--mode advisory`,
`--samples 3`, `--max-rounds 1`, `--threshold 85`, `--baseline auto`.

The CLI is in the image, so the verbs work with no Hermes mounted:

```bash
docker run --rm review-council                                     # the verbs
docker run --rm -v "$PWD:/repo" review-council doctor --repo /repo
```

Only a **review** needs Hermes.

### Build it yourself

```bash
nix build .#container && docker load < result   # with nix: the LAYERED image
docker build -t review-council .                # docker only: nix runs in the build
```

Both build from `flake.lock`, so the analyzers inside are the pinned store paths
either way. The flake is primary — its layers are content-addressed, so an
unchanged toolchain pulls as nothing. The Dockerfile is for a host with docker and
no nix, and produces one layer, because the layering is `dockerTools`'.

Neither is defined twice: `flake.nix` owns the image's contents, and the Dockerfile
adds only the container plumbing.

### What it needs

| | |
|---|---|
| **docker** or podman | to run the image |
| **Hermes** | the agents |
| **credentials, once** | per profile — see below |

Nothing else. No skill library, no nix on your machine (the Dockerfile installs it
inside the build), and no clone if you load the published image.

`council doctor` answers "is this machine ready?" in one place, Hermes included —
beta tells you how much of the score is deterministic and says nothing about
whether a review can run at all:

```
hermes    : Hermes Agent v0.0.0 (2026.9.24)  (/home/you/.nix-profile/bin/hermes)
  profiles: council-generalist, council-orchestrator  (provider configured: both)
  gateway : 127.0.0.1:9119 reachable  (a hint only; the council drives the launcher, not this)
  verdict : ready — a review can run
```

The verdict names the first thing that would stop a review, so you fix that one
thing rather than reading a list. `--probe` spends one real agent turn — the only
check that proves Hermes works.

## Install it

Four steps; the third is the one that bites. Full walkthrough, including the NixOS
path: **[docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)**.

**1. Get `council`** — whichever the machine has:

| the machine has | run |
|---|---|
| nix | `nix run github:washedupdeveloper/agentic-council -- setup` |
| docker | `docker run --rm -it -v "$PWD:/repo" review-council setup` |
| git + python ≥ 3.11 | `git clone https://github.com/washedupdeveloper/agentic-council && cd agentic-council && python scripts/council.py setup` |

The repository is published as `agentic-council`; the flake and directory are
`review-council`. Same project, two names.

**2. `council setup`** — guided. It detects Hermes, asks the few things that are
yours to decide (the gate, the sample count, the mode), shows what it will do, writes
one editable file, and installs the skill and the two member profiles. With no
terminal it takes every default, so a container or CI never hangs on a prompt.

**3. Credentials.** Hermes keeps them **per profile and shares none**, so the council
cannot reach a provider until each member has one — there are two:

```bash
hermes -p council-generalist setup
hermes -p council-orchestrator setup
```

Then prove it rather than assuming it:

```bash
hermes -p council-generalist chat -q 'Reply with exactly: SMOKE_OK'
```

A 401 here is a provisioning step, not breakage. Why, and how to do it declaratively
with a secret manager: [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md#3-credentials).

**4. Review something.**

```bash
council doctor     # which analyzers are present
council review <repo> --mode advisory --max-rounds 1
```

### On NixOS

Declare steps 1 and 2 instead of running them:

```nix
inputs.agentic-council.url = "github:washedupdeveloper/agentic-council";
home-manager.users.<name>.imports = [ inputs.agentic-council.homeManagerModules.default ];
```

That puts `council` on PATH and points Hermes at the skill as a **store path** —
read-only, so it cannot drift. Credentials are still step 3: a module can install a
definition, not a secret. Options: `nix/home-manager.md`; reasoning:
[docs/bootstrap.md](docs/bootstrap.md).

### Everything you might change is in one file

`$HERMES_HOME/review-council.toml`. Edit it, then `council setup bots`.

| key | what it does |
|---|---|
| `review.threshold` | the gate. Lower is stricter. |
| `review.samples` | reviewer passes per round. More finds more, costs more time. |
| `review.mode` | `advisory`, `semi`, or `full`. |
| `members.<name>.toolsets` | exactly what that member may do. |
| `members.<name>.model` / `.provider` | pin a model per member; empty inherits. |

TOML, not YAML, because the framework is stdlib-only and the toolchain's Python has
no PyYAML. A broken file is refused with the line and the reason rather than
half-applied. Capabilities are read from it, not hardcoded.

### Or drive it as a native `/goal`

```bash
council goal <repo>          # prints the completion contract and the quality gate
```

The gate is `council gate --latest --repo <repo>`, which scores the newest run and
exits 0 only when satisfied. Hermes runs quality gates **before** the judge and
skips the judge on a red gate, so the decision to stop is a command's exit code
rather than a model's opinion — and `/goal status`, `/goal pause`, `/subgoal` and
the turn budget come for free.

**Updating.** A skill is a deployment, not a copy you edit.

```bash
git pull && council setup skill          # non-nix: re-copy from source
nix flake update && home-manager switch  # nix: the store path moves atomically
council setup skill --check              # exits non-zero when the deployment lags
```

On the Nix path the deployment is a **store path**, so it is read-only and cannot
drift — there is nothing to re-sync. The copier remains for hosts without Nix.

## Before you trust a score

The shipped threshold (**87.1141**) was calibrated on *this* repository from **one**
known-good sample, and `scripts/calibration.json` calls it `PROVISIONAL`. On your
repository it is not a pass mark — read the score as a relative signal, or set your
own with `--threshold`.

**The findings are the portable output; the score is a local yardstick.**

## What it does

- **One reviewer, sampled N times**, carrying all five rubrics — security,
  correctness, readability, architecture, performance — and labelling each finding
  with its dimension. Measured against five isolated specialists at equal cost on a
  22-defect corpus: **22/22 against 13/22**, so the specialists were deleted.
- **A deterministic half.** 24 pinned analyzers (statix, deadnix, ruff, bandit,
  gitleaks, tokei, …) plus built-in probes that need nothing installed. `beta` is
  the fraction of the score they cover; at `beta` = 1 the score is deterministic.
- **A hybrid gate.** `score = beta·deterministic + (1−beta)·LLM`, against a
  threshold, with stall and no-improvement detection.
- **Incremental review.** `--baseline auto` reads only what changed since the last
  whole-repo run, carrying that run's findings for unchanged files. The denominator
  stays the whole repository, so the number stays comparable.

## How it is put together

One interface: `council <verb>`. Every verb is a module in `scripts/`, and the verb
table lives in `scripts/council.py`. Nothing here is meant to be run by hand — the
flake generates the launcher and the image carries the same tree, so both routes
run the same code.

Hermes is the only agent runtime: the reviewer is a Hermes profile, the loop spawns
it through Hermes, and there is no second backend to configure.

| | |
|---|---|
| `scripts/` | the programs; every verb is one module |
| `bots/`, `skills/` | the profiles, and the rubrics they carry |
| `tests/` | the suite, including the golden fixtures that pin scores |
| `docs/` | the design, and what the measurements ruled out |
| `research/`, `runs/` | the reports the design rests on, and the run records |
| `flake.nix` | the pinned toolchain, the launcher, the checks, the image |

### What it runs on

| | |
|---|---|
| **the flake** | `x86_64-linux`, `aarch64-linux`, `aarch64-darwin`. No x86_64-darwin: nixpkgs dropped it. |
| **the image** | any Linux docker host, either architecture |
| **the CLI** | Python 3 stdlib, no third-party packages. Windows is a supported target for the modules; only the image is Linux. |

Nothing resolves a path from the author's machine. See `docs/NIX.md`.

## Docs

| | |
|---|---|
| [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) | clone, install, credentials, first review — start here |
| [docs/bootstrap.md](docs/bootstrap.md) | the four setup paths, and what is deliberately not declarative |
| [docs/FRAMEWORK.md](docs/FRAMEWORK.md) | the design: roles, the finding contract, the score, the loop |
| [docs/AUTONOMY.md](docs/AUTONOMY.md) | the loop in detail, and the Hermes workflow |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, scoring math, integration points |
| [docs/BASELINE.md](docs/BASELINE.md) | incremental review, and what invalidates a carried finding |
| [docs/CALIBRATION.md](docs/CALIBRATION.md) | how the threshold and the curves were derived |
| [docs/BOTS.md](docs/BOTS.md) | the bot roster and the capability model |
| [docs/EXTENDING.md](docs/EXTENDING.md) | add a language, or a dimension |
| [docs/CI.md](docs/CI.md) | the CI jobs, and why neither needs a custom cache |
| [docs/DECISIONS.md](docs/DECISIONS.md) | the locked choices, and what the measurements ruled out |
| [docs/MILESTONES.md](docs/MILESTONES.md) | the plan and its acceptance records |
| [docs/CONTAINER.md](docs/CONTAINER.md) | the image: what it sets up, and its one limitation |
| [research/](research/) | the reports the design rests on |
| [CHANGELOG.md](CHANGELOG.md) | what shipped in each release |

## License

MIT — see [LICENSE](LICENSE).
