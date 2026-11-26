# Tasks

## 1. Scope each check's input

- [x] 1.1 Add a `scope` helper over `lib.fileset` and per-check path lists.
- [x] 1.2 Give every check its own fileset; `mkCheck` takes the paths.
- [x] 1.3 Carry tool configuration (`pyproject.toml`, `pyrightconfig.json`,
      `check-nix.allow`) in every scope, because a scoped copy without it checks
      with different rules.
- [x] 1.4 Snapshot a git repository inside each scoped copy, because the registry
      and several tests ask git questions.

## 2. Bound the mutation campaign

- [x] 2.1 Move the serial loop into a scoring function.
- [x] 2.2 Run the mutants through a bounded pool, one worker per core.
- [x] 2.3 Keep the verdict identical: every mutant, full suite, every one caught.

## 3. Guard the scopes

- [x] 3.1 Assert every scope path exists, so a typo is an evaluation error.
- [x] 3.2 Assert `testScope` covers every tree the suite opens.
- [x] 3.3 Assert every `mkCheck` call names a scope.
- [x] 3.4 Assert every check that runs the suite carries `testScope`.

## 4. Evidence

- [x] 4.1 A docs, spec or changelog edit rebuilds 5 checks where it rebuilt 11.
- [x] 4.2 A README edit rebuilds 6; a source edit still rebuilds 11, as it must.
- [x] 4.3 Mutations: 1911 s serial, 215 s parallel, 72/72 both ways.
- [x] 4.4 `nix flake check --keep-going` passes.
- [x] 4.5 `./bin/council-verify` holds.
