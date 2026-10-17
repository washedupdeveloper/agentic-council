# Optimisation research — compute, structure, and what the repo produces

Every number here was measured on this machine. Where a measurement failed or was
later found wrong, that is stated rather than quietly dropped — two of the numbers
below are corrections of my own earlier work.

Reproduce anything here with the scripts named in each section; they all live in
`~/.hermes/cache/scratch/` and none of them touch the tracked tree (each copies the
repo to a scratch directory first).

---

## 1. The toolchain ships tools nothing executes

`toolNames` in `flake.nix` declares 24 tools. Fifteen are never named in
`scripts/probes.py`, and **none of the fifteen is in `expected_tools`**, which is what
`scripts/score_reviews.py` computes beta from. The scored Nix tools are:

| dimension | scored nix tools |
|---|---|
| security | `statix`, `secret-grep` |
| correctness | `flake-check`, `nix-eval` |
| readability | `nixfmt`, `statix`, `deadnix` |
| performance | `nix-eval-time` |
| architecture | `dep-graph`, `declared-rules` |

Everything else in the toolchain is either a rubric *prose suggestion* or a mention in
`docs/AUTONOMY.md`. Eleven of those entries cost 313.6 MB of closure.

### 1.1 Marginal cost per tool — the number that matters

Individual closures overlap heavily, so `nix path-info -S nixpkgs#<tool>` overstates
what removing a tool frees. The only honest measure is a rebuilt toolchain's closure,
so each row below is one rebuild with that single entry dropped
(`scratch/single-tool-experiment.py`).

| tool | frees | % of toolchain | named as a command by |
|---|---|---|---|
| **vulnix** | **193.3 MB** | **19.7%** | `reviewer-security` |
| nix-fast-build | 25.1 MB | 2.6% | `reviewer-correctness` |
| nil | 9.5 MB | 1.0% | prose only |
| tokei | 6.3 MB | 0.6% | `reviewer-readability` |
| nix-tree | 5.7 MB | 0.6% | `reviewer-performance` |
| nixd | 5.6 MB | 0.6% | prose only |
| nix-diff | 4.3 MB | 0.4% | `reviewer-performance` |
| nix-du | 3.8 MB | 0.4% | prose only |
| cloc | 1.5 MB | 0.1% | prose only |
| yamllint | 0.6 MB | 0.1% | prose only |
| treefmt | **0.0 MB** | 0.0% | `reviewer-readability` |

`treefmt` freeing exactly nothing is the clearest evidence that per-tool closures
overlap: the `formatter` output already execs `pkgs.nixfmt-tree`, which *is* a
treefmt, so the standalone entry shares every dependency it has.

### 1.2 `vulnix` is 62% of the entire saving — shipped on demand, never probed

Measured by rebuild, with the edit verified before the build:

```
toolchain closure   983.3 MB  ->  790.0 MB     (-193.3 MB, -19.7%)
container           333 M     ->  307 M        (-26 MB compressed)
                    1.1 G     ->  867 M        (-233 MB uncompressed)
```

Five facts about it, each checked. Together they are why the answer is to **ship it
and never probe it** (§8) rather than either extreme:

1. **It is the single largest member of the closure.** Ranking every path in the
   toolchain by closure size, `vulnix-1.12.5` is first at **555 MiB** — ahead of
   `nix-2.34.8-dev` (376 MiB), `python3.14-bandit` (335 MiB) and `nix-fast-build`
   (323 MiB). Its own closure overlaps the rest, which is why removing it frees 193 MB
   rather than 555 MB, but nothing else in the toolchain comes close to its footprint.
2. **Not scored.** `security` scores `statix` and `secret-grep`. `vulnix` is absent from
   `expected_tools`, so removing it cannot move beta. Verified by re-running
   `council doctor` on a reduced toolchain: **beta 1.00 in every dimension, verdict
   `ready`**.
3. **Not probed.** `scripts/probes.py` names `osv-scanner` (`rc-osv-*`), `bandit`,
   `mypy`, `ruff`, `pytest`, `statix`, `secret-grep`, `deadnix`, `nixfmt`,
   `nix-eval`, `flake-check`, `dep-graph`, `declared-rules`, `nix-eval-time`,
   `py-compile`, `bash-n`. It never names `vulnix`. The CVE signal already comes from
   `osv-scanner`.
4. **Its whitelist does not exist.** The rubric line is
   `vulnix --system -w whitelist.toml --json`. No `whitelist.toml` exists anywhere in
   the repo — a reviewer following that line would fail on a missing file.
5. **The project calls it unreliable.** `skills/reviewer-security/SKILL.md:94` annotates
   the same line `# CVE count (unmaintained, high FP)`.

So the line is a suggestion the project itself flags as high-false-positive, pointing at
a file that isn't shipped, for a signal `osv-scanner` already provides, and it is the
single largest cost in the toolchain.

### 1.3 The remaining ten are not worth the churn

Removing the five tools a rubric does *not* name (`nixd`, `nil`, `yamllint`, `nix-du`,
`cloc`) frees **20.9 MB — 2.1%** (`scratch/tier-experiment.py`). Their dependencies are
almost entirely shared with tools that stay. Removing the six a rubric *does* name
(`vulnix`, `nix-tree`, `nix-diff`, `nix-fast-build`, `tokei`, `treefmt`) frees
**234.7 MB — 23.9%**, but that means editing six shipped rubric lines.

