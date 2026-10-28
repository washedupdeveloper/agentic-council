# Deterministic Tooling Matrix — Nix / NixOS / Clan Infrastructure Review

**Target artifact:** a Clan-based NixOS infrastructure flake
(`flake.nix`, `clan.nix`, `lib/default.nix`, `modules/flake/*`, `modules/nixos/*`,
`modules/home/*`, `machines/host/configuration.nix`, `sops/`, `vars/`).
**Host observed:** Windows 11 + git-bash; the repo is checked out at
a private Clan-based NixOS flake. No Nix toolchain is
installed on the review host (`nix`, `nixos-rebuild`, `statix`, `deadnix`, `tokei`, `cloc`,
`jq` all absent), so every signal below is specified to be executed **inside the repo's
devshell / CI**, not on the Windows review box.

**Purpose.** For each of five review categories this document fixes: the concrete tool,
its exact pin/install method, its exact CLI invocation, its output format, how to extract
one numeric or discrete signal, its runtime cost, and its false-positive character. It
closes with a deterministic 0→100 normalization scheme (Hill curve + threshold curve +
weighted geometric mean) and an explicit deterministic-vs-environment-dependent split.

A design principle throughout: **every category score must be reproducible from a pinned
tool set on a pinned nixpkgs revision**, with the only non-reproducible inputs being
wall-clock timings and closure sizes, which are handled as *regression ratios against a
pinned baseline* rather than as absolute values.

---

## 0. Tool inventory and pinning

All tools in the matrix are available from the single `nixpkgs` input
(`github:NixOS/nixpkgs/nixos-unstable`, pinned in `flake.lock`). That is the preferred pin
because it makes the whole tool set move atomically with one lock-file revision. The repo
already does this: `modules/flake/devshells.nix` puts `nixd deadnix statix nixfmt
nixfmt-tree nix-output-monitor` into the default devshell, and `modules/nixos/baseSystem.nix`
puts the same set into `environment.systemPackages`. `modules/flake/git-hooks.nix` wires
`nixfmt-rfc-style`, `deadnix`, `statix`, `gitleaks`, `markdownlint`, `editorconfig-checker`
as pre-commit hooks.

| Tool | Pin / install | Notes |
|---|---|---|
| `nixfmt` / `nixfmt-tree` | `pkgs.nixfmt` and `pkgs.nixfmt-tree` (nixpkgs) | `nixfmt-tree` is treefmt pre-configured for nixfmt; used as `formatter` in `flake.nix`. |
| `nixpkgs-fmt` | `pkgs.nixpkgs-fmt` | **Deprecated** — superseded by RFC 166; do not adopt. |
| `alejandra` | `pkgs.alejandra` | Alternative formatter; not RFC 166. |
| `statix` | `pkgs.statix` | Must be built with `--all-features` for JSON output. |
| `deadnix` | `pkgs.deadnix` | Has native JSON output. |
| `nix-linter` | `pkgs.nix-linter` (if present) | **Abandoned**; author recommends statix. |
| `nil` | `pkgs.nil` | LSP + CLI diagnostics. |
| `nixd` | `pkgs.nixd` | LSP, option-system aware. |
| `nixpkgs-hammering` | `nix run github:Mic92/nixpkgs-hammering` | Package-expression linter; not for NixOS modules. |
| `vulnix` | `pkgs.vulnix` | **Unmaintained**; the only store/CVE scanner. **Ships, but is never probed** — on demand only, see §4.1. |
| `nix-tree` | `pkgs.nix-tree` | Interactive closure browser + `--dot` + `--diff`. |
| `nix-diff` | `pkgs.nix-diff` | Derivation-level diff. |
| `nix-fast-build` | `pkgs.nix-fast-build` / `nix run github:Mic92/nix-fast-build` | Parallel eval+build of `checks`. |
| `nix-du` | `nixpkgs#nix-du` (`github:symphorien/nix-du`) | GC-root disk attribution. |
| `tokei` / `cloc` | `pkgs.tokei` / `pkgs.cloc` | Denominator (KLOC) for density metrics. |
| `gitleaks` | `pkgs.gitleaks` | Already wired as a pre-commit hook. |
| `jq` | `pkgs.jq` | JSON extraction glue. |

**Gap / correction:** the brief lists `nix store du`. **No such subcommand exists** in
the Nix CLI (`nix store` has `gc`, `optimise`, `verify`, `diff-closures`, `ls`, `ping`,
`prefetch`, `repair`, `sign`, … but not `du`). Disk-usage signals must come from
`nix path-info -Sh` or `du -sh /nix/store`, not `nix store du`. See §4.1.

