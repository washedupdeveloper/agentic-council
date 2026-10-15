# Declaring the council on a NixOS / home-manager host

The module in `nix/module.nix`, exported as `homeManagerModules.default`. Hermes
runs user-level with its own `HERMES_HOME`, so the skill it loads, the CLI on its
PATH and the settings that point at both are all user state — home-manager is the
scope that matches. See `docs/bootstrap.md` for the four paths and
`docs/adr/0004` for why the skill is a store path rather than a copy.

## Import

Add this repo as an input to the host flake and import the module for the user
that runs Hermes:

```nix
# flake.nix
inputs.review-council.url = "github:<owner>/review-council";

# the home-manager module for that user
home-manager.users.<name>.imports = [ inputs.review-council.homeManagerModules.default ];
```

That is the whole setup. `programs.council.package` and `programs.council.skill`
default to this flake's own outputs, so nothing else needs setting.

Then, on the machine:

```console
$ home-manager switch      # or: nh os switch, if HM runs as a NixOS module
$ council doctor           # which analyzers are present
```

## The two modes

`programs.council.mode` decides how the skill reaches Hermes.

| Mode | What it does | When |
|---|---|---|
| `external-dirs` (default) | Adds the derivation to Hermes' `settings.skills.external_dirs` | Hermes is configured through Nix |
| `library` | Links it into `<hermesHome>/skills/autonomous-ai-agents/council` | Hermes is not configured through Nix |

`external-dirs` is the default because it is the form that **protects** the
source: a store path is read-only, so a background write cannot land in it. A
`library` link does not prevent a write, it redirects one — the distinction in
`docs/adr/0001`. Prefer `external-dirs` unless you have a reason not to.

If `external-dirs` is selected and Hermes' own module is **not** imported, nothing
would consume the setting, so the module fails the build with an assertion saying
exactly that, rather than installing a CLI nothing points at.

## What the module does not do

The module installs the *definition* of every council member. It does not install
credentials:

```console
$ council setup bots    # a profile per member; each needs a provider key
```

A key belongs in your secret store (`sops`, `agenix`, a `passwordCommand`), not in
a world-readable store path. Run `setup bots` once and, if you want it declarative,
wire the resulting profile credentials to your secret store rather than to this
module.

## Options

| Option | Default | Meaning |
|---|---|---|
| `programs.council.enable` | `false` | The whole module |
| `programs.council.package` | this flake's `review-council` | The `council` CLI |
| `programs.council.skill` | this flake's `skill` | The deployable skill tree (store path) |
| `programs.council.mode` | `"external-dirs"` | `external-dirs` or `library` |
| `programs.council.hermesHome` | `"${home.homeDirectory}/.hermes"` | Read only in `library` mode |

## Verifying the module without a switch

`nix flake check` knows a fixed set of output names and silently skips the rest, so
`homeManagerModules` would never be evaluated by it. `checks.module-evaluates`
evaluates the module against a stub for the home-manager surface it touches and
asserts that both modes produce the setting they promise:

```console
$ nix build .#checks.x86_64-linux.module-evaluates
$ nix build .#checks.x86_64-linux.skill-layout
```
