# This repo's own gates: the checks and the devshell.
#
# Kept out of nix/flake-module.nix so that importing this flake's module gives a
# consumer the packages and nothing else — the suite is about THIS tree, and running
# it against someone else's would be meaningless.
{ lib, inputs, ... }:
let
  builders = import ./builders.nix {
    inherit lib;
    nixpkgs = inputs.nixpkgs or { };
  };

  # The devshell banner names the pin, read from this module's own `inputs`.
  nixpkgsRev = inputs.nixpkgs.rev or "unknown";
in
{
  perSystem =
    { pkgs, ... }:
    {
      checks =
        let
          tc = builders.mkToolchain pkgs;
          # The shipped tree, and the dev one. checks.commands asserts that the
          # difference between them is EXACTLY the audience split in the CLI's own
          # verb table, so this list cannot rot into a comment.
          fw = builders.mkFramework pkgs "user";
          fwDev = builders.mkFramework pkgs "dev";
          app = builders.mkDispatcher pkgs "user";
          dev = builders.mkDispatcher pkgs "dev";

          # Copied writable: the store is read-only and pytest writes caches.
          src = pkgs.runCommand "review-council-src" { } ''
            cp -r ${../.} $out
            chmod -R u+w $out
          '';

          # The linters run against this, not `src`: tests/golden is fixture data
          # and its line count is the golden suite's kloc, so formatting it would
          # move every pinned score.
          srcLint = pkgs.runCommand "review-council-src-lint" { } ''
            cp -r ${../.} $out
            chmod -R u+w $out
            rm -rf $out/tests/golden
          '';
        in
        {
          # The declarative path's two artifacts. Without these it is exercised only
          # by a user's switch, which is a late place to find a typo.
          skill-layout = pkgs.runCommand "check-skill-layout" { } ''
            s=${builders.mkSkill pkgs}
            for f in SKILL.md flake.nix flake.lock \
                     scripts/council.py scripts/council_loop.py \
                     assets/rubrics/reviewer-security/SKILL.md \
                     assets/bots/council-orchestrator/profile.yaml \
                     tests/golden/expect.json; do
              test -f "$s/$f" || { echo "missing from .#skill: $f" >&2; exit 1; }
            done
            # The copier never ships. Shipping it is how the deployed suite came
            # to import a file that is not there and run zero tests.
            test ! -e "$s/scripts/sync_to_skill.py" \
              || { echo "the copier shipped in .#skill" >&2; exit 1; }
            touch $out
          '';

          # `nix flake check` knows a fixed set of output names and skips anything
          # else with a warning, so homeManagerModules would never be evaluated.
          # Evaluate it against a stub for the home-manager surface it touches, and
          # assert that BOTH modes produce the setting each one promises.
          module-evaluates =
            let
              stub =
                { lib, ... }:
                {
                  # The attribute set is a whole, not a repeated `options.` prefix:
                  # statix's W20 flags the repeated-key form, and it is right — the
                  # dotted form reads as five separate declarations of `options`.
                  options = {
                    home = {
                      # A placeholder from the repo's allowlist, not an invented
                      # name: the portability test flags any /home/<name> that is
                      # not a known placeholder, and "stub" was a real hit.
                      homeDirectory = lib.mkOption {
                        type = lib.types.str;
                        default = "/home/user";
                      };
                      packages = lib.mkOption {
                        type = lib.types.listOf lib.types.anything;
                        default = [ ];
                      };
                      file = lib.mkOption {
                        type = lib.types.attrsOf lib.types.anything;
                        default = { };
                      };
                    };
                    # home-manager declares `assertions`; the module's mode check
                    # needs it, and its absence is what this check caught first run.
                    assertions = lib.mkOption {
                      type = lib.types.listOf lib.types.anything;
                      default = [ ];
                    };
                    services.hermes-agent.settings.skills.external_dirs = lib.mkOption {
                      type = lib.types.listOf lib.types.str;
                      default = [ ];
                    };
                  };
                };
              evalMode =
                mode:
                lib.evalModules {
                  modules = [
                    stub
                    (import ../nix/module.nix)
                    {
                      programs = {
                        council = {
                          enable = true;
                          package = pkgs.hello;
                          skill = builders.mkSkill pkgs;
                          inherit mode;
                        };
                      };
                    }
                  ];
                };
              dirs = (evalMode "external-dirs").config.services.hermes-agent.settings.skills.external_dirs;
              linked = (evalMode "library").config.home.file;
            in
            pkgs.runCommand "check-module-evaluates" { } ''
              test ${builtins.toString (builtins.length dirs)} -eq 1 \
                || { echo "external-dirs set ${builtins.toString (builtins.length dirs)} entries, wanted 1" >&2; exit 1; }
              test ${builtins.toString (builtins.length (builtins.attrNames linked))} -eq 1 \
                || { echo "library mode set no home.file entry" >&2; exit 1; }
              touch $out
            '';

          # §1: formatting is a binary gate, over every Nix file.
          nixfmt = pkgs.runCommand "check-nixfmt" { nativeBuildInputs = [ tc ]; } ''
            cd ${srcLint}
            find . -name '*.nix' -not -path '../.review-council/*' -print0 \
              | xargs -0 -r nixfmt --check
            touch $out
          '';

          # §1: statix lints. A non-zero exit must fail the check.
          statix = pkgs.runCommand "check-statix" { nativeBuildInputs = [ tc ]; } ''
            cd ${srcLint}
            statix check .
            touch $out
          '';

          # Dead Nix code — the class the framework's own probes report on.
          deadnix = pkgs.runCommand "check-deadnix" { nativeBuildInputs = [ tc ]; } ''
            cd ${srcLint}
            deadnix --fail .
            touch $out
          '';

          # The suite is a gate, not a CI nicety. `pkgs.git` is a real
          # dependency: baseline.py's changed_files shells out to `git diff` and
          # `git ls-files`, exercised against a throwaway repository.
          tests =
            pkgs.runCommand "check-tests"
              {
                nativeBuildInputs = [
                  tc
                  pkgs.git
                ];
              }
              ''
                cd ${src}
                python3 -m pytest tests/ -q
                touch $out
              '';

          # The golden suite, run the way CI runs it, so a moved score fails with
          # the number rather than a pytest traceback. Through the DEV dispatcher:
          # the fixtures live in tests/, which only the dev tree carries, and the
          # module refuses a direct invocation anyway.
          golden = pkgs.runCommand "check-golden" { nativeBuildInputs = [ tc ]; } ''
            ${dev}/bin/council golden --check
            touch $out
          '';

          # The toolchain must WORK, not merely exist: `python3 -m pytest` needs
          # pytest's runtime deps importable, which a bare symlinkJoin lacks.
          toolchain-built = pkgs.runCommand "check-toolchain" { } ''
            for b in statix deadnix nixfmt python3 pytest; do
              test -x ${tc}/bin/$b
            done
            ${tc}/bin/python3 -c 'import pytest, pluggy'
            touch $out
          '';

          # THE ANALYZER MATRIX. `toolchain-built` above asserts five binaries exist;
          # this asserts the ANALYZERS actually execute and parse, which is what
          # `council probes` feeds into beta and the deterministic half of the score.
          # Without it, a tool that is present but broken — wrong version, missing
          # runtime dep, unparsable output — lowers beta silently and the score
          # quietly becomes the LLM's judgement. It runs on EVERY system in
          # `systems`, so darwin is covered by the same claim rather than by a
          # separate assertion.
          probes =
            pkgs.runCommand "check-probes"
              {
                nativeBuildInputs = [ tc ];
              }
              ''
                mkdir -p fixture
                printf 'def add(a, b):\n    return a + b\n' > fixture/main.py
                printf '{ }\n' > fixture/flake.nix

                ${app}/bin/council probes --all --repo "$PWD/fixture" > probes.json

                ${tc}/bin/python3 - <<'PY'
                import json
                import sys

                doc = json.load(open("probes.json"))
                rows = doc["results"] if isinstance(doc, dict) and "results" in doc else doc
                ran = {r["tool"] for r in rows if r.get("ran")}

                # Every probe that needs no fixture content must have RUN. `ran`, not
                # `parsed` and not success: `flake-check` runs and reports FAILED on a
                # fixture with no outputs, and `osv-scanner` runs and reports nothing to
                # scan. Both are correct answers, so requiring a clean signal would
                # assert something untrue about a synthetic fixture.
                required = {
                    "bandit", "bash-n", "complexity", "deadnix", "declared-rules",
                    "dep-graph", "flake-check", "mypy", "nix-eval", "nixfmt",
                    "osv-scanner", "py-compile", "ruff", "secret-grep", "statix",
                }
                missing = sorted(required - ran)
                if missing:
                    print(f"probes that did NOT run: {missing}", file=sys.stderr)
                    print(f"ran: {sorted(ran)}", file=sys.stderr)
                    sys.exit(1)
                print(f"{len(ran)}/{len(rows)} probes ran")
                PY
                touch $out
              '';

          # One language. A .sh file in the tree means someone has added a second
          # way to do things, which is exactly what this layout exists to prevent:
          # every verb is a Python module reached through `council`.
          no-shell-scripts = pkgs.runCommand "check-no-shell" { nativeBuildInputs = [ pkgs.findutils ]; } ''
            found=$(find ${src} -name '*.sh' -not -path '*/.git/*' | head -5)
            if [ -n "$found" ]; then
              echo "shell scripts in the tree:" >&2
              echo "$found" >&2
              exit 1
            fi
            touch $out
          '';

          # The command surface, driven by the app's own verb table. Silent
          # breakage otherwise: a verb naming a module that was renamed, a data
          # file missing from the framework tree, and the audience split leaking
          # dev verbs into the shipped app.
          commands =
            pkgs.runCommand "check-commands"
              {
                nativeBuildInputs = [
                  tc
                  pkgs.jq
                ];
              }
              ''
                    ${app}/bin/council --verbs-json > verbs.json

                    # 1. every USER verb's module ships, and every DEV verb's does
                    #    NOT. This asserts flake.nix's shipping manifest against the
                    #    CLI's own verb table, so a new user verb whose module was
                    #    not listed fails here, and a dev module leaking into the
                    #    shipped tree fails here too.
                    jq -r '.[] | select(.audience=="user") | .script' verbs.json | sort -u > user-scripts.txt
                    while IFS= read -r s; do
                      test -f ${fw}/scripts/$s || { echo "shipped tree is missing scripts/$s" >&2; exit 1; }
                    done < user-scripts.txt

                    jq -r '.[] | select(.audience=="dev") | .script' verbs.json | sort -u > dev-scripts.txt
                    while IFS= read -r s; do
                      test -f ${fwDev}/scripts/$s || { echo "dev tree is missing scripts/$s" >&2; exit 1; }
                      if test -e ${fw}/scripts/$s; then
                        echo "scripts/$s belongs to a dev verb but ships in the image" >&2
                        exit 1
                      fi
                    done < dev-scripts.txt

                    # 2. the data files the modules resolve relative to themselves
                    for f in calibration.json eval-baseline.json score_reviews.py probes.py toolchain.py hermes_home.py hermes.py; do
                      test -f ${fw}/scripts/$f || { echo "shipped tree is missing scripts/$f" >&2; exit 1; }
                    done

                    # 3. the layout the modules derive their root from
                    test -d ${fw}/bots || { echo "shipped tree is missing bots/" >&2; exit 1; }
                    test -d ${fw}/skills || { echo "shipped tree is missing skills/" >&2; exit 1; }

                    # 3b. and the shipped tree carries nothing a review does not run
                    for f in tests pyproject.toml README.md flake.nix flake.lock; do
                      if test -e ${fw}/$f; then
                        echo "$f ships but nothing at review time reads it" >&2
                        exit 1
                      fi
                    done

                    # 4. the bare command is informative and succeeds
                    ${app}/bin/council > /dev/null || { echo "council with no args failed" >&2; exit 1; }
                    ${app}/bin/council --help > /dev/null || { echo "council --help failed" >&2; exit 1; }

                    # 5. every user verb starts. --help is safe on all of them: the ones
                    #    that parse arguments answer it, the ones that act get it here.
                    jq -r '.[] | select(.audience=="user") | .verb' verbs.json > user-verbs.txt
                    while IFS= read -r v; do
                      ${app}/bin/council $v --help > /dev/null || { echo "council $v --help failed" >&2; exit 1; }
                    done < user-verbs.txt

                    # 6. the audience split is real: a dev verb must NOT be in the shipped
                    #    app, and MUST be in the devshell's.
                    jq -r '.[] | select(.audience=="dev") | .verb' verbs.json > dev-verbs.txt
                    while IFS= read -r v; do
                      if ${app}/bin/council $v --help > /dev/null 2>&1; then
                        echo "council $v is dev-only but the shipped app accepts it" >&2
                        exit 1
                      fi
                      ${dev}/bin/council $v --help > /dev/null || { echo "council $v --help failed in the devshell" >&2; exit 1; }
                    done < dev-verbs.txt

                    # 7. setup dispatches, and rejects a bad sub-verb rather than doing
                    #    something surprising
                    if ${app}/bin/council setup nonsense > /dev/null 2>&1; then
                      echo "council setup accepted an unknown sub-verb" >&2
                      exit 1
                    fi

                    # 8. an unknown verb is refused, not silently treated as a repo path
                    if ${app}/bin/council definitely-not-a-verb > /dev/null 2>&1; then
                      echo "council accepted an unknown verb" >&2
                      exit 1
                    fi

                    # 9. the modules are not programs. A direct invocation must be
                    #    REFUSED and the same verb through the CLI must WORK, so this
                    #    fails both when the guard is dropped and when it is too eager.
                    #    That is the property keeping someone from running `corpus`,
                    #    `setup skill` or `review` by hand.
                    if python3 ${fw}/scripts/probes.py --list > /dev/null 2>&1; then
                      echo "scripts/probes.py ran without going through council" >&2
                      exit 1
                    fi
                    ${app}/bin/council probes --list > /dev/null || { echo "council probes --list failed" >&2; exit 1; }
                touch $out
              '';
        }
        # The image is a Linux userspace — `dockerTools` cannot build one from darwin —
        # so the same guard as the `container` output applies. Building it IS the
        # proof: `.#container` is a pure nix derivation over the same attrs as the
        # runtime tree, so a successful build is the whole claim, and no docker daemon
        # is involved because the output is a tarball. That is why this can be a check
        # where the VM test cannot (KVM) and why the image no longer needs a separate
        # CI job to be verified.
        // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          container = pkgs.runCommand "check-container" { } ''
            test -s ${builders.mkContainer pkgs}
            touch $out
          '';
        };

      devShells = {
        default = pkgs.mkShell {
          name = "review-council";
          packages = [
            (builders.mkToolchain pkgs)
            (builders.mkActivate pkgs)
            # The FULL verb set, dev verbs included. This is the only surface with
            # `council ablate` / `council calibrate` / `council corpus`, because
            # working on the framework is exactly what a devshell is for.
            (builders.mkDispatcher pkgs "dev")
          ];
          shellHook = ''
            echo "review-council devshell — pinned toolchain on PATH"
            echo "  nixpkgs: ${nixpkgsRev}"
            echo "  tools:   $(command -v statix >/dev/null && echo statix) $(command -v deadnix >/dev/null && echo deadnix) $(command -v nixfmt >/dev/null && echo nixfmt) $(command -v ruff >/dev/null && echo ruff) $(command -v gitleaks >/dev/null && echo gitleaks)"
            echo "  run:     council --help   (every verb; the shipped app has the user ones)"
          '';
        };
      };
    };
}
