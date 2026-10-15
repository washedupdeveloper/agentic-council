# CI

Two workflows, both on **GitHub-hosted** runners: `.github/workflows/ci.yml` (the tests
and the gate) and `.github/workflows/image.yml` (the container image).

| Job | Runner | What it proves |
|---|---|---|
| `tests` (ci.yml) | `ubuntu` + `macos` + `windows` | The framework is stdlib-only and runs on all three. This job **is** the portability guarantee (DECISIONS #2). |
| `gate` (ci.yml) | `ubuntu-latest` | `nix flake check` under the pinned toolchain, on a machine that shares nothing with yours — **including the darwin declaration**, evaluated by `--all-systems --no-build` at no macOS cost. |
| `release` (image.yml) | `ubuntu-latest` | On a `v*` tag: builds the image and attaches it to that release as `review-council.tar.gz`. Tags only — the gate already builds the image on every push and pull request. |

## The darwin declaration, without a macOS runner

`systems` declares `aarch64-darwin`, so something has to check it or it is an assertion
nobody verifies. The gate does, by evaluating every declared system and building none:

```bash
nix flake check --all-systems --no-build
```

**That command has teeth, measured rather than assumed.** A canary check referencing
`pkgs.systemd` — which exists on Linux and not on darwin — made it exit **1**, while a
plain `nix flake check` exited **0**. So it catches a darwin-only evaluation error: a tool
that does not exist for the platform, a platform-conditional mistake. It costs seconds and
no macOS minutes.

**What is not paid for is building on darwin.** macOS minutes count tenfold, the darwin
closure is 239 fetched paths and 5 built ones, and the author uses no Mac. Execution on
darwin is therefore left to whoever runs the flake there — one command,
`nix flake check`, which is exactly what this gate runs on Linux. `docs/NIX.md` states
this from the user's side. To add the runner back, restore the matrix:

```yaml
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
```

## The container image job

`nix build .#container` needs nix, but only on a runner: the person who runs
the council installs nothing but docker. `.#container` is a `dockerTools` layered image,
so the output is already one file — a gzipped `docker load` tarball, measured at 333 MB
with a single-path closure.

**It is verified by the gate, not by this workflow.** `checks.container` builds the image
on every push and pull request, on the clean runner, beside the tests. That is possible
because the output is a **tarball**: building it needs no docker daemon, so unlike the VM
test it can be an ordinary check. What remains in `image.yml` is publishing, which a check
cannot do.

**A release asset, not a registry.** The tarball is attached to the tag's GitHub Release
under a **fixed** name, so `releases/latest/download/review-council.tar.gz` is a URL that
survives every version. What that buys, measured:

| how it is published | downloadable without a GitHub account | how long it lasts |
|---|---|---|
| **release asset** | **yes** — 200 with no token | as long as the release |
| Actions artifact | **no** — 401 from the API, 404 from the web path; needs a signed-in user | 90 days by default |
| a registry (GHCR) | yes | as long as the registry entry |

So a release asset is the one option that needs no account, no expiry and no service to
run — and it drops `packages: write` from the workflow. The image is built **layered**
regardless, but that is now a build-cache property (`nix build` is a hit when the
toolchain is unchanged) rather than a registry-dedup one. `docs/CONTAINER.md` has the
user-facing side.

## The VM test

`nix build .#vm-test` runs the council end-to-end inside a real NixOS VM: boot, a target
repository, the pinned probes, the fan-out, the bucketing, the gate, and a verdict.

It is **not** in `nix flake check`, deliberately — a VM test needs KVM, and putting it in
the gate would require every contributor's machine to have it. It is a `packages` output
rather than a `checks` one for that reason, and the fast gate stays fast.

**The test's network is the test's own.** A VM here cannot reach services on your
machine: `127.0.0.1` is the VM, and the build sandbox's network namespace is what
QEMU's `10.0.2.2` gateway points at. `--option sandbox false` (with `--rebuild`) puts
the host's loopback at `10.0.2.2` — see `docs/AUTONOMY.md` for the measured table. The
stub is there precisely so the test needs no host service at all.

**The agent is a stub.** What is under test is the harness, not the model: a real LLM
would make the test slow, non-deterministic and billable, and would test the provider
rather than this repository. The stub honours the same contract a real Hermes does —
`hermes -p <profile> chat -q <prompt>`, then write the file the prompt names — which is
exactly what "Hermes is available" means at that boundary.

What it asserts:

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

The blocking case is the one that matters most: a test that only ever passes proves
nothing about a gate.

## Why the gate is hosted, not self-hosted

This was self-hosted first, and that was a mistake worth recording. `nix flake check`
already runs locally in seconds against the same store, so a self-hosted runner on your
own machine would only ever **repeat an answer you already have** — and the one thing CI
can give that local cannot is a machine that shares none of your state. Two things follow:

- **Availability.** A queued-forever gate is worse than no gate, because it looks like
  verification is coming and never arrives. Hosted runners always run.
- **Security, later.** Low risk on a private repo today — but the moment the repo is public
  or has a collaborator, a self-hosted runner executes *their* PR code on *your* machine,
  and by then the runner is already installed.

## No custom cache is needed

There was a Cachix step here, removed after measuring what a cold runner actually has to
do: the assumption behind it was false.

| Measurement | Value |
|---|---|
| Toolchain closure | **925.8 MiB**, 238 paths |
| Available from `cache.nixos.org` | **236 of 238** |
| Not available | our own `review-council-toolchain` and `python3-…-env` |

Those two are `symlinkJoin`s — directories of symlinks, holding almost no bytes, built in
seconds. Everything else is a stock nixpkgs package that Hydra already built and
published, and `nix` uses `cache.nixos.org` as its substituter **by default**. So a cold
CI run downloads the tools and builds two symlink directories: nothing for a private cache
to save, and one would add an account, a secret, a variable, a third-party dependency and
a new failure mode — for no gain. The claim that CI would "build 24 packages from scratch
on every push" was wrong: the tools are prebuilt and publicly served.

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

**A private cache** is the other option — Cachix, or any binary cache. Add the step
back to the `gate` job and set the two values:

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

That last line warms it from a machine that already has the store, so even the first
hosted run is fast. The auth token is a push credential — Actions secrets only, never
in the workflow file.

## The self-hosted alternative

Not shipped as a script. A self-hosted runner is the answer for an adopter who **cannot**
use hosted runners — air-gapped, minute-limited, or wanting the gate to run against a
store that is already warm — but it is the path this repository does not exercise, and an
unexercised install script is a liability rather than a feature. To use it, change the
`gate` job's `runs-on` to `[self-hosted, linux, nixos]` and drop the `install-nix-action`
step (the runner is the machine that already has nix; a second install over the top gives
two stores and a mystery). Everything else here applies unchanged.

## Action versions

The actions are pinned to a **major tag** (`actions/checkout@v7`), not a commit SHA.

| | Major tag | Commit SHA |
|---|---|---|
| Gets upstream patches | automatically | never, until you bump it |
| Immune to a retagged or compromised release | no | yes |
| Maintenance | none | a bump every time upstream releases |

For a repo with one maintainer and no third-party contributors the major tag wins: the
failure mode it does not protect against — a compromised action release — is rare, and the
one it does — an unpatched action — is constant. **Revisit this the moment the repo gains
a collaborator or goes public.**

### Node 20 → 24 (2026-10)

GitHub deprecated Node 20 for Actions and **removed it from the runners on 2026-09-23**.
After that date a Node-20 action is force-run on Node 24, with a warning on every job —
which is what the `tests` and `gate` jobs were showing. The fix is a major that declares
`runs.using: node24`, which is checkable rather than guessable:

```bash
curl -s https://raw.githubusercontent.com/actions/checkout/v7/action.yml \
  | grep -A1 '^runs:'
```

| Action | Node-20 majors | Node-24 majors |
|---|---|---|
| `actions/checkout` | v4 | **v5, v6, v7** |
| `actions/setup-python` | v5 | **v6, v7** |
| `cachix/install-nix-action` | — | composite action: **no node runtime**, unaffected |

Two notes:

- **A composite action has no node runtime at all**, so it never appears in this warning.
  `install-nix-action` is one; do not "fix" it.
- **Skipping majors is not automatically safe.** The skipped breaking changes were
  `checkout`'s `allow-unsafe-pr-checkout` (only for `pull_request_target` /
  `workflow_run` — this workflow uses `push` and `pull_request`) and `setup-python`'s
  removal of the `pip-install` input. Both were checked against how this workflow uses the
  actions; a bare `uses:` with no inputs is a small surface.

