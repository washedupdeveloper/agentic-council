# Nix / NixOS / Clan Code-Review Rubrics — Knowledge Base

**Purpose.** This is the domain knowledge base behind five specialist review agents
(Security, Performance, Readability/Maintainability, Correctness/Testing,
Architecture/Design) that review a **Clan-based NixOS infrastructure flake**.
Every checklist item is written to be *checkable*: a concrete anti-pattern, why it
is bad, how to detect it (file shape / grep / tool), and the idiomatic fix with a
Nix example. It is Nix-specific — no generic "write clean code" filler.

**Reference corpus.** The rubrics were derived from a Clan-based infrastructure
flake (`flake-parts` + `clan-core` +
`home-manager` + `nixos-wsl` + `nix-topology` + `devshell` + `git-hooks`).
A newer sibling (`example-infra-clan`) uses `treefmt-nix` + `nixfmt` + `statix` +
`deadnix` + `nixd` and real `clan.service` modules; it is used as the
"destination state" reference where the two diverge.

**Ground rule for reviewers:** never read or quote the *payload* of anything under
`sops/` or `vars/`. Review the *structure, ownership, mode, and whether plaintext
keys are committed* — not the secret values.

---

## 0. Scoring model (applies to all five categories)

Each category is scored **0–100** with anchored bands. A reviewer must land on an
anchor band, then adjust within the band using the checklist. The 1–5 mapping is
provided for callers that want a coarser scale.

| Band | Score | 1–5 | Meaning |
|---|---|---|---|
| Exemplary | 90–100 | 5 | No material findings; idiomatic, hardened, documented. |
| Solid | 75–89 | 4 | Minor nits only; no security/correctness exposure. |
| Adequate | 60–74 | 3 | Real gaps that should be fixed but are not blocking. |
| Weak | 40–59 | 2 | Multiple material defects; some are security or correctness relevant. |
| Poor | 20–39 | 1 | Systemic problems; the category's guarantees are not met. |
| Critical | 0–19 | 1 | Actively harmful (e.g. plaintext secret committed, firewall off). |

**Severity tags** used in the checklists: `CRITICAL` (secret exposure / root
compromise), `HIGH` (exploitable or breaks rebuilds), `MEDIUM` (hygiene, cost,
maintainability), `LOW` (style).

**Finding format for the agents:**
`<ID> [SEVERITY] <file:line> — <anti-pattern>. Why: <impact>. Fix: <snippet>.`

---

## 1. The shape these rubrics assume

The checks below are anchored to the shape of a `flake-parts` + `clan-core` +
`home-manager` infrastructure flake. Repository names differ; the *structure* is
what the checks refer to, so map your own tree onto it. Where your tree diverges,
the checklist still applies — only the paths change.

- `flake.nix`: `flake-parts.lib.mkFlake`; imports `clan-core.flakeModules.default`,
  `home-manager.flakeModules.home-manager`, `nix-topology.flakeModule`, plus a
  recursive auto-import of `./modules/flake`. `formatter = pkgs.nixfmt-tree`.
  Inputs: `nixpkgs` (nixos-unstable), `flake-parts`, `clan-core`, `home-manager`,
  `nix-topology`, `nixos-wsl`, `devshell`, `git-hooks`, `zed`.
- `clan.nix`: `meta`, the declared machines, `inventory.machines`, and
  `inventory.instances` for what every host runs (`sshd`, `user-root`, a per-user
  instance, `hm`, `base-system`, `wsl`). Shared modules are wired either through the
  generic `importer` service or through typed `clan.service` modules; the typed form
  is the destination state and the two are the most common divergence in this shape.
- `modules/nixos/baseSystem.nix`: the sudo and wheel policy, `nix.settings.trusted-users`,
  `accept-flake-config`, `experimental-features`, the binary caches, and
  `services.openssh` hardening. The security rubric reads this module first, because
  a mistake here is a host-wide one.
- `machines/<host>/configuration.nix`: the per-host firewall ports, GC policy,
  `nix-ld`, and per-host `trusted-users`.
- `modules/nixos/wsl.nix`: the drvfs bind of a Windows path into the guest with a
  restrictive `umask`, plus interop registration.
- `modules/home/default.nix`: `useGlobalPkgs`, `useUserPackages`, recursive
  auto-import of `modules/home/`, and `home.stateVersion` following
  `config.system.stateVersion`.
- `lib/`: the recursive-import helper, often written with pipe operators.
- `sops/` and `vars/`: per-machine keys and per-user secrets. **Read names, modes and
  ownership only — never the payload.** The rubric checks whether a plaintext key is
  committed, not what the key contains.
- CI, `checks`, VM tests and `assertions` are frequently **absent** in this shape,
  which is precisely what the Correctness rubric looks for.

---

## 2. Category 1 — Security

### 2.1 What "good" means
Secrets exist only as encrypted blobs in VCS and as `0400`/`0440` root-or-service-owned
files under `/run`; no secret value ever reaches the world-readable Nix store or an
environment variable; the host is deny-by-default on the network; SSH is key-only,
root login is constrained; privilege escalation is deliberate and audited; the Nix
daemon trust boundary is understood; every input is content-addressed and pinned;
and there is a documented update/CVE path.

### 2.2 Anchored rubric

| Band | Anchor |
|---|---|
| 90–100 | Secrets exclusively via one declarative store (sops-nix or clan vars) with explicit owner/mode; no plaintext key material committed; firewall on and ports justified per-service; SSH key-only + `PermitRootLogin="no"` (or explicitly justified); `trusted-users` minimal; `accept-flake-config=false`; sandbox on; no impure fetches; inputs pinned; gitleaks in pre-commit; security invariants asserted. |
| 75–89 | All of the above but 1–2 medium gaps (e.g. no `PermitRootLogin`, one broad port, `trusted-users` includes a group without comment). |
| 60–74 | Works and no secret is leaked, but several medium gaps: blanket `allowUnfree`, `accept-flake-config=true`, dev tools/mounts widen exposure, no CVE/update story, no assertions. |
| 40–59 | Multiple HIGH findings: passwordless sudo *and* root-key SSH *and* a broad mount/port; or an ambiguous secret backend mixing sops + clan vars without ownership rules. |
| 20–39 | A plaintext private key or password is committed, or `PasswordAuthentication`/firewall disabled, or `sandbox = false` with `trusted-users` broad. |
| 0–19 | Plaintext secret in the store, root-equivalent access granted to unprivileged users, or a known-vulnerable unpinned input on a security path. |

### 2.3 Checklist

