# Getting started — clone, then what

Four steps. Step 3 is the one people get stuck on, and it is not optional.

```
1. get `council`      — one of three commands, by what the machine has
2. council setup      — guided; writes one config file and installs
3. credentials        — per member, once. Hermes shares none between profiles.
4. council review     — a real review of a real repo
```

## 1. Get `council`

| the machine has | run |
|---|---|
| nix | `nix run github:washedupdeveloper/agentic-council -- setup` |
| docker | load the release tarball, then `docker run --rm -it -v "$PWD:/repo" review-council setup` |
| git + python ≥ 3.11 | `git clone https://github.com/washedupdeveloper/agentic-council && cd agentic-council && python scripts/council.py setup` |

For the docker row, get the image first — it is a release asset, not a registry pull:

```bash
curl -L -O https://github.com/washedupdeveloper/agentic-council/releases/latest/download/review-council.tar.gz
docker load -i review-council.tar.gz
```

The repository is published as **`agentic-council`**; the flake and the directory are
**`review-council`**. Same project, two names — the GitHub repo predates the rename.

The third row is the non-Nix path, and it needs no wrapper script: every module under
`scripts/` is stdlib-only, so the CLI itself runs on any Python ≥ 3.11. On a Hermes
host use `$HERMES_PYTHON` — never assume the interpreter is named `python3`, because
NixOS has none and Windows does not use that name.

## 2. `council setup`

Bare `council setup` is the guided first run. It detects Hermes, asks the few things
that are yours to decide (the gate, the sample count, the mode), **shows what it will
do**, writes `$HERMES_HOME/review-council.toml`, then installs the skill and the two
member profiles.

```bash
council setup --no-install   # write the config and stop
council setup --yes          # take every default; skips the questions, not the report
```

With no terminal it takes every default and says so, so a container or CI never hangs
on a prompt. Edit `review-council.toml` any time, then `council setup bots` to apply.

## 3. Credentials

**Hermes keeps provider credentials per profile and shares none between them.** So
installing the members is not the same as them being able to reach a provider, and
the council cannot run until each one can.

There are exactly **two** members, so two commands:

```bash
hermes -p council-generalist setup
hermes -p council-orchestrator setup
```

Each is interactive: it asks for the provider and the key, and writes them to that
profile's own `$HERMES_HOME/profiles/<name>/config.yaml`.

Three things worth knowing before you debug a 401:

- **A 401 right after install is a provisioning step, not breakage.** Profile
  export/import deliberately never carries credentials (`.env` is excluded), so an
  imported or freshly created profile has no working key until you provision one.
- **A profile does not inherit the global config.** A key in `~/.hermes/config.yaml`
  does not reach `~/.hermes/profiles/<name>/config.yaml`. Each profile needs its own.
- **`hermes config set` cannot create a `custom_providers` entry.** For a
  `custom:<name>` provider the key lives under `custom_providers`, and that block has
  to be written by round-tripping `config.yaml` — with a comment-preserving writer
  (ruamel, the one Hermes itself uses) — after backing the file up.

**Prove it, don't assume it.** One command per member:

```bash
hermes -p council-generalist chat -q 'Reply with exactly: SMOKE_OK'
```

A printed `SMOKE_OK` means that profile's credentials and model resolve. Do this
before a review, because otherwise the first failure you see is a reviewer exiting
non-zero several minutes into a run.

## 4. Review something

```bash
council doctor                # which analyzers are present; run this first
council review /path/to/repo --mode advisory --max-rounds 1
```

`--samples N` trades recall for wall-clock (default 5). Start with `advisory`: it
reports and changes nothing.

## The same thing on NixOS

The NixOS / home-manager path declares the first two steps instead of running them.
Add the flake as an input and import the module for the user that runs Hermes:

```nix
inputs.agentic-council.url = "github:washedupdeveloper/agentic-council";
home-manager.users.<name>.imports = [ inputs.agentic-council.homeManagerModules.default ];
```

That puts `council` on PATH and points Hermes at the skill — which is a **store
path**, so it is read-only and cannot drift. `nix/home-manager.md` has the options
and the two modes.

**Credentials remain step 3.** A module can install a definition; it cannot install a
secret, and a provider key does not belong in a world-readable store path. Two honest
options:

- **Run it once per member** (`hermes -p <member> setup`). Imperative, but it is a
  one-time act on a machine, and the profiles it writes are ordinary Hermes state.
- **Declare it with a secret manager.** Put the key in sops/agenix and have the
  profile's `config.yaml` `custom_providers` block read from it. This is fiddly,
  because Hermes owns that file and rewrites it — so verify with the smoke test after
  every switch, not once.

## Updating

A skill is a **deployment**, not a copy you edit.

```bash
git pull && council setup skill          # non-nix
nix flake update && home-manager switch  # nix
council setup skill --check              # exits non-zero when the deployment lags
```

## What "it works" looks like

| check | proves |
|---|---|
| `council --help` | the CLI and its pinned toolchain resolve |
| `council doctor` | which analyzers are present, and which are missing |
| `hermes -p <member> chat -q 'Reply with exactly: SMOKE_OK'` | that member's credentials and model resolve |
| `council setup skill --check` | the deployment matches its source |
| `council review <repo> --max-rounds 1` | the whole loop, end to end |

A bootstrap that has never run a review has verified nothing. Run the last row.
