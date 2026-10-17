# The container image

`nix build .#container` produces a layered OCI image. On a **tag**, CI attaches the
built tarball to that GitHub Release, so obtaining it needs **docker and nothing else
from this repository** — no nix, no clone, and no registry account:

```bash
curl -L -O https://github.com/washedupdeveloper/agentic-council/releases/latest/download/review-council.tar.gz
docker load -i review-council.tar.gz          # -> review-council:latest
```

The asset name is fixed, so `releases/latest/download/…` is a URL that keeps working
across versions. A nix host needs no download at all
(`nix build github:washedupdeveloper/agentic-council#container`), and a host with
docker but no nix can build it from the `Dockerfile` — see
[Building it yourself](#building-it-yourself).

## Run it

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo" \
  -v "$HOME/.hermes:/home/council/.hermes" \
  -v "$(dirname "$(command -v hermes)")/..:/opt/hermes:ro" \
  review-council /repo
```

Pass the repository as the argument — there is no implicit `/repo` default, so
`docker run <image>` prints the verbs instead of starting a review.

**`--user "$(id -u):$(id -g)"` matters.** The image runs as uid 1000, so a
repository mounted from an account with any other uid is read-only to it and the
run cannot create its output directory. Running it as yourself also means the run
directory and the reports in it belong to you rather than to a stray uid. The
entrypoint adds a passwd entry for that uid on startup, because `nix` resolves
`$HOME` through `getpwuid` and the image's passwd only knows uid 1000 — without one
every nix probe fails with `cannot determine user's home directory`, even with
`HOME` set, and beta silently drops. If you forget `--user`, the harness says so
and prints the flag rather than a traceback.

## What is in it

| | |
|---|---|
| the 13 pinned analyzers | the same store paths the native toolchain pins, from the same `flake.lock` |
| the framework | `scripts/`, `bots/`, `skills/`, under `/opt/review-council` — the runtime modules only; the dev verbs are not in the image |
| the `council` CLI | the same verb table as the flake app, so `doctor`, `gate`, `probes` and the rest work without Hermes |
| `git` | `--baseline` shells out to it to find what changed |
| the nix CLI | for the `nix eval` probe, with `/opt/nix/nix.conf` at `NIX_CONF_DIR` |
| `/repo` | the working directory — mount the project here |

It runs as **uid 1000** with `HOME=/home/council`. Hermes is **not** in it, on
purpose — see below.

### What needs Hermes, and what does not

The entrypoint resolves Hermes **only for a review**. Everything else is handed
straight to the `council` CLI, so the image is useful before you mount anything:

```bash
docker run --rm <image>                    # the verbs (Cmd is --help)
docker run --rm <image> doctor --repo /repo
docker run --rm <image> --verbs-json
```

This is also why there is no implicit `/repo`: `docker run <image>` used to try to
review `/repo` with no argument, which meant it resolved Hermes first and printed a
credential error where the help should have been.

## Why it is layered

`buildLayeredImage`, no nix database: **99 layers**. Measured on the current build, the
tarball is **313 MiB** (328,344,703 bytes) and its layers hold **1.06 GB**
(1,064,611,840) uncompressed. The layers are gzipped, so the download is not the image.
A store path's layer is content-addressed, so an unchanged toolchain produces
byte-identical layer digests — a push uploads only what changed and a pull fetches only
what the local copy lacks. That is the whole caching story; there is no build cache to
configure.

The earlier build used `buildImageWithNixDb` and one layer (**365 MiB** as a
tarball) to register the copied store paths in a nix database. Measured, the
database bought nothing: `nix --version`, `nix-instantiate --parse` (what the nix-eval
probe actually runs), all 14 analyzers that then shipped, and `doctor` reporting beta
1.00 all work without it. It was also the **only** thing forcing a single layer, because its
gcroots point into a layer that is not there while it is being generated:

```
ln: failed to create symbolic link 'nix/var/nix/gcroots/docker/...': Permission denied
```

## What is verified, and how to verify it yourself

Verified by loading the image into a **real docker daemon** in a disposable VM — so the
check needs no particular host and no container runtime on the build machine, and the
namespaces, mounts and cgroups are real rather than extracted layers under a chroot.

Verified: it loads; it runs as uid 1000 in `/repo`; all 13 analyzers resolve on PATH;
`git`, `nixfmt`, `ruff` and `deadnix` work; `nix --version`, `nix eval` and
`nix-instantiate` work with `NIX_CONF_DIR=/opt/nix`; the harness `--help` prints; a
file is written. And a **complete scored review runs inside it** — fan-out, bucketing,
beta measurement and the gate — with Hermes mounted, producing a verdict rather than
an environment check.

On your own host, the same assertions are one command:

```bash
docker run --rm -v "$PWD:/repo" review-council doctor --repo /repo
```

`doctor` reports the toolchain, the detected stacks and **beta now vs reachable**, so a
green line means the pinned analyzers are present and running in the image on *your*
machine.

**Not covered by the VM check:** the provenance of the artifact you download. CI builds
it and attaches it to the release, so the tarball is the one CI produced — not one built
here. There is no registry digest to compare against, which is the one thing a registry
gave that a release asset does not: check the size against the release's asset list, or
rebuild from the same `flake.lock` (deterministic, so the content matches) and compare.

### The Dockerfile's own verification

The Dockerfile is checked the same way.

Verified: the rootfs step is run **verbatim** (the same commands, extracted from the
file) and produces the right modes — `tmp` `1777`, `repo` and the profile home `0777`,
`etc/passwd` `0666` — with an `/etc/passwd` a non-root uid can append to, which is what
`--user "$(id -u):$(id -g)"` needs. The assembled rootfs is then imported into a **real
docker daemon** with the Dockerfile's `ENV`/`WORKDIR`/`USER`/`ENTRYPOINT`/`CMD`, and it
runs: a bare `docker run` prints the verbs, `REVIEW_COUNCIL_TOOLCHAIN` and `NIX_CONF_DIR`
are set, every pinned tool resolves **and executes**, and `probes --all` runs **16** of
them against a fixture.

And **`docker build` runs to completion**, in a NixOS VM with network
(`--option sandbox false`; the build sandbox has none by default, which is what made
this look untestable). The build pulls `nixos/nix:2.35.3`, resolves nixpkgs, builds the
tool closure and finishes: exit code 0, image tagged, verbs printed, every pinned tool
resolving inside the result.

That test found a real defect. The materialisation step piped through `sed`, and `nixos/nix` ships **no `sed` and no
`awk`** — its `/bin` holds only `sh` — so the build died at `[builder 9/9]` with
`/bin/sh: line 1: sed: command not found`. Every earlier check had stopped at "the
Dockerfile parses", which is a different claim from "the image builds". The step now
takes `coreutils`, `gnused`, `gnugrep`, `gnutar` and `findutils` from nixpkgs via
`.#image-prep-tools`, so it depends on the pin rather than on what a base image
happens to carry.

**The two paths carry the same content**, measured rather than assumed. On the build
this was taken from, the layered image held **261** store paths and **1,060,252,742**
bytes under `/nix/store`; the Dockerfile image held **260** and **1,060,259,347** —
0.04% apart. Their reported *image sizes* differ far more, and that is docker's layer
accounting, not missing content.

Both halves are a measurement of one earlier build, and the Dockerfile half cannot be
re-checked without a docker daemon. The store-path counts move with the toolchain, so
re-measure rather than trusting them; the *conclusion* does not depend on the numbers —
it follows from the two images being built from the same attrs.

The counts are not identical because the same three artifacts are built from
different inputs — the flake from the git tree, the Dockerfile from the staged build
context — so `review-council-framework`, `council-entrypoint` and
`review-council-nix-conf-at-opt` carry different store hashes on each side. Three
unique paths against two. Compare store paths, not the size column, before
concluding one image is short of something.

Run it yourself:

```bash
docker build -t review-council .
docker run --rm review-council            # the verbs
docker run --rm -v "$PWD:/repo" review-council doctor --repo /repo
```

## Known limitations

- **Hermes is not bundled.** The published wheel (0.19.0) and the nix build are
  different versions of Hermes, and pinning one in would silently differ from the
  one the user already has. The entrypoint resolves `HERMES_BIN`, then
  `/opt/hermes/bin/hermes`, then PATH, and prints what to do when it finds none.
- **A container score is not a nix score.** The analyzers are identical, so the
  deterministic half is. The agent's behaviour depends on the Hermes you mount.
- **The threshold is calibrated to this repository, from one sample.**
  `scripts/calibration.json` calls it `PROVISIONAL`. Read it as relative.

## Building it yourself

Three paths, the same content. Pick by what your machine has.

**Download the release asset** — the path that needs least:

```bash
curl -L -O https://github.com/washedupdeveloper/agentic-council/releases/latest/download/review-council.tar.gz
docker load -i review-council.tar.gz
```

**With nix** — the verified path, and a layered image:

```bash
nix build .#container
docker load < result
```

This one is **checked on every push**: `checks.container` builds `.#container` as part
of `nix flake check`, so a broken image fails the gate rather than a workflow of its own.

**With docker only, building from source** — nix runs inside the build, never on your
machine:

```bash
docker build -t review-council .
```

The Dockerfile is the fallback for a host that can run docker but not nix. It
produces a **single layer**: the layering is `dockerTools`' and
`docker build` cannot reproduce it, so prefer the flake when you have nix.

⚠️ **This path is instructions, not a verified one.** CI does not run `docker build`, so
nothing catches the Dockerfile drifting from the tree it copies. That is a deliberate
trade and it has already cost something once: the materialisation step used to pipe
through `sed`, and `nixos/nix` ships neither `sed` nor `awk`, so the build died at
`[builder 9/9]` while every cheaper check had passed — because "the Dockerfile parses" is
a different claim from "the image builds". Two consequences worth knowing:

- **Prefer the release asset or the flake.** Both are verified; the Dockerfile is not.
- **If you change anything the Dockerfile copies, run it once by hand.** The failure it
  produces is not subtle, but nothing will produce it for you.

The full `docker build` verification — in a NixOS VM, with network, asserting the built
image runs and every pinned tool executes — is described above and was run when it was
written. It is not part of CI.

**Neither path is defined twice.** `nix/builders.nix` owns what goes in the image —
`mkContainer` for the layered one, `mkImageRoot` for the tree the Dockerfile
copies, and both share `imagePrep`, the entrypoint and the nix config. The
Dockerfile adds only the container plumbing. A second copy of any of that is how
"the image works and the Dockerfile does not" happens, which is the one failure a
reader cannot debug.

One subtlety if you edit either path: **nix makes everything under a store path
read-only**, so the modes the flake sets do not survive into the Dockerfile's copy —
`tmp` arrives `0555`, not `1777`. That is why the prep ships as `.nix/prep.sh` and the
Dockerfile re-runs it. `mkContainer` needs no such step, because `dockerTools` runs
`extraCommands` on the image root, where modes are preserved. One definition of the
prep, two ways of applying it.