**SEC-01 `CRITICAL` — Secret value read into the Nix store via `builtins.readFile`/string interpolation.**
- *Why:* everything in `/nix/store` is world-readable; a secret interpolated into a
  derivation is leaked to every user and to any binary cache. Both sops-nix and agenix
  exist precisely to avoid this ([agenix README](https://github.com/ryantm/agenix);
  [sops-nix README](https://github.com/Mic92/sops-nix)).
- *Detect:* `rg 'builtins\.readFile|readFile .*secret|"\$\{.*secret' --glob '*.nix'`;
  grep for `password`, `token`, `key` near `''`-interpolation; review `environment.etc`
  and `systemd.services.*.serviceConfig` for literal secrets.
- *Fix:* declare the secret and reference its runtime `.path`:
  ```nix
  sops.secrets."api/token" = { owner = "myservice"; mode = "0400"; };
  systemd.services.myservice.serviceConfig.EnvironmentFile =
    config.sops.secrets."api/token".path;
  ```
  For non-root/dynamic users prefer systemd `LoadCredential` rather than widening the
  secret's owner ([sops-nix README](https://github.com/Mic92/sops-nix)).

**SEC-02 `CRITICAL` — Plaintext age/SSH private key committed to the repo.**
- *Why:* `sops/machines/<host>/key.json` and `sops/users/<u>/key.json` are the
  **decryption identities** for clan vars; if they hold an unencrypted age identity
  and are tracked by git, every secret they protect is compromised.
- *Detect:* `git ls-files sops vars | grep -E 'key\.json|/secret$'`; check whether the
  file parses as a cleartext age key (`AGE-SECRET-KEY-1…`) — **without printing it**;
  check `.gitignore` for `sops/machines/*/key.json`, `vars/**/secret`.
- *Fix:* gitignore the identities, or (clan-idiomatic) keep only the *public* half in
  the repo and the identity on the host at the path clan expects; rotate any key that
  was ever committed.
  ```gitignore
  sops/machines/*/key.json
  vars/**/secret
  vars/**/*-hash/secret
  ```

**SEC-03 `HIGH` — Secrets without explicit owner/mode (defaults to `root:root` but mode/consumer unset).**
- *Why:* sops-nix defaults secrets to `root:root`; the `keys` group can read
  `/run/secrets.d`. A service running as a non-root user cannot read its own secret,
  which pushes authors to `chmod 0644` or world-readable workarounds.
- *Detect:* `rg 'sops\.secrets' -A5 | rg -v 'owner|mode'`; for clan vars inspect the
  generator `files.<name>.mode`/`owner` ([clan vars reference](https://clan.lol/docs/26.05/reference/clan.core/vars)).
- *Fix:*
  ```nix
  sops.secrets."db/pass" = { owner = "postgres"; group = "postgres"; mode = "0400"; };
  ```
  clan vars default `mode = "0400"` and `neededFor = "services"`; only use
  `neededFor = "users"` for `hashedPasswordFile`, and note owner/group must then be root.

**SEC-04 `HIGH` — Secret exported as a world-readable environment variable.**
- *Why:* `/proc/<pid>/environ` and systemd unit dumps leak env vars; `Environment=`
  with a secret is visible to anything that can read the unit.
- *Detect:* `rg 'Environment\s*=\s*\[?"?.*(TOKEN|PASSWORD|SECRET|KEY)' -i`.
- *Fix:* use `EnvironmentFile = config.sops.secrets.x.path` (file mode 0400) or
  `LoadCredential`, not inline `Environment`.

**SEC-05 `HIGH` — `users.mutableUsers` / `initialPassword` misuse.**
- *Why:* `initialPassword` writes a plaintext password into the store and only applies
  on first creation; with `mutableUsers = true` a `passwd` change survives rebuilds and
  drifts from config.
- *Detect:* `rg 'initialPassword|initialHashedPassword|mutableUsers'`.
- *Fix:* `users.mutableUsers = false;` and a hashed, runtime-decrypted password:
  ```nix
  users.users.alice.hashedPasswordFile =
    config.sops.secrets."user-password".path;  # neededForUsers = true on the secret
  ```
  Clan's `users` service generates `user-password`/`user-password-hash` vars for exactly
  this ([clan users service](https://clan.lol/docs/26.05/services/official/users)).

**SEC-06 `HIGH` — Passwordless sudo or wheel group is unbounded.**
- *Why:* `security.sudo.wheelNeedsPassword = false` means a stolen SSH key is instant
  root. `execWheelOnly = false` (default) lets non-wheel users invoke the sudo binary,
  widening the CVE surface (CVE-2021-3156 class).
  ([nixpkgs sudo module](https://github.com/NixOS/nixpkgs/blob/master/nixos/modules/security/sudo.nix),
  [execWheelOnly](https://mynixos.com/nixpkgs/option/security.sudo.execWheelOnly)).
- *Detect:* `rg 'wheelNeedsPassword|execWheelOnly|NOPASSWD|security\.sudo'`.
- *Fix:* keep `execWheelOnly = true` (already set here); for `wheelNeedsPassword`, if it
  is `false` demand a compensating control (hardware key / no remote wheel) in a comment,
  otherwise set `true`. Note `trusted-users`/`@wheel` is *also* root-equivalent (SEC-09).

**SEC-07 `HIGH` — SSH not fully hardened / authorized keys unmanaged.**
- *Why:* password auth is the #1 brute-force vector; `PermitRootLogin` unset defaults to
  `prohibit-password` (key-only root), which still permits direct root. Hardcoded
  `openssh.authorizedKeys.keys` in machine configs bypasses Clan's key management.
  ([NixOS wiki SSH](https://wiki.nixos.org/wiki/SSH)).
- *Detect:* `rg 'services\.openssh|PermitRootLogin|PasswordAuthentication|authorizedKeys'`.
- *Fix:*
  ```nix
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "no";          # or "prohibit-password" if deploy needs root
      AllowUsers = [ "alice" ];
      X11Forwarding = false;
    };
  };
  ```
  Manage keys through Clan's `sshd` inventory service (host keys + authorizedKeys),
  not ad-hoc `authorizedKeys.keys` ([clan sshd service](https://clan.lol/docs/26.05/services/official/sshd)).
  If Clan deploy uses `deploy.targetHost = "root@…"`, either justify `PermitRootLogin`
  or switch the deploy user to a key-only admin.

**SEC-08 `HIGH` — Firewall opened too broadly or disabled; service bound to `0.0.0.0`.**
- *Why:* NixOS's firewall is on by default and denies inbound; every added port is an
  attack surface. A service listening on `0.0.0.0` is reachable the moment the port is
  open, even on a laptop/WSL.
  ([NixOS wiki Firewall](https://wiki.nixos.org/wiki/Firewall)).
- *Detect:* `rg 'networking\.firewall|allowedTCPPorts|allowedUDPPorts|openFirewall|listenAddress|0\.0\.0\.0'`;
  runtime `ss -tlnp` / `nft list ruleset`.
- *Fix:* prefer per-service `openFirewall` next to the service definition; scope holes
  per interface (`networking.firewall.interfaces."tailscale0".allowedTCPPorts`); bind
  services to `127.0.0.1` or a VPN interface unless genuinely public.

**SEC-09 `CRITICAL` — `nix.settings.trusted-users` grants root-equivalent power.**
- *Why:* a trusted user can set arbitrary `nix.conf` options, add substituters, and
  build as root — the NixOS wiki states it is *equivalent to having root access*
  ([nixos-rebuild wiki](https://wiki.nixos.org/wiki/Nixos-rebuild)).
- *Detect:* `rg 'trusted-users'`.
- *Fix:* keep it to `[ "root" ]` unless a specific user must `nixos-rebuild`; if `@wheel`
  is required, document that wheel is already root. Never add a plain unprivileged user.

**SEC-10 `MEDIUM` — `accept-flake-config = true`.**
- *Why:* a flake's `nixConfig` can then silently set substituters, `extra-substituters`,
  or sandbox settings — a supply-chain vector for any flake you evaluate.
- *Detect:* `rg 'accept-flake-config'`.
- *Fix:* set `false`; if a cache is needed, add it explicitly to `substituters` +
  `trusted-public-keys`.

**SEC-11 `HIGH` — Weakened sandbox / IFD / risky experimental features.**
- *Why:* `sandbox = false`, `allow-import-from-derivation = true` in untrusted contexts,
  or `impure-derivations`/`configurable-impure-env` broaden what a build can reach
  ([nix.conf](https://nix.dev/manual/nix/2.24/command-ref/conf-file)).
- *Detect:* `rg 'sandbox|allow-import-from-derivation|experimental-features'`.
- *Fix:* keep `sandbox = true` (default); only enable `pipe-operators`/`nix-command`/
  `flakes` deliberately (this repo needs `pipe-operators` for `lib/default.nix`).

**SEC-12 `HIGH` — Impure fetches without a hash.**
- *Why:* `builtins.fetchTarball`/`fetchurl` without `sha256` are mutable and a build-time
  MITM vector; `builtins.fetchGit` without a rev is non-reproducible. nixpkgs bans
  builtin fetchers for this reason ([IFD / blocking eval](https://jade.fyi/blog/nix-evaluation-blocking)).
- *Detect:* `rg 'builtins\.fetch(Tarball|url|Git|Tree)|fetchTarball|fetchurl'`;
  `rg -- '--impure'`.
- *Fix:* use `pkgs.fetchFromGitHub`/`fetchurl` with a real `hash`, or a flake input.
  Never rely on `--impure` for a normal build.

**SEC-13 `MEDIUM` — Blanket `nixpkgs.config.allowUnfree = true`.**
- *Why:* pulls untested, uncached, sometimes license-encumbered software into the whole
  closure; hides *which* unfree package was needed.
  ([Unfree software wiki](https://wiki.nixos.org/wiki/FAQ/unfree),
  [nixpkgs config](https://ryantm.github.io/nixpkgs/using/configuration/)).
- *Detect:* `rg 'allowUnfree'`.
- *Fix:*
  ```nix
  nixpkgs.config.allowUnfreePredicate = pkg:
    builtins.elem (lib.getName pkg) [ "vscode" "rocmPackages" ];
  ```

**SEC-14 `MEDIUM` — Security-relevant inputs track a moving branch.**
- *Why:* `nixos-wsl.url = "…/main"` and `clan-core` at `refs/heads/main` are pinned in
  `flake.lock`, but `nix flake update` then silently jumps the security baseline; release
  pinning gives a reviewable upgrade.
- *Detect:* `rg 'url = ".*(main|master|nixos-unstable)' flake.nix`.
- *Fix:* pin to a tag/release or to `clan-core/nixpkgs` for the whole closure
  ([clan nixpkgs flake input](https://clan.lol/docs/25.11/guides/nixpkgs-flake-input)).

**SEC-15 `MEDIUM` — No kernel/sysctl hardening.**
- *Why:* defaults leave `kptr_restrict`, `dmesg_restrict`, `unprivileged_userns_clone`,
  and `kernel.unprivileged_bpf_disabled` permissive.
- *Detect:* `rg 'boot\.kernel\.sysctl|kernel\.sysctl'` → empty.
- *Fix:*
  ```nix
  boot.kernel.sysctl = {
    "kernel.kptr_restrict" = 2;
    "kernel.dmesg_restrict" = 1;
    "kernel.unprivileged_bpf_disabled" = 1;
    "net.core.bpf_jit_harden" = 2;
  };
  ```

**SEC-16 `MEDIUM` — Service exposure beyond what the role needs.**
- *Why:* `services.locate.enable = true` (plocate) indexes the whole FS into a DB any
  user can query; `usbip.enable = true` in WSL attaches USB devices.
- *Detect:* `rg 'locate|usbip|interop|startMenuLaunchers'`.
- *Fix:* enable only on roles that need them; gate with `lib.mkIf config.<role>`.

**SEC-17 `HIGH` — WSL-specific exposure (drvfs mount of the Windows home / `.ssh`).**
- *Why:* binding `C:\Users\<user>\.ssh` into WSL means Windows-side private keys become
  readable inside the Linux guest, and the mount persists regardless of Linux file
  permissions. `interop.register = true` + `startMenuLaunchers` widen the Windows↔Linux
  boundary.
- *Detect:* inspect `modules/nixos/wsl.nix` for `fileSystems."/home/…/.ssh"` and drvfs
  options; `rg 'drvfs|C:\\\\Users|interop'`.
- *Fix:* prefer a WSL-local `~/.ssh` with keys copied once; if the bind is required,
  keep `umask=0077`, `uid`/`gid` correct, and document the trust crossing. Never bind a
  Windows path that holds unencrypted long-lived keys without noting the risk.

**SEC-18 `MEDIUM` — No update / CVE posture.**
- *Why:* a homelab still needs a patch path; `nixVersions.latest` can outrun what the
  flake was tested against, and there is no `system.autoUpgrade` or documented cadence.
- *Detect:* `rg 'autoUpgrade|nixVersions|nix.package'`; check for a README/ADR upgrade section.
- *Fix:* either `system.autoUpgrade` on a schedule, or a documented `nix flake update`
  cadence; prefer the distro default `nix.package` unless a newer Nix is required.

**SEC-19 `MEDIUM` — Ambiguous/mixed secret backends.**
- *Why:* the repo has **both** `sops/` and clan `vars/`. Mixing is legal (clan vars can
  use sops-nix as the store) but must be deliberate: some secrets in `sops/`, others
  generated by vars, with no clear ownership, invites drift and orphaned ciphertext.
- *Detect:* `find sops vars -maxdepth 3 -type d`; cross-check each `vars/per-machine/*`
  tree against an enabled `inventory.instances` entry.
- *Fix:* document the split ("vars own generated material: ssh host keys, user
  passwords, state-version; sops owns hand-managed secrets") and delete orphans.
  The sibling ADR flags exactly this (`user-password-root/`, `mycelium/` staleness).

**SEC-20 `MEDIUM` — No secret scanning in pre-commit.**
- *Why:* a single `git add` of a plaintext key is the most common NixOS secret incident.
- *Detect:* `rg 'gitleaks|detect-secrets|trufflehog' modules/**/git-hooks.nix`.
- *Fix:* the repo already wires `gitleaks` with `--staged`; ensure it is actually active
  (flake imports the module) and add `.gitignore` entries for key files.

**SEC-21 `LOW` — SSH CA not enforced (`trustedUserCAKeys`).**
- *Why:* the repo generates an `openssh-ca` var but if `TrustedUserCAKeys` is not set,
  the CA is unused; if it *is* set, revocation is centralized.
- *Detect:* `rg 'TrustedUserCAKeys|openssh-ca|hostCertificate'`.
- *Fix:* either wire the CA into `services.openssh.settings.TrustedUserCAKeys` or drop
  the unused CA var.

**SEC-22 `MEDIUM` — Security invariants are not asserted.**
- *Why:* a future edit can silently re-enable password auth or open a port.
- *Detect:* `rg 'assertions ='` → none in `baseSystem.nix`.
- *Fix:*
  ```nix
  assertions = [{
    assertion = config.services.openssh.settings.PasswordAuthentication == false;
    message = "PasswordAuthentication must stay false on every host";
  }];
  ```

---

## 3. Category 2 — Performance

### 3.1 What "good" means
Evaluation is pure and IFD-free; `nix flake check` and `nixos-rebuild build` are fast
because there are no overlays forcing mass rebuilds and inputs share one `nixpkgs`;
the system closure excludes dev tooling; binary caches are configured with their keys;
GC is scheduled; and WSL-specific costs (store growth, `nix-ld`) are accounted for.

### 3.2 Anchored rubric

| Band | Anchor |
|---|---|
| 90–100 | No IFD; one nixpkgs via `follows`; no dev tools in system closure; caches configured; GC scheduled with `min-free`; `nix path-info -Sh` shows a lean closure; home-manager uses global pkgs; `stateVersion` correct. |
| 75–89 | One medium issue (e.g. dev tools in `systemPackages`, GC disabled, or a single overlay with a small rebuild blast radius). |
| 60–74 | Several medium issues: dev tools in system closure, no cache strategy for the flake's own outputs, GC off, IFD in one module. |
| 40–59 | Overlay/nixpkgs duplication causing whole-closure rebuilds, or IFD in a hot path, or a closure bloated with build tooling. |
| 20–39 | Pervasive IFD, multiple nixpkgs copies, no caches, store unbounded. |
| 0–19 | Evaluation cannot complete without network/IFD, or rebuilds recompile the world on every change. |

### 3.3 Checklist

**PERF-01 `HIGH` — Import From Derivation (IFD).**
- *Why:* IFD pauses evaluation to realise a derivation; the evaluator is sequential, so
  multiple IFD sites serialise and are "much slower than otherwise"
  ([Nix manual IFD](https://nix.dev/manual/nix/latest/language/import-from-derivation)).
- *Detect:* `rg 'readFile|readDir|pathExists|import ' --glob '*.nix'` where the argument
  is a **derivation** (`''${pkgs.runCommand …}`), not a source path; run
  `nix flake check --no-build` and watch for serial "building …" during eval.
- *Fix:* precompute/generate Nix files and commit them, or move the computation into a
  fixed-output derivation. (The repo's `lib/default.nix` uses `builtins.readDir` on the
  *source* tree — that is **not** IFD and is fine.)

**PERF-02 `HIGH` — Dev tools in `environment.systemPackages`.**
- *Why:* `nixd`, `deadnix`, `statix`, `nixfmt(-tree)`, `nix-output-monitor`, `direnv`
  in `baseSystem.nix` bloat every machine's closure and its GC footprint; they belong in
  the devShell or user profile.
- *Detect:* `rg -n 'systemPackages' -A15 modules/nixos/baseSystem.nix`;
  `nix path-info -rsSh /run/current-system | sort -nk2 | tail`.
- *Fix:* move them to `modules/flake/devshells.nix` (already duplicated there!) or
  `home.packages`.
  ```nix
  # devshell, not system
  devshells.default.packages = with pkgs; [ nixd deadnix statix nixfmt nixfmt-tree nom ];
  ```

**PERF-03 `MEDIUM` — Closure bloat not measured.**
- *Why:* you cannot review performance you have not measured.
- *Detect:* `nix path-info -Sh /run/current-system`; `nix path-info -rsSh <pkg>`;
  `nix store gc --dry-run` for reclaimable space
  ([nix path-info manual](https://nix.dev/manual/nix/2.13/command-ref/new-cli/nix3-path-info)).
- *Fix:* set a budget (e.g. system closure < 3 GiB) and treat additions above it as
  review findings.

**PERF-04 `HIGH` — Overlays / `nixpkgs` changes force whole-closure rebuilds.**
- *Why:* an overlay that touches a low-level package (glibc, openssl, stdenv) rebuilds
  everything downstream; adding a second `nixpkgs` because `follows` is missing
  duplicates the whole package set in the store and doubles download size.
- *Detect:* `rg 'overlays'`; `nix flake metadata` and `rg '"nixpkgs(_[0-9]+)?"' flake.lock`
  — multiple `nixpkgs*` nodes mean missing `follows`.
- *Fix:* make every input follow the flake's nixpkgs (`inputs.X.inputs.nixpkgs.follows = "nixpkgs"`),
  and keep overlays additive and high in the dependency graph.

**PERF-05 `MEDIUM` — No/incorrect binary cache configuration.**
- *Why:* without `substituters` + `trusted-public-keys`, every build compiles from source.
- *Detect:* `rg 'substituters|trusted-public-keys'`.
- *Fix:* the repo lists four caches with keys — good. Additionally, publish the flake's
  own CI outputs to a Cachix (e.g. `example-infra.cachix.org`) so a host need not rebuild.

**PERF-06 `MEDIUM` — `auto-optimise-store` vs scheduled `nix.optimise`.**
- *Why:* `auto-optimise-store = true` optimises on every build (CPU cost, latency);
  `nix.optimise.automatic = true` hardlinks on a schedule instead.
- *Detect:* `rg 'auto-optimise-store|nix.optimise'`.
- *Fix:* pick one; for a host `auto-optimise-store = true` is acceptable, for a
  fleet prefer scheduled optimisation.

**PERF-07 `MEDIUM` — GC not scheduled / no free-space guard.**
- *Why:* generations are GC roots; unbounded growth fills the disk. The repo sets
  `nix.gc.automatic = false` in the machine config (overriding `baseSystem`'s
  `mkDefault true`) and relies on `nh clean --keep-since 7d`.
  ([GC wiki](https://wiki.nixos.org/wiki/Garbage_Collection)).
- *Detect:* `rg 'nix\.gc|keep-since|min-free|max-free'`.
- *Fix:* enable scheduled GC and add a floor:
  ```nix
  nix.gc = { automatic = true; dates = "weekly"; options = "--delete-older-than 14d"; };
  nix.settings.min-free = 5 * 1024 * 1024 * 1024;
  nix.settings.max-free = 20 * 1024 * 1024 * 1024;
  ```

**PERF-08 `MEDIUM` — `system.stateVersion` wrong / churned.**
- *Why:* `stateVersion` selects compatibility defaults (e.g. database versions). Setting
  it to the *current* release on upgrade can trigger migrations; changing it repeatedly
  is worse. It does **not** control which nixpkgs you use
  ([system.stateVersion](https://mynixos.com/nixpkgs/option/system.stateVersion),
  [FAQ](https://nixos.wiki/wiki/FAQ)).
- *Detect:* `rg 'stateVersion'`; cross-check against `vars/per-machine/*/state-version`.
- *Fix:* set it once to the install release and never bump it; remove the duplicate
  clan `state-version` var if it conflicts with `system.stateVersion`.

**PERF-09 `MEDIUM` — Home-manager not using global pkgs.**
- *Why:* `useGlobalPkgs = false` builds a second nixpkgs evaluation per user, doubling
  eval and duplicating store paths.
- *Detect:* `rg 'useGlobalPkgs|useUserPackages'`.
- *Fix:* the repo already sets both `true` — keep it.

**PERF-10 `MEDIUM` — Expensive `lib` recursion on a hot path.**
- *Why:* `lib.collect`/recursive `readDir` over large trees at eval time is slow; the
  auto-import helpers in `lib/default.nix` walk `modules/flake`.
- *Detect:* `rg 'lib\.collect|readDir|listFilesRecursive|filterAttrs'`.
- *Fix:* keep auto-import trees small and flat; avoid walking `vars/`/`sops/`.

**PERF-11 `LOW` — No build UX tooling.**
- *Why:* `nix-output-monitor` / `nix-fast-build` / `nh` make builds legible and cache-aware.
- *Detect:* `rg 'nix-output-monitor|nix-fast-build|programs.nh'`.
- *Fix:* keep `nh` (already present) and `nom` in the devShell.

**PERF-12 `LOW` — `systems` breadth.**
- *Why:* every added system multiplies `perSystem` evaluation and check builds.
- *Detect:* `rg 'systems = ' flake.nix`.
- *Fix:* add `aarch64-linux` only when a Pi actually lands (as the ADR plans).

**PERF-13 `LOW` — `pipe-operators` experimental feature required to evaluate.**
- *Why:* `lib/default.nix` uses `|>`; on a host without the feature, `nix flake check`
  fails before it can build — a portability/perf-of-onboarding issue.
- *Detect:* `rg '\|>' --glob '*.nix'`; `rg 'pipe-operators'`.
- *Fix:* keep `pipe-operators` in both `nix.settings.experimental-features` and the
  devShell `NIX_CONFIG` (already done), or rewrite with `lib.pipe` which needs no feature.

**PERF-14 `LOW` — Network/build buffer tuning without rationale.**
- *Why:* `download-buffer-size = 524288000` (500 MB) is a deliberate tradeoff; uncommented
  magic numbers are maintainability debt.
- *Detect:* `rg 'download-buffer-size|connect-timeout|http-connections'`.
- *Fix:* comment the rationale or drop to default.

**PERF-15 `MEDIUM` — WSL store growth / `nix-ld` cost.**
- *Why:* WSL disk images grow and do not shrink automatically; `programs.nix-ld.enable`
  adds a wrapper for dynamically-linked binaries.
- *Detect:* inspect `modules/nixos/wsl.nix` + machine config for GC; `du -sh /nix`.
- *Fix:* schedule GC inside WSL and periodically compact the VHDX; keep `nix-ld` (needed
  for interoperability) but be aware of its closure cost.

**PERF-16 `MEDIUM` — Duplicate `nixpkgs` inputs.**
- *Why:* each extra `nixpkgs` node in `flake.lock` is a full second copy of the package
  set in the store. The repo mostly uses `follows` — verify `nixos-wsl`, `devshell`,
  `git-hooks`, `zed` also follow (they currently do not declare `follows`).
- *Detect:* `rg -c '"nixpkgs' flake.lock` and inspect nodes.
- *Fix:* add `inputs.nixpkgs.follows = "nixpkgs"` to inputs that can share it.

**PERF-17 `LOW` — Building docs/manpages.**
- *Why:* `documentation.enable = false` (already set) avoids building `nixos-help`/man pages.
- *Detect:* `rg 'documentation'`.
- *Fix:* keep disabled on non-desktop hosts.

**PERF-18 `LOW` — Check/pre-commit cost.**
- *Why:* `pre-commit.check.enable = true` runs hooks inside `nix flake check`; a slow
  hook (e.g. `nil` on a large tree) slows CI.
- *Detect:* `rg 'pre-commit' modules/flake/git-hooks.nix`.
- *Fix:* keep hook set lean; the sibling enables `nixfmt` via treefmt instead of a
  separate formatter hook.

---

## 4. Category 3 — Readability / Maintainability

### 4.1 What "good" means
One formatter (RFC 166 `nixfmt`) enforced by CI/pre-commit; no dead bindings; no
statix anti-patterns; modules are one-concern-per-file with a clear name; `lib.mkIf`/
`lib.mkMerge` are used for readability, not cleverness; options are namespaced and
documented; and machines/modules have a short README or ADR.

### 4.2 Anchored rubric

| Band | Anchor |
|---|---|
| 90–100 | Single RFC-166 formatter enforced; `statix`/`deadnix` clean and wired into pre-commit + CI; one concern per file; documented options; no `with`; no dead code. |
| 75–89 | Clean but a few nits (occasional `with`, a stale comment, a missing module docstring). |
| 60–74 | Inconsistent formatting or an unenforced formatter; several statix/deadnix findings; some grab-bag modules. |
| 40–59 | Two competing formatters, dead code in tree, deeply nested attrsets, `with` everywhere, no docs. |
| 20–39 | No formatter, deadnix/statix fail, modules are unmaintainable. |
| 0–19 | Files that do not parse or cannot be reviewed. |

### 4.3 Checklist

**READ-01 `MEDIUM` — Formatter not the standard one, or multiple formatters.**
- *Why:* RFC 166 establishes `nixfmt` as the official formatter; mixing
  `nixpkgs-fmt`/`alejandra`/`nixfmt` produces churn and review noise
  ([RFC 166](https://github.com/NixOS/rfcs/blob/master/rfcs/0166-nix-formatting.md),
  [nixfmt standard](https://github.com/NixOS/nixfmt/blob/master/standard.md)).
- *Detect:* `rg 'nixpkgs-fmt|alejandra|nixfmt-rfc-style|nixfmt-classic|nixfmt-tree'`.
- *Fix:* pick `pkgs.nixfmt-tree` (already the flake `formatter`) and enforce it.

**READ-02 `LOW` — `nixfmt-tree` vs `treefmt-nix` inconsistency across the family.**
- *Why:* the root repo uses `formatter = pkgs.nixfmt-tree` and a `nixfmt-rfc-style`
  pre-commit hook; the sibling uses `treefmt-nix`. Divergent tooling across the family
  makes "run the formatter" mean different things.
- *Detect:* compare `flake.nix` `formatter` + `modules/flake/git-hooks.nix` vs
  `example-infra-clan/modules/treefmt.nix`.
- *Fix:* standardise on `treefmt-nix` with `programs.nixfmt.enable = true` and
  `settings.global.excludes = [ "flake.lock" "vars/**" "sops/**" ".direnv/**" ]`
  ([treefmt-nix](https://github.com/numtide/treefmt-nix)).

**READ-03 `MEDIUM` — Dead bindings / unused args (deadnix).**
- *Why:* unused `let` bindings and lambda args rot and mislead.
- *Detect:* `deadnix .` (add `--no-lambda-arg` for module signatures)
  ([deadnix](https://github.com/astro/deadnix)).
- *Fix:* remove them; the repo already runs `deadnix` with `noUnderscore = true`.
  Note `_module.args.username` is passed but deadnix cannot see module-system usage —
  exclude with `...` or a `_` prefix.

**READ-04 `MEDIUM` — statix anti-patterns.**
- *Why:* `manual_inherit`, `bool_comparison` (`x == true`), `empty_let_in`,
  `eta_reduction`, `useless_parens`, `legacy_let_syntax` are all linted
  ([statix](https://github.com/oppiliappan/statix)).
- *Detect:* `statix check .`.
- *Fix:* `statix fix .`; e.g. `x = x;` → `inherit x;`.

**READ-05 `MEDIUM` — `with` overuse.**
- *Why:* `with pkgs;` shadows and defeats tooling; statix warns; it hides where a name
  comes from. The repo uses `with pkgs;` in `baseSystem.nix`, `wsl.nix`, `git.nix`,
  `devshells.nix`.
- *Detect:* `rg 'with pkgs;|with lib;'`.
- *Fix:*
  ```nix
  # before
  environment.systemPackages = with pkgs; [ git curl ];
  # after
  environment.systemPackages = [ pkgs.git pkgs.curl ];
  ```

**READ-06 `LOW` — Inconsistent naming.**
- *Why:* mixed `baseSystem.nix` (camelCase) vs `git-hooks.nix` (kebab) vs `git.nix`.
- *Detect:* `find modules -name '*.nix'`.
- *Fix:* adopt one convention (kebab-case filenames, camelCase options) and document it.

**READ-07 `MEDIUM` — Grab-bag modules / multiple concerns per file.**
- *Why:* `baseSystem.nix` mixes users, SSH, nix settings, locale, docs, and GC; hard to
  review and to reuse per machine.
- *Detect:* read each module and count top-level option namespaces.
- *Fix:* split by concern (`ssh.nix`, `nix-settings.nix`, `locale.nix`, `gc.nix`) or
  expose a typed `clan.service` with settings (the sibling ADR's Option B).

**READ-08 `LOW` — `lib.mkIf`/`lib.mkMerge` used unreadably.**
- *Why:* deeply nested `mkMerge` with inline conditions is hard to audit.
- *Detect:* `rg 'mkMerge|mkIf' -A5`.
- *Fix:* bind conditions in `let` and use `lib.mkIf cond { … }`; prefer
  `lib.optionalAttrs` for single-attr conditionals.

**READ-09 `MEDIUM` — No comments/docstrings on non-obvious options.**
- *Why:* `trusted-users`, `accept-flake-config`, `wheelNeedsPassword=false` need a
  "why"; the ADR documents architecture but modules do not.
- *Detect:* `rg '# ' modules/nixos` density; look for undocumented security-relevant lines.
- *Fix:* one-line comment per surprising choice, or a `README.md` beside the module.

**READ-10 `MEDIUM` — Deeply nested attrsets.**
- *Why:* `inventory.instances.<svc>.roles.<role>.settings.<opt>` is already deep; further
  nesting hurts.
- *Detect:* visual inspection; `rg 'settings = \{' -A10`.
- *Fix:* use `let` bindings for the settings block; keep one role per instance where possible.

**READ-11 `LOW` — Dead/commented-out blocks.**
- *Why:* `flake.nix` has a commented `_module.args.pkgs` block; `clan.nix` has commented
  `zerotier`/`tor`; `clan/modules/git-hooks.nix` has a commented `nil` hook. These hide
  intent and rot.
- *Detect:* `rg '^\s*#' -c` and review; `rg 'zerotier|tor =|# nil'`.
- *Fix:* delete or move to the ADR/issue; keep at most a one-line pointer.

**READ-12 `MEDIUM` — No machine/module docs.**
- *Why:* the sibling has `docs/adr/0001-…md`; the root repo has no README/ADR.
- *Detect:* `find . -maxdepth 2 -iname 'README*' -o -iname '*.md'` (root repo: none).
- *Fix:* add a README (machines, how to deploy, secret backend) and an ADR for the
  importer-vs-clan.service decision.

**READ-13 `LOW` — Manual `inherit` vs `lib.attrsets` helpers.**
- *Why:* hand-rolled attr plumbing is more error-prone than `lib.attrsets.*`.
- *Detect:* statix `manual_inherit`/`manual_inherit_from`.
- *Fix:* `inherit x;` / `inherit (a) x;`.

**READ-14 `LOW` — Auto-import magic vs explicit imports.**
- *Why:* `lib.importModulesRecursive ./modules/flake` and the home auto-import mean a
  stray `.nix` file silently becomes a module.
- *Detect:* read `lib/default.nix` and `modules/home/default.nix`.
- *Fix:* keep auto-import dirs small and documented; exclude non-module helpers by name.

---

## 5. Category 4 — Correctness / Testing

### 5.1 What "good" means
`nix flake check` passes for every machine; options have correct types; `mkDefault`/
`mkForce` precedence is intentional; `stateVersion` is immutable; configs are built
(`nixos-rebuild build`) before switching; there are assertions/warnings for invariants;
at least the security-critical paths have a VM test; and pre-commit + CI gate the tree.

### 5.2 Anchored rubric

| Band | Anchor |
|---|---|
| 90–100 | `nix flake check` green; every machine evaluates and builds; typed options; precedence correct; `stateVersion` fixed; assertions/warnings present; VM tests for SSH/firewall; CI runs `nix flake check` + lint + `--pure-eval`. |
| 75–89 | Green and builds, but no VM tests and only a couple of assertions. |
| 60–74 | Green, but precedence is ad-hoc, no tests, no CI. |
| 40–59 | Some machines do not evaluate, or `mkForce` hides conflicts, or `stateVersion` was bumped. |
| 20–39 | `nix flake check` fails; type errors; configs unbuildable. |
| 0–19 | The flake does not evaluate at all. |

### 5.3 Checklist

**CORR-01 `HIGH` — `nix flake check` not run / not green.**
- *Why:* it evaluates every flake output and builds `checks.*`; the canonical gate
  ([nix flake check](https://nix.dev/manual/nix/2.24/command-ref/new-cli/nix3-flake-check.html)).
- *Detect:* `nix flake check --no-build`; `nix flake check -L`.
- *Fix:* fix failures; add a `checks` output for machines if none exists.

**CORR-02 `HIGH` — Wrong option type (`types.str` vs `types.lines` vs `types.path`).**
- *Why:* `types.path` copies the file into the store — **fatal if it is a secret**;
  `types.str` cannot hold multi-line content that `types.lines` can; `types.str` on a
  path can leak a store path.
- *Detect:* `rg 'types\.(str|lines|path|attrs)' --glob '*.nix'`; audit any `types.path`
  near secrets.
- *Fix:*
  ```nix
  # multi-line config text
  services.foo.configFile = lib.mkOption { type = lib.types.lines; };
  # a file the module will read, never a secret
  src = lib.mkOption { type = lib.types.path; };
  ```

**CORR-03 `HIGH` — `mkDefault`/`mkForce` precedence mistakes.**
- *Why:* `mkDefault` loses to any normal definition; `mkForce` silently overrides and
  hides conflicts. `baseSystem.nix` uses `mkDefault` heavily, which is correct for a
  shared baseline, but `stateVersion`/`hostPlatform` as `mkDefault` invite accidental
  override.
- *Detect:* `rg 'mkDefault|mkForce|mkOverride|mkBefore|mkAfter'`; for each, ask "is losing
  to a machine definition intended?".
- *Fix:* `mkDefault` for shareable defaults; never `mkForce` to win a fight — fix the
  conflicting definitions; use `lib.mkOption { default = …; }` at the definition site.

**CORR-04 `HIGH` — `system.stateVersion` changed.**
- *Why:* it records the install release and drives stateful migrations; bumping it can
  corrupt databases. `mkDefault "26.05"` plus a clan `state-version` var is a duplication
  risk ([stateVersion](https://mynixos.com/nixpkgs/option/system.stateVersion)).
- *Detect:* `rg 'stateVersion'`; compare `baseSystem.nix`, the clan var, and
  `home.stateVersion`.
- *Fix:* set `system.stateVersion` once (hard-coded, not `mkDefault`), remove the duplicate
  clan var if unused, and keep `home.stateVersion` as its own literal.

**CORR-05 `HIGH` — Switching without building first.**
- *Why:* `nixos-rebuild switch` activates a config that may not build/activate; `build`
  (or `boot`) first is the safe path.
- *Detect:* check docs/README for the deploy command; ADR says `switch --flake .#host`.
- *Fix:* `nixos-rebuild build --flake .#host` (or `nh os build`) then switch; the
  sibling ADR's action items list this.

**CORR-06 `HIGH` — Evaluation errors / deprecation warnings ignored.**
- *Why:* renamed options (`services.openssh.settings.*` replaced top-level `permitRootLogin`
  etc.) produce warnings that become errors on the next release.
- *Detect:* `nix flake check -L 2>&1 | rg -i 'warning|deprecated|renamed'`.
- *Fix:* migrate to `services.openssh.settings.*` (already done) and fix every warning.

**CORR-07 `MEDIUM` — No `assertions`/`warnings` for invariants.**
- *Why:* nothing prevents a regression of the security baseline.
- *Detect:* `rg 'assertions =|warnings ='` → none.
- *Fix:* add assertions (see SEC-22) and `warnings` for soft checks (e.g. "trusted-users
  includes a group").

**CORR-08 `MEDIUM` — No NixOS VM tests.**
- *Why:* `pkgs.testers.runNixOSTest` is the standard way to prove SSH/firewall/users work
  ([runNixOSTest](https://github.com/NixOS/nixpkgs/blob/master/nixos/doc/manual/development/writing-nixos-tests.section.md),
  [nix.dev VM testing](https://nix.dev/tutorials/nixos/integration-testing-using-virtual-machines.html)).
- *Detect:* `rg 'runNixOSTest|nixosTest|testers\.'`.
- *Fix:*
  ```nix
  # modules/flake/checks.nix
  perSystem = { pkgs, ... }: {
    checks.firewall = pkgs.testers.runNixOSTest {
      name = "infra-firewall";
      nodes.machine = { ... }: { imports = [ ./../nixos/baseSystem.nix ]; };
      testScript = ''
        machine.wait_for_unit("multi-user.target")
        machine.fail("ss -tln | grep ':23 '")
      '';
    };
  };
  ```

**CORR-09 `MEDIUM` — No `checks` outputs.**
- *Why:* without `checks`, `nix flake check` only verifies evaluation, not behaviour;
  git-hooks' `pre-commit.check` is the only check today.
- *Detect:* `nix eval .#checks.x86_64-linux --apply builtins.attrNames`.
- *Fix:* add a `checks` module (formatting check, pre-commit, VM tests, and a
  `nixosConfigurations.host` build).

**CORR-10 `MEDIUM` — Pre-commit not wired.**
- *Why:* the root repo has `modules/flake/git-hooks.nix`, but the sibling ADR records
  that a `git-hooks.nix` module "was never actually wired into the flake" historically;
  verify the import path.
- *Detect:* `rg 'git-hooks' flake.nix`; `nix develop -c pre-commit run --all-files`.
- *Fix:* ensure the flake module is imported (root: `importModulesRecursive ./modules/flake`
  covers it) and `check.enable = true` ([git-hooks.nix](https://github.com/cachix/git-hooks.nix)).

**CORR-11 `HIGH` — No CI.**
- *Why:* no `.github/` means nothing runs `nix flake check` on push; regressions land.
- *Detect:* `find . -maxdepth 2 -name '.github'`.
- *Fix:* a workflow running `nix flake check --no-build`, `statix check`, `deadnix`,
  and `nix fmt -- --check` on PRs.

**CORR-12 `MEDIUM` — Impure evaluation (`--impure`, `builtins.currentSystem`).**
- *Why:* flakes default to pure eval; `--impure` and `builtins.currentSystem` make
  results host-dependent ([nix.dev flakes](https://nix.dev/concepts/flakes.html)).
- *Detect:* `rg 'builtins\.currentSystem|--impure'`; `nix flake check --pure-eval`.
- *Fix:* thread `system` explicitly; drop `--impure`.

**CORR-13 `MEDIUM` — `flake.lock` drift / undisciplined updates.**
- *Why:* `nix flake update` updates everything at once; per-input updates are reviewable.
- *Detect:* `git diff flake.lock`; `nix flake metadata`.
- *Fix:* `nix flake lock --update-input <name>` per input; commit lock changes with the
  config change that needed them.

**CORR-14 `HIGH` — Machine configs may not evaluate.**
- *Why:* the deliverable is a working machine.
- *Detect:*
  ```bash
  nix eval --raw .#nixosConfigurations.host.config.system.build.toplevel.drvPath
  nix build .#nixosConfigurations.host.config.system.build.toplevel --dry-run
  ```
- *Fix:* fix evaluation errors; add the eval to `checks`.

**CORR-15 `MEDIUM` — Clan vars inconsistent with enabled instances.**
- *Why:* `vars/per-machine/host/user-password-root` exists; is `user-root` enabled?
  Orphaned vars bloat the repo and confuse `clan vars generate`.
- *Detect:* `clan vars list host`; diff against `inventory.instances`.
- *Fix:* regenerate or delete orphans; keep one var tree per enabled service.

**CORR-16 `LOW` — Conditional modules with wrong condition.**
- *Why:* `lib.mkIf config.<x>` where the option is always true is dead; the `wsl` module is
  gated by the `wsl` tag, so `modules/nixos/wsl.nix` assumes WSL.
- *Detect:* review `mkIf` conditions against the tags in `clan.nix`.
- *Fix:* gate on the actual predicate (`config.wsl.enable` or the role tag).

**CORR-17 `MEDIUM` — Overlay correctness (`final` vs `prev`).**
- *Why:* referencing `prev` where `final` is needed (or vice versa) causes subtle breakage.
- *Detect:* `rg 'overlays' -A5`; the repo currently has none (commented out).
- *Fix:* if adding one, `final: prev: { … }` and never reference the package being overridden
  via `prev` inside its own override.

**CORR-18 `LOW` — Home-manager `stateVersion` semantics.**
- *Why:* `home.stateVersion = config.system.stateVersion` couples two independent
  compatibility knobs.
- *Detect:* `rg 'stateVersion' modules/home`.
- *Fix:* give home-manager its own literal (e.g. `"24.05"`), matching the release the
  user profile was created with.

---

## 6. Category 5 — Architecture / Design

### 6.1 What "good" means
`flake-parts` modules are small and single-purpose; the flake module / NixOS module /
home module / clan service layers are distinct and justified; `specialArgs` carry
cross-cutting values; shared config is reused via `lib` or typed clan services rather
than copy-paste; secrets, config, and generated vars have separate owners; and the
upgrade path (release pinning vs unstable) is deliberate.

### 6.2 Anchored rubric

| Band | Anchor |
|---|---|
| 90–100 | Clean flake-parts module graph; clear layering; typed clan services for shared config; `specialArgs` used correctly; `lib` helpers reused; documented ADR; deliberate pinning. |
| 75–89 | Sound structure, minor duplication, one layer used where another would be better. |
| 60–74 | Works, but `importer` used where a typed service is warranted; some copy-paste; no ADR. |
| 40–59 | Import cycles / fragile auto-imports; heavy duplication; no clear layer boundaries. |
| 20–39 | Monolithic machine config; no reuse; vendored duplicate flakes. |
| 0–19 | Structure prevents safe change (e.g. every machine edits shared modules). |

### 6.3 Checklist

**ARCH-01 `MEDIUM` — flake-parts structure & auto-imports.**
- *Why:* `imports = [...] ++ lib.importModulesRecursive ./modules/flake` is idiomatic but
  opaque; a stray file becomes a flake module.
- *Detect:* read `flake.nix` + `lib/default.nix`.
- *Fix:* keep the tree flat and documented; list auto-imported modules in a comment or README.

**ARCH-02 `HIGH` — Module layering confusion.**
- *Why:* flake modules (`modules/flake/*`) configure the flake; NixOS modules
  (`modules/nixos/*`) configure machines; home modules configure the user; clan services
  compose machines. Mixing them (e.g. NixOS config in a flake module) breaks evaluation.
- *Detect:* check `imports`/`perSystem` vs plain `{ config, ... }:` module signatures.
- *Fix:* keep each file in the layer matching its signature; the repo does this correctly
  today (baseSystem/wsl are NixOS modules; devshells/git-hooks are flake modules).

**ARCH-03 `MEDIUM` — `specialArgs` vs `_module.args`.**
- *Why:* `specialArgs`/`extraSpecialArgs` are for values a module *cannot* get from
  `config` (e.g. flake `inputs`); `_module.args` is for values with an option system.
  Misuse causes infinite recursion.
- *Detect:* `rg 'specialArgs|extraSpecialArgs|_module.args'`.
- *Fix:* the repo uses `specialArgs = { inherit inputs; }` at the clan level and
  `extraSpecialArgs = { inherit inputs username; }` for home-manager — correct. Set
  `_module.args.username` per machine in `clan.nix` (already done).

**ARCH-04 `HIGH` — Import cycles.**
- *Why:* two modules importing each other (or a module importing its own directory)
  deadlocks evaluation.
- *Detect:* `nix flake check` infinite loop / "infinite recursion" error.
- *Fix:* factor shared code into `lib/` or a leaf module both import.

**ARCH-05 `MEDIUM` — Copy-paste instead of `lib` reuse.**
- *Why:* `lib/default.nix` exists but only exposes import helpers; shared machine logic
  (SSH, firewall, GC) lives in one big `baseSystem.nix`.
- *Detect:* compare modules across machines; count duplicated blocks.
- *Fix:* add focused helpers to `lib/default.nix` (e.g. `mkHost`, `mkUser`) and use them.

**ARCH-06 `MEDIUM` — `importer` where a typed `clan.service` is warranted.**
- *Why:* `base-system`/`wsl` are wired through clan's generic `importer` with
  `extraModules`; the sibling ADR chose real `clan.service` modules with typed
  `interface.options` so a second machine can override settings per-instance.
- *Detect:* read `clan.nix` `inventory.instances`; look for `module.name = "importer"`.
- *Fix:* for genuinely shared/cross-machine config, author a `clan.service` with
  `interface.options` and register it via `clan.modules`; keep `importer` for single-machine
  glue (the ADR's split).
  ([clan service definition](https://clan.lol/docs/26.05/services/definition),
  [intro to services](https://clan.lol/docs/26.05/guides/services/intro-to-services-revised)).

**ARCH-07 `HIGH` — Secrets / config / vars not separated.**
- *Why:* sops ciphertext, clan-generated vars, and plain config must have distinct owners;
  mixing invites plaintext leakage and orphaned ciphertext.
- *Detect:* `find sops vars -maxdepth 3`; cross-reference with `inventory.instances`.
- *Fix:* document the ownership split (SEC-19) and keep `sops/` hand-managed vs `vars/`
  generator-owned.

**ARCH-08 `MEDIUM` — Host-specific vs shared config blurred.**
- *Why:* the machine config hardcodes `hostName = "host-wsl"`, `nh.flake` path, and
  `C:\Users\<user>\.ssh`; that is host-specific and should not leak into shared modules.
- *Detect:* compare `machines/*/configuration.nix` against `modules/nixos/*`.
- *Fix:* keep host-specific values in the machine file; shared modules take them as options
  (`_module.args`, `interface.options`).

**ARCH-09 `MEDIUM` — Upgrade path not deliberate.**
- *Why:* `nixpkgs` on `nixos-unstable` + `nixos-wsl` on `main` means frequent breakage;
  the sibling follows `clan-core/nixpkgs` for a tested closure.
- *Detect:* `rg 'nixos-unstable|/main|clan-core/nixpkgs' flake.nix`.
- *Fix:* choose deliberately — either follow `clan-core/nixpkgs` (CI-tested) or pin your own
  and accept the frontier; document the choice
  ([clan nixpkgs flake input](https://clan.lol/docs/25.11/guides/nixpkgs-flake-input)).

**ARCH-10 `MEDIUM` — Clan topology under-specified.**
- *Why:* one machine means roles/tags are untested; `roles.default.tags.all` vs
  `machines.host` mixes selectors.
- *Detect:* read `inventory.instances`.
- *Fix:* standardise on tags for multi-machine services and `machines.<name>` for
  single-target ones; document the convention.

**ARCH-11 `MEDIUM` — Input `follows` hygiene / duplicate nixpkgs.**
- *Why:* missing `follows` duplicates `nixpkgs` in `flake.lock` and the store
  ([clan flake-parts guide](https://clan.lol/docs/26.05/guides/flake-parts)).
- *Detect:* `rg -c '"nixpkgs' flake.lock`; inspect nodes for `nixpkgs_2.._5`.
- *Fix:* add `inputs.nixpkgs.follows = "nixpkgs"` to `nixos-wsl`, `devshell`, `git-hooks`,
  `zed` where compatible.

**ARCH-12 `MEDIUM` — Vendored/nested duplicate flake (`clan/`).**
- *Why:* the root repo contains a `clan/` directory with its own `flake.nix`, `flake.lock`,
  `.git`, and a duplicated `modules/` tree. Two sources of truth for the same infra is a
  maintainability trap.
- *Detect:* `find . -maxdepth 2 -name flake.nix` (finds `./flake.nix` and `./clan/flake.nix`).
- *Fix:* remove the nested copy or make it the single source and delete the outer; document
  which is authoritative.

**ARCH-13 `LOW` — Dead flake input (`zed`).**
- *Why:* `zed.url = "github:zed-industries/zed"` is declared but never referenced in
  outputs — it pins a large input for nothing and adds lock churn.
- *Detect:* `rg 'zed' flake.nix clan.nix modules/`; `rg 'inputs.zed'`.
- *Fix:* drop the input or actually use it (e.g. a `zed` package/module).

**ARCH-14 `MEDIUM` — Multi-arch strategy unimplemented.**
- *Why:* the ADR wants a Pi (`aarch64-linux`) and a ThinkPad; `systems` is x86_64-only and
  modules assume WSL.
- *Detect:* `rg 'systems = '`; check module guards.
- *Fix:* when adding a machine, add its system, scaffold `machines/<name>/`, tag it, and
  ensure shared modules are `mkIf`-guarded.

**ARCH-15 `MEDIUM` — Secrets backend consistency across the family.**
- *Why:* root repo uses sops + clan vars; `infra/` uses a `sops/users` layout; the sibling
  uses sops + vars. Inconsistent layouts make cross-repo reasoning hard.
- *Detect:* compare the `sops/` trees across the sibling flakes.
- *Fix:* standardise one layout (`sops/{machines,users,secrets}` + `vars/{per-machine,shared}`)
  and document it.

**ARCH-16 `LOW` — Deploy topology.**
- *Why:* `deploy.targetHost = "wsl-root"` for a self-managed machine is odd; the ADR says
  `host` should have **no** `targetHost` and be rebuilt in place.
- *Detect:* `rg 'targetHost'`.
- *Fix:* remove `deploy.targetHost` for the self-managed host; add `root@<ip>` only for
  machines managed from host.

**ARCH-17 `LOW` — `nix-topology` imported but not wired.**
- *Why:* `inputs.nix-topology.flakeModule` is imported, but no `topology` output is defined,
  so the import does nothing but cost eval.
- *Detect:* `rg 'topology' flake.nix`; `nix eval .#topology`.
- *Fix:* define the global topology (and the NixOS module) or drop the import
  ([nix-topology](https://github.com/oddlama/nix-topology)).

**ARCH-18 `MEDIUM` — No architecture documentation.**
- *Why:* the sibling has `docs/adr/0001-clan-flake-parts-architecture.md`; the root repo
  has none, so the importer-vs-service and pinning decisions are implicit.
- *Detect:* `find . -iname '*.md' -not -path './.git/*'`.
- *Fix:* port the ADR; keep it updated as machines land.

---

## 7. Cross-category Nix smells

These span categories; the owning agent should report them but tag the cross-cutting impact.

| Smell | Categories | Why it bites | Detect | Fix |
|---|---|---|---|---|
| `with pkgs;` | Readability + Correctness | Hides name origin; statix warns; shadowing bugs | `rg 'with (pkgs\|lib);'` | Fully-qualify (`pkgs.git`) |
| `builtins.readFile` on a derivation/secret | Security + Performance | IFD (slow) or secret-in-store (fatal) | `rg 'builtins\.readFile'` | Precompute; for secrets use sops `.path` |
| `import <nixpkgs>` / `<nixpkgs>` | Correctness + Architecture | Bypasses flake pinning; impure | `rg 'import <nixpkgs>|<nixpkgs>'` | Use the flake's `inputs.nixpkgs` |
| `--impure` / `NIXPKGS_ALLOW_UNFREE` | Security + Correctness | Non-reproducible; hides config | `rg -- '--impure\|NIXPKGS_ALLOW_UNFREE'` | Thread `system`/config explicitly |
| `mkForce` abuse | Correctness + Architecture | Silently wins option conflicts, hiding a real disagreement | `rg 'mkForce'` | Fix the conflicting definitions; use `mkDefault`/`mkOverride` deliberately |
| `builtins.fetchTarball`/`fetchGit` without hash | Security + Performance | Mutable, MITM-able, non-reproducible | `rg 'builtins\.fetch'` | `pkgs.fetchFromGitHub` with `hash`, or a flake input |
| Overlays that touch low-level pkgs | Performance + Architecture | Mass rebuilds, cache misses | `rg 'overlays'` | Keep additive; follow one nixpkgs |
| Multiple `nixpkgs` in `flake.lock` | Performance + Architecture | Duplicate store copies | `rg -c '"nixpkgs' flake.lock` | Add `follows` |
| `rec { }` / self-referential attrsets | Readability + Correctness | Subtle infinite recursion | `rg 'rec \{'` | Use `let` bindings |
| Stringly-typed config (`types.str` for a path/secret) | Security + Correctness | Store copy or no validation | `rg 'types\.str'` | `types.path` (non-secret) / runtime secret path |
| Blanket `allowUnfree` | Security + Readability | Untested/uncached software, hides intent | `rg 'allowUnfree'` | `allowUnfreePredicate` |
| Commented-out config blocks | Readability | Rot; hides intent | review `^\s*#` runs | Delete or move to ADR |
| `trusted-users` with a group/user | Security | Root-equivalent power | `rg 'trusted-users'` | Restrict to `root` |
| `accept-flake-config = true` | Security | Supply-chain config injection | `rg 'accept-flake-config'` | Set `false` |
| Dev tools in `systemPackages` | Performance | Closure bloat | `rg 'systemPackages'` | Move to devShell/home |
| Secrets via `Environment=` | Security | `/proc/*/environ` leak | `rg 'Environment\s*='` | `EnvironmentFile`/`LoadCredential` |
| `stateVersion` bumped | Correctness | State migrations/data loss | `rg 'stateVersion'` | Set once, never change |

---

## 8. Sources

**Nix / nix.dev**
- Import From Derivation — https://nix.dev/manual/nix/latest/language/import-from-derivation
- `nix.conf` (trusted-users, sandbox, experimental-features, allow-import-from-derivation) — https://nix.dev/manual/nix/2.24/command-ref/conf-file
- Flakes / pure evaluation — https://nix.dev/concepts/flakes.html
- `nix flake check` — https://nix.dev/manual/nix/2.24/command-ref/new-cli/nix3-flake-check.html
- `nix path-info` (closure sizes) — https://nix.dev/manual/nix/2.13/command-ref/new-cli/nix3-path-info
- NixOS VM tests (`runNixOSTest`) — https://nix.dev/tutorials/nixos/integration-testing-using-virtual-machines.html
- RFC 166 (Nix formatting) — https://github.com/NixOS/rfcs/blob/master/rfcs/0166-nix-formatting.md

**NixOS manual / wiki**
- Firewall — https://wiki.nixos.org/wiki/Firewall
- SSH hardening — https://wiki.nixos.org/wiki/SSH
- `security.sudo` module source — https://github.com/NixOS/nixpkgs/blob/master/nixos/modules/security/sudo.nix
- `security.sudo.execWheelOnly` — https://mynixos.com/nixpkgs/option/security.sudo.execWheelOnly
- `system.stateVersion` — https://mynixos.com/nixpkgs/option/system.stateVersion
- stateVersion FAQ — https://nixos.wiki/wiki/FAQ
- Garbage collection / store hygiene — https://wiki.nixos.org/wiki/Garbage_Collection
- Unfree software — https://wiki.nixos.org/wiki/FAQ/unfree
- nixpkgs global configuration (`allowUnfree`, predicates) — https://ryantm.github.io/nixpkgs/using/configuration/
- Writing NixOS tests — https://github.com/NixOS/nixpkgs/blob/master/nixos/doc/manual/development/writing-nixos-tests.section.md

**Secrets**
- sops-nix README (owner/mode, `neededForUsers`, LoadCredential) — https://github.com/Mic92/sops-nix
- agenix README (why the store is unsafe for plaintext) — https://github.com/ryantm/agenix
- agenix wiki — https://wiki.nixos.org/wiki/Agenix
- systemd credentials — https://systemd.io/CREDENTIALS/

**Clan**
- Flake-parts guide — https://clan.lol/docs/26.05/guides/flake-parts
- Services definition — https://clan.lol/docs/26.05/services/definition
- Intro to services (roles/tags/settings) — https://clan.lol/docs/26.05/guides/services/intro-to-services-revised
- sshd service — https://clan.lol/docs/26.05/services/official/sshd
- users service — https://clan.lol/docs/26.05/services/official/users
- `clan.core.vars` reference — https://clan.lol/docs/26.05/reference/clan.core/vars
- `clan vars` CLI — https://clan.lol/docs/25.11/reference/cli/vars
- Nixpkgs flake input / pinning — https://clan.lol/docs/25.11/guides/nixpkgs-flake-input
- Inventory autoincludes (referenced in repo) — https://docs.clan.lol/latest/guides/inventory/autoincludes/

**Tooling**
- statix (anti-patterns) — https://github.com/oppiliappan/statix
- deadnix (dead code) — https://github.com/astro/deadnix
- nixfmt — https://github.com/NixOS/nixfmt ; standard — https://github.com/NixOS/nixfmt/blob/master/standard.md
- treefmt-nix — https://github.com/numtide/treefmt-nix
- git-hooks.nix — https://github.com/cachix/git-hooks.nix
- nix-topology — https://github.com/oddlama/nix-topology
- NixOS-WSL — https://github.com/nix-community/NixOS-WSL
- flake-parts — https://flake.parts/
- nix-output-monitor / nix-fast-build — https://github.com/maralorn/nix-output-monitor ; https://github.com/Mic92/nix-fast-build
