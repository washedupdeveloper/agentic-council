#!/usr/bin/env bash
# Extract an OCI image tarball into a rootfs. Usage: materialise-image.sh IMAGE ROOT
set -euo pipefail
image=$1
root=$2
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

tar -xf "$image" -C "$work"
"${PYTHON:-python3}" - "$work" "$root" <<'PY'
import json, subprocess, sys, pathlib
work, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
layers = json.loads((work / "manifest.json").read_text())[0]["Layers"]
root.mkdir(parents=True, exist_ok=True)
for layer in layers:
    subprocess.run(["tar", "-xf", str(work / layer), "-C", str(root),
                    "--transform", "flags=r;s|^/||"], check=True)
print(f"layers: {len(layers)}")
PY