---

## 1. Readability / maintainability

Formatter and linters are fully deterministic: pure AST transforms with no evaluation, no
network, no store access.

| Tool | Invocation | Output | Signal | Runtime | False positives |
|---|---|---|---|---|---|
| **nixfmt (RFC 166)** | `nixfmt --check <files>` / `treefmt --ci` / `nix fmt -- --ci` | exit code; diff on stdout | `fmt_clean ∈ {0,1}` = (exit 0) | O(ms–s) per file; repo-wide < 1 s | Effectively zero for the canonical style; flags legitimate formatting drift, not bugs. |
| **nixfmt-tree** | `nixfmt-tree` (formats all `.nix` under cwd) | exit code + diff | same | as above | same |
| **statix** | `statix check . -o json` | **JSON** (requires `--all-features` build) | list of `{file, line, severity, code}` | ~10–100 ms/file | Low. Lints are AST-local; a handful (e.g. `useless_has_attr`, `bool_simplification`) can fire on intentional clarity. All 16 lints are enabled by default. |
| **deadnix** | `deadnix --output-format json --fail .` | **JSON** | `[{file, results:[{line,column,message}]}]` | ~10–100 ms/file | Moderate. Fires on intentionally-unused lambda pattern names; `--no-lambda-pattern-names` / `-L` suppresses the callPackage case. The repo already sets `noUnderscore = true`. |
| **nix-linter** | `nix-linter --json <files>` | JSON | finding count | fast | **Do not adopt** — abandoned upstream; superseded by statix. |
| **nil (CLI diagnostics)** | `nil diagnostics <files>` | text/JSON; `--deny-warnings` sets exit code | error/warning count | ~ms/file (incremental) | Low. Exit code is 1 only on *errors* unless `--deny-warnings`. |
| **nixd (LSP)** | LSP `textDocument/publishDiagnostics` | LSP diagnostics | diagnostic count | background | Low; requires `nixpkgs.expr` + `options` config or option-aware diagnostics are wrong. |
| **treefmt** | `treefmt --ci --no-cache` | exit code | aggregate `{0,1}` | < 1 s | zero |
| **git-hooks.nix** | `pre-commit run --all-files` | text | pass/fail | seconds | zero |

**Signal to normalize.** Finding density
`F = (w_statix · N_statix + w_deadnix · N_deadnix) / KLOC`, where `KLOC = tokei -t Nix --output json | jq .Nix.code / 1000`
(or `cloc --json --include-lang Nix`). Severity weights: statix `W##` map to fixed weights
(error-class = 2, warning-class = 1); deadnix = 1 each. Formatting is a *separate* binary
gate, not folded into density.

- statix lints/suggestions: <https://github.com/oppiliappan/statix>
- deadnix: <https://github.com/astro/deadnix>
- nixfmt + RFC 166: <https://github.com/NixOS/nixfmt>, <https://github.com/NixOS/rfcs/pull/166>, <https://github.com/NixOS/nixfmt/blob/master/standard.md>
- nixpkgs-fmt deprecation / RFC 101 closure: <https://github.com/NixOS/rfcs/pull/101>, <https://github.com/nix-community/nixpkgs-fmt>
- alejandra: <https://github.com/kamadorueda/alejandra>
- nix-linter abandoned: <https://github.com/Synthetica9/nix-linter>
- nil: <https://github.com/oxalica/nil>
- nixd: <https://github.com/nix-community/nixd>, <https://github.com/nix-community/nixd/blob/main/nixd/docs/configuration.md>
- treefmt / treefmt-nix: <https://github.com/numtide/treefmt>, <https://github.com/numtide/treefmt-nix>
- git-hooks.nix: <https://github.com/cachix/git-hooks.nix>

---

## 2. Correctness / testing

This is the only category with **hard pass/fail gates**; the rest of the score is
evaluation and type-checking signals.

