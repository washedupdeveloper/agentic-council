# Home-manager module — add this to your home.nix.
#
#   imports = [ ./council.nix ];
#
# Written by `nix flake init -t github:washedupdeveloper/agentic-council#home-manager`.
#
# The defaults come from the flake you took this from, so importing it is the whole
# setup: `programs.council.package` and `programs.council.skill` already point at the
# pinned store paths, and `mode` already deploys the skill where Hermes looks.
#
# This assumes a flake-based home-manager configuration with
#   specialArgs = { inherit inputs; };
# so that `inputs` resolves. If yours is not flake-based, import the module from a
# path instead, or take it from the flake directly and skip this file.
{ inputs, ... }:
{
  imports = [ inputs.review-council.homeManagerModules.default ];

  programs.council = {
    enable = true;

    # Everything else has a default. The three worth knowing about:
    #
    #   mode         "external-dirs" deploys the skill and points Hermes at it;
    #                "store-path" only puts the package on PATH.
    #   hermesHome   defaults to <home.homeDirectory>/.hermes.
    #   package      the council dispatcher, with the pinned toolchain in its bin/.
    #
    # See `nix/module.nix` in the source for the options and why each exists.
  };
}
