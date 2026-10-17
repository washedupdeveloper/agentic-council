# CI

Two workflows, both on **GitHub-hosted** runners: `.github/workflows/ci.yml` (tests +
gate) and `.github/workflows/image.yml` (the image).

| Job | Runner | What it proves |
|---|---|---|
| `tests` (ci.yml) | `ubuntu` + `macos` + `windows` | The framework is stdlib-only and runs on all three. This job **is** the portability guarantee (DECISIONS #2). |
| `gate` (ci.yml) | `ubuntu-latest` | `nix flake check` under the pinned toolchain, on a machine that shares nothing with yours — **including the darwin declaration**, evaluated by `--all-systems --no-build` at no macOS cost. |
| `release` (image.yml) | `ubuntu-latest` | On a `v*` tag: builds the image and attaches it to that release as `review-council.tar.gz`. Tags only — the gate already builds the image on every push and pull request. |

## The darwin declaration, without a macOS runner

`systems` declares `aarch64-darwin`, so something has to check it:

```bash
nix flake check --all-systems --no-build
```

**Measured, not assumed:** a canary check referencing Linux-only `pkgs.systemd` made it exit
**1**, while a plain `nix flake check` exited **0**. So it catches a darwin-only evaluation
error — a tool that does not exist for the platform — in seconds, for no macOS minutes.

**Building on darwin is what is not paid for.** macOS minutes count tenfold, the darwin
closure is 239 fetched paths and 5 built ones, and the author uses no Mac: execution there
is left to whoever runs the flake — `nix flake check`, the same command this gate runs on
Linux (`docs/NIX.md` states this from the user's side). To add the runner back, restore the
matrix:

```yaml
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
```

## The container image job

`nix build .#container` needs nix only on a runner; the person who runs the council installs
nothing but docker. `.#container` is a `dockerTools` layered image, so the output is one
file: a gzipped `docker load` tarball, measured at 333 MB with a single-path closure.

**The gate verifies it, not this workflow.** `checks.container` builds the image on every
push and pull request, on the clean runner, beside the tests — possible because the output
is a **tarball**: no docker daemon needed, so unlike the VM test it can be an ordinary
check. `image.yml` only publishes, which a check cannot do.

**A release asset, not a registry.** The tarball is attached to the tag's GitHub Release
under a **fixed** name, so `releases/latest/download/review-council.tar.gz` survives every
version. Measured:

| how it is published | downloadable without a GitHub account | how long it lasts |
|---|---|---|
| **release asset** | **yes** — 200 with no token | as long as the release |
| Actions artifact | **no** — 401 from the API, 404 from the web path; needs a signed-in user | 90 days by default |
| a registry (GHCR) | yes | as long as the registry entry |

It drops `packages: write`. The image is still built **layered**, now a build-cache property (`nix build` hits when the toolchain is
unchanged) rather than registry dedup. `docs/CONTAINER.md` has the user-facing side.

## The VM test

`nix build .#vm-test` runs the council end-to-end in a real NixOS VM: boot, a target
repository, the pinned probes, the fan-out, the bucketing, the gate, a verdict.

It is **not** in `nix flake check`: a VM test needs KVM, and the gate would then require it
of every contributor — hence a `packages` output, not a `checks` one, and a fast gate.

**The test's network is its own.** `127.0.0.1` is the VM, and QEMU's `10.0.2.2` gateway
points at the build sandbox's network namespace, so a VM cannot reach services on your
machine; `--option sandbox false` (with `--rebuild`) puts the host's loopback at `10.0.2.2`
(measured table in `docs/AUTONOMY.md`). The stub means no host service is needed at all.

**The agent is a stub.** What is under test is the harness, not the model: a real LLM would
be slow, non-deterministic and billable, and would test the provider rather than this
repository. The stub honours the same contract a real Hermes does —
`hermes -p <profile> chat --query-file <path>`, then write the file the prompt names —
which is what "Hermes is available" means at that boundary.

| Step | Assertion |
|---|---|
| launcher | `hermes --version` runs. `which` alone would pass on a file that cannot execute. |
| detection | with no profiles, `doctor` says **`no-profiles`** — the honest negative, and the bug this reporting exists to prevent |
| detection | after the profiles carry a provider, the verdict moves to **`ready`** |
| the review | `council review` produces all five dimension files and a numeric aggregate |
| coverage | probes **actually ran** in the VM (10 of 17 on the tiny fixture target) |
| the gate | a clean run is `satisfied`; a run with one open **high** finding is refused **with every score still 100** — so the block is the finding, not the aggregate |
| the deliverable | `next-steps.md` names the blocking finding |
| the guard | a bare `python3 …/probes.py` **fails** in the VM, and the same verb through `council` succeeds |

## Why the gate is hosted, not self-hosted

`nix flake check` already runs locally in seconds against the same store, so a self-hosted
runner would only **repeat an answer you already have** — and the one thing CI adds is a
machine sharing none of your state.

- **Availability.** A queued-forever gate is worse than no gate: it looks like verification
  is coming and never arrives. Hosted runners always run.
- **Security, later.** Low risk on a private repo today — but once the repo is public or has
  a collaborator, a self-hosted runner executes *their* PR code on *your* machine, by which
  time it is already installed.

## No custom cache is needed

A Cachix step was removed here after measuring what a cold runner actually has to do; the
assumption behind it was false.

| Measurement | Value |
|---|---|
| Toolchain closure | **919.8 MB**, 180 paths |
| Available from `cache.nixos.org` | **178 of 180** |
| Not available | our own `review-council-toolchain` and `python3-…-env` |

Both are `symlinkJoin`s — directories of symlinks, almost no bytes, seconds to build.
Everything else is a stock nixpkgs package Hydra already published, and `nix` uses
`cache.nixos.org` as its substituter **by default**. So a cold CI run downloads the tools
and builds two symlink directories: nothing for a private cache to save, at the price of an
account, a secret, a variable, a third-party dependency and a new failure mode. The claim
that CI would "build every package from scratch on every push" was wrong — the tools are
prebuilt and publicly served.

Both numbers move with the toolchain, so re-measure rather than trusting them: query each
closure path against the cache **one at a time**. Batched queries silently report misses,
and a batched run here once showed 30 absent paths where the true figure was 2.

### If you do want a cache

Two reasons you might: your closure stops being fully substitutable (a nixpkgs revision
Hydra did not finish, a package built from a flake input), or download volume matters more
than setup cost.

**More substituters** is the cheaper answer, and needs no account:

```nix
# flake.nix, or the runner's nix.conf
nixConfig.extra-substituters = [ "https://nix-community.cachix.org" ];
nixConfig.extra-trusted-public-keys = [
  "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
];
```

**A private cache** — Cachix, or any binary cache. Add the step back to the `gate` job and
set the two values:

```yaml
      - uses: cachix/cachix-action@v15
        with:
          name: <cache>
          authToken: ${{ secrets.CACHIX_AUTH_TOKEN }}
```

```bash
nix profile add nixpkgs#cachix
cachix authtoken <token>        # https://cachix.org -> Auth Tokens
cachix create <cache>
cachix push <cache> $(nix build .#toolchain --print-out-paths --no-link)
```

That last line warms it from a machine that already has the store, so even the first hosted
run is fast. The auth token is a push credential — Actions secrets only, never in the
workflow file.

## The self-hosted alternative

Not shipped as a script: this repository does not exercise that path, and an unexercised
install script is a liability. It is the answer for an adopter who **cannot** use hosted
runners — air-gapped, minute-limited, or wanting an already-warm store. Change the `gate`
job's `runs-on` to `[self-hosted, linux, nixos]` and drop the `install-nix-action` step (the
runner already has nix; a second install gives two stores and a mystery). Everything else
applies unchanged.

## Action versions

Pinned to a **full commit SHA**, with the release version in a trailing comment:
`actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`.

| | Major tag | Commit SHA |
|---|---|---|
| Gets upstream patches | automatically | never, until you bump it |
| Immune to a retagged or compromised release | no | yes |
| Maintenance | none | a bump every time upstream releases |

**This section used to argue the other way, and its own condition for revisiting has
fired.** The old text said a major tag wins "for a repo with one maintainer and no
third-party contributors", and ended "revisit the moment the repo gains a collaborator or
goes public". The repository is public, its releases are downloadable anonymously, and
anyone can fork it — so the premise is gone.

What settled it was measurement, not preference: `zizmor` (now a probe, see
`docs/TOOLCHAIN.md`) reported **5 high-severity `unpinned-uses` findings** against this
repository's own workflows — the same defect this framework raises when it reviews
someone else's. A tag is a moving reference: `@v7` runs whatever that tag points at when
the job starts, so an upstream force-push or account compromise executes inside this
repository's runner.

The maintenance cost is real and is the price: a bump when upstream releases. `zizmor`
reports a stale-but-pinned action as nothing, so the pin is a standing obligation rather
than a one-off edit. `persist-credentials: false` accompanies it — without it the
checkout token stays in `.git/config`, where a later step can read it (`artipacked`).

Measured after the change: `council probes zizmor --repo .` reports **0 findings over 2
files**.

### Node 20 → 24 (2026-10)

GitHub deprecated Node 20 for Actions and **removed it from the runners on 2026-09-23**.
After that date a Node-20 action is force-run on Node 24, warning on every job — what the
`tests` and `gate` jobs were showing. The fix is a major declaring `runs.using: node24`,
checkable rather than guessable:

```bash
curl -s https://raw.githubusercontent.com/actions/checkout/v7/action.yml \
  | grep -A1 '^runs:'
```

| Action | Node-20 majors | Node-24 majors |
|---|---|---|
| `actions/checkout` | v4 | **v5, v6, v7** |
| `actions/setup-python` | v5 | **v6, v7** |
| `cachix/install-nix-action` | — | composite action: **no node runtime**, unaffected |

- **A composite action has no node runtime at all**, so it never appears in this warning;
  `install-nix-action` is one, so do not "fix" it.
- **Skipping majors is not automatically safe.** The skipped breaking changes were
  `checkout`'s `allow-unsafe-pr-checkout` (only for `pull_request_target` / `workflow_run` —
  this workflow uses `push` and `pull_request`) and `setup-python`'s removal of the
  `pip-install` input. Both were checked against how this workflow uses the actions; a bare
  `uses:` with no inputs is a small surface.