| Tool | Invocation | Output | Signal | Runtime | False positives |
|---|---|---|---|---|---|
| **`nix flake check`** | `nix flake check --no-build --keep-going`, then `nix flake check --keep-going` | text; exit code | **hard gate** `flake_check ∈ {0,1}` (eval-only is not a pass — a run-tier check is a derivation, and `--no-build` never builds it) | seconds–minutes (eval) | None for evaluation; may report unrelated warnings as failures. Use `--keep-going` to collect all errors, not just the first. |
| **`nix flake check` (build)** | `nix flake check --keep-going` | text; exit code | builds every `checks.<system>.*` and `nixosConfigurations.*.config.system.build.toplevel` | minutes–hours | None, but expensive; run nightly. |
| **`nix eval --json`** | `nix eval .#nixosConfigurations.host.config.system.build.toplevel.drvPath` | JSON/raw | evaluates the full NixOS config; exit 0 = option typecheck passes | seconds–minutes | None. |
| **`nixos-rebuild build --flake .#<host>`** | `nixos-rebuild build --flake .#host --no-build` (or without for full build) | text; `result` symlink | build success | minutes | None; needs a Linux host. |
| **`nix build --dry-run`** | `nix build .#checks.x86_64-linux.<check> --dry-run` | text (planned paths) | number of paths to build (0 = fully cached) | seconds | None. |
| **`nix-instantiate --parse`** | `nix-instantiate --parse <file>` | AST text; exit code | syntax errors per file | ms/file | None — pure parser. |
| **`nix eval --option pure-eval true`** | `nix eval --option pure-eval true .#...` | JSON; exit code | detects impurity (network, absolute paths, `builtins.currentSystem`) | as eval | Can fail on legitimate uses of `builtins.getEnv` in non-flake contexts. |
| **`nixos-option`** | `nixos-option <option.path>` / `-r` | text | confirms an option exists and its type/default/value | seconds | Only inspects the NixOS module system; not arbitrary expressions. |
| **`clan vars check`** | `clan vars check --flake .` | text; exit code | **gate**: all generated vars present & up to date | seconds | Requires generators to have run; reports "missing" until `clan vars generate` has been executed once. |
| **`nix-fast-build`** | `nix-fast-build --flake .#checks --result-format json --result-file out.json` | **JSON / JUnit** | per-check pass/fail + timing | minutes | None. |
| **`nixpkgs-hammering`** | `nixpkgs-hammer <attr>` | text | package-expression anti-pattern count | seconds/pkg | Designed for *nixpkgs package* PRs, **not** NixOS/Clan modules — near-zero applicability to a NixOS/Clan module tree; use only if the flake gains `packages`. |

**Signals to normalize.** `flake_check` and `clan vars check` are binary gates (0/1).
Evaluation-time and `--dry-run` path counts feed performance (§3), not correctness.
`nix-instantiate --parse` gives a syntax-error count per file, useful as a cheap
pre-check before the expensive full eval.

- `nix flake check`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake-check>
- `nix eval`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-eval>
- `nix-instantiate`: <https://nix.dev/manual/nix/latest/command-ref/nix-instantiate>
- `nix build`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-build>
- `nixos-rebuild` / NixOS manual: <https://nixos.org/manual/nixos/unstable/>
- `pure-eval` / conf-file: <https://nix.dev/manual/nix/latest/command-ref/conf-file>
- `nixos-option`: NixOS manual (option inspection) — <https://nixos.org/manual/nixos/unstable/>
- `nixpkgs-hammering`: <https://github.com/Mic92/nixpkgs-hammering>
- `nix-fast-build`: <https://github.com/Mic92/nix-fast-build>
- Clan `nix flake check` guidance: <https://clan.lol/docs/25.11/getting-started/whats-next>

---

## 3. Performance

Performance signals are **environment-dependent** (wall time, closure size) and are
therefore expressed as **ratios to a pinned baseline recorded in-repo**, never as absolute
scores.