Removing all eleven at once:

```
toolchain   983.3 MB -> 669.7 MB   (-313.6 MB, -32%, -87 paths)
container   333 M    -> 287 M      (-46 MB compressed)
            1.1 G    -> 806 M      (-294 MB uncompressed)
```

Validated after the removal: **406 tests pass, mypy clean, ruff clean,
`nix flake check` reports `all checks passed!`, beta 1.00 in every dimension.**

### 1.4 The score does not depend on any of this

The decisive check: on the reduced toolchain, `council doctor` reports
`beta = 1.00` for `security` (4/4), `correctness` (4/4), `readability` (5/5),
`performance` (2/2), `architecture` (2/2), verdict `ready`. The removed tools were
never deterministic signal.

---

## 2. Three of my own measurements were wrong — stated so they are not reused

**`nix path-info -rS` double-counts.** I summed every row and reported a 27 GB
toolchain closure. Each row of `-rS` carries *that path's* closure size, so summing
them counts shared dependencies once per dependent. The toolchain is **983 MB**. The
correct call is `nix path-info -S <root>` (one row) plus `nix path-info -r <root>`
for the count.

**A failed `nix develop` silently skipped an edit.** I edited `flake.nix` inside a
`bash -c` that only ran if `nix develop` succeeded; it did not, so the edit never
happened and the build produced an unchanged image, which I nearly read as "the tool is
not in the image". Two further attempts failed the same way — once because NixOS has no
system `python3` outside the devshell, so the edit script did not run at all. The
number in §1.2 comes from a run that prints `occurrences of vulnix in flake.nix now: 0`
before building.

**A `bc`-based timer reported 0.00s for everything.** I timed four `nix` invocations
with `date +%s.%N` and `echo … | bc`. **`bc` is not installed on this system**, so the
arithmetic produced nothing and every row printed `0.00s` — a set of numbers that looked
like "nix is instant" and was pure garbage. Re-measured with Python timing:

| command | warm |
|---|---|
| `nix eval --raw .#toolchain.drvPath` | 2.34s |
| `nix eval --raw .#vm-test.drvPath` | **3.90s** |
| `nix flake check --no-build` | 1.88s |
| `nix develop --command true` | 0.17s |

So a warm flake evaluation costs roughly **2–4 seconds per invocation**, and the
single most expensive thing to evaluate is the VM test — consistent with its 608-line
`testScript`. Any timer written for this repo must not depend on `bc`, and must be
checked against a known-slow command before its output is believed.

Three measurements of mine were wrong, and all three were wrong the same way: the
measuring instrument silently returned nothing or the wrong thing, and the result looked
plausible. Verify the input changed, and verify the timer ticks.

---

## 3. Structure

| | value |
|---|---|
| `flake.nix` | **1,351 lines, one file** |
| of which `mkVmTest` | **608 lines (45%)** |
| python (scripts) | 10,315 lines |
| python (tests) | 6,661 lines |
| nix (total) | 1,453 lines |
| shell | **0 lines** |
| markdown | 4,243 lines |

The NixOS VM test's `testScript` is 608 lines of shell inside a Nix string, in the same
file as everything else. That is 45% of `flake.nix` for one output, and it is the main
argument for splitting the file.

Container facts, measured: **99 layers**, tarball 313 MiB, and its layers hold 1.06 GB
uncompressed — the layers are gzipped, so the download is not the image.

`flake.nix` has no flake-parts and no clan. Whether that should change, and in which
order of the clan → flake-parts → nix priority the user asked for, is the subject of
the second half of this research and is reported separately.

---

## 4. Runtime: the prompt carries the probe JSON five times

`council_loop.py` builds each sample prompt with
`probe_json=json.dumps(probes, indent=2)` — the full probe document, inline, in every
sample. Probes run once per round, but the JSON is serialised into each of the five
sample prompts.

Measured on the review-council self-review run: `probes.json` is 24,272 chars, of which

| form | chars | share |
|---|---|---|
| raw | 24,272 | 100% |
| findings + signal only | 16,527 | 68.1% |
| metadata only (tool, ran, signal, finding count) | 1,092 | 4.5% |

So roughly a third of the inlined JSON is `notes` / raw output that is not the evidence
itself. On this repo the absolute numbers are small; on `hermes-skills` the same file is
~397 KB, and there the third is ~130 KB per sample per round.

For scale: the instruction template itself is **2,751 characters** with 15 placeholders
(`{probe_json}`, `{rubrics}`, `{stacks}`, `{carry_block}`, `{goal_*}` …). The probe JSON is
the largest thing injected into it, which is why it is the lever worth measuring.

This is a token-cost lever, not a correctness one, and it is the only runtime
optimisation found that does not change what the reviewers see. It is **not measured
end-to-end** — I have not run a round with condensed probes to confirm the review
quality holds, so it is a candidate, not a recommendation.

---

## 5. The clan → flake-parts → nix verdict

The user asked for code written "the clan way", then "the flake-parts way", then "the
nix way", in that priority order. Applied honestly to this repository, priority 1
resolves to *not adopting clan*, and priority 2 is where the real work is. Here is the
evidence for that, not an assumption.

### 5.1 "The clan way" — clan prescribes nothing for this flake

