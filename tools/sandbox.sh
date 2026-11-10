#!/usr/bin/env bash
# Run a command with a read-only root, a private /tmp and an overlay home.
# Every write to $HOME or /tmp disappears with the process. Linux/bwrap only;
# on macOS or Windows use the OCI image (docs/PORTABILITY.md).
set -euo pipefail

if [[ "${1:-}" == "--" ]]; then
  shift
fi
if [[ $# -eq 0 ]]; then
  echo "usage: tools/sandbox.sh -- <command> [args...]" >&2
  exit 2
fi
if ! command -v bwrap >/dev/null 2>&1; then
  echo "sandbox: bwrap is not installed" >&2
  echo "  NixOS: nix shell nixpkgs#bubblewrap" >&2
  echo "  macOS/Windows: use the OCI image (docs/PORTABILITY.md)" >&2
  exit 3
fi

cwd=$PWD
home=${HOME:-/root}
bind=()
case "$cwd" in
  "$home"|"$home"/*) ;;
  *) bind=(--ro-bind "$cwd" "$cwd") ;;
esac

exec bwrap --die-with-parent --unshare-pid \
  --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp \
  "${bind[@]}" \
  --overlay-src "$home" --tmp-overlay "$home" \
  --chdir "$cwd" -- "$@"
