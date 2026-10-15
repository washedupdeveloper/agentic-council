# Council Run — reference corpus (Clan NixOS flake)

| | |
|---|---|
| Date | 2026-10-05 |
| Target | a private Clan-based NixOS flake, reviewed in place |
| HEAD | `05bbd322988ed031040b6142672475d32419ce32` (master) |
| Mode | whole-repo snapshot, Nix config only; `sops/`/`vars/` payloads never read |
| Orchestrator | `council-orchestrator` profile, session `20261005_123442_1bf324` |
| Duration | 7m 28s · 54 messages · 38 tool calls · ~$0.066 |
| **Termination** | **escalate** |
| Aggregate | **71.54** (effective β) / **70.40** (nominal β) vs threshold 80 (uncalibrated) |
| Open CRITICAL | 1 · open P0/P1: 4 |

## Deviations (self-reported, honest)

1. **Fan-out did not happen.** `delegate_task` failed — the one-shot run's delegation budget was
   exhausted (0/2 children). The orchestrator ran the five specialist passes **inline**, so the
   "columns" are single-session passes, **not independent agents**. Independence is reduced and
   confidence is capped accordingly.
2. `scripts/score_reviews.py` does not exist (the council repo is still *planned*), so the hybrid was
   computed inline by a scratch script.
3. Threshold 80 is a working default, not a locked calibration.

## Host determinism

No Nix toolchain on this Windows host → the deterministic layer **could not run at all**.
β_effective = sec 0.15 · cor 0 · rea 0 · arc 0 · per 0. Every pass was static-only and said so.

## Scores

| Category | Score | β nominal | β effective |
|---|---|---|---|
| security | 68.8 | 0.60 | 0.15 |
| correctness | 72.0 | 0.60 | 0.00 |
| readability | 74.0 | 0.60 | 0.00 |
| architecture | 64.0 | 0.20 | 0.00 |
| performance | 85.0 | 0.20 | 0.00 |

Weights: security .30 · correctness .25 · readability .20 · architecture .15 · performance .10.

## Verified facts (unioned at full weight, no voting)

- **V1** No plaintext secret in the Nix config; secrets wired only via sops/clan vars (paths).
- **V2** No `builtins.readFile` on a secret; no hash-less fetchers; `flake.lock` pins every input with rev + narHash.
- **V3** No `--impure`, no `builtins.getEnv`, no `builtins.currentSystem`.
- **V4** No `openFirewall = true`; firewall opens only TCP/22; SSH password auth disabled.
- **V5** `PasswordAuthentication = false`, `KbdInteractiveAuthentication = false`.
- **V6** `security.sudo.execWheelOnly = true` (positive hardening).
- **V7** `nix flake check` is invoked **nowhere** in git-hooks or CI → the correctness hard gate is unwired.
- **V8** `.statix.toml` / `.editorconfig` / `.markdownlint*` absent at repo root (only inside `clan/`).
- **V9** `clan/` is **not gitignored** (`git check-ignore clan/` → exit 1) and is untracked.
- **V10** No IFD and no overlays anywhere.

## Minority-veto

`F-SEC-01` (passwordless sudo for `wheel`) and `F-SEC-02` (`accept-flake-config`) are high-severity
safety claims raised by a single specialist and unresolved → **minority-veto blocks `satisfied`**,
independent of the aggregate.

## Top findings (ranked)

1. **[ARCH/SEC — CRITICAL]** Untracked nested `clan/` near-duplicates the whole repo (own `.git`,
   divergent `flake.nix`, the only `.statix.toml`) and is **not gitignored**; it duplicates `sops/`
   and `vars/`, so a careless `git add -A` would commit a second copy of the secret store.
2. **[SEC — HIGH]** `security.sudo.wheelNeedsPassword = false` (`baseSystem.nix:46`).
3. **[SEC — HIGH]** `nix.settings.accept-flake-config = true` (`baseSystem.nix:80`) — supply-chain foothold.
4. **[SEC/COR — MEDIUM]** `trusted-users` set twice (`baseSystem.nix:81` + `machines/host/configuration.nix:34`)
   with no priority marker → the list **merges**, so the apparent per-host restriction does not restrict.
5. **[COR — MEDIUM]** Correctness hard gate unwired — `nix flake check` in no hook or CI.
6. **[COR/REA — MEDIUM]** `lib/default.nix` uses pipe operators `|>` (lines 8/10/27/32) → the
   *evaluator* needs the `pipe-operators` experimental feature, not just the configured system.
7. **[ARC/COR — MEDIUM]** `system.stateVersion` has two sources of truth (hardcoded `mkDefault "26.05"`
   vs a clan `state-version` var generator) — silent-drift hazard on the one value that must never change.
8. **[SEC — MEDIUM]** WSL mounts the Windows host `C:\Users\<user>\.ssh` into the guest via drvfs
   (`wsl.nix:37-49`) — host hardcode + a second copy of SSH private keys inside WSL.
9. **[COR/PERF — LOW/MED]** `nix.gc.automatic = false` silently overrides the base `mkDefault true`.
10. **[PERF/ARC — LOW]** Dev-only tools in `environment.systemPackages` (`baseSystem.nix:11-19`),
    duplicated in the devshell.
11. **[REA/COR — LOW]** Enabled hooks with no config file at the repo root.
12. **[REA/ARC — LOW]** Inline `capitalize` helper + reimplemented module discovery; commented-out dead
    blocks; inconsistent indentation in `wsl.nix:11-15`.

## What would change the verdict

- Install the Nix toolchain (Linux/macOS/WSL2) and run `nix flake check`, `statix`, `deadnix`,
  `nixfmt --check` → β rises and A1–A5 resolve.
- Resolve the `clan/` duplicate → clears the only open CRITICAL.
- Confirm/drop passwordless sudo and `accept-flake-config` → disengages the minority-veto.

## Bottom line

A tidy, secret-hygiene-clean homelab flake (no plaintext secrets, no unpinned fetchers, no IFD, no
overlays, SSH key-only). **Not certifiable as satisfied** — the deterministic layer never ran, an
untracked full-repo duplicate sits uncommitted and unignored, and two high-severity safety settings
are open. Escalate to a human with a Nix host.

---

## Verdict on the system itself

The council behaved as designed on the hard cases:

- It **honestly declared** that fan-out failed rather than pretending five agents ran.
- It **zeroed β** for every dimension whose deterministic tools could not run, instead of scoring on
  vibes.
- It applied the **minority-veto** on unresolved high-severity safety claims.
- It **de-escalated** a finding (F-SEC-05) rather than inflating it, citing the prior bot's calibration.
- It marked unmeasured claims `AMBIGUOUS`/`UNMEASURABLE` rather than asserting numbers.
- It terminated `escalate` rather than forcing `satisfied` on low confidence.

**Defects this run exposed in the council itself**

1. **One-shot sessions cannot fan out.** `delegation.oneshot_max_children` (default 2) blocks the
   five-child batch in a `chat -q` run. Real independent review requires an interactive session, a
   raised budget, or the kanban/durable path. This is the single biggest gap to close.
2. **No scoring code yet.** The orchestrator improvised the hybrid from its rubric because
   `scripts/score_reviews.py` (M4) and the protocol (M1) do not exist.
3. **β is nominal, not measured.** The BOTS.md β values (sec .60 etc.) are hand-set; the run computed
   an "effective β" by hand. M2 must derive β from actual analyzer coverage.
4. **No fix/re-review loop** was exercised (no-edit run), so M5/M6 remain unproven end to end.
