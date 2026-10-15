# Council Run 2 — reference corpus @ committed baseline `05bbd32`

| | |
|---|---|
| Date | 2026-10-05 |
| Target | clean `git worktree` checkout at `master` @ `05bbd322988ed031040b6142672475d32419ce32` |
| Scope | whole-repo snapshot of the **committed** Nix config (4 files) |
| Session | `20261005_134902_cccc11` · 4m 20s · 40 messages · 28 tool calls · ~$0.056 |
| **Termination** | **escalate** |
| Aggregate | **71.40** (effective β) / **71.56** (nominal β) vs threshold 80 |
| Open P1 | 2 · minority-veto: 1 |

## This run is the first genuine council

Run 1 could not fan out (`delegation.oneshot_max_children` default 2 blocked the batch); it ran five
passes **inline in one model**, so its "columns" were not independent. This run fixed that:

```
child            status     schema_valid  retries  tools used
security         completed  true          0        read_file, search_files, terminal
performance      completed  true          0        read_file, search_files, terminal
readability      completed  true          0        read_file, search_files, terminal, execute_code
correctness      completed  true          0        read_file, search_files, terminal
architecture     completed  true          0        read_file, search_files, terminal
```

**Five distinct child sessions** (`20261005_135026_*`), one `delegate_task` batch, each reading its own
rubric in its own context. All `schema_valid=true`, zero bounded retries.

## Scores

| Dimension | Rubric | β nominal | **β effective (measured)** | Score |
|---|---|---|---|---|
| security | 88 | 0.60 | **0.33** | 88.66 |
| correctness | 38 | 0.60 | 0.00 | 38.00 |
| readability | 83 | 0.60 | 0.00 | 83.00 |
| architecture | 66 | 0.20 | 0.00 | 66.00 |
| performance | 88 | 0.20 | 0.00 | 88.00 |

**β is now measured, not declared** — one of the four defects run 1 exposed. Security's β = 0.33 comes
from the runnable fraction of its deterministic weights (grep-class checks only, since `nix`/`statix`/
`deadnix`/`nixfmt` are absent). The other four had zero runnable deterministic signal → β = 0.

## Evidence matrix

Cells `AGREE / DISAGREE / DID_NOT_EXAMINE`; silence is never agreement.

| Claim | SEC | COR | REA | ARC | PER |
|---|---|---|---|---|---|
| A empty/stub machine config | DN | AGREE | AGREE | AGREE | DN |
| B `modules/gnome.nix` unreachable | DN | AGREE | DN | AGREE | DN |
| C clan.nix placeholders unresolved | AGREE | AGREE | AGREE | AGREE | DN |
| D machine undeclared vs on-disk secrets | AGREE | AGREE | DN | AGREE | DN |
| E no checks / `nix flake check` unwired | DN | AGREE | AGREE | AGREE | DN |
| F dead commented-out blocks | AGREE | DN | AGREE | AGREE | DN |
| G duplicate flake-parts input | DN | DN | DN | AGREE | AGREE |
| H `flake.lock` matches `flake.nix` | AGREE | AGREE | DN | AGREE | DN |
| I `.envrc` committed, not gitignored | AGREE | DN | DN | AGREE | DN |
| J clan admin/zerotier/tor exposure | AGREE | DN | DN | AGREE | DN |
| K lean closure / no IFD / no overlay | AGREE | DN | DN | AGREE | AGREE |
| L no README/docs | DN | DN | AGREE | DN | DN |

**No `DISAGREE` cells** — and the orchestrator correctly refused to read that as corroboration:
*"the specialists did not contradict one another, they examined disjoint subsets. That is NOT
corroboration."* Rows A, B, E, G, L have zero cross-dimension support.

## Ranked findings

1. **[COR — HIGH, VERIFIED]** `machines/host/configuration.nix` is a non-functional stub
   (`imports = []`, no options).
2. **[COR/SEC — HIGH, AMBIGUOUS]** Generated vars and sops keys exist for machine `host`, but
   no machine is declared in `inventory.machines`. Touches secret material and is unresolved →
   **minority-veto**.
3. **[SEC — LOW, AMBIGUOUS]** `sops/` + `vars/` blobs unverified as encrypted-at-rest (contents not
   read, per the prohibition).
4. **[ARC — MEDIUM]** clan placeholders (`__CHANGE_ME__`, `changeme`, `__YOUR_PUBLIC_KEY__`) unresolved
   while real machine secrets exist.
5. **[ARC — MEDIUM, AMBIGUOUS]** `.envrc` committed and not gitignored.
6. **[COR — LOW, VERIFIED]** `modules/gnome.nix` is imported by nothing.
7. **[COR — LOW, VERIFIED]** No `checks` output, no `nix flake check` in CI/hooks.
8. **[ARC/PERF — LOW]** Duplicate `flake-parts` node in `flake.lock`.
9. **[REA — LOW]** Dead commented blocks; stale `# New machine!`; no README.
10. **[PERF — INFO]** devShell pulls `clan-cli`; 4-system matrix; no IFD/overlay.
11. **[SEC — LOW]** `clan.nix` admin/zerotier/tor roles grant broad reach once real values land.

## Verdict

A **clean-but-uninstantiated Clan template**. No plaintext secret, no unpinned fetcher, no IFD, no
overlay — but the machine is an empty stub whose generated secrets exist without a declared machine,
the correctness hard gate is unwired and unrunnable here, and the deterministic layer never fired.
Not certifiable as satisfied → **escalate to a human with a Nix host.**

**What would change the verdict:** install the Nix toolchain (raises β, resolves C-02/SEC-01/ARCH-06);
declare `host` and populate `configuration.nix` (or remove it with its vars/sops); confirm
every sops/vars blob is encrypted at rest; set real `meta.name`/`meta.domain`; wire the `gnome.nix`
import; add checks/CI.

## Integrity

No files in the target were modified (`git status` shows only two `sops/` mode-only entries with zero
content change; all other mtimes are the checkout time). The original working tree is untouched. The
orchestrator's scratch writes landed in its own profile cache.

## Honest deviations (recorded by the orchestrator)

1. `scripts/score_reviews.py` does not exist → the gate could not be run; the hybrid was computed by an
   inline script.
2. Nix toolchain absent → β_eff = 0 for four dimensions; only security's grep-class layer ran.
3. `.envrc` blocked as a secret-bearing env file and `sops/`+`vars/` contents prohibited → "encrypted
   at rest" is unverified.
4. Threshold 80 is an uncalibrated working default.
5. No fix/re-review loop exercised (run forbids edits).
6. `execute_code` blocked in the unattended one-shot session; arithmetic ran via `terminal` instead.

## System-level notes

- **Fixed since run 1:** fan-out now works; β is measured rather than declared; the orchestrator
  distinguishes "no disagreement" from "corroboration".
- **Still open:** `protocol/` (M1) and `scripts/score_reviews.py` (M4) do not exist, so the gate is
  improvised rather than enforced; `execute_code` was unavailable in the one-shot session.