## What the gate runs

```bash
nix flake check --keep-going     # builds, does not just evaluate
nix develop -c pytest tests/ -q
nix develop -c ruff check scripts tests
```

`--keep-going` matters: without it the first failing check hides the rest, so one red check
reads as one problem when there may be several.

Two of those checks are what the gate is *for*:

- **`checks.probes` — the analyzer matrix.** It runs `council probes --all` against a
  fixture and asserts every analyzer that needs no fixture content actually **ran**; a tool
  present but broken (wrong version, missing runtime dep, unparsable output) lowers beta
  silently and the score quietly becomes the LLM's judgement. `toolchain-built` asserts
  seven binaries exist; this asserts the analyzers execute.
- **`checks.container` — the image.** It builds `.#container`, so a broken image fails the
  gate rather than a separate workflow. Linux only, matching the output's own guard, because
  `dockerTools` cannot build a Linux userspace from darwin.

## Quota

Private repos on the Free plan get 2,000 Linux-equivalent minutes per month, multiplied
before deduction:

| Runner | Multiplier |
|---|---|
| Linux | 1× |
| Windows | 2× |
| macOS | 10× |

The `tests` matrix — three OSes — costs roughly 20 quota-minutes per push, about 15 of them
macOS. The `gate` job is **Linux-only** and adds the closure download plus a few minutes of
checks, including the darwin declaration's evaluation (seconds, no macOS minutes). The
`image` workflow runs only on a **tag**, so it adds nothing per push. Call it **~25–30 per
push** for `tests` + `gate`, or **~70 pushes a month** on the free tier; if the repo goes
public, hosted minutes become unlimited.

