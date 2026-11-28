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
      #
      # `aarch64-linux` is declared so the package evaluates for it, which is a
      # build contract, not a CI leg: `.github/workflows/gate.yml` gates
      # x86_64-linux only. A declared system must still evaluate, so leaving it
      # here costs nothing and keeps the arm build one matrix entry away.
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
          ps.pyyaml
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

      # What each check actually reads. `nix flake check` skips a check whose
      # derivation is unchanged, but a single input carrying the whole tree means
      # every edit changes every hash: measured, a README edit rebuilt 11 of 12
      # checks. These filesets are each the *superset* a command opens, so an
      # edit outside them leaves that check cached. Proven on the real flake: a
      # docs edit rebuilt 3 checks, a spec edit 2, where both rebuilt 11 before.
      #
      # A path missing here is a check that silently reads less, which is worse
      # than a slow gate. `tests/test_governance.py` holds the lists to what the
      # suite and the tools actually open.
      scopeRoot = ./.;
      scope =
        paths:
        nixpkgs.lib.fileset.toSource {
          root = scopeRoot;
          fileset = nixpkgs.lib.fileset.unions (map (p: scopeRoot + "/${p}") paths);
        };

      # Tool configuration travels with every scope. Without it a scoped copy
      # silently falls back to defaults: pyright reported type errors in the build
      # sandbox that it does not report in the checkout, because its copy had no
      # `pyrightconfig.json`. A check must see the same configuration everywhere.
      toolConfig = [
        "pyproject.toml"
        "pyrightconfig.json"
        "check-nix.allow"
      ];

      # The Python package and the suite that exercises it.
      codeScope = [
        "src"
        "tests"
      ]
      ++ toolConfig;

      # `pytest` also opens the governance and documentation fixtures.
      testScope = codeScope ++ [
        # The suite reads the flake itself: the governance tests assert its matrix
        # and systems, and `tests/test_build_scope.py` parses the scope lists below.
        "flake.nix"
        "flake.lock"
        ".github"
        "docs"
        "openspec"
        "fixtures"
        "skills"
        "claims.toml"
        "README.md"
        "CHANGELOG.md"
        "AGENTS.md"
        "GLOSSARY.md"
        "LICENSE"
        "Dockerfile"
        "bin"
        "tools"
      ];

      # `tools/release.py` reads the changelog, the version and the tree layout.
      releaseScope = [
        "CHANGELOG.md"
        "src"
        "tools"
        "docs"
        "README.md"
        "openspec"
      ]
      ++ toolConfig;
    in
    # `rec` because `packages` links to its sibling `checks` through
    # `passthru.tests`: a consumer of the artifact can reach what proves it.
    rec {
      packages = each (pkgs: {
        # `passthru.tests` links the artifact to what proves it, so a consumer can
        # run `nix build .#default.passthru.tests` (or `nix flake check`) rather
        # than trusting an untested build. It is not `doCheck`: the suite cannot
        # run in the package build, because the build's own artifacts and Nix's
        # `HOME=/homeless-shelter` each break a test that the copied-tree check
        # passes. `passthru` is excluded from the derivation, so this does not
        # change the output path.
        default = (app pkgs).overrideAttrs (prev: {
          passthru = (prev.passthru or { }) // {
            tests = checks.${pkgs.stdenv.hostPlatform.system};
          };
        });

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
        council-server =
          (serverApp pkgs (with pkgs.python3Packages; [
            mcp
            agent-client-protocol
          ]) "council-mcp council-acp").overrideAttrs
            (prev: {
              passthru = (prev.passthru or { }) // {
                tests = checks.${pkgs.stdenv.hostPlatform.system};
              };
            });
      });

      # The cheap half of the gate, ordered by how fast a failure is found and how
      # likely it is. `nix run .#gate-fast` builds exactly this list and stops there:
      # a typo costs 22 ms, a type error 3.6 s, a broken test 31 s -- and the
      # mutation campaign, which is the whole cost of the gate, never starts.
      # `tests/test_governance.py` holds the workflow to this list.
      fastChecks = [
        "lint"
        "types"
        "pyright"
        "tests"
      ];

      checks = each (
        pkgs:
        let
          py = pythonEnv pkgs;

          # Each check runs in a writable copy: the flake source in the store is
          # read-only, and pytest, mypy and the mutation check all write.
          mkCheck =
            name: paths: command:
            pkgs.runCommand name
              {
                nativeBuildInputs = with pkgs; [
                  py
                  git
                  bubblewrap
                  ruff
                  pyright
                ];
                src = pkgs.runCommandLocal "${name}-src" { } ''
                  cp -r ${scope paths} $out
                  chmod -R u+w $out
                '';
              }
              ''
                cp -r $src work
                chmod -R u+w work
                cd work
                set -e
                export HOME=$TMPDIR
                # A scoped copy carries no history, and the claims registry and
                # several tests ask the repository questions. A one-commit
                # snapshot is enough for every one of them.
                if [ ! -d .git ]; then
                  git init -q .
                  git add -A
                  git -c user.email=council@example.invalid \
                      -c user.name=council commit -qm snapshot
                fi
                # The subshell matters: `set -e` does not fire for the left side of
                # a `&&` list, so a failing check joined with `&&` would fall through
                # to `touch $out` and report success. In a subshell the list's
                # failure is the subshell's status, and `set -e` sees it.
                ( ${command} )
                touch $out
              '';
        in
        {
          # `COUNCIL_STRICT_SKIPS=1` makes a skipped test fail this check: the gate
          # asks for proof, and a skip proves nothing. A developer running pytest by
          # hand still gets the platform guards.
          tests =
            mkCheck "council-tests" testScope
              "COUNCIL_STRICT_SKIPS=1 python -m pytest -q -p no:cacheprovider --basetemp=$TMPDIR/pytest-base";

          types = mkCheck "council-types" codeScope "mypy src";

          # The editor's language server over the same source. mypy owns the
          # package contract; pyright catches Optional access in tools too.
          pyright = mkCheck "council-pyright" (codeScope ++ [ "tools" ]) "pyright";

          # F: a name that is imported and never used. E9: code that cannot run.
          lint = mkCheck "council-lint" (codeScope ++ [ "tools" ]) "ruff check --select F,E9 src tools tests";

          # The registry, executed: every sentence in claims.toml is a command
          # that must exit 0, so the documentation cannot outrun the code.
          # Invoked through bash because the sandbox has no /usr/bin/env.
          claims = mkCheck "council-claims" (
            testScope ++ [ "bin" ]
          ) "bash ./bin/council-verify && bash ./bin/council-verify --check docs/CLAIMS.md";

          # The optional adapters are importable and expose their command help
          # under the same test interpreter as the core suite.
          server-mcp =
            mkCheck "council-server-mcp" codeScope
              "PYTHONPATH=src python -m council_mcp --help > /dev/null";
          server-acp =
            mkCheck "council-server-acp" codeScope
              "PYTHONPATH=src python -m council_acp --help > /dev/null";

          # The suite, broken on purpose eighteen ways. It must notice each one.
          mutations = mkCheck "council-mutations" (
            testScope ++ [ "tools" ]
          ) "python tools/mutation_check.py --no-cache";

          # v1.9.0's pinned verdicts beside this rule, on the same fixtures.
          differential = mkCheck "council-differential" testScope "python tools/differential.py";

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
          release = mkCheck "council-release" releaseScope "python tools/release.py check";

          # The wheel is built and installed into a fresh prefix, then run.
          wheel = mkCheck "council-wheel" (codeScope ++ [ "README.md" ]) ''
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
            # To stderr: `nix develop -c council review --json > verdict.json` must write
            # JSON and nothing else. On stdout this banner lands in front of the verdict
            # and every consumer that parses it fails on line 1 column 1.
            {
              echo "council devshell — $(python --version 2>&1)"
              echo "  python -m pytest     the suite"
              echo "  mypy src             strict types"
              echo "  pyright               LSP diagnostics"
              echo "  ./bin/council-verify every claim"
              echo "  nix flake check       every check, including the Nix sources"
            } >&2
          '';
        };
      });

      apps = each (pkgs: {
        # The spec CLI, resolved through `flake.lock`: `nix run .#openspec -- …`.
        # `npx` resolves outside the lock and leaves a second version on PATH that the
        # lockfile does not describe, which is the drift the pin exists to prevent.
        openspec = {
          type = "app";
          program = "${pkgs.openspec}/bin/openspec";
        };

        # Everything except the campaign, for CI: the shard jobs own that. Local
        # `nix flake check` remains the one full gate, so nothing here weakens what
        # a contributor runs before a push.
        gate-ci = {
          type = "app";
          program = toString (
            pkgs.writeShellScript "council-gate-ci" ''
              set -euo pipefail
              exec nix build --no-link --keep-going --print-build-logs \
                ${nixpkgs.lib.concatStringsSep " " (
                  map (c: "\".#checks.${pkgs.stdenv.hostPlatform.system}.${c}\"") (
                    builtins.attrNames (builtins.removeAttrs checks.${pkgs.stdenv.hostPlatform.system} [ "mutations" ])
                  )
                )}
            ''
          );
        };

        # One command for the inner loop: `nix run .#gate-fast`.
        gate-fast = {
          type = "app";
          program = toString (
            pkgs.writeShellScript "council-gate-fast" ''
              set -euo pipefail
              exec nix build --no-link --keep-going --print-build-logs \
                ${nixpkgs.lib.concatStringsSep " " (
                  map (c: "\".#checks.${pkgs.stdenv.hostPlatform.system}.${c}\"") fastChecks
                )}
            ''
          );
        };
      });

      formatter = each (pkgs: pkgs.nixfmt-rfc-style);
    };
}
