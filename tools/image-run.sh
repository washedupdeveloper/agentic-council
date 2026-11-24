#!/usr/bin/env bash
# Materialise the image and run its entrypoint in a user namespace.
# Usage: image-run.sh IMAGE [COMMAND...]
set -euo pipefail
image=$1
shift || true
# The rootfs lives inside a private parent: an image root header can change the
# rootfs's own mode, which must not be able to open the directory to others.
root=$(mktemp -d "${TMPDIR:-/tmp}/council-image-root.XXXXXX")/root
mkdir -- "$root"
cleanup() {
  chmod -R u+w "$root" 2>/dev/null || true
  rm -rf "$root" 2>/dev/null || true
}
trap cleanup EXIT
# Follow the script's own symlink: a launcher may be linked into PATH, and the
# helper it calls sits beside the real file, not beside the link.
self=${BASH_SOURCE[0]}
while [[ -L $self ]]; do
  target=$(readlink -- "$self")
  [[ $target == /* ]] || target=$(dirname -- "$self")/$target
  self=$target
done
here=$(cd -- "$(dirname -- "$self")" && pwd)
"$here/materialise-image.sh" "$image" "$root"
if [ "$#" -eq 0 ]; then set -- /bin/council --help; fi
unshare --user --map-root-user chroot "$root" "$@"