Clan is `clan-core` (hosted at `git.clan.lol/clan/clan-core`; the old
`github:SnowflakePowered/clan-core` is a 404). It is **a framework for fleets of
VPN-connected NixOS machines** — inventory, sops secrets, `nixos-anywhere` deploys. Its
own docs are entirely machine- and service-oriented.

Is there a documented clan convention for a flake that is a *tool* rather than a set of
machines? **No.** Checked three ways:

1. **`clan-core` itself is the only worked example**, and it is a tool flake that is also
   a clan: it declares `clan.meta.name = "clan-core"` and keeps exactly one dummy test
   machine.
2. **The `flake-parts-minimal` template is a clan with zero machines** — so zero machines
   is *tolerated*, which means the clan module imposes nothing on a machine-less flake.
3. **But `clan.meta.name` is required** (`types.strMatching "[a-zA-Z0-9_-]*"`, no
   default). So importing the clan flake module forces this repo to name a clan it does
   not have.

Adopting clan here would buy nothing and cost a required option plus a conceptual lie
("this tool is a clan of machines"). The clan-relevant act that *would* apply is
publishing a `clanService` or a flake module so clan users can consume us — and that is
only meaningful if we ship NixOS services, which we do not.

Also worth recording because it is easy to get wrong: **`clanModules` is not a current
clan flake output.** It was the old service format. The current form is the
`clan.modules` option plus `clanServices` (module class `clan.service`). And
`nixosConfigurations` are generated from `clan.machines`/the inventory, **not** from
`clan.meta` — `meta.name`/`meta.domain` are identity only.

**Determination: do not adopt clan.** Priority 1 is satisfied by establishing that it
does not apply. Recorded here so the decision is not silently revisited.

### 5.2 "The flake-parts way" — a good fit, and the main structural win

The measured structure is the argument:

| binding in `flake.nix` | lines |
|---|---|
| **`mkVmTest`** | **608** |
| `mkStubHermes` | 87 |
| `mkContainer` | 85 |
| `mkDispatcher` | 78 |
| `mkImageRoot` | 74 |
| `mkToolchain` | 47 |
| `flakeFiles` | 39 |
| `mkSkill` | 36 |
| `mkFramework` | 33 |
| `mkContainerEntrypoint` | 33 |
| `mkActivate` | 25 |
| `mkImagePrepTools` | 19 |
| `mkContainerNixConf` | 17 |
| **total** | **1,351 (one file)** |

`mkVmTest` is **45% of the file** — 608 lines of shell inside a Nix string, sitting in
the same file as the toolchain, the container and the dispatcher. That, not
`forAllSystems` boilerplate, is the reason to split.

flake-parts is actively maintained (last commit 2026-10-02) and used by clan-core itself.
**It has no version and no tags** — GitHub Releases says "There aren't any releases
here" — so it is pinned by revision in `flake.lock`, not by a version number.

What it would buy here:

- **Module splitting without losing the `let` scope.** `imports` takes files or
  `inputs.<flake>.flakeModules.default`; the documented bridge for lexical variables is
  `flake-parts-lib.importApply ./mod.nix { localFlake = self; }`. Six modules would replace
  1,351 lines in one file.
- **`perSystem` replaces `forAllSystems`** and transposes into
  `flake.<attr>.<system>` for `packages`/`checks`/`apps`/`devShells`/`formatter`/
  `legacyPackages`. `systems` becomes a top-level option, a sibling of `perSystem`.
- **Merge semantics** across modules for the standard outputs.

What it would cost:

- **Two extra entries in every consumer's `flake.lock`** (`flake-parts` and its
  `nixpkgs-lib`). Mitigable at our end with
  `flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs"`. Output consumers are unaffected —
  nobody needs flake-parts to `nix build` our packages.
- **A module mental model**: `config` vs `options`, `self'` vs `self` (bare `self` inside
  `perSystem` throws by design), and the documented recursion traps — the old
  `mkFlake { inherit self; }` form, and perSystem `pkgs` wired into a
  `nixosConfigurations` hostPlatform.
- **`perSystem` is evaluated for every declared system** on `nix flake check
  --all-systems`, so it must stay cheap.

Two corrections to the common lore, both checked against the source: **`easyOverlay` is
the only built-in "easy" helper** (`easyHosts` is third-party, `tgirlcloud/easy-hosts`;
`easyModules` does not exist — the real module is `flakeModules.modules`). And flake-parts
**does not warn against** `follows` on `nixpkgs-lib`; the ecosystem sets it routinely.

### 5.3 "The nix way" — what stays

Under either structure the output shape is the plain flake schema: `packages`,
`checks`, `apps`, `devShells`, `formatter`, `legacyPackages` per system, plus
`lib.optionalAttrs` for Linux-only outputs (the container). Nothing in flake-parts
changes what a consumer sees.

### 5.4 Proposed split, if the user wants it

Anchored to the measured line spans:

| module | contents | lines |
|---|---|---|
| `nix/toolchain.nix` | `mkToolchain`, `mkActivate` | 72 |
| `nix/framework.nix` | `mkFramework`, `mkSkill`, `flakeFiles` | 108 |
| `nix/dispatcher.nix` | `mkDispatcher` | 78 |
| `nix/container.nix` | `mkContainer*`, `mkImagePrepTools`, `mkImageRoot` | 228 |
| `nix/stub-hermes.nix` | `mkStubHermes` | 87 |
| `nix/vm-test.nix` | `mkVmTest` | **608** |
| `flake.nix` | `systems`, `perSystem`, `flake`, `imports` | remainder |

