#!/usr/bin/env bash
# The full acceptance gate. Run from anywhere; uses the repository's flake.
set -euo pipefail

cd "$(dirname "$0")/.."

printf '%s\n' '== tests =='
nix develop -c python -m pytest -q -p no:cacheprovider
printf '%s\n' '== claims =='
nix develop -c ./bin/council-verify
printf '%s\n' '== mutations =='
nix develop -c python tools/mutation_check.py
printf '%s\n' '== flake =='
nix flake check

printf '%s\n' 'all checks passed'