| Tool | Invocation | Output | Signal | Runtime | False positives |
|---|---|---|---|---|---|
| **`nix path-info`** | `nix path-info -Sh --recursive <toplevel>` | text; `--json` for JSON | closure size (bytes) | seconds | None; size is exact. |
| **`nix path-info --json`** | `nix path-info --json --closure-size <path>` | **JSON** (`narSize`, `closureSize`) | machine-readable closure bytes | seconds | None. |
| **`nix-tree`** | `nix-tree <path>` / `nix-tree --diff <old> <new>` / `--dot` | TUI; `--dot` → Graphviz | per-path size + diff totals | seconds | None. |
| **`nix-diff`** | `nix-diff <old.drv> <new.drv>` | text | derivation-level change count (rebuild surface) | seconds | None; textual. |
| **`nix store diff-closures`** | `nix store diff-closures <before> <after>` | text | added/removed packages + size deltas | seconds | None. |
| **eval time** | `NIX_SHOW_STATS=1 nix eval .#... 2>stats.txt` | text stats | `cpuTime`, thunk/GC counts | as eval | None, but noisy across machines. |
| **eval profiler** | `nix eval --option eval-profiler flamegraph --option eval-profile-file p .#...` | flamegraph profile | self-time per attribute | as eval | None. |
| **`nix-fast-build`** | `nix-fast-build --flake .#checks --result-format json` | JSON | per-attr build time | minutes | None. |
| **IFD detection** | `nix eval --option allow-import-from-derivation false .#...` | exit code | **gate**: 0 = no IFD | as eval | Legitimate IFD (e.g. some generators) will fail the gate; allow-list explicitly. |
| **`--max-jobs` / `--cores`** | `nix build --max-jobs 0 --cores 0` | — | build parallelism (config signal) | — | N/A (config review, not measurement). |

**Signals to normalize.** Two metrics:
1. `eval_ratio = eval_seconds / baseline_eval_seconds` (baseline pinned in
   `ci/baseline.json`).
2. `closure_ratio = closure_bytes / baseline_closure_bytes`.
Plus one **gate**: `ifd_free ∈ {0,1}` from
`allow-import-from-derivation = false`.

IFD is the single most important performance *code* signal: any store path read during
evaluation pauses evaluation and serialises realisation, so it cannot be parallelised —
the manual states evaluation "is therefore much slower than otherwise". Disabling it is
the deterministic way to detect it.

- `nix path-info`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-path-info>
- `nix store diff-closures`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-store-diff-closures>
- `nix-tree`: <https://github.com/utdemir/nix-tree>
- `nix-diff`: <https://github.com/Gabriella439/nix-diff>
- IFD: <https://nix.dev/manual/nix/latest/language/import-from-derivation>
- conf-file (`allow-import-from-derivation`, `max-jobs`, `cores`): <https://nix.dev/manual/nix/latest/command-ref/conf-file>

---

## 4. Security

### 4.1 Closure / store hygiene

| Tool | Invocation | Output | Signal | Runtime | False positives |
|---|---|---|---|---|---|
| **`vulnix`** — **on demand, never probed** | `vulnix --system -w whitelist.toml --json` | **JSON** | CVE count (filtered by whitelist) | minutes (NVD download, cached) | **High.** Matches name+version against NVD; upstream backports are invisible, so patched-but-same-version packages report as vulnerable. Whitelisting is mandatory to make it usable. Unmaintained. |
| **`nix store verify`** | `nix store verify --recursive --sigs-needed 1 <path>` | exit code | unsigned/untrusted path count | seconds | None. |
| **`nix why-depends`** | `nix why-depends --all <pkg> <dep>` | text | whether a sensitive path is reachable from a service closure | seconds | None. |
| **`nix flake archive`** | `nix flake archive --json .` | **JSON** | input closure size / all inputs locked | seconds | None. |
| **`nix store gc`** | `nix store gc --dry-run` | text | reclaimable paths (old generations retained) | seconds | None. |
| **`du -sh /nix/store`** | (no `nix store du`) | text | store disk usage | seconds | None. |
| **Nixpkgs security tracker** | `curl https://tracker.security.nixos.org/` / GitHub advisories | HTML/JSON | open advisories affecting pinned nixpkgs | network | Advisory-vs-revision matching is manual. |

### 4.2 Secrets handling (sops-nix / agenix patterns)

Deterministic, high-value checks — these are **grep-class** and belong in the security
gate:

| Check | Method | Signal |
|---|---|---|
| `builtins.readFile` on a decrypted secret path | `rg -n 'readFile' modules/ \| rg -i 'secret\|sops\|age'` | count of suspicious reads → gate |
| Nix path literal to a private key | `rg -n 'age\.identityPaths\|sops\.age\.(sshKeyPaths\|keyFile)' -A3 \| rg '\.\./'` | count of path literals (must be strings) |
| `--impure` / `--impure`-implying flags in CI | `rg -n -- '--impure' .github/ Makefile justfile` | count |
| `builtins.fetchTarball` without `sha256` | `rg -n 'fetchTarball' \| rg -v 'sha256'` | count |
| `allowUnfree = true` | `rg -n 'allowUnfree'` | count |
| `accept-flake-config = true` | `rg -n 'accept-flake-config'` | count (this repo **sets it true**) |
| world-readable store secret | sops-nix/agenix place plaintext under `/run/…`; a `builtins.readFile` of that path re-enters the store | gate |