This is a proposal with a measured basis, **not** something I have built or verified.
Any conversion must keep `nix flake check` green and the 406 tests passing, or it does
not ship.

---

## 6. Python: dead code, duplication, complexity

Verified by re-grepping every claim below. `ruff` and `mypy` are both **clean** (0
findings, 23 files), so nothing here is a lint failure — it is code that exists and does
nothing.

### 6.1 Dead code — four confirmed, one with a live CLI promise attached

| what | where | evidence |
|---|---|---|
| `pick_threshold` | `scripts/calibrate.py:298` | 1 reference repo-wide = its own `def` |
| `calibrate_ladder` | `scripts/calibrate.py:389` | 1 reference = its own `def` |
| `recalibrate` | `scripts/calibrate.py:321` | never called; the third hit is an argparse *help string* |
| `head_sha` | `scripts/baseline.py:107` | only its own `def` |
| `carried_llm_scores` | `scripts/baseline.py:319` | only its own `def`; body is `return dict(baseline_scores)` |

The sharpest one: the verb table at `scripts/council.py:40` describes the `calibrate` verb
as **"recalibrate the threshold and curves"** — but `calibrate.py`'s `main()` dispatches
only to `build_eval_ladder` (`--build-eval`) and `calibrate()` (`--good`/`--bad`). It
never calls `recalibrate()`. **The CLI advertises a capability the code cannot reach.**
`docs/CALIBRATION.md:147` compounds it by documenting `calibrate.recalibrate(...)` as
the way to re-derive the threshold.

Either wire it (`calibrate --recalibrate <measured.json>`) or delete it and the two doc
claims. Leaving it is the worst option: a documented, advertised, unreachable function.

Also: `scripts/probes.py:579` binds `baseline_path` and never reads it.

### 6.2 Duplication — five real clusters

| cluster | locations | note |
|---|---|---|
| module-from-file loader | `golden.py:33`, `sample.py:33`, `merge.py:28`, `council_loop.py:402/528/548`, `probes.py:114`, `entrypoint.py:180` | **8 copies**; `golden.py:33 _load` is already the clean generic version — the others should import it |
| `kloc` + `SOURCE_SUFFIXES` | `calibrate.py:32/27`, `score_reviews.py:312/25` | near-identical, and they **diverge on the floor**: calibrate floors at `0.001`, score_reviews returns `0.0` with no floor — the same repo yields two densities |
| fingerprint | `ablate.py:222`, `baseline.py:34`, `council_loop.py:771` | first two are byte-identical (deliberately, pinned by a test); the **third diverges** — it does not strip punctuation, so a carried finding and a re-found one can hash differently |
| hermes subprocess wrapper | `install_bots.py:109`, `sync_to_skill.py:54` | identical call, different return shape |
| loose-JSON reader | `ablate.py:246`, `council_loop.py:780` | same code-fence-strip + brace-slice recovery |

The fingerprint cluster is the one with defect potential, not just tidiness.

### 6.3 Complexity — 7 of 27 are worth splitting

27 functions have cyclomatic complexity ≥ 15 (average across 301 blocks: B/6.74). Most
are inherently branchy CLI mains, output parsers, scoring math or renderers. The seven
that are genuinely worth splitting:

| CC | function |
|---|---|
| 47 | `sync_to_skill.py:222 main` — arg parsing + destination guard + six copy phases + pruning in one body |
| 42 | `score_reviews.py:812 improvement_opportunities` — three sequential output-building loops |
| 37 | `council_loop.py:832 merge_generalist_samples` — dedupe / bucket / account are separable |
| 36 | `install_bots.py:134 install_member` — profile-create / skill-copy / prune / config |
| 31 | `council_config.py:189 validate` — flat sequence of independent checks (borderline) |
| 27 | `council_loop.py:1465 render_next_steps` — markdown builder |
| 21 | `council_loop.py:1393 decide_stop` — each stop reason is an independent predicate |

Maintainability index flags two modules as the least maintainable: `council_loop.py`
(1,887 lines, MI **C/0.00**) and `score_reviews.py` (1,105 lines, MI **B/10.20**). All
other 20 modules grade A.

### 6.4 One corrupted docstring

`scripts/council_loop.py:519-523` — `_gate_module`'s docstring cuts a sentence mid-clause
("…cannot be compared") and immediately restates it. A botched merge of two drafts.

### 6.5 Standards: clean

`ruff check scripts tests` → **all checks passed**. `mypy scripts/` → **no issues in 23
files**. `from __future__ import annotations` in 23/23 files. 0 mutable default
arguments, 0 bare `except:`. Four `except Exception` sites, all annotated and all
converting to a degraded result rather than swallowing. 27 `subprocess` calls: 21 capture
output without `check=` by design, and an AST check confirms **19 of 19 assigned results
are read, 0 assigned-but-ignored**. 0 `open()` without `encoding` (6 scanner hits were
`"rb"` or a local helper that sets UTF-8). 650 f-strings, 8 `.format()` (all multi-line
prompt templates), 0 `%`. Only gap: two unannotated `loop` params at `sample.py:40` and
`sample.py:66`.