## What the gate runs

```bash
nix flake check --keep-going     # builds, does not just evaluate
nix develop -c pytest tests/ -q
nix develop -c ruff check scripts tests
```

`--keep-going` matters: without it the first failing check hides the rest, so one red
check reads as one problem when there may be several.

Two of those checks are worth naming, because they are what the gate is *for*:

- **`checks.probes` — the analyzer matrix.** It runs `council probes --all` against a
  fixture and asserts every analyzer that needs no fixture content actually **ran**. A
  tool that is present but broken (wrong version, missing runtime dep, unparsable output)
  lowers beta silently, and the score quietly becomes the LLM's judgement. `toolchain-built`
  asserts five binaries exist; this asserts the analyzers execute.
- **`checks.container` — the image.** It builds `.#container`, so a broken image fails the
  gate rather than a separate workflow. Linux only, matching the output's own guard, because
  `dockerTools` cannot build a Linux userspace from darwin.

## Quota

Private repos on the Free plan get 2,000 Linux-equivalent minutes per month. Minutes are
multiplied before they are deducted:

| Runner | Multiplier |
|---|---|
| Linux | 1× |
| Windows | 2× |
| macOS | 10× |

So the `tests` matrix — three OSes — costs roughly 20 quota-minutes per push, of which
the macOS job is about 15. The `gate` job is **Linux-only** and adds the closure download
plus a few minutes of checks — including the darwin declaration's evaluation, which is
seconds and costs no macOS minutes. The `image` workflow runs only on a **tag**, so it adds
nothing per push. Call it **~25–30 per push** for `tests` + `gate`, or **~70 pushes a
month** on the free tier. If the repo ever goes public, hosted minutes become unlimited and
this stops mattering.