The security model to encode: ciphertext may live in the store; **plaintext must never be
evaluated into it**. `sops-nix` decrypts at activation into `/run/secrets/…`, agenix into
`/run/agenix/…`; the correct pattern is to pass `config.sops.secrets.<n>.path` /
`config.age.secrets.<n>.path` to a `*File` option, never `builtins.readFile`.

- vulnix: <https://github.com/nix-community/vulnix>
- Nixpkgs security tracker: <https://tracker.security.nixos.org/>
- NixOS security team: <https://nixos.org/community/teams/security/>
- sops-nix: <https://github.com/Mic92/sops-nix>
- agenix: <https://github.com/ryantm/agenix>
- secrets comparison (NixOS wiki): <https://wiki.nixos.org/wiki/Comparison_of_secret_managing_schemes>
- `nix store verify`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-store-verify>
- `nix why-depends`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-why-depends>
- `nix flake archive`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake-archive>
- `nix store gc`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-store-gc>
- `nix-du`: <https://github.com/symphorien/nix-du>

---

## 5. Architecture / design

Mostly **static, textual and module-structure** signals — the least tooling-mature category.

| Signal | Method | Output | Determinism |
|---|---|---|---|
| Module evaluates as a module set | `lib.evalModules { modules = [...]; }` via a tiny `eval.nix` | error / `config` | deterministic |
| Undeclared / unused options | `nix eval .#nixosConfigurations.<h>.options --apply builtins.attrNames` vs. option use sites | name set | deterministic |
| `mkIf` / `mkMerge` misuse | grep + AST: `mkIf` outside a `config` attrset, `mkIf` on `_module.args` | count | deterministic (heuristic) |
| `specialArgs` vs `_module.args` | grep `specialArgs` in `flake.nix` / `clan.nix`; both mechanisms present | count | deterministic |
| Import cycles | evaluation failure ("infinite recursion") under `nix flake check` | boolean | deterministic |
| flake-parts module structure | module count vs. `importModulesRecursive` result; `nix eval .#flake.lib...` | count | deterministic |
| Dead module files | `deadnix` on `modules/**`; plus "module never imported" = files not reachable from `flake.nix` imports | count | deterministic |
| Layering (nixos vs home vs flake) | a module under `modules/home/` importing `nixosModules` is a layering violation | count | heuristic |
| Clan topology | `clan machines list`, `clan show`, inventory tag coverage | text/JSON | deterministic |
| Option declarations vs definitions | count `mkOption` vs. count `config.<x> =` per module; a module defining without declaring is fine in NixOS, but a *flake* module declaring and never defining is dead | ratio | heuristic |

**Module-system primitives.** `lib.evalModules` is the function that evaluates modules,
applies type checking, and merges values; the merged result lives under `config`, the
declarations under `options`. `specialArgs` is only for arguments needed during module
*structure* resolution (imports); everything else belongs in `_module.args`. `mkIf` is
"entirely useless" for `_module.args`. These are the exact rules a deterministic
architecture check encodes.

**Clan specifics.**

| Command | Purpose | Output |
|---|---|---|
| `clan machines list` | enumerate managed machines | text |
| `clan machines build <m> --dry-run` | validate config without building | text |
| `clan vars check` | verify all vars generated/present | exit code |
| `clan vars generate` | (re)generate vars | text |
| `clan vars list <m>` | list public/secret var ids | text |
| `clan secrets list` / `clan secrets get` | inspect secret store | text |
| `clan show` | show meta information about the clan | text |
| `clan select` | select NixOS values from the flake | text |
| `nix flake check` | the Clan-recommended validation gate | exit code |

- `lib.evalModules` (nixpkgs manual): <https://nixos.org/manual/nixpkgs/unstable/#module-system-lib-evalModules>
- Module system deep dive: <https://nix.dev/tutorials/module-system/deep-dive.html>
- `lib/modules.nix` (source of truth): <https://github.com/NixOS/nixpkgs/blob/master/lib/modules.nix>
- flake-parts: <https://flake.parts/>, <https://github.com/hercules-ci/flake-parts>
- Clan CLI overview: <https://clan.lol/docs/26.05/reference/cli>
- Clan machines: <https://clan.lol/docs/26.05/reference/cli/machines>
- Clan vars: <https://clan.lol/docs/26.05/reference/cli/vars>
- Clan secrets: <https://clan.lol/docs/26.05/reference/cli/secrets>
- Clan flake-parts guide: <https://clan.lol/docs/26.05/guides/flake-parts>
- Clan autoincludes: <https://docs.clan.lol/latest/guides/inventory/autoincludes/>