---

## 7. The flake-parts conversion — done, and what it preserved

Converted. `flake.nix` went from **1,351 lines in one file** to **~90 lines of
configuration**, with the construction moved to three modules:

| file | lines | contents |
|---|---|---|
| `flake.nix` | 90 | inputs, `systems`, `imports`, `flake` outputs |
| `nix/builders.nix` | 870 | every `pkgs -> derivation` builder, `toolNames`, the module lists |
| `nix/flake-module.nix` | 85 | the consumer-facing surface: packages, formatter, app |
| `nix/checks.nix` | 389 | this repo's own gates and the devshell |

The builders were moved as **text**, not retyped — a script cut the `let` block,
rewrote the 18 `./` path literals to `../` (a file under `nix/` resolves against
itself, so `${./scripts}` would have meant `nix/scripts`), and re-exported the 19
bindings through one `inherit`. Two edits were not mechanical and are asserted in
the script: `self.apps.${…}.council` became `config.apps.council` (bare `self`
throws inside `perSystem`), and the devshell banner's `nixpkgs.rev` became a
module-level `nixpkgsRev`.

### 7.1 The oracle: what is provably unchanged

Every output's derivation path was captured before and after. **Six are
byte-identical:**

```
packages.toolchain          q69gcv8qayk0vad33sm37rlcj3nxjh1l
packages.framework          0dcqzx77if8azxpvrbmkxg5b6vvrvia1
packages.default            q69gcv8qayk0vad33sm37rlcj3nxjh1l
packages.image-prep-tools   f27aaax5ac6f4ig3y3rrakhsdv31i1pz
checks.toolchain-built      5yhmx984gvnlb103fijj8a462ihxl775
checks.module-evaluates     bdx5ysnf4sw2h6hq99wbdrxp7a2wb9as
```

That is the strongest available evidence: the toolchain, the framework tree, the
home-manager module evaluation and the toolchain check are the *same derivations*
as before, so the path rewrites and the module split changed nothing they build.

The other 16 changed, and every one is explained by `flake.nix`/`flake.lock`/`tests/`
being inputs to it: the 10 that embed the flake files (`skill`, `container`,
`image-root`, `review-council`, `vm-test`, `commands`, `golden`, `probes`,
`skill-layout`, `container`-check), the 5 that read the whole tree via `${src}`
(`nixfmt`, `statix`, `deadnix`, `no-shell-scripts`, `tests`), and `dev-framework`,
which ships `tests/` — and I edited a test file.

### 7.2 The two failures, and what caught them

1. **`checks.nixfmt` failed** on all three new files — they were generated, not
   formatted. `nixfmt` fixed it.
2. **`checks.tests` failed** one test: `test_the_launchers_pass_the_flake_location`
   read `flake.nix` by name and asserted `REVIEW_COUNCIL_FLAKE_DIR` appeared twice.
   The launchers now live in `nix/builders.nix`. The test was rewritten to read
   every `.nix` file except fixture data, so the next move does not break it.

That second failure was also *evidence*: the suite ran from `${src}` and found
`tests/`, which is what proves `${../.}` resolves to the repo root and not to
`nix/`.

### 7.3 The split broke the deployed skill, and the check could not see it

Found after the conversion was already committed, by asking what the deployed skill's
`flake.nix` would do with the modules absent. It failed outright:

```
error: path '.../nix/flake-module.nix' does not exist
```

A flake's `imports` are **eager**: they are resolved before any output is chosen, so
the deployed skill could not evaluate *anything* — `.#toolchain` included, which is the
one thing shipping the flake there exists to provide. Verified as a regression rather
than pre-existing, by running the pre-split `flake.nix` (from `b9b6472`) in the same
deployed layout: **that evaluates fine**, because everything was inline.

`checks.skill-layout` could not catch it because it asserted file *existence* only, and
every file it listed did exist. A flake that references files which are not shipped
satisfies that check and evaluates to nothing.

**Three copiers ship those two files, and all three needed the modules:**

| copier | what it is for |
|---|---|
| `mkSkill` (nix) | `.#skill`, the read-only store path Hermes loads |
| `flakeFiles` (nix) | `REVIEW_COUNCIL_FLAKE_DIR` — what the launcher and `setup skill` read |
| `sync_to_skill.py` (python) | the repo → mount mirror |

