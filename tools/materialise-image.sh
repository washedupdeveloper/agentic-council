#!/usr/bin/env bash
# Extract an OCI or Docker image tarball into a rootfs.
# Usage: materialise-image.sh IMAGE ROOT
set -euo pipefail
image=$1
root=$2
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

tar -xf "$image" -C "$work"
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
"${PYTHON:-python3}" "$here/materialise_image.py" "$work" "$root"
