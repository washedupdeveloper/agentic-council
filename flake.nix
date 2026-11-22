{
  description = "council — a review is a claim until a check settles it";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/151fa4e8ddfdd8dd25d945ad94ed54a13de9f6e4";

  # What nixfmt cannot see: twenty rules over the flake, the scripts and the
  # documents, each resting on the parse tree, the lock file or an evaluated
  # value rather than on taste. It arrives as an input, so the rules are versioned
  # with this flake and a rule change is a `nix flake update` to review.
  inputs.nix-best-practices.url = "github:rokokol/nix-best-practices-skill";
  inputs.nix-best-practices.inputs.nixpkgs.follows = "nixpkgs";

  outputs =
    {
      self,
      nixpkgs,
      nix-best-practices,
    }:
    let
      # bubblewrap is Linux-only. Darwin has no sandbox here, so it must not be
      # advertised as a supported system.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      each = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # The version is written once, in pyproject.toml; the package, the image
      # and the wheel check read it from there.
      version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;

      # Defined once: the package and the image ship the same application.
      base =
        pkgs:
        pkgs.python3Packages.buildPythonApplication {
          pname = "council";
          inherit version;
          format = "pyproject";
          src = self;
          nativeBuildInputs = with pkgs; [ python3Packages.setuptools ];
          doCheck = false;
          meta = {
            description = "A review is a claim until a check settles it.";
            mainProgram = "council";
          };
        };

      # bwrap is on the binary's own PATH: a sandboxed proof must not depend on
      # whatever the caller's environment happens to contain.
      app =
        pkgs:
        pkgs.runCommand "council-${version}" { nativeBuildInputs = with pkgs; [ makeWrapper ]; } ''
          mkdir -p $out/bin
          makeWrapper ${base pkgs}/bin/council $out/bin/council \
            --prefix PATH : ${pkgs.bubblewrap}/bin
          # `council-verify` runs pytest and the claim registry; those are
          # development inputs, not runtime dependencies. Shipping the plain
          # application wrapper here made `council-verify` fail everywhere
          # outside the devshell. The source-tree `./bin/council-verify` is the
          # only supported entry point.
        '';

      # One interpreter with the tools the checks need. The protocol SDKs are
      # dev dependencies because the server adapters are tested here; the core
      # `council` package itself still has no runtime dependencies.
      pythonEnv =
        pkgs:
        pkgs.python3.withPackages (ps: [
          ps.pytest
          ps.hypothesis
          ps.mypy
          ps.setuptools
          ps.pip
          ps.wheel
          ps.mcp
          ps.agent-client-protocol
        ]);

      # The optional protocol servers use the same source and version. Their
      # Python closures differ: the core package must not gain MCP/ACP deps.
      serverBase =
        pkgs: deps:
        pkgs.python3Packages.buildPythonApplication {
          pname = "council-server";
          inherit version;
          format = "pyproject";
          src = self;
          nativeBuildInputs = with pkgs; [ python3Packages.setuptools ];
          dependencies = deps;
          doCheck = false;
          meta = {
            description = "council's optional ACP and MCP adapters";
            mainProgram = "council";
          };
        };

      serverApp =
        pkgs: deps: commands:
        pkgs.runCommand "council-server-${version}"
          {
            nativeBuildInputs = with pkgs; [ makeWrapper ];
          }
          ''
            mkdir -p $out/bin
            for name in council ${commands}; do
              makeWrapper ${serverBase pkgs deps}/bin/$name $out/bin/$name \
                --prefix PATH : ${pkgs.bubblewrap}/bin
            done
          '';

      # A writable copy of the tree: the flake source is read-only, and pytest,
      # mypy and the mutation check all write caches.
      workTree =
        pkgs:
        pkgs.runCommandLocal "council-src" { } ''
          cp -r ${self} $out
          chmod -R u+w $out
        '';
    in
    {
      packages = each (pkgs: {
        default = app pkgs;

        # The full checker: the rules `--static` inside `mkCheck` leaves out,
        # because a build sandbox has neither the network nor a daemon.
        nix-lint = nix-best-practices.packages.${pkgs.stdenv.hostPlatform.system}.check-nix;

        # The builder is nix; the user gets a wheel with no dependencies.
        wheel =
          pkgs.runCommandLocal "council-wheel"
            {
              nativeBuildInputs = [ (pythonEnv pkgs) ];
            }
            ''
              cp -r ${self} src
              chmod -R u+w src
              cd src
              python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
              mkdir -p $out
              cp dist/*.whl $out/
            '';

        # The tool, not the reviewer: mount a hermes binary and a repository.
        image = pkgs.dockerTools.buildLayeredImage {
          name = "council";
          tag = version;
          contents = with pkgs; [
            bash
            coreutils
            git
            cacert
            bubblewrap
            (app pkgs)
          ];
          config = {
            Entrypoint = [ "/bin/council" ];
            Env = [
              "PATH=/bin"
              "HOME=/tmp"
              "GIT_SSL_CAINFO=/etc/ssl/certs/ca-bundle.crt"
            ];
            WorkingDir = "/repo";
          };
        };

        # Protocol-specific server closures. The core `council` package above
        # remains free of both SDKs.
        council-mcp = serverApp pkgs (with pkgs.python3Packages; [ mcp ]) "council-mcp";
        council-acp = serverApp pkgs (with pkgs.python3Packages; [ agent-client-protocol ]) "council-acp";
        council-server = serverApp pkgs (with pkgs.python3Packages; [
          mcp
          agent-client-protocol
        ]) "council-mcp council-acp";
      });

      checks = each (
        pkgs:
        let
          py = pythonEnv pkgs;
          src = workTree pkgs;

          # Each check runs in a writable copy: the flake source in the store is
          # read-only, and pytest, mypy and the mutation check all write.
          mkCheck =
            name: command:
            pkgs.runCommand name
              {
                nativeBuildInputs = with pkgs; [
                  py
                  git
                  bubblewrap
                  ruff
                  pyright
                ];
              }
              ''
                cp -r ${src} work
                chmod -R u+w work
                cd work
                set -e
                export HOME=$TMPDIR
                # The subshell matters: `set -e` does not fire for the left side of
                # a `&&` list, so a failing check joined with `&&` would fall through
                # to `touch $out` and report success. In a subshell the list's
                # failure is the subshell's status, and `set -e` sees it.
                ( ${command} )
                touch $out
              '';
        in
        {
          tests = mkCheck "council-tests" "python -m pytest -q -p no:cacheprovider";

          types = mkCheck "council-types" "mypy src";

          # The editor's language server over the same source. mypy owns the
          # package contract; pyright catches Optional access in tools too.
          pyright = mkCheck "council-pyright" "pyright";

          # F: a name that is imported and never used. E9: code that cannot run.
          lint = mkCheck "council-lint" "ruff check --select F,E9 src tools tests";

          # The registry, executed: every sentence in claims.toml is a command
          # that must exit 0, so the documentation cannot outrun the code.
          # Invoked through bash because the sandbox has no /usr/bin/env.
          claims = mkCheck "council-claims" "bash ./bin/council-verify && bash ./bin/council-verify --check docs/CLAIMS.md";

          # The optional adapters are importable and expose their command help
          # under the same test interpreter as the core suite.
          server-mcp = mkCheck "council-server-mcp" "PYTHONPATH=src python -m council_mcp --help > /dev/null";
          server-acp = mkCheck "council-server-acp" "PYTHONPATH=src python -m council_acp --help > /dev/null";

          # The suite, broken on purpose eighteen ways. It must notice each one.
          mutations = mkCheck "council-mutations" "python tools/mutation_check.py";

          # v1.9.0's pinned verdicts beside this rule, on the same fixtures.
          differential = mkCheck "council-differential" "python tools/differential.py";

          # The flake and the scripts, held to what the formatter cannot check.
          # `--static` inside mkCheck: the sandbox has no network, so the rules
          # that need the flake's inputs are the half a contributor runs with
          # `nix run .#nix-lint` (the package exposes the same checker).
          nix-lint = nix-best-practices.lib.mkCheck {
            inherit pkgs;
            root = ./.;
            namespaces = [ ];
          };

          # The version, the changelog and every prose claim agree, and the
          # changelog is ordered. Maintainer tool: it is not a shipped verb.
          release = mkCheck "council-release" "python tools/release.py check";

          # The wheel is built and installed into a fresh prefix, then run.
          wheel = mkCheck "council-wheel" ''
            python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
            python -m pip install --no-index --target dist/site dist/*.whl
            PYTHONPATH=dist/site python -m council --help > /dev/null
            PYTHONPATH=dist/site python -c "import council, pathlib; assert council.__version__ == '${version}'; assert (pathlib.Path(council.__file__).parent / 'py.typed').is_file()"
          '';
        }
      );

      devShells = each (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            (pythonEnv pkgs)
            git
            ruff
            jq
            bubblewrap
            pyright
            nix-best-practices.packages.${pkgs.stdenv.hostPlatform.system}.check-nix
          ];
          shellHook = ''
            echo "council devshell — $(python --version 2>&1)"
            echo "  python -m pytest     the suite"
            echo "  mypy src             strict types"
            echo "  pyright               LSP diagnostics"
            echo "  ./bin/council-verify every claim"
            echo "  nix flake check       every check, including the Nix sources"
          '';
        };
      });

      formatter = each (pkgs: pkgs.nixfmt-rfc-style);
    };
}