---

## 6. Observations from the reference corpus

These are **hypotheses the deterministic tools above would confirm or refute**; they are
recorded because they are exactly the class of finding the matrix is meant to surface.

1. **Duplicated flake.** `clan/` is a nested second copy of the whole flake (its own
   `flake.nix`, `clan.nix`, `machines/`, `modules/`). Two divergent `clan.nix` files
   already differ (root `hm` instance imports only `modules/home/default.nix`; `clan/clan.nix`
   additionally imports `git.nix` and `shell.nix`). This is dead/duplicated architecture —
   a `deadnix` + module-reachability check plus a human gate.
2. **statix config placement.** `.statix.toml` exists only under `clan/`, not at repo root,
   so root-level `statix check .` will not pick it up. Its key is `ignore = [...]`, but
   statix's documented config key for lint suppression is `disabled = [...]`; path
   exclusions are normally passed with `-i/--ignore`. The config is likely a **no-op** —
   verify before relying on it.
3. **`accept-flake-config = true`** in `modules/nixos/baseSystem.nix`: a malicious/compromised
   input's `flake.nix` config can then change substituters/options on the evaluating machine.
   Security signal.
4. **`trusted-users = [ username ]`** added in `machines/host/configuration.nix`:
   the login user can set arbitrary substituters/`--option`, a supply-chain escalation.
   Combined with `security.sudo.wheelNeedsPassword = false`, the blast radius is large.
5. **Commented-out config** in `flake.nix` (`_module.args.pkgs`, `pkgs = pkgs`) and
   `modules/nixos/wsl.nix` (dead `variables` block with odd indentation) — readability/
   dead-code signals.
6. **Unused input**: `zed` is declared in `inputs` but referenced nowhere in `outputs`;
   `nix-topology` is imported. `nix flake archive` + grep gives the set.
7. **`nix.gc.automatic`** is `true` in `baseSystem.nix` and overridden to `false` in the
   host config — an intentional-but-worth-documenting layering decision.
8. **`builtins.fetchTarball` without hash** — none found in the visible tree, but the
   security grep should run on every PR to keep it that way.
9. **`sops/` and `vars/`** were deliberately not read (secret payloads). The security
   checks operate on *references* to those paths, never their contents.

---

## 7. Normalization to 0→100 per-category scores

### 7.1 Raw signal → sub-score

Two transform families, both fixed and versioned.

**(a) Hill (sigmoid) curve** for unbounded, monotone metrics:

```
H(x; K, n) = 100 / (1 + (x / K)^n)          # decreasing: smaller x is better
H⁺(x; K, n) = 100 / (1 + (K / x)^n)         # increasing: larger x is better
```

- `K` = half-saturation point (the value that scores exactly 50).
- `n` = steepness (>1 concentrates the penalty near the knee; `n = 1` is a soft linear-ish
  roll-off in log space).
- Concrete parameters:

| Metric | Direction | K | n |
|---|---|---|---|
| `F` = weighted lint findings / KLOC | decreasing | 3.0 | 1.2 |
| `eval_ratio` (vs pinned baseline) | decreasing | 1.5 | 3.0 |
| `closure_ratio` (vs pinned baseline) | decreasing | 1.25 | 3.0 |
| `N_cve` (whitelisted-out) | decreasing | 5 | 1.0 |
| `N_security_grep_hits` | decreasing | 1 | 2.0 |
| `N_unsigned_paths` | decreasing | 0.5 | 4.0 |
| `N_arch_heuristic_hits` | decreasing | 4 | 1.0 |

**(b) Threshold (piecewise-linear / step) curve** for gates and discrete counts:

```
T(x) = 100                    if x ≤ x_good
     = 100 · (x_bad − x)/(x_bad − x_good)   if x_good < x < x_bad
     = 0                      if x ≥ x_bad
```

Used where a human has fixed "acceptable" and "unacceptable" bounds, e.g. `N_security_grep_hits`:
0 → 100, ≥3 → 0.

### 7.2 Hard gates (multiplicative, not additive)

Gates are **not** averaged; they cap or zero the category so that a single catastrophic
failure cannot be diluted by good scores elsewhere:

