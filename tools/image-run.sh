#!/usr/bin/env bash
# Materialise the image and run its entrypoint in a user namespace.
# Usage: image-run.sh IMAGE [COMMAND...]
set -euo pipefail
image=$1
shift || true
root=${TMPDIR:-/tmp}/council-image-root
if [ -d "$root" ]; then
  chmod -R u+w "$root" 2>/dev/null || true
  rm -rf "$root" 2>/dev/null || true
fi
here=$(dirname "$(readlink -f "$0")")
"$here/materialise-image.sh" "$image" "$root"
if [ "$#" -eq 0 ]; then set -- /bin/council --help; fi
exec unshare --user --map-root-user chroot "$root" "$@"