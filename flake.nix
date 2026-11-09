{
  description = "council — a review is a claim until a check settles it";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/151fa4e8ddfdd8dd25d945ad94ed54a13de9f6e4";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      each = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # The version is written once, in pyproject.toml; the package, the image
      # and the wheel check read it from there.
      version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;

      # Defined once: the package and the image ship the same application.
      base = pkgs: pkgs.python3Packages.buildPythonApplication {
        pname = "council";
        version = version;
        format = "pyproject";
        src = self;
        nativeBuildInputs = [ pkgs.python3Packages.setuptools ];
        doCheck = false;
        meta = {
          description = "A review is a claim until a check settles it.";
          mainProgram = "council";
        };
      };

      # bwrap is on the binary's own PATH: a sandboxed proof must not depend on
      # whatever the caller's environment happens to contain.
      app = pkgs: pkgs.runCommand "council-${version}" { nativeBuildInputs = [ pkgs.makeWrapper ]; } ''
        mkdir -p $out/bin
        makeWrapper ${base pkgs}/bin/council $out/bin/council \
          --prefix PATH : ${pkgs.bubblewrap}/bin
        ln -s ${base pkgs}/bin/council-verify $out/bin/council-verify
      '';

      # One interpreter with the two tools the checks need, so `nix develop`,
      # `nix build` and `nix flake check` agree on the versions.
      pythonEnv = pkgs: pkgs.python3.withPackages (ps: [
        ps.pytest ps.hypothesis ps.mypy ps.setuptools ps.pip ps.wheel
      ]);

      # A writable copy of the tree: the flake source is read-only, and pytest,
      # mypy and the mutation check all write caches.
      workTree = pkgs: pkgs.runCommandLocal "council-src" { } ''
        cp -r ${self} $out
        chmod -R u+w $out
      '';
    in
    {
      packages = each (pkgs: {
        default = app pkgs;

        # The builder is nix; the user gets a wheel with no dependencies.
        wheel = pkgs.runCommandLocal "council-wheel" {
          nativeBuildInputs = [ (pythonEnv pkgs) ];
        } ''
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
          contents = [ pkgs.bash pkgs.coreutils pkgs.git pkgs.cacert pkgs.bubblewrap (app pkgs) ];
          config = {
            Entrypoint = [ "/bin/council" ];
            Env = [ "PATH=/bin" "HOME=/tmp" "GIT_SSL_CAINFO=/etc/ssl/certs/ca-bundle.crt" ];
            WorkingDir = "/repo";
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
            nativeBuildInputs = [ py pkgs.git pkgs.bubblewrap pkgs.ruff ];
          } ''
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

          # F: a name that is imported and never used. E9: code that cannot run.
          lint = mkCheck "council-lint" "ruff check --select F,E9 src tools tests";

          # The registry, executed: every sentence in claims.toml is a command
          # that must exit 0, so the documentation cannot outrun the code.
          # Invoked through bash because the sandbox has no /usr/bin/env.
          claims = mkCheck "council-claims"
            "bash ./bin/council-verify && bash ./bin/council-verify --check docs/CLAIMS.md";

          # The suite, broken on purpose eighteen ways. It must notice each one.
          mutations = mkCheck "council-mutations" "python tools/mutation_check.py";

          # v1.9.0's pinned verdicts beside this rule, on the same fixtures.
          differential = mkCheck "council-differential" "python tools/differential.py";

          # The version, the changelog and every prose claim agree, and the
          # changelog is ordered. Maintainer tool: it is not a shipped verb.
          release = mkCheck "council-release" "python tools/release.py check";

          # The wheel is built and installed into a fresh prefix, then run.
          wheel = mkCheck "council-wheel" ''
            python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
            python -m pip install --no-index --target dist/site dist/*.whl
            PYTHONPATH=dist/site python -m council --help > /dev/null
            PYTHONPATH=dist/site python -c "import council; assert council.__version__ == '${version}'"
          '';
        });

      devShells = each (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pythonEnv pkgs) pkgs.git pkgs.ruff pkgs.jq pkgs.bubblewrap ];
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
