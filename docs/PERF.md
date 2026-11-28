# What the gate costs, and why

Every number here was measured on this machine, not estimated. The method is at the
bottom; if a figure has no command behind it, it does not belong in this file.

## The shape of the cost

One mutant = one run of the **whole** suite against a mutated tree. That is the unit, and
everything follows from it:

```
campaign  ≈  (mutants × suite) / workers  +  one baseline suite
          =  (72 × 26.7s) / 12           +  27s
          =  160s + 27s  (measured 258s: the pool runs at ~73%, not 100%)
```

The suite is paid **72 times**. Nothing else in the gate is multiplied like that, which is
why the campaign is 84% of the total and why every optimisation question is a question
about that product.

## Measured steps

Workstation: 12 cores, warm store, `devshell` unless noted. 2026-11-28.

| step | wall | env |
|---|---:|---|
| devshell start | 0.15 s | devshell |
| ruff | 0.17 s | devshell |
| mypy | 0.6 s | devshell |
| pyright | 2.8 s | devshell |
| pytest (full suite) | 27.0 s | devshell |
| claims (265, batched per file) | 14.8 s | devshell |
| differential | 0.2 s | devshell |
| **mutations (72)** | **257.8 s** | devshell, 12 workers |
| mutations, identical tree (cached) | **1.2 s** | devshell |
| `nix flake check`, warm | 4.3 s | nix build sandbox |
| `nix flake check`, full | ~245 s | nix build sandbox |

Inside the suite, the top twelve tests are 11.3 s of the 26.5 s and every one of them
spawns a subprocess. Interpreter startup alone is 18.3 ms per spawn, and importing
`council.cli` adds ~1 ms — so a spawn costs about as much as a trivial test, and the suite
is 700 of them.

## What moved, and by how much

| change | measured effect |
|---|---:|
| claims batched per file (251 → 45 processes) | 21.4 s → 14.8 s |
| mutation shards 4 → 8 in CI | 247–252 s → 160–214 s per job |
| bwrap probe through the devshell | −30 s per CI job |
| mutation cache, identical tree | 326 s → **1.2 s** |
| local binary cache, cold store, same tree | 245 s → 23 s |

## What does **not** help, measured

- **Test selection per mutant.** Two designs, 138.9 s and 90.0 s, both rejected: they
  changed which claims a mutant was reported to break. A subset may prove a catch; only
  the whole suite may prove a miss.
- **Faster imports.** `import council.cli` is ~1 ms over interpreter startup. The idea
  that lazy imports would cut the suite was wrong by two orders of magnitude.
- **A binary cache for a new commit.** Every check is a new derivation, so nothing is
  substitutable; measured 328 s with the cache against 310 s without.

## The cache

`tools/mutation_check.py --cache PATH` records each verdict under a digest of everything
that can change it: `src/`, `tests/`, `claims.toml`, the tool itself, and the interpreter.
A hit means a byte-identical experiment, never a guess. `--no-cache` scores everything;
the Nix derivation passes it, because Nix already caches the whole check and the sandbox
is read-only.

The guarantee is pinned by `tests/test_mutation_cache.py` and the claim
`a-cached-verdict-is-keyed-to-the-tree`.

## Reproducing

```bash
nix develop -c python -m pytest -q -p no:cacheprovider          # the suite
nix develop -c ./bin/council-verify                              # the claims
nix develop -c python tools/mutation_check.py                    # the campaign, cached
nix develop -c python tools/mutation_check.py --no-cache         # every mutant, from scratch
nix flake check                                                  # the whole gate
```

Timing a step: `/usr/bin/time` is not installed here; use
`s=$(date +%s%N); … ; echo $(( ($(date +%s%N)-s)/1000000 ))ms`.
