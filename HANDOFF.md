# Handoff — council v2

**Read this first on a new machine.** It is the project context, the verified
state, and the shortest path to a green run. The repository's own documentation
is authoritative for design; this file is the index and resume note.

- **Project:** `reviewc/council`, the v2 review engine
- **Branch:** `v2`
- **Last verified commit:** `ba9ef80` (`M24.2: close the scope proof gaps`)
- **Published at:** `https://github.com/washedupdeveloper/agentic-council/tree/v2`
- **Tag:** `v2.0.0` is at `4247078`; it does **not** point at this handoff's
  commit. Do not move it without following `docs/VERSIONING.md`.

## What this is

`council` reviews a change and produces a verdict from evidence states, not a
numeric score. A finding is `PROVEN`, `REFUTED`, `UNSETTLED` or `UNRUNNABLE`;
only `PROVEN` blocks. The exit codes are:

| code | meaning |
|---|---|
| 0 | PASS |
| 1 | FAIL |
| 2 | the review ran but evidence is missing |
| 3 | the review could not start; no run and no model call |

The v1 implementation remains a frozen differential reference at
`~/projects/review-council` on the original machine; it is not part of this
repository.

## Start here

```sh
git clone --branch v2 git@github.com:washedupdeveloper/agentic-council.git
cd agentic-council

nix develop -c python -m pytest -q -p no:cacheprovider
nix develop -c ./bin/council-verify
nix develop -c python tools/mutation_check.py
nix flake check
```

`nix develop -c ./scripts/verify.sh` runs the same gate in one command. It is
slow by design: the test suite, 175 claims, 30 mutations and the flake check
are separate checks.

Do not use a system `python3`: this machine and NixOS generally have none.
Use `nix develop -c …`. `council doctor` is the right first runtime probe on a
new host; it checks git, the reviewer binary, `bwrap` and the Hermes profile.
Hermes itself must already exist; this project does not install it.

## Verified state at `ba9ef80`

- **556 tests** collected and passing
- **175/175 claims** hold; `docs/CLAIMS.md` is generated from `claims.toml`
- **30/30 mutations** caught; **36** claims declare a mutation falsifier
- `mypy src`: 35 files clean
- `ruff check --select F,E9`: clean
- `nix flake check`: all checks passed on **x86_64-linux**

The last three milestones were:

1. `e512ce5` — accepted-risk baselines with owner, reason, expiry,
   fingerprint tamper protection and base-revision loading for `ci`/`pr`.
2. `b76b50e` — caller-owned `--include`/`--exclude` scope and `--staged`
   review.
3. `ba9ef80` — focused tests closing the proof gaps: `?` matching, scope
   before slicing, config negative, plan text/JSON, and real CLI scope/staged
   paths through `review` and `ci`.

## Read next (in this order)

1. [`README.md`](README.md) — user-facing contract and every CLI flag.
2. [`GLOSSARY.md`](GLOSSARY.md) — one meaning per domain term.
3. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — pure kernel, effect shell,
   SOLID scorecard and the remaining debt.
4. [`docs/STATE-MACHINES.md`](docs/STATE-MACHINES.md) — M1–M14 transitions and
   the SM issue register.
5. [`docs/BASELINE.md`](docs/BASELINE.md) and [`docs/SCOPE.md`](docs/SCOPE.md)
   — the two most recent behaviours.
6. [`docs/CLAIMS.md`](docs/CLAIMS.md) — the executable claim registry.
7. [`docs/VERSIONING.md`](docs/VERSIONING.md) — release procedure and tag
   rules.

## Known limits — not hidden defects

- **Platform:** the gate was observed on x86_64-linux. `nix flake check`
  explicitly omitted `aarch64-linux`, `aarch64-darwin` and `x86_64-darwin`.
  Do not claim those platforms are proven without running the gate there.
- **Live model:** the deterministic suite uses a stub reviewer for the new CLI
  end-to-end tests. The parser, request, prompt and verdict path is proven; a
  provider's live answer is not. Run `council doctor` and one small real review
  when the new host's Hermes profile is available.
- **Architecture debt:** `src/council/run.py` is 765 lines and still owns
  validation, preparation, sampling, adjudication, payload construction and
  persistence. The next safe cut is `validate_request`, `verdict_payload` and a
  `RunStore` adapter, preserving the existing state-machine tests.

## Next work

1. Split `run.py` along the three boundaries above; keep `docs/STATE-MACHINES.md`
   and the 556-test gate green.
2. Then continue the feature roadmap from the reasons recorded in
   `CHANGELOG.md` and `docs/ARCHITECTURE.md` — do not invent a new direction
   without reading those first.
3. Re-run the full gate before calling any later milestone complete. A green
   suite alone is not a live review; `council doctor` plus a small review is
   the runtime check.

## Operating rules

- Work on `v2` or a new feature branch. Never commit to `master`; never move or
  force-push a published tag. The repository owner controls the default branch
  and releases.
- `.council/`, model answers and local run evidence are ignored by git. Do not
  commit credentials, `.env`, provider keys or raw session data.
- Keep LF endings and a trailing newline in every text file; `tests/test_files.py`
  enforces the latter.
- New source files must be staged before `nix flake check`, because Nix's flake
  source only sees tracked files.
- A run that is missing evidence is `INCOMPLETE` (exit 2), never PASS. A
  baseline can suppress only `PROVEN` blocking findings, never missing
  evidence.

## Resume prompt for a new Hermes session

Paste this after cloning:

> Read `HANDOFF.md` in this repository. Verify the current commit and run the
> full gate before changing anything. Then continue with the next work item in
> the handoff, using the existing claims, state-machine and architecture
> documents as the contract.

The original conversation is not published with the repository. This handoff,
the commits, `claims.toml` and `docs/` are the durable context; keep any private
Hermes profile or session archive off the public repository.