The third is the interesting one: its `flake_dir` *is* the `flakeFiles` derivation, so
fixing `sync_to_skill.py` first did nothing until `flakeFiles` staged the modules too.
Making the missing-modules case **fatal** rather than a silent skip is what surfaced
that — the same defect its own comment already described one level up ("skipped BOTH
files silently ... nothing anywhere said so").

**The check now derives the requirement** instead of trusting a hand-written list: it
strips comments from the deployed `flake.nix`, extracts every `./nix/...` reference, and
fails if any is absent — with a guard that fails if the extraction itself matches
nothing, so it cannot pass vacuously.

All three now verify: `.#skill` evaluates, the mirror evaluates, and the gate is green.

One more real failure came out of this, and it is the same class: the portability test
asserted `REVIEW_COUNCIL_FLAKE_DIR` appeared exactly **twice** across all Nix sources. A
comment explaining what the staged tree is for mentions the name, so a doc line failed
the test. It now counts **assignments** (`NAME=`), which is the property the test
actually cares about.

### 7.4 Integrating it into another flake

`flake.flakeModules.default` is the integration point:

```nix
imports = [ inputs.review-council.flakeModules.default ];
```

which yields `packages.{toolchain,council,skill,framework,…}`, `formatter` and the
`council` app — the same definitions this repo builds for itself. The home-manager
module stays a separate output (`inputs.review-council.homeManagerModules.default`),
which is how HM modules are consumed anyway.

Cost: `flake-parts` plus its `nixpkgs-lib` would appear in a consumer's
`flake.lock`; the flake sets `flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs"`
so only one entry is added.

### 7.5 Clan: not adopted, and why that is the right call for priority 1

Clan prescribes nothing for a flake that deploys no machines, and importing its
flake module forces a required `clan.meta.name` for a clan this repo is not. The
clan-relevant act would be publishing a `clanService`, which needs NixOS services
to mean anything. So "the clan way" is satisfied by establishing that it does not
apply — recorded here so the decision is not silently revisited.

---

## 8. `vulnix`: what it does, and remove-vs-implement

### What it actually achieves

`vulnix` is a **store-closure** CVE scanner. From its own `--help`:

```
-S, --system     Scan the current system.
-C, --closure    Examine the closure of an output path (runtime dependencies).
-w, --whitelist  Load whitelist from file or URL
-m, --mirror     Mirror to fetch NVD archives from.
```

It resolves a Nix closure, maps each package to name+version, and matches those
against the NVD feed. That is a genuinely different question from what
`osv-scanner` answers: `osv-scanner` reads **declared dependency lockfiles**
(PyPI, npm, cargo, Go, Ruby, Composer), so it sees what a manifest admits to;
`vulnix` sees **what is actually built into a closure**, including transitive
store paths no manifest mentions.

### The pros of keeping it, and of doing it properly

- **It is the only closure-level scanner in the set.** For a Nix-focused reviewer
  that is on-mission, and nothing else in the toolchain substitutes for it.
- Implementing it properly means: ship a maintained `whitelist.toml`, add a
  `vulnix` probe to `probes.py`, and add it to `expected_tools` so it contributes
  to beta — i.e. make it a first-class deterministic signal.

### The cons, each verified

- **193.3 MB, 19.7% of the toolchain** and 26 MB off the container. Its own closure
  is 555 MiB, the single largest member of the toolchain.
- **Unmaintained upstream.** `research/nix-tooling.md:47` records it as
  "**Unmaintained** but still the only store/CVE scanner", and `:414` names the
  Nixpkgs security tracker as the community replacement.
- **High false-positive rate, by construction.** The same table
  (`research/nix-tooling.md:182`): "Matches name+version against NVD; upstream
  backports are invisible, so patched-but-same-version packages report as
  vulnerable. Whitelisting is mandatory to make it usable."
- **The whitelist it needs does not exist.** The rubric line is
  `vulnix --system -w whitelist.toml --json`; there is no `whitelist.toml`
  anywhere in the repo, so a reviewer following that line fails on a missing file.
- **It needs the network and varies by date.** `-m` fetches NVD archives, and
  `research/nix-tooling.md:403` classifies `vulnix` NVD data as
  *environment-dependent*, which is why it is excluded from scoring.
- **It contributes nothing to the score today.** `security` scores `statix` and
  `secret-grep`; `vulnix` is absent from `expected_tools`, so removing it cannot
  move beta. Verified: beta is 1.00 in every dimension with it removed.
- **`--system` audits the wrong thing for a repo review.** This is the decisive
  one. The council reviews a *repository*; `vulnix --system` scans the closure of
  **the machine or container running it** — in the review container, that is the
  council's own toolchain, not the tree under review. To scan the reviewed repo's
  closure you would first have to build its NixOS configuration, which the council
  does not do and should not start doing to justify a rubric line.

### Verdict: available on demand, never probed — APPLIED

Removing it was measured first and then reverted, deliberately. The user's call splits
the decision in two rather than taking either extreme: **ship it, do not run it.**
`vulnix` is back in `toolNames`, so it is on the toolchain PATH (devshell, container,
`nix shell .#review-council`), and it stays out of `probes.py`, so no routine review
pays for it.

The removal was real and its numbers stand — they are now the price of *availability*
rather than a saving:

```
toolchain closure   983.3 MB -> 790.0 MB   (-193.3 MB, -19.7%)
toolchain paths     212      -> 156        (-56)
```

Both halves of the final decision are verified, not asserted:

```
vulnix on the toolchain PATH     yes   ($toolchain/bin/vulnix, version 1.12.5)
'vulnix' in the probe set        False (17 probes: bandit, bash-n, complexity,
                                        deadnix, declared-rules, dep-graph,
                                        flake-check, mypy, nix-eval, nix-eval-time,
                                        nixfmt, osv-scanner, py-compile, pytest,
                                        ruff, secret-grep, statix)
'vulnix' executed on a real run  False
'vulnix' named in probes.py      False
toolchain closure                983.3 MB / 212 paths
```

`tests/test_probes.py::test_an_on_demand_tool_ships_but_is_not_probed` pins both
halves — shipped, and not probed — so neither can drift alone. It has teeth: wiring a
stub `vulnix` probe into `PROBES` makes it fail, and restoring the file makes it pass.

The rubric line in `skills/reviewer-security/SKILL.md` is restored as an explicit
**on-demand** step with its caveats attached (unmaintained; name+version matching hides
backports, so a whitelist is mandatory and none ships; `--system` scans the machine
running it, not the repo). The cheap routine answer sits beside it: the Nixpkgs
security tracker, which answers "does my pin have known CVEs" without a 555 MiB closure,
a mandatory whitelist, or a network fetch at review time. `docs/AUTONOMY.md` is back to
24 tools with the on-demand note, and both `research/nix-tooling.md` rows say "ships,
but is never probed".

Why not a Nix list of on-demand tools? Because nothing would read it, and a declared key
nothing reads is a dead key — the same defect §6.1 reports elsewhere. The distinction is
documented in the comment where a reader looks, and enforced by the test that reads both
sides.

---

## 9. The dead code — fixed, and what the fix taught

All of it is fixed and verified. Three of the five were **wired** rather than
deleted, because the CLI and the docs already promised them; two were deleted.

| symbol | outcome |
|---|---|
| `calibrate.recalibrate` | **wired** — `council calibrate --recalibrate <manifest> [--k K]` |
| `calibrate.calibrate_ladder` | **wired** — `council calibrate --ladder <manifest>` |
| `calibrate.pick_threshold` | **deleted** — provably unreachable (below) |
| `baseline.head_sha` | **deleted** — `since` comes from the round's meta |
| `baseline.carried_llm_scores` | **deleted** — an identity wrapper; the behaviour lives in `council_loop.apply_carry` |
| `probes.py:579` `baseline_path` | **deleted** — bound and never read |

`--build-eval` already produced a manifest whose entries carry
`{level,path,label,defects_seeded}` — exactly what `calibrate_ladder` reads — and
its `measured` output is exactly what `recalibrate` reads. The shapes already
lined up, which is why wiring was small. A malformed manifest is refused by name:
`has no 'measured' — it must be a calibration manifest, not a ladder`, `has no
'ladder' — make it with --build-eval`, `no such manifest`.

### 9.1 My first attempt was wrong, and exercising the code proved it

I first tried to make `pick_threshold` live as a documented fallback:
`choose_threshold(points) or pick_threshold(sweep)`. Running `--recalibrate` on a
label-less manifest returned `recommended_threshold: None`, which sent me to the
two implementations:

```
choose_threshold:  return None   when not bad or not good
sweep_threshold:   return []     when not n_bad or not n_good
```

**Identical conditions.** So whenever `choose_threshold` gives `None` the sweep is
empty, and `pick_threshold([])` also gives `None` — the `or` branch can only ever
contribute `None`. It is not a fallback, it is dead code wearing a fallback's
docstring, and the doc claiming otherwise was wrong. `pick_threshold` is now
deleted, the helper is gone, and `docs/CALIBRATION.md` states *why* there is no
fallback: a threshold derived from a one-class sweep would be a number with no
evidence behind it, so reporting nothing is the honest answer.

### 9.2 A real bug, found the same way

`recalibrate` did not carry `measured` through to its output, so a re-tuned
manifest could not be re-tuned again — which defeats the function's entire stated
purpose (measure once, re-tune many times). Fixed, and pinned by a test. Verified
end to end: `--recalibrate --k 1.4` → threshold 29.7536, then `--recalibrate` on
*that* output with `--k 2.5` → 25.8787.

### 9.3 The pros and cons of wiring recalibrate into the CLI

**Pros.** It makes the CLI's own description true — the `calibrate` verb is
described as "recalibrate the threshold and curves" and previously could not. It
makes `docs/CALIBRATION.md` true. It is genuinely useful: `k` and the selection
rule are free parameters, while measuring the ladder is the expensive half (every
probe against every rung), so re-tuning without re-measuring is the difference
between seconds and a full toolchain sweep. And the manifest shapes already
matched, so the change is small and has no new dependencies.

**Cons.** It adds two flags and a manifest-reading path to a verb that previously
took only paths — a bigger surface to keep honest. It makes a *file* an interface:
the manifest format is now a contract, and a change to `measured`'s shape breaks a
workflow rather than a test. It is also a feature, not a cleanup, and it sits in
`calibrate`, which is a **dev** verb — so nothing a shipped user runs changes.
Deleting instead would have been defensible and smaller: it needs one CLI
description and two doc paragraphs edited, and no new surface. I wired it because
leaving a documented, advertised capability unreachable is the worst of the three
options, and because the two doc sites would otherwise have to be corrected to say
the capability does not exist.

---

## 10. The duplication — consolidated into `scripts/_shared.py`

Five clusters were reported in §6.2. What each turned into:

| cluster | outcome |
|---|---|
| module loader ×8 | **kept** — §10.2 gives the reason, and it is not laziness |
| `fingerprint` ×3 | **one** — and `norm_path` ×2 with it: `baseline`'s and `ablate`'s copies were byte-identical, so all four delegate |
| `kloc` + `SOURCE_SUFFIXES` ×2 | **one** — and the divergence is now an explicit parameter, not an accident |
| `hermes` subprocess wrapper ×2 | **one** — `hermes_output` is `hermes_run(args)[1]` |
| loose-JSON reader ×2 | **NOT** consolidated — see §10.2 |

The diff is deliberately minimal: every module keeps the same public name and its
body delegates, so **no call site changed anywhere**. `_shared.py` was added to
`runtimeModules` in `nix/builders.nix`, because a shared module that does not ship is
a shared module that breaks the shipped tree — and that manifest is exactly what
`checks.commands` exists to catch.

### 10.1 The `kloc` divergence is now explicit

This was the one with teeth. The two copies differed in a way nobody had written
down:

```
score_reviews.kloc:  return total / 1000.0            # no floor
calibrate.kloc:      return max(total / 1000, 0.001)  # floored
```

Neither was wrong — the scorer wants `0.0` for an unmeasurable repo so it falls back
to raw counts, and the calibration wants a density that is always defined — but the
difference existed only as a coincidence of two copies. It is now a keyword
argument, `kloc(root, *, floor=0.0)`, and each caller states its own.

### 10.2 Three things I deliberately did NOT consolidate

**The module loader.** Eight sites look like duplication, and replacing them with a
plain `import` is the obvious fix. It is the wrong one here. `council` **execs** each
module (`subprocess.run([sys.executable, str(target)])`), so `sys.path[0]` is
`scripts/` at runtime — but a test or `entrypoint.py` loads a module **by path**,
where it is not. So a plain import either needs a package (which a script run by name
cannot use) or a `sys.path` mutation, and a `sys.path` entry lets a third-party
module shadow a sibling of the same name — `hermes` is exactly such a name, which is
presumably why the by-path load exists. `_shared.load_module` is there for new code;
the existing sites keep the idiom that works in both contexts. My first attempt at
this also broke `ablate.py`, which already uses a `sys.path` shim, by inserting the
load block *inside* a parenthesised `from council_loop import (` — see §10.3.

**`council_loop._finding_key`.** It normalises the claim differently from
`fingerprint` (`" ".join(claim.lower().split())` — no punctuation stripping) **and**
the path differently (`lstrip("./")`, which strips any leading run of `.` and `/`).
Unifying it changes which findings merge within a round, which changes counts, which
changes scores. That is a behaviour change wearing a cleanup's clothes, so it is
reported and left alone. The risk it carries is real and unchanged: a finding carried
from the baseline is keyed by `fingerprint` while a re-found one is keyed by
`_finding_key`, so the same defect can be counted twice.

**The loose-JSON reader.** `ablate.read_findings` and `council_loop.read_json_tolerant`
share the intent but not the code, and the code differs in a way that matters: the
first strips a fence with `re.sub(r"^```[a-zA-Z]*
?", "", text)`, the second with
`text.split("
", 1)[1]`. Those disagree on a single-line ```` ```json{...}``` ````
document. They also return different shapes (a finding list vs a dict), so unifying
means choosing one parser's behaviour for the other — a change to how model output is
recovered, not a rename. Left alone; §10.1 is the model for doing it properly, by
making the difference an explicit parameter rather than picking a winner.

### 10.3 What the first attempt got wrong

Worth recording, because the same trap is one edit away for anyone else.

My load-block inserter found "the last line starting with `import`/`from`" and put
the block after it. Two ways that breaks:

1. **It split a parenthesised import.** `ablate.py` has
   `from council_loop import (` followed by an indented name list, so the block landed
   *inside* the parentheses and the file stopped parsing.
2. **It matched an INDENTED import.** Every module ends with
   `if __name__ == "__main__":` → `from council import require_dispatch`, so the block
   was inserted inside that guard in `install_bots.py` and `sync_to_skill.py`.

The fix is to require column 0 and to follow parentheses when finding the end of the
import region. The tell for both was the same and worth trusting: `ast.parse` failed
on three of the six files, and the module loader itself then failed with
`cp: cannot stat '…/scripts/_shared.py'` — because an **untracked** new file does not
exist to Nix, which is the repo's own standing rule and cost one extra cycle here.

---

## 11. What I did not verify

- **The container saving in a published release asset.** The 307 M figure is a
  local build; the published asset is 348,769,967 bytes and was not rebuilt.
- **The condensed-probe prompt** (§4) — no round has been run with it.
- **darwin execution** — unchanged from `docs/NIX.md`: declared and evaluated, not
  built.
- **The container size with `vulnix` restored.** The 983.3 MB toolchain closure is
  measured; the container was not rebuilt from it (it was 333 M at that size before).
- **`council_loop._finding_key`'s divergence** (§10.2) — left alone deliberately,
  because unifying it moves which findings merge.
- **The module-loader idiom** (§10.2) — kept, and the reason is recorded there rather
  than left as an unexplained duplication.
- **A false claim of mine, corrected here.** I first reported that
  `baseline.carried_llm_scores`' contract was "implemented nowhere", on the evidence
  that its parameter name `baseline_scores` appeared nowhere else in `scripts/`. That
  was wrong: the contract **is** implemented, in `council_loop.apply_carry`
  (`council_loop.py:991-1022`), under different names — it sets
  `review["score"]` to the baseline's value and marks `llm_carried_from_baseline`,
  with the docstring "Its self-assigned number is discarded and the baseline's is
  carried." So the deleted function was a dead *duplicate* of live behaviour, not the
  only statement of it. The lesson is narrow and worth keeping: grepping for one
  identifier cannot establish that a *contract* is absent.