The macOS line in `tests` is the remaining 10× cost. It is kept because it is a different
claim from the gate's — the framework's stdlib portability (DECISIONS #2), not the flake's
darwin support — and it is cheap in wall-clock. Drop it the same way the gate's macOS leg
was dropped if quota starts to bite: one line out of the `os:` list.

## Failure modes worth knowing

- **`gate` fails with `nix: command not found`.** The `install-nix-action` step is
  missing or was moved below the step that needs it.
- **`gate` is slow.** Check whether the closure is still substitutable: compare
  `nix-store -qR $(nix build .#toolchain --print-out-paths --no-link)` against
  `nix path-info --store https://cache.nixos.org`. If a nixpkgs bump moved the pin to a
  revision Hydra had not finished, the tools build locally and that is the cause.
- **`tests` fails on one OS only.** That is the job doing its work — the framework must
  pass on all three with nothing but pytest installed. Two traps have already cost a
  run each, and both are about the *host*, not the code:
  - **Comparing a resolved path to an unresolved one.** `Path(td).resolve()` against a
    value returned verbatim passes on Linux and fails on macOS, because `TMPDIR` there
    is under `/var`, which is a symlink to `/private/var` — so `resolve()` yields a
    different string for the same directory. Compare like for like. Reproduce it on
    Linux without a Mac by pointing the fixture at a path reached through a symlink.
  - **A fixture that must execute.** A `#!/bin/sh` file with no extension cannot run on
    Windows: CreateProcess refuses it, so anything asserting it *works* fails. Skip it
    with a reason rather than weakening the assertion.
  - **A capability the platform does not have.** `ensure_passwd_entry` needs `pwd`, and
    Windows has no passwd database, so it reports "nothing added" there — correctly.
    A test asserting it *added* an entry is asserting a container-only capability, and
    fails on Windows. Guard the test and pin the other platform's behaviour separately,
    by hiding the module (`sys.modules["pwd"] = None`) so the fallback is exercised
    everywhere.
- **Reading a failing job when you have no token.** Job logs need admin rights
  (`/actions/jobs/<id>/logs` answers `403`), so a Windows-only failure can be invisible
  to anyone without repository admin. Annotations do not: the checks API serves them
  unauthenticated for a public repository. The `tests` job therefore writes
  `--junitxml` and a following step emits one `::error` annotation per failing test,
  which is then readable with:
  `curl -s https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs`
  to find the check-run id, then `.../check-runs/<id>/annotations`. Allow a minute or
  two after the run for the annotations to appear.
- **A step that reports success while its command failed.** `set -e` is **ignored inside a
  subshell that is part of a condition** — `if ! ( ... )` — so a failing command is not
  fatal there and the subshell's status becomes whatever the *last* command returned. A
  step that ran `cmd`, then `rm -f …`, therefore passed with `cmd` failed. This is how a
  publish step can go green while uploading nothing. Chain with `&&` instead, which is
  immune to the suppression, or keep `set -e` out of the subshell and check `$?`
  explicitly. Verify with a stub: `bash -c 'if ! ( set -e; false; echo reached ); then
  echo fail; else echo pass; fi'` prints `reached` and `pass`.
- **`gate` queued forever.** Only possible if you switched it back to self-hosted;
  check `systemctl --user status gha-runner.service` on that machine.