| Gate | Condition | Effect |
|---|---|---|
| `flake_check` | `nix flake check` fails | correctness category → 0 |
| `clan_vars_check` | `clan vars check` fails | correctness category × 0.5 |
| `fmt_clean` | `nixfmt --check` / `treefmt --ci` fails | readability category × 0.5 |
| `secret_in_store` | any `builtins.readFile`-on-secret hit | security category → 0 |
| `unsigned_paths` | `nix store verify` finds unsigned paths | security category × 0.5 |
| `ifd_free` | IFD present | performance category × 0.6 |

Represent as `G_category ∈ [0,1]`; multiply the aggregated category score by it.

### 7.3 Category aggregation — weighted geometric mean

```
Score_cat = 100 · G_cat · exp( Σ_i w_i · ln( max(s_i, ε) / 100 ) ) / 100
```

equivalently, in normalized form, `Score_cat = 100 · G_cat · Π_i (s_i / 100)^{w_i}`, with
`Σ w_i = 1` and `ε = 1` (clamp sub-scores to `[1, 100]` so a single 0 becomes a 1-point
floor rather than a hard `ln(0)`).

The **geometric mean is chosen deliberately**: it penalises a single failing dimension far
more than an arithmetic mean, which matches how infrastructure review works — one exposed
secret is not offset by twenty clean modules.

**Category weights (default, versioned):**

| Category | Signals (weights sum to 1 within category) |
|---|---|
| Security | `secret_in_store` gate, `N_security_grep_hits` (0.30), `N_cve` (0.25), `N_unsigned_paths` (0.20), `accept-flake-config`/`trusted-users` (0.15), `builtins.fetchTarball` no-hash (0.10) |
| Performance | `eval_ratio` (0.35), `closure_ratio` (0.35), `ifd_free` gate, build-time regression (0.30) |
| Readability / maintainability | `F` density (0.60), `fmt_clean` gate, `deadnix` unused-binding count (0.25), `N_module_files` dead/unreachable (0.15) |
| Correctness / testing | `flake_check` gate, `clan_vars_check` gate, `nix-instantiate --parse` error count (0.30), option-typecheck pass (0.40), `nix-fast-build` failing-check count (0.30) |
| Architecture / design | `N_arch_heuristic_hits` (0.40), import-cycle count (0.25), unused-input count (0.15), layering-violation count (0.20) |

### 7.4 Baselines and regression handling

`eval_ratio` and `closure_ratio` require a **pinned baseline** checked into the repo
(`ci/baseline.json`, produced by the same tool set on the same machine class and updated
only on an explicit, reviewed commit). This converts an environment-dependent absolute
measurement into a deterministic *relative* one. The absolute numbers themselves are
recorded but never scored directly.

### 7.5 Deterministic vs environment-dependent

| Class | Signals | Reproducible across machines? |
|---|---|---|
| **Fully deterministic** | nixfmt/nixfmt-tree, statix, deadnix, nix-linter, `nix-instantiate --parse`, `nix flake check` (eval only), `lib.evalModules`, option-set diffs, grep-based security checks, `nix why-depends` reachability, `clan vars check`, `clan machines list`, import-cycle detection, `nix store verify` | **Yes** — same lock file ⇒ same result |
| **Deterministic modulo pinned baseline** | `eval_ratio`, `closure_ratio`, `nix-diff`/`nix store diff-closures` change counts | Yes if baseline + toolchain pinned |
| **Environment-dependent** | absolute eval wall time, absolute build time, `NIX_SHOW_STATS` CPU/thunk counts, absolute closure bytes, `nix-fast-build` per-attr times, `vulnix` NVD data (network, date-varying) | **No** — score only ratios/signs, weight low |
| **Heuristic / non-tool** | `mkIf`/`mkMerge` misuse, layering violations, "module never imported", duplication detection | Deterministic rule, but rule is heuristic → require human confirmation |

---

## 8. Coverage gaps

- **No `nix store du`** — the brief's command does not exist; substitute `nix path-info -Sh`
  / `du -sh /nix/store` / `nix-du`.
- **No deterministic NixOS-module linter** equivalent to nixpkgs-hammering; module-level
  architecture checks are grep + `lib.evalModules`, not a mature linter.
- **`vulnix` is unmaintained**; the Nixpkgs security tracker is the community replacement
  but has no stable machine API for a pinned revision.
- **nix-linter is abandoned**; statix is the successor but covers only AST-local lints.
- **`nix flake check` does not check NixOS module *quality*** — it evaluates, it does not
  judge `mkIf` misuse or layering.