The macOS line in `tests` is the remaining 10× cost. It is kept because it is a different
claim from the gate's — the framework's stdlib portability (DECISIONS #2), not the flake's
darwin support — and it is cheap in wall-clock. Drop it the same way the gate's macOS leg
was dropped if quota bites: one line out of the `os:` list.

## Failure modes worth knowing

- **`gate` fails with `nix: command not found`.** The `install-nix-action` step is missing
  or was moved below the step that needs it.
- **`gate` is slow.** Check whether the closure is still substitutable: compare
  `nix-store -qR $(nix build .#toolchain --print-out-paths --no-link)` against
  `nix path-info --store https://cache.nixos.org`. If a nixpkgs bump moved the pin to a
  revision Hydra had not finished, the tools build locally — that is the cause.
- **`tests` fails on one OS only.** That is the job doing its work: the framework must pass
  on all three with nothing but pytest installed. Three traps have each cost a run, all
  about the *host*, not the code:
  - **A resolved path compared to an unresolved one.** `Path(td).resolve()` against a value
    returned verbatim passes on Linux and fails on macOS: `TMPDIR` there is under `/var`, a
    symlink to `/private/var`, so `resolve()` yields a different string for the same
    directory. Compare like for like. Reproduce it on Linux without a Mac by pointing the
    fixture at a path reached through a symlink.
  - **A fixture that must execute.** A `#!/bin/sh` file with no extension cannot run on
    Windows — CreateProcess refuses it — so anything asserting it *works* fails. Skip it
    with a reason rather than weakening the assertion.
  - **A capability the platform lacks.** `ensure_passwd_entry` needs `pwd`; Windows has no
    passwd database, so it correctly reports "nothing added" there, and a test asserting it
    *added* an entry is asserting a container-only capability. Guard the test and pin the
    other platform's behaviour separately by hiding the module (`sys.modules["pwd"] = None`)
    so the fallback is exercised everywhere.
- **Reading a failing job without a token.** Job logs need admin rights
  (`/actions/jobs/<id>/logs` answers `403`), so a Windows-only failure can be invisible to
  anyone without repository admin. Annotations do not: the checks API serves them
  unauthenticated for a public repository. The `tests` job writes `--junitxml`, and a
  following step emits one `::error` annotation per failing test, readable with
  `curl -s https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs` to find the
  check-run id, then `.../check-runs/<id>/annotations`. Allow a minute or two after the run.
- **A step that reports success while its command failed.** `set -e` is **ignored inside a
  subshell that is part of a condition** — `if ! ( ... )` — so a failing command is not fatal
  there and the subshell's status becomes whatever the *last* command returned. A step that
  ran `cmd`, then `rm -f …`, therefore passed with `cmd` failed: that is how a publish step
  goes green while uploading nothing. Chain with `&&` instead, which is immune to the
  suppression, or keep `set -e` out of the subshell and check `$?` explicitly. Verify with a
  stub: `bash -c 'if ! ( set -e; false; echo reached ); then echo fail; else echo pass; fi'`
  prints `reached` and `pass`.
- **`gate` queued forever.** Only possible if you switched it back to self-hosted; check
  `systemctl --user status gha-runner.service` on that machine.
