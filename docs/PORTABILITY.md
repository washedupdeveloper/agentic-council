# Portability — ephemeral execution beyond NixOS

The product assumes one thing: **a run must not leave state the caller did not
ask for.** NixOS makes that easy; other systems need a boundary chosen for them.

## Matrix

| host | builds | reviewer | whole run | notes |
|---|---|---|---|---|
| NixOS | `nix build`, sandboxed | `bwrap` (in the package PATH) | `--ephemeral` default | the native path; `nix flake check` runs every check in a Nix sandbox |
| Linux + bwrap | your compiler | `bwrap` | `--ephemeral` default | same code path; `tools/sandbox.sh` wraps arbitrary commands |
| macOS | your compiler | none | `--ephemeral` default | use an OCI container as the boundary; `sandbox-exec` is deprecated and per-profile |
| Windows | WSL2 or container | none natively | `--ephemeral` default | WSL2 gets the Linux path; native Windows has no bwrap |
| any OCI host | image | container boundary | `--ephemeral` default | `--rm --read-only --tmpfs /tmp`; the container is the sandbox |

"none" for the reviewer means `reviewer_sandbox: false` is recorded; the tool
does not pretend a wheel without bubblewrap is sandboxed.

## OCI: the portable boundary

Use the image built by `nix build .#image` (and published by the release owner),
or build the plain `Dockerfile` on a host with Docker/Podman.

```sh
docker build -t council .
docker run --rm --read-only --tmpfs /tmp \
  -v "$PWD:/repo:ro" \
  -v "$HOME/.config/hermes:/root/.config/hermes:ro" \
  council review -C /repo --base HEAD --json
```

- `--rm` removes the container filesystem; `--read-only` makes the image
  immutable; `--tmpfs /tmp` gives the run somewhere to write that also vanishes.
- The repository is mounted read-only: the reviewer reads it, proofs overlay it,
  and nothing is written back.
- The Hermes configuration is mounted read-only; the model connection still
  needs the network, which the container has by default.
- The run state is ephemeral by default; use `--keep /out` with a writable
  mount only when you want the evidence.

The container boundary is coarser than bwrap: it shares the host kernel and
needs a container runtime. It is the answer on macOS and Windows where bwrap
does not exist.

## NixOS: what is actually sandboxed

- `nix build` / `nix flake check` run in the Nix sandbox (no network unless the
  derivation asks for it, no writes outside the store).
- `nix develop` is a shell, not a sandbox for the commands you type in it. Use
  `tools/sandbox.sh -- <command>` for an ephemeral command, or put the command
  in a derivation.
- The reviewer uses bwrap: read-only root, private `/tmp`, overlay `$HOME`.
- The run directory is ephemeral by default; `--no-ephemeral` is the explicit
  opt-in to `.council/runs`.

## What "ephemeral" does not mean

- **No network isolation.** The reviewer must reach the model; `bwrap` keeps the
  filesystem boundary, not the network one.
- **No secrecy from the host.** The reviewer can read what the host exposes; the
  sandbox prevents writes, not reads.
- **No image garbage collection.** `--rm` removes the container, not the image
  or the build cache; those are the runtime's to manage.
- **No promise on a platform without a boundary.** Without bwrap or a container,
  `--ephemeral` still removes the run tree, but a process can write elsewhere.
  The evidence records `reviewer_sandbox: false`; that is the honest signal.