- **Clan CLI output stability** is not guaranteed across releases; pin the `clan-cli`
  version used for scoring and treat text parsing as version-fragile.
- **`sops/` and `vars/`** contents were out of scope by instruction; secret *handling
  patterns* are scored, secret payloads are not read.

---

## 9. Sources

1. Nixfmt (RFC 166): <https://github.com/NixOS/nixfmt>
2. RFC 166: <https://github.com/NixOS/rfcs/pull/166>
3. Standard Nix format: <https://github.com/NixOS/nixfmt/blob/master/standard.md>
4. RFC 101 (closed) / nixpkgs-fmt deprecation: <https://github.com/NixOS/rfcs/pull/101>
5. nixpkgs-fmt: <https://github.com/nix-community/nixpkgs-fmt>
6. alejandra: <https://github.com/kamadorueda/alejandra>
7. statix: <https://github.com/oppiliappan/statix>
8. deadnix: <https://github.com/astro/deadnix>
9. nix-linter (abandoned): <https://github.com/Synthetica9/nix-linter>
10. nil: <https://github.com/oxalica/nil>
11. nixd: <https://github.com/nix-community/nixd>
12. nixd configuration: <https://github.com/nix-community/nixd/blob/main/nixd/docs/configuration.md>
13. treefmt: <https://github.com/numtide/treefmt>
14. treefmt-nix: <https://github.com/numtide/treefmt-nix>
15. git-hooks.nix: <https://github.com/cachix/git-hooks.nix>
16. nixpkgs-hammering: <https://github.com/Mic92/nixpkgs-hammering>
17. `nix flake check`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake-check>
18. `nix eval`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-eval>
19. `nix-instantiate`: <https://nix.dev/manual/nix/latest/command-ref/nix-instantiate>
20. `nix build`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-build>
21. `nix path-info`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-path-info>
22. `nix store diff-closures`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-store-diff-closures>
23. `nix store verify`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-store-verify>
24. `nix why-depends`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-why-depends>
25. `nix flake archive`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake-archive>
26. `nix store gc`: <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-store-gc>
27. Nix conf-file (`pure-eval`, `allow-import-from-derivation`, `max-jobs`, `cores`): <https://nix.dev/manual/nix/latest/command-ref/conf-file>
28. Import From Derivation: <https://nix.dev/manual/nix/latest/language/import-from-derivation>
29. `lib.evalModules` (nixpkgs manual): <https://nixos.org/manual/nixpkgs/unstable/#module-system-lib-evalModules>
30. Module system deep dive: <https://nix.dev/tutorials/module-system/deep-dive.html>
31. `lib/modules.nix`: <https://github.com/NixOS/nixpkgs/blob/master/lib/modules.nix>
32. vulnix: <https://github.com/nix-community/vulnix>
33. Nixpkgs security tracker: <https://tracker.security.nixos.org/>
34. NixOS security team: <https://nixos.org/community/teams/security/>
35. sops-nix: <https://github.com/Mic92/sops-nix>
36. agenix: <https://github.com/ryantm/agenix>
37. Secrets comparison (NixOS wiki): <https://wiki.nixos.org/wiki/Comparison_of_secret_managing_schemes>
38. nix-tree: <https://github.com/utdemir/nix-tree>
39. nix-diff: <https://github.com/Gabriella439/nix-diff>
40. nix-fast-build: <https://github.com/Mic92/nix-fast-build>
41. nix-du: <https://github.com/symphorien/nix-du>
42. flake-parts: <https://flake.parts/> · <https://github.com/hercules-ci/flake-parts>
43. NixOS manual: <https://nixos.org/manual/nixos/unstable/>
44. Clan CLI overview: <https://clan.lol/docs/26.05/reference/cli>
45. Clan machines: <https://clan.lol/docs/26.05/reference/cli/machines>
46. Clan vars: <https://clan.lol/docs/26.05/reference/cli/vars>
47. Clan secrets: <https://clan.lol/docs/26.05/reference/cli/secrets>
48. Clan flake-parts guide: <https://clan.lol/docs/26.05/guides/flake-parts>
49. Clan autoincludes: <https://docs.clan.lol/latest/guides/inventory/autoincludes/>
50. NixOS Wiki — Flakes: <https://wiki.nixos.org/wiki/Flakes>
51. nix.dev best practices: <https://nix.dev/guides/best-practices>
