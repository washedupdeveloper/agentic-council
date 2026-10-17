# Downstream consumption — 2026-10-17

**Question.** Every test in this repository builds the flake from the **local working
tree**. Nothing verified that a stranger can consume the **published** one. crane tests
exactly that (`test/flake.nix` takes `crane.url = "github:ipetkov/crane"` rather than a
path), which is what prompted this.

**Method.** A throwaway flake in `/tmp/consumer` whose only input is
`github:washedupdeveloper/agentic-council` — the published repository, not a path, not a
store copy. Resolved at `a2b51af`.

## Result — it works

| step | result |
|---|---|
| `nix flake metadata github:washedupdeveloper/agentic-council` | resolves, `a2b51af` |
| build `packages.review-council` | builds from source, `/nix/store/wq16mg0…-review-council` |
| run the built binary | `council --help` prints its verbs |
| the package's `bin/` | 45 entries — the dispatcher **and** every analyzer (`nix`, `ruff`, `zizmor`, `osv-scanner`, `shellcheck`, `statix`, `deadnix`, `vulnix`, `bandit`, `mypy`, `treefmt`, …) |
| import `homeManagerModules.default` into a consumer config | evaluates; `mode=external-dirs`, `skill=/nix/store/…-council-skill`, `hermesHome` derived from `home.homeDirectory`, `package=review-council`, **0 failing assertions** |

The module needed `assertions`, `home.homeDirectory`, `home.file` and `home.packages` to
exist — all four are home-manager's own options, which a real configuration supplies.
A bare `evalModules` must declare them, and that is a property of home-manager, not a
defect here.

## What this found

**`packages.council` does not exist, and `packages.default` is not the council either.**
The app is `apps.council`; the *package* is `packages.review-council`; `packages.default`
is the **toolchain** (`review-council-toolchain`). `docs/NIX.md` listed `apps.council` but
neither `packages.review-council` nor `packages.skill` nor `homeManagerModules.default`,
so a consumer reading the docs had no way to learn the installable's name. Three rows
added, and the `packages.default` trap is called out in the table.

The naming is inconsistent — `council` for the app, `review-council` for the package, and
`default` pointing at something else again — but **it is not changed here**: per
`docs/VERSIONING.md`, `packages.*` is public interface, so renaming it is a major version.
Documenting the real names costs nothing and breaks nobody.

## Not done, deliberately

- **No `default.nix` / `shell.nix`.** crane ships `flake-compat` so non-flake users can
  consume it. This project's stated toolchain order is clan, then flake-parts, then plain
  Nix — all flake-based — so a non-flake entry point would be a fourth style to maintain
  for a consumer who does not exist yet.
- **No `nixConfig` substituter.** crane points at `crane.cachix.org`. Here 178 of 180
  toolchain paths are already on `cache.nixos.org` (`docs/CI.md`), so a private cache
  would carry two `symlinkJoin`s and add a secret to CI for no measured gain.

## Limits

- The consumer flake was built on **x86_64-linux only**. The same flake on darwin is
  declared and evaluated but never built, as elsewhere.
- `nix run` was not exercised from the consumer; the binary was run from its store path.
  `apps.council` was confirmed to be a valid app definition
  (`{type = "app"; program = …; meta = …}`).
