# syntax=docker/dockerfile:1

# A nix-centric Dockerfile. Nix provisions the image, from the same `flake.lock`
# as every other path, so the analyzers inside are the pinned store paths and not
# whatever the base image happened to ship.
#
# It exists for a host that can run docker but not nix: nix is installed only
# inside the build, never on your machine. `nix build .#container` is the primary
# path and produces a LAYERED image; this produces the same tree as a single
# layer, because the layering is dockerTools' and `docker build` cannot reproduce
# it. Use the flake when you have nix, this when you have only docker.
#
# Nothing about the image is defined here. `.#image-root` in flake.nix is the one
# definition, shared with `.#container`, so the two cannot drift apart.

FROM nixos/nix:2.35.3 AS builder

WORKDIR /src
# Only the sources the flake evaluates. An edit to a doc must not invalidate the
# expensive build below.
COPY flake.nix flake.lock ./
COPY scripts/ scripts/
COPY skills/ skills/
COPY bots/ bots/
COPY pyproject.toml ./

# `--extra-experimental-features`: do not rely on the base image's nix.conf.
RUN nix --extra-experimental-features 'nix-command flakes' \
      build --out-link /image-root .#image-root

# Materialise the closure into a rootfs. `nix-store -qR` yields exactly the store
# paths the image runs, so the runtime layer carries no build-time dependencies and
# no builder — the pinned `nix` CLI is in there because the nix probes run it, but
# the nix that built the image is not.
#
# tar, not `cp -a`: a store path is mode 0555, and GNU cp propagates the source
# directory's mode onto the destination, so `cp -a` here leaves /rootfs read-only
# and the prep below cannot run. tar records modes without altering the extraction
# root, and one archive beats 260 `cp` invocations.
#
# `.nix/prep.sh` is the writable dirs, the passwd/group entries and the mode
# fixes, shipped by the flake so there is one definition of them. It has to be
# re-run here because nix makes a store path read-only: the modes the flake set do
# not survive the copy, and a container whose /tmp is 0555 fails every probe that
# needs scratch.
# The tools this step needs, from nixpkgs. `nixos/nix` has no `sed` (and no
# `awk`), so piping through `sed` here failed with `/bin/sh: line 1: sed: command
# not found` at the last instruction of the build. Declaring them keeps the step
# off the base image's incidental toolset, and they land in the BUILDER only.
RUN nix --extra-experimental-features 'nix-command flakes' \
      build --out-link /prep .#image-prep-tools

RUN export PATH="/prep/bin:$PATH" \
 && ROOT=$(readlink -f /image-root) \
 && nix-store --query --requisites "$ROOT" \
      | grep -v "^$ROOT$" \
      | sed 's|^/||' > /paths.txt \
 && tar -cf /closure.tar -C / -T /paths.txt \
 && mkdir -p /rootfs \
 && tar -xf /closure.tar -C /rootfs --no-overwrite-dir \
 && tar -cf /root.tar -C "$ROOT" . \
 && tar -xf /root.tar -C /rootfs --no-overwrite-dir \
 && chmod u+w /rootfs \
 && cd /rootfs \
 && sh .nix/prep.sh \
 && chmod -R u+w /rootfs/.nix \
 && rm -rf /rootfs/.nix /paths.txt /closure.tar /root.tar

FROM scratch

COPY --from=builder /rootfs/ /

ENV HOME=/home/council \
    HERMES_HOME=/home/council/.hermes \
    REVIEW_COUNCIL_TOOLCHAIN=/opt/toolchain \
    NIX_CONF_DIR=/opt/nix \
    PYTHONUNBUFFERED=1

# The same contract as `nix build .#container`: uid 1000, /repo as the working
# directory, `--help` as the default so a bare `docker run` lists the verbs
# instead of starting a review.
WORKDIR /repo
USER 1000:1000
ENTRYPOINT ["/bin/council-entrypoint"]
CMD ["--help"]
