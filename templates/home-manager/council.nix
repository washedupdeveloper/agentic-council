# Home-manager module — add to home.nix as `imports = [ ./council.nix ];`
# Written by `nix flake init -t github:washedupdeveloper/agentic-council#home-manager`.
#
# Defaults come from the flake you took this from, so importing it is the whole
# setup: `package` and `skill` already point at the pinned store paths, and `mode`
# already deploys the skill where Hermes looks.
#
# Assumes a flake-based home-manager with `specialArgs = { inherit inputs; };` so
# `inputs` resolves; otherwise import the module from a path and skip this file.
{ inputs, ... }:
{
  imports = [ inputs.review-council.homeManagerModules.default ];

  programs.council = {
    enable = true;

    # Everything else has a default. Worth knowing: `mode` "external-dirs" deploys
    # the skill and points Hermes at it, "library" links it into
    # <hermesHome>/skills instead; `hermesHome` defaults to
    # <home.homeDirectory>/.hermes; `package` is the dispatcher with the pinned
    # toolchain in its bin/. Options and reasoning: nix/module.nix.
  };
}
