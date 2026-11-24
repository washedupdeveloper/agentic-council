#!/usr/bin/env bash
# Materialise the image and run its entrypoint in a user namespace.
# Usage: image-run.sh IMAGE [COMMAND...]
set -euo pipefail
image=$1
shift || true
root=$(mktemp -d "${TMPDIR:-/tmp}/council-image-root.XXXXXX")
cleanup() {
  chmod -R u+w "$root" 2>/dev/null || true
  rm -rf "$root" 2>/dev/null || true
}
trap cleanup EXIT
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
"$here/materialise-image.sh" "$image" "$root"
if [ "$#" -eq 0 ]; then set -- /bin/council --help; fi
unshare --user --map-root-user chroot "$root" "$@"
