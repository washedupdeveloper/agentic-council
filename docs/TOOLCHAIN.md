# The toolchain: what each tool is for, and whether it is necessary

The standard applied here: a tool is **necessary** when something in this repository
either (a) scores it, (b) executes it, or (c) is the mechanism that provides it. A tool
that nothing scores, nothing runs, and nothing but `toolNames` names is not necessary —
it is a declaration.

Evidence for every row: `scripts/probes.py` (what executes), `scripts/score_reviews.py`
(`STACK_TOOLS`/`GENERIC_TOOLS` → `expected_tools` → beta), `scripts/doctor.py`'s
`CATALOG` (the repo's own statement of why a tool is needed), and the rubric files.

## The verdict in one table

| tool | MB | role | verdict |
|---|---|---|---|
| `nix` | — | probed (`nix-eval`, `flake-check`, `dep-graph`, `nix-eval-time` all shell out to it) | **necessary** |
| `nixfmt` | — | scored (readability/nix), probed | **necessary** |
| `statix` | — | scored (security/nix, readability/nix), probed | **necessary** |
| `deadnix` | — | scored (readability/nix), probed | **necessary** |
| `osv-scanner` | — | scored (security/python, javascript, rust, go), probed | **necessary** |
| `zizmor` | 25.8 | probed (security) — the only analyzer that reads `.github/`; **not** in the expected set, so it cannot lower β where no workflows exist | **necessary** |
| `ruff` | — | scored (readability/python), probed | **necessary** |
| `mypy` | — | scored (readability/python), probed | **necessary** |
| `pytest` | — | scored (correctness/python), probed | **necessary** |
| `bandit` | — | scored (security/python), probed | **necessary** |
| `shellcheck` | — | scored (security/shell, readability/shell) — **but never probed** | **necessary, gap** |
| `nixfmt-tree` | — | provides the `formatter` output | **necessary** |
| `gitleaks` | 16.4 | in the CATALOG for "secret scanning (security)" — **never probed** | **gap** |
| `vulnix` | 193.3 | rubric (security), on demand by decision | on demand |
| `nix-fast-build` | 25.1 | rubric (correctness) | on demand |
| `nil` | 9.5 | LSP; referenced only as fixture *text* in a dev module | **no purpose** |
| `tokei` | 6.3 | rubric names it for the KLOC denominator — which Python computes | **no purpose** |
| `nix-tree` | 5.7 | rubric (performance) | on demand |
| `nixd` | 5.6 | LSP | **no purpose** |
| `nix-diff` | 4.3 | rubric (performance) | on demand |
| `nix-du` | 3.8 | rubric (performance) | on demand |
| `cloc` | 1.5 | rubric names it as the tokei alternative | **no purpose** |
| `jq` | 1.2 | the check that needs it pulls `pkgs.jq` directly | **no purpose** |
| `yamllint` | 0.6 | nothing, anywhere | **no purpose** |
| `treefmt` | 0.0 | the `formatter` execs `nixfmt-tree`'s binary | **no purpose** |

## 1. Necessary: 11 tools

Nine are scored — `expected_tools` computes beta from them, so removing one caps the
score below 1.0 for the affected dimension. One (`nix`) is what four probes shell out
to. One (`nixfmt-tree`) is what the `formatter` output execs, so `nix fmt` depends on
it.

`GENERIC_TOOLS` is empty for every dimension, so beta is entirely stack-driven: a tool
matters only when its stack is detected. This repository detects `nix` and `python`.

## 2. Two gaps — a tool the gate expects that nothing runs

These are the opposite of dead weight: the gate asks for a signal the toolchain cannot
produce.

**`shellcheck`** is scored for the `shell` stack (`STACK_TOOLS["security"]["shell"]` and
`["readability"]["shell"]`), and `.sh`/`.bash` are in `STACK_EXTENSIONS`, so `shell` is
detectable. There is **no `shellcheck` probe in `probes.py`**. A repository containing
shell therefore has an expected tool that can never run, and beta cannot reach 1.0 for
it. `tests/test_probes.py::test_every_expected_tool_has_a_probe` was written to catch
exactly this, but its list is hardcoded to 16 names and `shellcheck` is not among them —
so the test that guards this class misses the instance in it.

**`gitleaks`** is in `doctor.py`'s `CATALOG` as "secret scanning (security)", and
`doctor.py` states in a comment that "the security dimensions use statix + gitleaks
(Nix) and bandit + osv-scanner (Python)". That is **not what happens**: the security
probe is `secret-grep`, a hand-rolled Python regex over source files that does not read
git history and has no entropy detection. So the CATALOG claims a tool the pipeline does
not use, and the tool it names is the better scanner.

Both are fixable in the same direction — add the probe — and that is the recommendation
rather than removal: a shipped tool with no probe is a missing signal, not a waste.

## 3. No purpose: 7 tools, 24.7 MB

Nothing scores them, nothing executes them, and they are absent from the repo's own
`CATALOG`.

- **`nixd`, `nil`** — language servers. A real convenience for a human editing Nix, but
  no part of the pipeline reads them, and neither is in the CATALOG. `nil`'s only
  occurrence in code is fixture *text* inside a dev module's defect corpus
  (`inject_defects.py` injects `nil` into a sample config to create a performance
  finding) — which is a mention, not a use.
- **`tokei`, `cloc`** — the readability rubric names `tokei -t Nix --output json |
  jq .Nix.code` as "the KLOC denominator (or cloc …)". The denominator is not computed
  that way: `probes.py` calls `_shared.kloc()`, pure Python over `SOURCE_SUFFIXES`. So
  the rubric documents a method the framework does not use, and two tools exist to
  support it.
- **`jq`** — the only code that needs jq is `checks.commands`, and it lists `pkgs.jq` in
  its own `nativeBuildInputs`. The `toolNames` entry is not what satisfies it.
- **`treefmt`** — the `formatter` output execs `${pkgs.nixfmt-tree}/bin/treefmt`, i.e.
  the binary inside `nixfmt-tree`. The standalone `treefmt` package is a second copy of
  the same thing, which is why removing it frees exactly **0.0 MB** — measured, and the
  clearest evidence in this audit that per-tool closure figures overlap.
- **`yamllint`** — nothing anywhere. Not in the CATALOG, not in a rubric, not in code.

Removing all seven is a tidiness and clarity change worth ~24.7 MB — about 2.5% of the
toolchain. It is not a compute win of any consequence, and saying otherwise would be
dishonest.

## 4. On demand: 5 tools, 232.2 MB

Named as commands in a rubric, so a reviewer may run them, but nothing runs them
automatically. This is the `vulnix` pattern the owner chose deliberately: available, not
probed.

| tool | rubric | MB |
|---|---|---|
| `vulnix` | reviewer-security | 193.3 |
| `nix-fast-build` | reviewer-correctness | 25.1 |
| `nix-tree` | reviewer-performance | 5.7 |
| `nix-diff` | reviewer-performance | 4.3 |
| `nix-du` | reviewer-performance | 3.8 |

`vulnix` is 83% of this group and 20% of the whole toolchain. If the goal were minimum
compute rather than availability, this group is where the decision lies — and it is one
decision, not five.

## 5. The opposite defect: the gate expects 25 tools nothing ships

`expected_tools` unions `STACK_TOOLS[dimension][stack]` across detected stacks. For
stacks this toolchain does not provide, the expected tools do not exist:

```
gosec, jest, tsc, cargo-test, cargo-check, cargo-bench, clippy, rustfmt,
gofmt, golint, go-test, go-vet, go-bench, eslint, prettier, bundle-size
```

A JavaScript, Rust or Go repository reviewed by this framework would therefore have beta
capped well below 1.0, for tools the toolchain never intended to ship. Some of the
remaining names in that set are not tools at all but **probe names** implemented inside
`probes.py` (`flake-check`, `nix-eval`, `nix-eval-time`, `secret-grep`, `dep-graph`,
`declared-rules`, `complexity`, `py-compile`, `bash-n`) — which is fine and intentional,
but it means `expected_tools` mixes two kinds of name, so a reader cannot tell "missing
tool" from "internal probe" without cross-referencing.

That is a clarity defect, and it is the same one the owner's principle names. Either the
unsupported stacks should be dropped from `STACK_TOOLS` (so beta stops expecting them),
or they should be documented as "reviewed with a degraded toolchain".

## What was done — all four recommendations, applied

**1. Both missing probes added.** `probes.py` now has `probe_gitleaks` and
`probe_shellcheck`, both registered, and `gitleaks` is scored for every stack's security
dimension while `shellcheck` finally has a probe behind the score it already carried.

The gitleaks probe reads the **working tree** (`--no-git`), not git history, and the
report's `Secret` field never reaches a finding — only the rule, the file and the line
do, and `--redact` keeps the value out of stdout too. A probe that leaked the credential
it found into a review report would be the exact failure it exists to catch.

**2. The toolchain is split, not just pruned.** The owner's rule: the shipped toolchain
carries the *centralised* quality assurance, and everything else is a contributor's own
choice. So `nix/builders.nix` now has two lists:

| list | count | where it lands |
|---|---|---|
| `toolNames` | 13 | devshell, container, `nix shell .#review-council` |
| `devToolNames` | 9 | devshell only (`mkDevTools`) |

Measured: the QA toolchain closure is **919.8 MB / 180 paths**, down from 983.3 MB / 212.
The 9 DX tools are absent from the container entirely.

Two tools were dropped outright rather than moved:

- **`treefmt`** — the `formatter` execs `${nixfmt-tree}/bin/treefmt`, so the standalone
  package was a second copy of the same binary (measured: frees 0.0 MB).
- **`yamllint`** — nothing uses it. It was *tested* as a flake-check candidate against
  the repo's own workflows and **fails** on them (line-length errors), so making it pass
  would have meant adding a config file to justify a linter nothing needs. For linting
  the workflows the right tool is `actionlint`, which CI already uses.

The three rubrics that named a moved tool (`nix-tree`, `nix-diff`, `nix-du`,
`nix-fast-build`, `tokei`, `cloc`) now say **devshell only**, so a reviewer in the
container is not sent looking for a binary that is not there. The readability rubric's
KLOC line was also simply wrong and is corrected: the denominator is computed by
`probes.py`, not by `tokei` or `cloc`.

**3. The on-demand group stands.** `vulnix` ships and is never probed — the owner's
decision, pinned by a test. The other four in that group (`nix-fast-build`, `nix-tree`,
`nix-diff`, `nix-du`) turned out to be DX rather than review tooling, so they moved to
the devshell: they are rubric *conveniences*, and a review does not depend on them.

**4. The `expected_tools` name space is explicit.** `score_reviews.EXTERNAL_TOOLS`
declares which expected names are binaries the toolchain must ship; every other name is a
probe implemented inside `probes.py`. Four tests pin the contract:

- every expected name for a stack we ship has a probe (derived from `STACK_TOOLS`, so it
  cannot drift — the previous hand-written list missed `shellcheck`, which is how the
  gap survived);
- every name in `EXTERNAL_TOOLS` is actually expected (a typo would silently exempt a
  tool from the shipping requirement);
- every non-external expected name is a probe;
- every external scored tool for a supported stack ships in `toolNames`.

**Not fixed, deliberately:** the gate still lists tools for JavaScript, Rust and Go
(`jest`, `tsc`, `cargo-*`, `go-*`, `eslint`, `prettier`, `clippy`, `rustfmt`, `gofmt`,
`golint`, `gosec`, `bundle-size`). The framework does not ship those toolchains, so a
repository in one of those languages has beta capped by missing coverage. That is
arguably the honest answer — the framework cannot verify what it cannot run — but it is
a *policy* decision rather than a defect, so it is recorded here and left alone. The
tests scope themselves to `nix`, `python` and `shell` for the same reason.
