{
  description = "council — a review is a claim until a check settles it";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/151fa4e8ddfdd8dd25d945ad94ed54a13de9f6e4";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      each = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # One interpreter with the two tools the checks need, so `nix develop`,
      # `nix build` and `nix flake check` agree on the versions.
      pythonEnv = pkgs: pkgs.python3.withPackages (ps: [ ps.pytest ps.mypy ps.setuptools ]);

      # A writable copy of the tree: the flake source is read-only, and pytest,
      # mypy and the mutation check all write caches.
      workTree = pkgs: pkgs.runCommandLocal "council-src" { } ''
        cp -r ${self} $out
        chmod -R u+w $out
      '';
    in
    {
      packages = each (pkgs: {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "council";
          version = "0.1.0";
          format = "pyproject";
          src = self;
          nativeBuildInputs = [ pkgs.python3Packages.setuptools ];
          doCheck = false;
          meta = {
            description = "A review is a claim until a check settles it.";
            mainProgram = "council";
          };
        };
      });

      checks = each (pkgs:
        let
          py = pythonEnv pkgs;
          src = workTree pkgs;

          # Each check runs in a writable copy: the flake source in the store is
          # read-only, and pytest, mypy and the mutation check all write.
          mkCheck = name: command: pkgs.runCommand name {
            nativeBuildInputs = [ py pkgs.git ];
          } ''
            cp -r ${src} work
            chmod -R u+w work
            cd work
            export HOME=$TMPDIR
            ${command}
            touch $out
          '';
        in
        {
          tests = mkCheck "council-tests" "python -m pytest -q -p no:cacheprovider";

          types = mkCheck "council-types" "mypy src";

          # The registry, executed: every sentence in claims.toml is a command
          # that must exit 0, so the documentation cannot outrun the code.
          # Invoked through bash because the sandbox has no /usr/bin/env.
          claims = mkCheck "council-claims"
            "bash ./bin/council-verify && bash ./bin/council-verify --check docs/CLAIMS.md";

          # The suite, broken on purpose eighteen ways. It must notice each one.
          mutations = mkCheck "council-mutations" "python tools/mutation_check.py";

          # v1.9.0's pinned verdicts beside this rule, on the same fixtures.
          differential = mkCheck "council-differential" "python tools/differential.py";
        });

      devShells = each (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pythonEnv pkgs) pkgs.git pkgs.ruff pkgs.jq ];
          shellHook = ''
            echo "council devshell — $(python --version 2>&1)"
            echo "  python -m pytest     the suite"
            echo "  mypy src             strict types"
            echo "  ./bin/council-verify every claim"
          '';
        };
      });

      formatter = each (pkgs: pkgs.nixfmt-rfc-style);
    };
}
