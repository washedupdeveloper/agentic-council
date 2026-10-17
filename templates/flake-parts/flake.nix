{
  description = "A flake that reviews itself with agentic-council";

  # Written by `nix flake init -t github:washedupdeveloper/agentic-council`.
  #
  # Importing `flakeModules.default` yields the same packages, formatter and app
  # this project builds for itself — not a copy of them.
  inputs = {
    review-council.url = "github:washedupdeveloper/agentic-council";

    # Follow our nixpkgs so your lock file carries one revision, not two.
    nixpkgs.follows = "review-council/nixpkgs";

    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
  };

  outputs =
    inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      imports = [ inputs.review-council.flakeModules.default ];
    };
}
