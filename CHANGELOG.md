# Changelog

All notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.0] — 2026-10-17

### Added

- **`templates`, so onboarding is one command.** Six repositories were read for their Nix
  conventions; the clearest thing crane and devshell do that this project did not is
  `nix flake init -t`. Now:

  ```bash
  nix flake init -t github:washedupdeveloper/agentic-council          # a consumer flake
  nix flake init -t github:washedupdeveloper/agentic-council#home-manager   # a module
  ```

  The first writes a flake-parts flake importing `flakeModules.default` — the same
  packages, formatter and app this repository builds for itself. The second writes a
  home-manager module enabling `programs.council`.

- **`checks.templates`, because a rotted template fails in someone else's repository.**
  Templates reference a URL, not this tree, so nothing else in the gate would notice them
  drifting. The check asserts each still points at the **published** repository (not a
  path), still imports the module, and declares **the same systems as `flake.nix`** —
  derived from `flake.nix`, so adding a system here and forgetting the template fails.
  Verified with teeth: a local-path URL, a removed import, an extra system and a broken
  home-manager import each make it fail.

- **`renovate.json`.** The flake pins nixpkgs and flake-parts and nothing updated them.
  `automerge` is off, deliberately: the toolchain is what the score is computed from, so a
  `flake.lock` bump can move a pinned fixture and needs a human — `docs/VERSIONING.md`
  requires a release that moves the score to record the movement and show the threshold
  still yields the same verdicts.

- **`.envrc`** (`use flake`) and **`CONTRIBUTING.md`**. The first makes the devshell
  ambient for anyone with direnv, which four of the six reference repositories do. The
  second is the file GitHub links from its new-issue page; `AGENTS.md` is written for an
  agent and stays the fuller statement.

### Changed

- **`docs/NIX.md` records the conventions adopted and the ones rejected, with the reason.**
  Rejections are measurements, not preferences: crane's `nix-eval-jobs` fast-check was
  dropped because evaluating every check takes **3 s** and a cached full gate **15 s**, so
  there is nothing to parallelise; `default.nix`/`shell.nix` back-compat was dropped
  because crane's and treefmt-nix's are *library* entry points and this is not a library.
  `templates.*` and `flakeModules.default` are now named as public outputs in
  `docs/VERSIONING.md`, which they already were in fact.

### Fixed

- **`docs/NIX.md` said 236/238 toolchain paths were on `cache.nixos.org`.** The measured
  figure is **179 of 181**, corrected alongside the other stale counts.
## [1.4.4] — 2026-10-17

### Fixed

- **Six stale measurements across five docs, all traceable to `zizmor` being added in
  v1.4.0.** Adding one tool moved every figure that counts or weighs the toolchain, and
  nothing re-measured them:

  | claim | was | measured |
  |---|---|---|
  | toolchain closure | 919.8 MB / 180 paths | **945.6 MB (901.8 MiB) / 181 paths** |
  | substitutable from `cache.nixos.org` | 178 of 180 | **179 of 181** |
  | QA tool count | 13 | **14** |
  | release tarball | 313 MiB / 328,344,703 B | **322.0 MiB / 337,566,420 B** |
  | layer content | 1.06 GB | **1.02 GiB (1,090,508,800 B)** |
  | darwin dry-run | 239 paths fetched | **209 paths (454.3 MiB), 5 built** |

  The count was wrong in six places (`docs/NIX.md` ×2, `docs/TOOLCHAIN.md`,
  `docs/AUTONOMY.md`, `README.md`, `docs/CONTAINER.md`), and `docs/AUTONOMY.md` listed
  only 13 names against a stated count of 14 — `zizmor` was missing from the enumeration.

  Two counts were **removed rather than corrected**: `docs/CONTAINER.md` said "all 13
  analyzers resolve on PATH" and "all 14 analyzers that then shipped". The first is now
  "every analyzer in `toolNames`", which cannot go stale; the second described a past
  measurement whose exact count is no longer recoverable, so it says "all the analyzers
  that then shipped".

  Every figure above was measured on this host: the closure and its substitutability path
  by path against `cache.nixos.org` (one at a time — batched queries silently report
  misses), the tarball and its 99 layers by downloading and unpacking the actual v1.4.3
  release asset, and the darwin numbers from a `--dry-run` for `aarch64-darwin`.
## [1.4.3] — 2026-10-17

### Added

- **`docs/NIX.md` now names the outputs a consumer actually needs.** It listed
  `apps.council` but not `packages.review-council`, `packages.skill` or
  `homeManagerModules.default`, so anyone integrating this flake had to discover the
  names by trial. Two of them are traps: **`packages.council` does not exist** (the app is
  `apps.council`) and **`packages.default` is the toolchain, not the council**. Both are
  now stated in the table rather than left to be found.

  The names themselves are unchanged — `packages.*` is public interface, so renaming is a
  major version, and documenting costs nothing.

### Fixed

- **Nothing verified the published flake, only the working tree.** Every test built from a
  local path. A throwaway consumer flake whose only input was
  `github:washedupdeveloper/agentic-council` now proves the published artifact resolves,
  builds `packages.review-council`, runs the binary, and evaluates
  `homeManagerModules.default` in a consumer configuration with 0 failing assertions
  (`runs/downstream-consumption-2026-10-17.md`).
## [1.4.2] — 2026-10-17

### Changed

- **The threshold was measured against real repositories, and the answer is that it
  cannot be derived.** Five well-regarded repos were reviewed end-to-end on the hybrid
  scale — the same numbers the gate enforces — at one sample and one round each
  (`runs/clean-baseline-evaluation-2026-10-17.md`):

  | repo | hybrid | verdict |
  |---|---:|---|
  | treefmt-nix | 98.40 | passes |
  | clan-infra | 94.83 | passes |
  | devshell | 89.23 | passes |
  | zero-to-nix | 80.63 | fails |
  | flake-utils | 60.86 | fails |

  **Three of five pass 87.1141 unchanged**, and the two failures are verifiable rather
  than marginal: zero-to-nix's security `det` is 58.84 because `osv-scanner` reports 45
  dependency CVEs, and flake-utils has two blocking findings (an unpinned `@main` action,
  and a template that fails its own `nix flake check`).

  The classes do not separate. The best failing repo (80.63) sits **0.59 points** above
  the golden defects fixture (80.04), so a max-margin threshold would be **80.34 with a
  margin of 0.30** — a line that puts a repository with 45 CVEs within a rounding step of
  passing. The reason is structural: both classes contain imperfect code, so "known-good"
  and "known-bad" differ in density, not in kind, and a weighted mean reflects density.

  **The threshold is therefore recorded as a policy line, not a measured boundary**, and
  it is left at 87.1141. It sits above every repository in the sample with a real finding
  and below every one without; nothing in this run argues for moving it. `docs/CALIBRATION.md`
  says so, with the sample's limits stated: n=1 per repo, β varies by content, and five
  hand-picked repositories are not a distribution.
## [1.4.1] — 2026-10-17

### Fixed

- **This repository's own workflows had 5 high-severity unpinned actions.** Adding
  `zizmor` immediately reported them against `ci.yml` and `image.yml` —
  `actions/checkout@v7`, `actions/setup-python@v7`, `cachix/install-nix-action@v31` — the
  same defect the framework raises when it reviews someone else's workflows. Every action
  is now pinned to a full commit SHA with the version in a comment, and each checkout sets
  `persist-credentials: false` so the token does not stay in `.git/config` for a later
  step to read.

  `docs/CI.md` had argued the other way, and its own condition for revisiting had fired:
  the old text justified major tags "for a repo with one maintainer and no third-party
  contributors" and said to revisit "the moment the repo gains a collaborator or goes
  public". The repository is public and its releases are downloadable anonymously. The
  section now records that reversal, the measurement that settled it, and the standing
  cost — a pin is an obligation to bump, not a one-off edit.

  Measured after the change: `council probes zizmor --repo .` reports **0 findings over 2
  files**.
## [1.4.0] — 2026-10-17

### Added

- **`zizmor` — the only analyzer that reads `.github/`.** A workflow file is executed by
  a forge with the repository token's authority, so it is attack surface nothing else in
  the toolchain looked at. It catches the class a reviewer has to notice by hand: an
  unpinned `uses: owner/repo@main` runs whatever that branch points at on every push, and
  an absent `permissions:` block leaves the default token, which is write-all on
  repositories created before February 2023.

  Measured on `numtide/flake-utils`: **5 findings, including
  `uses: NixOS/nix-installer-action@main`** — the same defect an end-to-end LLM review of
  that repository found, caught mechanically and at a fixed cost. On `ipetkov/crane`,
  which pins every action to a full SHA and sets `permissions: contents: read`: **0
  findings**, so the probe distinguishes the two rather than flagging CI in general.

  It is deliberately **not** in `STACK_TOOLS`. It only applies when
  `.github/workflows` exists, and listing it as expected would make beta fall on every
  repository without CI — punishing a repository for a check that cannot apply to it. It
  contributes to `det` through `tools_run` whenever it does run. `docs/TOOLCHAIN.md` and
  a test both pin that.

  Cost: the QA toolchain goes from 919.8 MB / 180 paths to **945.6 MB / 181 paths**
  (+25.8 MB; zizmor's own closure is 78.4 MB, the rest shared with tools already
  present).
## [1.3.3] — 2026-10-17

### Added

- **`calibrate --good` is repeatable, and `calibrate_many` scores every baseline.**
  One known-good repo makes the threshold's upper edge that repo's own score, so a
  second clean repo that is merely less tidy fails the gate. Each `--good` now
  contributes its own labelled point, and `d*` anchors on the **worst** density seen
  per tool across the whole set — `d*` is the density at which a tool scores 50, so
  anchoring on the tidiest repo would mark every other clean repo as failing.

### Fixed

- **`calibrate.run_probes` measured nothing when called as a library.** `probes.py`
  refuses a bare invocation and prints usage instead of JSON, and `run_probes` treated
  any non-JSON answer as "no probes" — so a calibration invoked outside
  `council calibrate` produced **zero points** and reported "no labels" instead of the
  truth. It now sets `REVIEW_COUNCIL_DISPATCHED` for the child, and raises with the
  probe's own message rather than returning an empty list.
## [1.3.2] — 2026-10-17

### Added

- **`council calibrate --sensitivity <round-dir>`** measures how much the aggregate
  weights (`α_t`) could move a verdict, which is the question M8 left open by recording
  them as uncalibrated. It sweeps each weight from **0 to 3×** its shipped value,
  redistributes the others proportionally so the total stays 1, and recomputes the
  aggregate with the gate's own `renormalized_aggregate` — so the measurement cannot
  disagree with the score it is measuring.

  The result reframes the item rather than closing it with a guess. On every input
  available, **no single weight change flips a verdict**: the defects fixture moves at
  most 8.63 points and stays between 74.29 and 82.92 against an 87.11 threshold, and
  zeroing security — deleting the dimension from the aggregate entirely — still leaves it
  below the line. The `clean` fixture is uniform at 100, so it is weight-invariant by
  construction and cannot test the weights at all.

  So `α_t` is not a parameter waiting for calibration data; it encodes **consequence
  cost** per dimension, which needs incident data rather than defect labels. The working
  defaults now stand as a documented policy choice, with the caveat recorded that a score
  near the threshold with a large spread could still be weight-sensitive — which the tool
  reports (`any_verdict_flips`) instead of assuming away.
## [1.3.1] — 2026-10-17

### Added

- **The no-toolchain path is tested, not asserted.** M9's acceptance was "fresh machine
  → documented install → green end-to-end run on all three OSes", and the first half was
  never exercised: the suite always ran with the pinned toolchain on PATH, so the
  degradation path — the entire reason the built-in probes exist — was prose.
  `tests/test_fresh_machine.py` runs the real `probes.py` and `doctor.py` in a subprocess
  with `REVIEW_COUNCIL_TOOLCHAIN` removed **and `PATH` set to an empty directory**. The
  second half is the part that makes it a fresh machine: `toolchain.env()` resolves the
  toolchain itself when `nix` is on PATH, so unsetting the variable alone still runs
  every analyzer.

  Measured on that path: **6 of 20 probes run** (the stdlib set), **13 report
  `ran: false` with a reason**, **zero report a signal they did not measure**, and
  `doctor` reports **beta 0.32** rather than 1.00 — so the score degrades visibly
  instead of quietly becoming the LLM's judgement, which is the β defect M8.5 shipped
  once already.

  The test has teeth: making `statix` report `ran: true` when it cannot run fails it,
  checked by injection and reverted. Because it runs in the pytest matrix, the claim is
  now verified on Linux, macOS and Windows on every push.
## [1.3.0] — 2026-10-17

### Added

- **`council pr`** — posts a run's verdict to a GitHub pull request, closing M7's last
  gap. The body's numbers come from `score_reviews.evaluate`, the gate's own function, so
  a PR comment cannot disagree with `council gate` about the same run. It prints the
  request and posts only with `--post`; the default event is `COMMENT`, which cannot block
  a merge, and `--event auto` sends `REQUEST_CHANGES` when the gate fails.

  Three hazards are handled rather than documented away. GitHub has **no idempotency key
  for reviews**, so the body carries an HTML-comment marker naming the run and the PR, and
  an existing review carrying it is skipped — a re-run cannot leave a second copy of the
  same verdict. The review is **pinned to `commit_id`** from the run's `meta.json`, so it
  attaches to the commit the council actually scored rather than the PR's latest one. And
  the token is read from `GITHUB_TOKEN`/`GH_TOKEN`, **never from argv**, where it would be
  visible in `ps` and in shell history.

  `--api` (or `GITHUB_API_URL`) addresses GitHub Enterprise, and is what let the request
  shape be exercised against a stub server that records what is actually sent: endpoint,
  `Bearer` header, payload, and that the token appears in none of it.
## [1.2.0] — 2026-10-17

### Added

- **`AGENTS.md`** — the project context an agent loads in this workdir. It states the
  rules that are easy to break by accident (tracked files only, because Nix cannot see an
  untracked one; no shell scripts; a new verb touches three places; user verbs ship and dev
  verbs do not; prompts travel in a file; a review is a read) and points at `docs/` rather
  than repeating it. It was an M0 deliverable that had never landed.
- **`council metrics`** — the interactive half of M8, computed from the `status` field
  every finding already carries. Reports acceptance rate, addressed rate, coverage and
  iterations per run, and reports **`null` with a named reason** when nobody has judged a
  finding, because no data is not a zero rate. Two corrections to what M8 assumed:
  iterations never needed an operator (`outcome.json` records one score per round, so its
  length *is* the count), and the record the other two need was already in the schema — the
  gap was a missing computation, not a missing signal.
- **`council cron <repo>`** — prints (or `--install`s) a `hermes cron create` job for an
  unattended review. The prompt tells the agent to RUN the council and report the gate's
  numbers verbatim, never to review the code itself: a cron agent reviewing on its own
  would be a reviewer outside the framework. It prints by default because a schedule
  outlives the session that made it.

### Changed

- **The `status` vocabulary gained `rejected`.** It was `open|fixed|wontfix|accepted`,
  which could express "real and fixed", "real and declined" and "not judged", but not
  "judged not real" — the false positive that SNR measures on the ladder. `council metrics`
  treats `accepted|fixed|wontfix` as judged real, `fixed` alone as addressed, and reports
  any value outside the set as a mistake rather than guessing at it.
- **`docs/MILESTONES.md` M7 is complete except the PR path.** The re-claim branch was
  exercised end to end on a throwaway board — claim → reclaim → `ready` → re-claim as
  `run 2`, bounded by `max-retries: 2` — and the council-side guard verified: a repeat
  `council swarm` returns the *same* root card id, so a reclaimed dispatch cannot fork a
  second round (`runs/reclaim-verification-2026-10-17.md`). Cron is built. The GitHub PR
  path stays unbuilt rather than built and unverified.
- **`docs/MILESTONES.md` §3 is no longer a list of open questions.** All six were answered
  by building or measuring; the section now records each answer beside the question it
  closed.

## [1.1.0] — 2026-10-17

### Added

- **A written version policy, and the check that enforces it.** `docs/VERSIONING.md`
  defines what major, minor and patch mean here: the deciding question is whether an
  existing user has to change something, applied to the surfaces that actually exist —
  user verbs, flake outputs, module options, run artifacts, finding fields, gate exit
  codes, the container and the score. `council version` (devshell) prints, checks and
  bumps; `checks.version` runs the check on every `nix flake check`; and `image.yml`
  compares the pushed tag against `pyproject.toml` before it builds, so a mistyped tag
  costs a minute instead of publishing a 300 MB artifact under the wrong version.

- **The gate is three tiers, and the eval tier is a real one.** `checks.module` and
  `checks.flake` assert on the *evaluated* configuration through `lib.runTests`, so a
  wiring mistake fails in milliseconds and names the test, the expected value and the
  actual one. They replace `checks.module-evaluates`, which was a `runCommand`
  asserting two hardcoded counts — an eval assertion paying for a build, and
  reporting a bare exit code — and which covered neither the library link's path, nor
  the option defaults, nor the refusal message, nor the disabled case. All four are
  asserted now, in `nix/tests.nix`.

  The rule, recorded in `nix/tests.nix` and in the `checks.*` row of `docs/NIX.md`:
  an assertion belongs in the cheapest tier that can make it — **eval** for a value
  in the configuration, **build** for the artifact a builder produced, **e2e** for
  what a running machine does. `.#vm-test` stays outside `checks` because it needs
  `/dev/kvm`.

- **`council setup` is a guided first-run wizard.** It detects Hermes, asks only
  the questions that are actually the user's (the gate, the sample count, the
  autonomy mode, whether any member pins a model), prints a summary of what it is
  about to do, writes one editable file, and then installs. It never hangs: with
  no terminal it takes every default and says so, so a container or CI cannot wedge
  on a prompt. Re-running is "change one thing", not "answer everything again",
  because existing values become the defaults.
- **One editable config, `$HERMES_HOME/review-council.toml`, and nothing else
  hardcodes it.** Which members exist, what each may do, the gate, the sample
  count, the autonomy mode — all of it is read from that file, and
  `council setup bots` applies an edit. It is TOML rather than YAML because the
  framework is stdlib-only and the pinned toolchain's interpreter has no PyYAML;
  `tomllib` is stdlib. The file is round-tripped through a real parser before it is
  written, and a broken one is refused with the line and the reason rather than
  half-applied. Validation reports every problem at once, and `delegation` in a
  member's toolsets is refused outright — the harness is the only fan-out, and a
  member that could delegate would bypass the rubrics.
- **`council goal <repo>` expresses a run as a native Hermes `/goal`.** Hermes
  ships completion contracts (`outcome`, `verification`, `constraints`,
  `boundaries`, `stop_when`) and **quality gates** — deterministic shell commands
  that must exit 0 before the goal can be judged done, run *before* the judge, with
  a red gate skipping the judge entirely. The council's own gate is already such a
  command, so its autonomous mode no longer needs a bespoke loop: `council gate
  --latest --repo <repo>` scores the newest run and exits non-zero when it is not
  satisfied, and the decision to stop becomes a command's exit code rather than a
  model's opinion. `/goal status`, `/goal pause`, `/subgoal` and the turn budget
  then apply for free. `--json` gives the fields.
- **`council gate --latest`** resolves the newest run under a repo, so the quality
  gate needs no run directory a user would have to know. With no run yet it exits 1
  and says which directory it looked in: "not met" is a failed gate, not an error.
- **`council setup` installs the skill too, and `setup skill` installs it alone.**
  The first-run path used to create the profiles and stop, so a newcomer following
  it got a working `council review` and **no `/council`** — the skill that makes the
  agent command exist had no installer at all. `sync` did it, but it is a dev verb,
  so the shipped surface could not reach it. `council setup` now installs the skill
  and then the profiles, in that order: the skill is the half that needs no Hermes
  profile to exist yet, and the half that carries the framework. Measured from a
  fresh `HERMES_HOME`: 19 script modules, 6 rubrics, the bot definitions and the
  pinned `flake.lock` land in the library, both profiles are created, and the
  installed skill then runs itself with no clone and no nix.
- **A `Dockerfile`, and it is nix-centric.** A host that can run docker but not nix
  can now `docker build -t review-council .`; nix is installed only inside the
  build, never on the machine. `nix build .#container` stays the primary path
  because its layers are content-addressed, and the Dockerfile says so rather than
  pretending to be equivalent. **The image is still defined once**: `mkContainer`
  (dockerTools) and `mkImageRoot` (the tree the Dockerfile copies) share
  `imagePrep`, the entrypoint and the nix config, so the two cannot drift into "the
  image works and the Dockerfile does not" — the one failure a reader cannot debug.
  Two things that only a real build teaches, both now handled: nix makes a store
  path **read-only**, so the modes the flake sets do not survive into the copy
  (`tmp` arrived `0555`, not `1777`) and the prep has to ship as a file and be
  re-run; and GNU `cp -a` propagates the source directory's mode onto the
  destination, leaving the rootfs read-only, so the copy is done with `tar`
  (`--no-overwrite-dir`), which records modes without altering the extraction root.
- **`council doctor` reports Hermes, in layers.** It answered "β 1.00" on a machine
  with no Hermes at all, which says nothing about whether a review can run. The
  council does **not** talk to a Hermes *gateway* — it shells out to the `hermes`
  launcher — so the question is answered cheapest-and-most-certain first and a weak
  signal is never promoted into a strong claim: **L0** the launcher (deterministic,
  local), **L1** `--version`, which proves it *executes* rather than merely resolving,
  **L2** the council profiles exist *and carry a provider*, **L3** a gateway port
  (optimistic, a **hint**, never part of the verdict), **L4** one real turn, the only
  authoritative layer and therefore opt-in behind `council doctor --probe`. The verdict
  names the first thing that would stop a review, because that is the one worth fixing.
- **`nix build .#vm-test`** — the council end-to-end inside a real NixOS VM: boot, a
  target repo, the pinned probes, the fan-out, the bucketing, the gate, a verdict. The
  agent is a stub honouring the real CLI contract, because what is under test is the
  harness, not the model. It asserts the honest negatives too: no profiles reads
  `no-profiles`, and one open **high** finding is refused **with every score still
  100** — so the block is the finding, not the aggregate. Not in `nix flake check`: a
  VM test needs KVM, and the fast gate must not require it.
- **`scripts/hermes.py`** — the single launcher resolver. `council_loop.hermes_bin()`
  and `doctor` now share it, because two copies would drift into "doctor finds it and
  the loop does not", which reads as a flaky agent.
- **Nothing under `scripts/` is a program any more.** Every module refuses a direct
  invocation — `python3 scripts/inject_defects.py` — unless the dispatcher set
  `REVIEW_COUNCIL_DISPATCHED`, and only `scripts/council.py` sets it. Several of
  these files *act*: `setup bots` writes into `HERMES_HOME`, `sync` prunes a skill
  deployment, `corpus` plants defects in a repository it is pointed at, and
  `review`, `sample` and `ablate` spend real agent turns. The refusal names the verb
  to run instead. Child processes inherit the variable, which is how the harness
  still runs `probes.py` and `score_reviews.py`. Enforced twice: `test_modules.py`
  fails if a verb's module has no guard or names a verb the CLI does not expose, and
  `checks.commands` fails if a direct invocation *succeeds* or the same verb through
  the CLI *does not*.
- **A shipping manifest in the flake.** `runtimeModules` is what a review needs;
  `devModules` (`ablate`, `calibrate`, `golden`, `corpus`, `sync`) is development
  tooling. `checks.commands` reads the verb table back from the built app and fails
  if a user verb's module is missing from the shipped tree or a dev verb's is present
  in it — so the list cannot rot into a comment.

- **Every tool the gate expects is now a harness probe, so beta is a property of
  the pinned toolchain rather than of the reviewer's diligence.** `ruff`, `mypy`,
  `bandit`, a dependency scanner and `pytest` were *expected* by the gate and run
  by nobody: the reviewer had to both choose to invoke each one and report it
  accurately, so a reviewer who skipped `ruff` cost the readability dimension 40%
  of its determinism while `ruff` sat pinned on PATH the whole time. That is the
  asymmetry — deterministic on the Nix side, hostage to diligence on the Python
  side — and it is closed. Measured with `doctor` on this repository: security
  **0.50 → 1.00**, and all five dimensions now report **1.00**.
- **A `--python-executable` mypy probe** resolves imports against the pinned
  interpreter. Without it every third-party import is reported as a missing stub,
  which says more about mypy's search path than about the code.
- **`tests/test_probes.py` and `tests/test_score_reviews.py` grew 9 tests** covering
  the degradation path (a probe that cannot run must never invent a result), the
  JSON-array parser, the two distinct `osv-scanner` outcomes, the `det[c]` leak and
  the density fallback.


### Changed

- **The score moved when the analyzer set changed, and this release records it.** Adding
  `gitleaks` and `shellcheck` as probes moved the golden defects fixture from **52.69 to
  55.16**, and beta *fell* on dimensions where a newly expected tool cannot run on that
  fixture (security 1.0 to 0.667): beta is coverage, so expecting a tool that does not run
  lowers it. The shipped threshold **87.1141** still yields the same verdicts on both
  golden fixtures — clean satisfied at 100.0, defects not satisfied — which is what keeps
  this a minor release under `docs/VERSIONING.md` rather than a major one. A threshold
  tuned by hand before this release should be recalibrated.


- **The shipped tree carries only what a review runs.** `mkFramework` now takes the
  audience, exactly as the verb surface does: the app and the image get the runtime
  modules, `bots/` and `skills/`, and the devshell gets those plus the dev verbs and
  the suite. `packages.framework` is the shipped tree; `packages.dev-framework` is
  the devshell's. Dropped from the shipped tree: `tests/`, `pyproject.toml`,
  `README.md`, `flake.nix` and `flake.lock` — nothing at review time reads any of
  them, and the image no longer carries a suite or a flake it never builds.
- **The dispatcher bakes `REVIEW_COUNCIL_TOOLCHAIN`.** `toolchain.py` used to fall
  back to `nix build <tree>#toolchain`, which is why the framework copy had to carry
  the flake. The launcher exports the store path the build already fixed, so no
  runtime path needs a writable store or a flake to find it — and the two agree by
  construction rather than by coincidence.
- **`docs/ARCHITECTURE.md` §8 is now the real inventory** — every top-level entry
  with what it is and whether it ships, plus the per-module table. The old section
  still listed `protocol/` and `src/review_council/` from M1, which was never built.
- **`docs/EXTENDING.md` gained "Add a verb"** — the three things a new verb must
  satisfy, all of them enforced by the gate. And the probe section now states that
  `signal` is a density (`score_from_density(findings, root)`), not a count.

- **`det[c]` is now computed from category `c`'s tools alone.** FRAMEWORK §6 says
  `det[c] = geometric_mean(normalize(tool_signals_c))`; the code averaged *every*
  tool into *every* category, so readability depended on bandit and security
  depended on mypy. That was invisible while beta < 1 let the reviewer's score
  dominate the result. At beta = 1 `det` **is** the score, so the leak would decide
  verdicts rather than colour them.
- **Probe signals are findings *densities*, which is what §6 defines.** The Hill
  curve takes `findings / KLOC`; the probes were feeding it a raw count, scoring a
  14 KLOC repository's 16 findings as 16 *per KLOC* — about 14× the harshness the
  spec defines. Measured on this repository: `bandit` 20 → 86, `mypy` 9 → 70,
  `complexity` 19 → 85. Before the fix the aggregate fell to 84.36 against a
  87.1141 threshold; after it, 93.26 and satisfied. A large repository is no longer
  penalised for being large.
- **`pip-audit` is replaced by `osv-scanner`, because `pip-audit` cannot run in this
  toolchain at all.** Its nixpkgs wrapper execs `sys.executable -m pip --version`
  before it will audit anything, and the interpreter it runs under ships no pip — so
  the dependency scanner was on PATH and unable to execute. Adding `pip` to the
  toolchain's Python env did not help, because the wrapper uses a different
  interpreter. `osv-scanner` is one static binary with no runtime dependency of its
  own, and it reads the lockfiles of every ecosystem this framework covers, so it
  also replaces `npm-audit` and `cargo-audit`: **one dependency scanner instead of
  three.** Where a repository declares dependencies in a manifest it cannot read
  (`pyproject.toml` is not a lockfile) the probe reports `ran=False` with that
  reason rather than a clean bill of health.
- **CI builds and publishes the container image.** `.github/workflows/image.yml`
  builds it on every pull request (so a broken image fails the PR) and pushes it to
  GHCR on `master`, tagged `latest` and `sha-<12>`. Using the council now needs
  docker and nothing else from this repository — no nix, no clone.
- **The container carries the `council` CLI, not only the review entry point.** The
  entrypoint now hands anything that is not a review straight to the CLI, so the
  image is useful before a Hermes is mounted: `docker run <image>` prints the verbs,
  and `doctor` / `gate` / `probes` / `--verbs-json` all work. The verb table is
  asked of the CLI rather than copied, so a new verb is reachable in the image the
  moment it exists. Previously the entrypoint resolved Hermes *before* looking at
  its arguments, so `docker run <image>` — whose `Cmd` is `--help` — printed a
  credential error where the help should have been, and no CLI verb was reachable
  at all.

### Fixed

- **The documented image size was the download, not the image.** "99 layers,
  333 MiB" is the *tarball*. The layers are gzipped, so `docker load` followed by
  `docker images` reports **2.33 GB** (2,331,098,089 bytes). Measured by loading
  the built image in a VM and asking docker, rather than restating the tarball.
  Both figures are now stated wherever the size appears, and the two stale
  variants of the number (324 MiB in two files, 333 in one) are reconciled.
- **The Dockerfile could not build.** Its last step piped through `sed`, and the
  `nixos/nix` base image has no `sed` (nor `awk`; `/bin` holds only `sh`). Every
  check up to now had stopped at "the Dockerfile parses", which is not the same
  claim, so `docker build` died at `[builder 9/9]` with `/bin/sh: line 1: sed:
  command not found` — the whole path existed for a host with docker and no nix,
  and it had never once completed. The step now takes `coreutils`, `gnused`,
  `gnugrep`, `gnutar` and `findutils` from nixpkgs via a new `.#image-prep-tools`
  output, so it depends on the pin rather than on what a base image happens to
  carry. Proven by running the build to completion in a VM with network.
- **The deployed skill pointed the agent at three files that do not ship.** The
  sync copies `scripts/`, `tests/`, `assets/`, `SKILL.md` and `flake.*` — not
  `docs/` or `runs/` — while `SKILL.md` told the agent to consult
  `docs/BASELINE.md`, `docs/MILESTONES.md` and `runs/ablation-22-defect-2026-10-11.md`.
  Verified dangling in the deployment and present in the repo. The references now
  name the repository, which is where those files are.
- **`.pytest_cache` was deployed into the skill tree.** A cache, not content, and
  host-specific. Added to the sync's cleanup beside `__pycache__`.
- **A member's capabilities were declared in a file nothing read.** The toolsets
  were hardcoded in `install_bots.py` while `bots/*/bot.yaml` declared them again —
  so the file was decorative, and a user editing either saw no effect. That is the
  worst kind of configurable: it looks configurable. Capabilities now come from
  `review-council.toml`, which the installer reads, and the config module is the
  only place the defaults live. Verified end to end: editing a member's `toolsets`
  to `["file", "terminal"]` and re-running `council setup bots` leaves the profile
  running exactly those two.
- **`bots/council-orchestrator/bot.yaml` shipped one machine's private provider and
  model.** A file that ships publicly named a provider and a model that belong to
  the author, in a repository about to become public. Removed; a member's
  model/provider is the user's choice and defaults to inherit. A test now fails if
  any shipped file names a provider, a model or a key.
- **The orchestrator installed with NO rubric, silently.** The rubric is
  `review-council-orchestrator` while the member is `council-orchestrator`, and the
  installer globbed `f"{name}*"` — which matched nothing. A member with zero skills
  installs cleanly and simply cannot read its own instructions, so nothing reported
  it. The glob is now a suffix match, and an orchestrator with no rubric is a hard
  error rather than a quiet success.
- **`profile.yaml` described a design that no longer exists.** It still said the
  orchestrator "fans out one delegate_task batch to the five specialist reviewers" —
  the five were measured worse at equal cost and deleted at M8.5, and the
  orchestrator has no delegation toolset at all. `install_bots.py` copies that file
  into every profile, so every user was shown the stale description.
- **`probes.score_from_density` claimed to match the scorer's curve and did not.**
  Its docstring said "matching score_reviews.hill_curve", but its half-point is a
  hardcoded `k=5.0` while the scorer applies the calibrated `d*=1.8921`. Measured,
  the two disagree by up to **26 points** over the density range, and 19 points on a
  probe reporting one finding per KLOC — and at β=1 the probe signal is 0.7 of the
  score. The docstring now states the difference, the constant is named so the
  assumption is greppable, and `docs/CALIBRATION.md` records it as the open
  calibration question it is: unifying the two would make every probe signal
  stricter and require re-deriving the shipped threshold, which is a calibration
  decision rather than a bug fix.
- **`council setup skill` skipped the flake silently, so a deployment's `flake.nix`
  went stale forever.** The copy loop was `if os.path.isfile(src): place(...)` with
  no else. The shipped framework tree carries no `flake.nix` by design, so a sync run
  from the nix app, the devshell or the container found nothing to install and said
  nothing — and the installed skill could no longer `nix build` its own toolchain.
  Found on a real deployment: 489 lines and two major changes behind, with the
  drift check reporting only `flake.nix` and no explanation. The flake now stages the
  two files as their own store path and both launchers export
  `REVIEW_COUNCIL_FLAKE_DIR`, so the source reaches the sync from every entry point;
  and a sync that cannot find them **refuses** (exit 2) with the reason rather than
  skipping. Verified from all four entry points: checkout, a tree without the
  variable (refuses), the nix launcher (installs), and a tree with the variable set.
- **A prune was silent.** `prune_tree` deleted a file the source did not have and
  printed nothing, so a sync run from an audience-limited tree removed the dev verbs
  from a deployment with no evidence but their absence. Removals now print
  (`REMOVED <path> (not in the source)`), matching what `--check` already reported.
- **The skill's Bootstrap documented two commands that refuse to run.** It told a
  reader to run `python3 <skill_dir>/scripts/install_bots.py` and
  `python3 <skill_dir>/scripts/doctor.py`, and both exit 1 with "this is a module of
  the council CLI, not a program" — the dispatch guard refuses a hand-run module, and
  the two documented lines were never updated when it was added. Verified in a fresh
  `HERMES_HOME`. They also used a bare `python3`, which the skill's own path-resolution
  section tells you not to, and which does not exist on a NixOS host or as a name on
  Windows. Both now go through `council.py` with `"$PY"`, and the section states the
  rule rather than leaving the next editor to rediscover it.
- **The documented `docker run` could not write its own output.** The image runs as
  uid 1000, so a repository mounted from an account with any other uid was
  read-only to it and the run died with `PermissionError: '/repo/.review-council'`.
  Measured on a fresh account (uid 1001) in a real docker daemon. Both the README
  and `docs/CONTAINER.md` now pass `--user "$(id -u):$(id -g)"`, the image makes
  `/home/council` and `/repo` writable by the runtime uid so that flag is
  sufficient on its own, and the harness reports the situation with the flag to
  pass instead of a traceback.
- **There is no implicit `/repo`.** `docker run <image>` used to start a review of
  `/repo` when given no argument, which meant it needed Hermes to print anything.
  A review now always names its target.
- **`council corpus` deleted its output before validating anything.** `--out` was
  `rmtree`'d before `apply_and_locate` ran on the copy, so `--base B --out B`
  destroyed the base and then died in `copytree`, and `--base B --out V` — V an
  unrelated populated directory — emptied V and only then reported that B was the
  wrong base. An `--out` that is the base, contains it, or sits inside it is now
  refused, and the injection targets are validated against the base **read-only**
  before anything is deleted. *Found by the council reviewing this repository
  inside the container, with both reproductions.*
- **An agent turn inherited the module guard's variable.** `council_loop.py` passed
  `env=dict(os.environ)` to every reviewer and orchestrator turn, so a turn spawned
  by the harness had `REVIEW_COUNCIL_DISPATCHED=1` and a module run from inside a run
  was **not** refused. The council demonstrated it in its own session: inside a
  council-spawned turn the variable read `1`, and `python3 scripts/inject_defects.py
  --base B --out V` executed and destroyed V, where the identical command from a
  clean shell was refused. The variable is now removed from the agent environment —
  the copy the framework hands over, which is the part it controls.
- **The dispatch guard is documented as what it is.** It stops an *accidental*
  `python3 scripts/x.py` and names the verb to run instead. It is **not** a security
  boundary: any caller who sets one environment variable passes, and so can an agent
  with a terminal toolset. `docs/ARCHITECTURE.md` §8.2 and `scripts/council.py` now
  say so, because a guard that claims more than it can hold invites trust it cannot
  earn.

### Changed

- **What it runs on is now stated, not implied.** The README says which platforms the
  flake covers (`x86_64-linux`, `aarch64-linux`, `aarch64-darwin`), that the image is
  any Linux docker host on either architecture, and that the CLI is standard-library
  Python with Windows a supported target for the modules — only the image is Linux.
  A tool that claims to work anywhere should name where it does.
- **Nothing describes one machine's setup any more.** The rubrics' knowledge base
  was anchored to a specific private infrastructure flake and named its users,
  hosts and secret paths. It now describes the *shape* those rubrics assume —
  which is what a reader needs, and what the checks actually test — because a
  username in an example snippet and a repository name in a validation record are
  leaks with no upside, and they made a general tool read as one person's
  configuration. The validation records keep their findings; only the identifiers
  changed.
- **The container's verification notes no longer describe the machine they were
  written on.** "No container runtime on the build host" was true of one author's
  machine and irrelevant to a reader, and it had gone stale anyway — a scored
  review does run in the image. The section now says what is verified, how, and the
  one command that verifies it on *your* machine.
- **A `127.0.0.1` inside a guest is the guest.** Measured in a NixOS VM test rather
  than assumed, with a control listener to prove the probe works: `127.0.0.1` reaches
  the guest in every configuration. The host is at `10.0.2.2` (QEMU's SLIRP gateway) —
  but only with `--option sandbox false --rebuild`, because the Nix build sandbox gives
  the build its own network namespace, so by default that gateway is the sandbox's
  loopback and the host's services are invisible. WSL's mirrored networking *does* let
  `127.0.0.1` reach the Windows host, which is why the assumption is easy to make — it
  is a property of that setup, not of guests in general. `docs/AUTONOMY.md` records the
  full table.
- **The image is layered.** `buildLayeredImage`, no nix database: **99 layers,
  324 MiB**, against the previous single-layer 365 MiB. A store path's layer is
  content-addressed, so an unchanged toolchain produces byte-identical layer
  digests and a pull fetches only what the local copy lacks. That is the whole
  caching story; there is no build cache to configure.
- **The nix database is gone, and it cost nothing to drop.** It existed for
  `nix path-info` / `nix-store -q`, which nothing calls, and it was the *only*
  thing forcing a single layer — its gcroots point into a layer that is not there
  while it is being generated (`ln: ... Permission denied`). Measured without it:
  `nix --version`, `nix-instantiate --parse` (what the nix-eval probe actually
  runs), all 14 analyzers, and `doctor` reporting beta 1.00 all still work.
- **The README leads with the image, 280 → 102 lines.** The build-it-yourself
  instructions are gone; `nix build .#container` is one line in the container
  README.
- **The entrypoint finds a mounted Hermes at `/opt/hermes/bin/hermes`** without
  being told, so mounting an install needs no `-e HERMES_BIN`. `HERMES_BIN` still
  wins when set.
- **`docs/MILESTONES.md`** no longer calls M7 "in progress" — it shipped, and the
  plan it linked is gone.
- **No shell scripts.** Every operation is a `council <verb>` subcommand, and every
  verb is a Python module under `scripts/`. The verb table, the usage text and the
  dispatch moved out of a generated shell `case` into `scripts/council.py`, where
  the test suite can assert them. Measured: `find . -name '*.sh'` → **0**, and the
  container image carries none either.
- **The WSL bridge is gone.** nix does not run on Windows, so on Windows the council
  runs in the container image; there is no Windows-native path to keep working.
  `doctor` now says so instead of reporting an unresolvable toolchain.
- **Module docstrings cut to a statement of what the module is.** They had grown
  into documents — `council_loop.py`'s was 61 lines — and the reasoning belongs in
  `docs/`, where a reader can find it. `flake.nix` lost the same way, 909 → 682
  lines, most of it long block comments.
- **`docs/` rewritten for the above and cut hard.** Every number and measured
  result survives; the framing and the restatements do not.

### Removed

- **`start`** — a third interface over the flake and the image, and one more thing
  to keep in step. The flake and the published image cover both routes.
- **`scripts/install-ci-runner.sh`** — it registered a *self-hosted* runner, and CI
  is GitHub-hosted. `docs/CI.md` still describes the alternative; there is
  deliberately no script for the path this repository does not exercise.
- **`scripts/export-handoff.sh`** — bundled the project for moving it between the
  author's own machines.
- **`docs/M7-PLAN.md`, `docs/TESTING.md`, `docs/HANDOFF.md`** — a plan for a
  milestone that shipped, a self-declared historical log, and an author's machine
  migration procedure.

- **The five shell scripts, replaced by Python modules.** `nix-toolchain.sh` and
  `nix-toolchain-inner.sh` → `scripts/toolchain.py`, which `doctor.py` and
  `probes.py` now import instead of shelling out to; `install-bots.sh` →
  `install_bots.py`; `install-dispatcher.sh` → `install_dispatcher.py`;
  `sync-to-skill.sh` → `sync_to_skill.py`; `inject-defects.py` →
  `inject_defects.py` (a hyphen is not a valid identifier, so it could not be
  imported); `containers/entrypoint.sh` → `scripts/entrypoint.py`.
- **`scripts/test_ablate.py`** — a stale copy of `tests/test_ablate.py` holding 29
  of its 45 tests, imported by nothing and collected by nothing
  (`testpaths = ["tests"]`).

`scripts/sync-to-skill.sh` was cut with the above and **restored**: it is how this
repository's scripts reach the deployed skill a Hermes session loads, not author
tooling. Its absence would have left `/council` undeployable. It is now
`scripts/sync_to_skill.py` — the same job, in the repository's one language.


### Fixed

- **`beta` could not see a tool whose command had a path in its arguments, so three
  of five dimensions were scored partly on judgement when they were fully
  deterministic.** `tool_name_candidates` stripped everything before the last `/`
  in the WHOLE command string, which for a command containing a path takes the tail
  of the last argument instead of the executable:

  ```
  PATH=$TC/bin:$PATH python3 -m pytest tests/ -q   ->  candidates {-q, -q-(308}
  PATH=$TC/bin:$PATH ruff check scripts/ tests/    ->  {(all, (all-checks}
  python3 -m py_compile scripts/*.py               ->  {*.py}
  ```

  On the run that found it, the reviewers HAD run pytest, ruff and mypy and the
  pinned toolchain provides them, but `correctness` measured beta **0.75** and
  `readability` **0.60**. Only the executable is path-stripped now, and leading
  `NAME=value` prefixes are skipped, so both measure **1.00**. The remaining
  `security` beta of 0.50 is honest: those reviewers genuinely never ran bandit or
  pip-audit.

  `council golden --check` reproduces exactly (no pinned score moved) and the
  fixture suite is unchanged — the fixtures' commands have no path arguments, which
  is why the regression was invisible to them.
- **The beta advice said "install", which was the wrong fact.** `tools_missing`
  means "expected, not reported as run"; whether a tool is installed is the
  environment's answer, which `council doctor` gives. The wording sent a reader to
  install ruff, mypy, bandit and pip-audit that were already pinned in the toolchain
  and, for ruff and mypy, already run. It now reads `ruff, mypy not run`.

- **The council reviewed this refactor and found three defects, each reproduced
  before it was fixed.** Run advisory, 3 samples, 1 round: aggregate **91.49 >=
  87.1141, satisfied**, no open high or critical.
  - **`sync_to_skill.py` interpolated the repo path into a `glob` pattern**, so a
    checkout under a directory named `a[b]` shipped 34 files instead of 62 — no
    scripts, no tests, exit 0, no warning. The shell version quoted the prefix, so
    this was a port regression. `glob.escape()` now.
  - **`DEST_SKILL` was trusted verbatim and feeds `prune_tree()`**, which deletes
    whatever the repo does not have. Pointed at a skills-library root instead of the
    council directory, it removed two files belonging to another skill, exit 0. A
    non-empty destination must now hold a `SKILL.md` naming the council.
  - **The verb table existed twice** — in `flake.nix` and `scripts/council.py` — and
    had already drifted: `baseline` was a user verb in the CLI and absent from the
    flake's copy, so nothing checked that `baseline.py` shipped or that its `--help`
    worked. The flake's copy is gone; `checks.commands` asks the built app
    (`council --verbs-json`), and a table that exists once cannot drift.
- **`toolchain.py` raised `IndexError`** on a value-taking option with no value,
  while its sibling arg parser handled the same case. `--interval` was written into
  the systemd unit unvalidated, so `--interval foo` produced a service that fails at
  start rather than at install. `council setup --help` printed "expected one of" and
  exited 2 instead of answering.
- **`doctor.py`'s only `shell=True`** (nothing needs a shell there, and
  `sys.executable` can contain a space), **`entrypoint.py`'s hardcoded `python3`**
  where every other call site uses `sys.executable`, a dead `extra_cfg` parameter no
  caller passed, and `resolve_hermes_home` duplicated verbatim in two modules — now
  one `scripts/hermes_home.py`.
- **The fixed-PATH portability guard was deleted with the shell scripts while a
  fixed PATH list still existed** — in the dispatcher's systemd unit, where it
  matters more than it did in a shell script, because a unit does not inherit the
  caller's PATH. Restored as `tests/test_portability.py`, and `tests/test_modules.py`
  now covers the modules the port introduced, none of which had a test.
- **The CRLF test failed on a stale `.mypy_cache`** in a dev clone while the flake's
  gate stayed green (it checks a git-filtered tree). It skips tool caches now.

- **CI actions moved off Node 20** (`actions/checkout@v4` → `@v7`,
  `actions/setup-python@v5` → `@v7`). Node 20 was removed from GitHub's runners on
  2026-09-23, so the old majors were force-run on Node 24 with a warning on every job.
  `cachix/install-nix-action@v31` is a composite action with no node runtime and is
  correctly unaffected. `docs/CI.md` records how to check an action's runtime, and why
  these are pinned to major tags rather than SHAs.

- **Three `PATH` lists named only NixOS's `/run/current-system/sw/bin`**, so `nix` was not
  found on a native install on another distribution or inside the container image.
  `scripts/nix-toolchain-inner.sh`, `scripts/install-dispatcher.sh` and
  `scripts/install-ci-runner.sh` now list every place `nix` lives, in precedence order. The
  failure was the quiet kind: the helper that resolves the pinned toolchain reported
  "could not resolve", every nix probe returned `ran: false`, and beta dropped with nothing
  in the output to explain why.

- **The container image had no `nix.conf`, so its nix probes could not run.** A minimal
  image has no `/etc/nix/nix.conf`, which leaves the experimental features off — and
  `nix eval` and `nix flake check`, which is what the nix probes actually run, then fail
  with `experimental feature 'nix-command' is disabled`. Measured on the extracted image:
  without a conf `nix eval` and `nix path-info` both refuse; with one, `nix eval` evaluates
  and `nix-instantiate --parse` parses the flake. The conf is staged at `/opt/nix/nix.conf`
  — it cannot live in `/etc`, which arrives from the toolchain as a mode-555 directory —
  and `NIX_CONF_DIR` points at it. It also clears `build-users-group`, because a minimal
  image has no `nixbld` group and nix warns about that on every invocation.

- **The container image had no `/etc/passwd`, so every `nix` invocation failed** with
  `error: cannot determine user's home directory`. Nix resolves `$HOME` through
  `getpwuid()` rather than trusting the environment, so a numeric `config.User` — which is
  all the kernel needs — is not enough for it. `extraCommands` now writes the entry after
  `chmod u+w etc`, since `etc` is mode 555.

- **An unanchored session asks for the project instead of only refusing.** The session
  route is still preferred and unchanged: the loop walks up from the session's cwd looking
  for a git root or a project marker. But when there is no anchor and a terminal is
  attached, it now prompts for the path rather than exiting — which is the "first time"
  case. With no terminal (a scheduled job, a spawned worker, an agent turn) it still
  refuses with exit 2, because nobody is there to answer and blocking would hang instead
  of failing.

- **The author's own paths are out of everything that ships** — `research/` and `runs/`
  records, the `C:/path/to/project` placeholders in the usage text, `docs/AUTONOMY.md` and
  `skills/council/SKILL.md`. The fact each record carries survives; the incidental
  directory does not, and a reader who sees the author's home learns nothing from it.

### Added

- **`./start` — one command, and it works out the rest.** A newcomer should not
  have to know whether they want the nix deployment or the container, and the
  README previously opened with `nix run .#council`, which is only the right
  answer for someone who already has nix. `./start` is bash-only, needs nothing
  installed, and:

  - reports what the machine has (hermes, nix, docker/podman) before doing anything;
  - picks the route and says why — nix native when nix is present, because the
    flake pins the analyzer set and the Nix probes can run; the container otherwise;
  - checks Hermes first, because that is the one requirement it cannot supply, and
    answers it with the single install command rather than failing later;
  - refuses rather than guessing: an unknown option, an invalid `--route`, a
    missing path, or a directory with no `.git` and no project marker. The last
    one matters — an explicit path was previously taken on trust, so `./start /tmp`
    would have reviewed `/tmp` and written `.review-council/` into it, undoing the
    refusal the loop already makes for an unanchored session;
  - warns before the run that a review spends LLM calls, and names `-- --dry-run`,
    `-- --max-rounds 1` and `-- --mode advisory` as the cheap ways to look first;
  - warns when a Nix repository is being reviewed through the container, and about
    the threshold, before a score is read rather than after.

  It is also `nix run .#start`, and it ships in the framework tree so the container
  has it at `/opt/review-council/start`.

- **`council doctor` now prints the score caveat.** `calibration.json` has always
  carried its caveats and nobody reads them; `doctor` is where someone asks "is
  this machine ready?" and it answered only about tooling. It now says whether the
  shipped threshold was calibrated for *the repository in front of you* — it was
  not, unless that repository is this one — and what to do instead. A newcomer who
  runs a review, gets FAIL and concludes the tool is broken is the failure this
  prevents.

- **`checks.start-script`** — shellchecks `./start`, runs it with an empty `PATH`
  (the machine it is written for), and asserts every refusal: an unknown option,
  an invalid `--route`, a nonexistent path and a non-project directory must all
  exit non-zero. The refusals are the contract, so they are a gate.

- **`tests/test_portability.py` — the audit is now a gate.** It scans every shipped file
  for a personal home directory and every fixed `PATH` list for the places `nix` is
  installed, so neither can come back. Two of its assertions guard the guard: that the
  detector still matches the lines it claims to, and that the allowlist is still
  exercised — a regex that silently matches nothing passes forever, and a list of
  permitted names that no longer appears anywhere cannot be reasoned about. It skips
  lines that *prepend* to `$PATH` (they inherit it), `Environment=PATH=$VAR` (a use, not
  a definition) and a `*_PATH` holding a single file rather than a list.

- **`--baseline` — incremental review that carries a whole-repo baseline's findings.**
  `council review <repo> --baseline auto` reads only what changed since the last
  qualifying whole-repo run, carrying that run's findings for the files that did not
  change. The carried findings go back into the numerator before the gate reads the
  files, so `carried + new` still covers the whole repository and the aggregate stays
  comparable to the baseline.

  This is deliberately **not** `--scope diff`. That narrows what is read and puts
  nothing back, so the score rises because less was reviewed — measured on a real
  repository with the scorer's own functions, 69.71 → 89.61 on identical code, clearing
  a threshold of 87.11. `--scope` is a prompt hint and always was; this is a scoring
  change, which is why it carries.

  Three invariants keep the number meaningful, and `docs/BASELINE.md` records why each
  one exists: the denominator is always the whole repo, the probes always re-run
  whole-repo (the deterministic half of beta is never stale), and the LLM self-score is
  carried rather than re-derived, because a reviewer that saw six files cannot honestly
  score a fifty-file repository. An incremental run records `mode: "incremental"` so it
  cannot itself become a baseline.

  A finding is invalidated when its own file changed (`self`) or when a file-like token
  in its claim changed (`reference`) — the cross-cutting class, a doc or comment that
  asserts something about a file that has since moved. Both are conservative on
  purpose: dropping a live finding is worse than keeping a stale one, because the
  reviewer is no longer reading that file.

  A baseline must be complete: whole-repo scope, a pinned sha, all five dimension files,
  and `dropped == 0` **recorded**. `merge_generalist_samples` now writes that count (and
  the probe results, as `probes.json`) into the round, so a run can be validated as a
  baseline at all. Runs made before those fields existed are rejected with the reason,
  not assumed complete.

  The saving scales with the fraction of the repository that did not change, so this is
  worth little on a small repo: 50 files with 16 changed saves almost nothing, while
  2000 files with 5 changed saves most of the sampling cost.

- **`council setup dispatcher` — the durable dispatcher (M7).** Installs
  `hermes-kanban-dispatch.service` as a systemd **user** unit so a swarm advances without
  anyone running `hermes kanban dispatch` by hand, and resumes after a reboot. Resolves
  `hermes` at install time rather than hardcoding a path, and refuses to install if the
  standalone daemon is absent from the build.
- **`council merge <run-dir>`** — buckets a round's generalist samples into the per-dimension
  files the gate reads. The loop did this in-process; in a swarm the samples are written by
  separate cards, so nothing did, and the gate found no reviewer output at all.
- **`council sample <repo> --index N`** — runs ONE reviewer sample and writes
  `generalist-N.json`. It imports the prompt from `council_loop.py`, so a swarm sample and a
  loop sample are the same code and cannot drift.

- **`council swarm <repo>` — the durable council (M7, increment A).** `council review`
  spawns the reviewer as a subprocess and dies with it; the swarm builds the same round
  as a durable kanban board the gateway's dispatcher can reclaim. One worker card per
  sample, all `council-generalist`, with `council-orchestrator` as verifier and
  synthesizer — no third profile.

  The verifier's card instruction is to **run `council gate`** and report its exit code
  and aggregate, not to judge. A model asked to verify a score produces a plausible
  number; the gate produces the actual one. That is the same distinction the β defect
  violated. `docs/M7-PLAN.md` records the design, the increments and the open choices.

- **The golden end-to-end regression suite (M8).** `scripts/golden.py` +
  `tests/golden/`, wired as `checks.golden` and the `council golden` dev verb. It
  replays fixed inputs through the real scoring pipeline and diffs against pinned
  values, so a change to a weight, a tool table, the calibration or the threshold fails
  with the number that moved instead of passing quietly.

  This closes M8's last deliverable, and its acceptance criterion is *demonstrated*:
  `tests/test_golden.py` breaks one scoring input at a time and requires the suite to
  notice.

  It exists because the β defect shipped with 210 green tests — every merge test
  supplied its own fixture, so nothing asserted a score end to end. Two things learned
  while writing it are recorded in the tests themselves: `HILL_K` is dead on a
  calibrated checkout (`hill_density` reads the manifest instead), and `d*` is pooled
  over the non-floored tools only, so mutating a floored tool's `d*` is inert by design.

  The repo's own linters now skip `tests/golden/`: the fixture's line count *is* the
  suite's `kloc`, so a formatter bump that reformatted it would move every pinned score.

### Changed

- **CI runs the gate on GitHub-hosted runners, and no custom cache is used.** Two
  corrections to the 1.0.0 CI setup, both from measurement:
  - The `gate` job was self-hosted. That was wrong: `nix flake check` already runs
    locally against the same store, so a runner on the author's own machine could only
    repeat an answer already held. A hosted runner is the one thing that shares none of
    that state, and it always runs rather than queuing while a box is down.
  - The Cachix step was removed. Of the toolchain's 238-path closure, **236 are already
    in `cache.nixos.org`**, which nix uses by default; the two it cannot fetch are our
    own symlinkJoins, which hold almost no bytes. The claim that CI built "24 packages
    from scratch" was false — they are prebuilt and publicly served. A private cache
    would have added an account, a secret and a failure mode for no gain.

  `docs/CI.md` records both, with the numbers, plus how to add substituters or a private
  cache if the closure ever stops being fully substitutable.

### Changed

- **`flake.nix` is a flake-parts flake.** It was 1,351 lines in one file; it is now
  ~90 lines of configuration over four modules — `nix/builders.nix` (the derivation
  builders), `nix/flake-module.nix` (the consumer-facing surface), `nix/checks.nix`
  (this repo's own gates and the devshell) and `flake.nix` itself. The builders were
  moved as text rather than retyped, and the proof is derivation path: six outputs are
  byte-identical to their pre-conversion paths, including `packages.toolchain`,
  `packages.framework` and `checks.module-evaluates`.
- **`vulnix` ships, but is never probed — on demand only.** It is in the toolchain so
  closure CVEs can be asked when that is the question, and absent from `probes.py` so no
  routine review pays for it. Running it is the expensive half: it fetches NVD data over
  the network (minutes, and the answer moves with the date), it is unmaintained, and it
  matches name+version against NVD so upstream backports are invisible — whitelisting is
  mandatory and no whitelist ships. Its own closure is 193.3 MB, 19.7% of the toolchain
  and 26 MB of the container, which is the price of having it available. The rubric line
  is restored as an explicit on-demand step, `docs/AUTONOMY.md` is back to 24 tools, and
  both `research/nix-tooling.md` rows say "ships, but is never probed".
  `tests/test_probes.py` pins both halves — shipped, and not probed — and the test has
  teeth: wiring a stub `vulnix` probe into `PROBES` makes it fail.
- **`flake.flakeModules.default` is the integration point for another flake.**
  `imports = [ inputs.review-council.flakeModules.default ];` yields the packages, the
  formatter and the app — the same definitions this repo builds for itself, not a copy.
  `flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs"` keeps it to one extra lock entry
  for a consumer.
- **`docs/OPTIMISATION.md`** records the measurements behind all of the below, including
  the ones that were wrong first.

### Removed

- **Three unreachable functions and one unused binding.** `calibrate.pick_threshold`
  (provably unreachable — `sweep_threshold` returns `[]` under exactly the condition that
  makes `choose_threshold` return `None`, so a sweep-based fallback could only ever
  contribute `None`); `baseline.head_sha` (the changed set comes from the round's
  recorded `target_sha`); `baseline.carried_llm_scores` (an identity wrapper — the
  behaviour lives in `council_loop.apply_carry`); and `probes.py`'s unused
  `baseline_path`.

### Fixed

- **The deployed skill can evaluate its flake again.** Splitting `flake.nix` into
  modules under `nix/` broke the deployed copies: a flake's `imports` are eager, so a
  `flake.nix` whose modules are not shipped alongside it evaluates to *nothing* —
  `.#toolchain` included. All three copiers now ship `nix/` (`mkSkill`, `flakeFiles` for
  `REVIEW_COUNCIL_FLAKE_DIR`, and `sync_to_skill.py` for the mirror), and
  `checks.skill-layout` derives the requirement from the deployed `flake.nix` instead of
  asserting a hand-written file list, which is why existence checks passed while the
  flake was inert. Verified: `.#skill` and the mirror both evaluate.
- **`council calibrate --ladder` and `--recalibrate` exist and work.** The verb's own
  description promised "recalibrate the threshold and curves" and `docs/CALIBRATION.md`
  documented `calibrate.recalibrate(...)`, but `main()` never called it. `--ladder`
  measures a ladder once and records the raw points; `--recalibrate` re-derives `d*`, the
  sweep and the threshold from those points without re-running the probes. A manifest of
  the wrong kind is refused by name rather than by traceback.
- **`recalibrate` keeps the measurements it was given.** It dropped `measured` from its
  output, so a re-tuned manifest could not be re-tuned again — which defeats the
  function's whole purpose. Now pinned by a test.
- **`docs/CALIBRATION.md` no longer claims a sweep fallback that cannot exist.** It
  described `pick_threshold` as the fallback "when labels are unavailable", but a
  one-class point set empties the sweep too, so the honest answer is no threshold at all.
- **The duplicated helpers are one implementation, `scripts/_shared.py`.** `norm_path`
  (×2) and `fingerprint` (×2) were byte-identical; `kloc` (×2) differed by a floor nobody
  had written down, which is now the explicit `kloc(root, *, floor=...)`; the `hermes`
  subprocess wrapper (×2) is one function. `_shared.py` is listed in `runtimeModules`,
  because a shared module that does not ship breaks the shipped tree.
- **`tests/test_portability.py` reads every Nix source, not `flake.nix` by name.** The
  launchers moved into `nix/builders.nix`, and a test pinned to one filename fails on the
  next move rather than on a regression.

### Added

- **`gitleaks` is probed and scored.** It was in `doctor.py`'s CATALOG for "secret
  scanning (security)" and named by that file's own comment, but no probe existed — so
  the CATALOG described a signal the framework never produced. The probe reads the
  WORKING TREE (`--no-git`), not git history, and the report's `Secret` field never
  reaches a finding: only the rule, the file and the line are used, and `--redact` keeps
  the value out of stdout too. A probe that leaked the credential it found into a review
  report would be the exact failure it exists to catch. `gitleaks` is now scored for
  every stack's security dimension, alongside the framework's own dependency-free
  `secret-grep` — they fail differently, so both are expected.
- **`shellcheck` is probed.** It was SCORED for the `shell` stack with no probe behind
  it, so a repository containing shell had an expected tool that could never run and beta
  could not reach 1.0 for a dimension the framework claimed to cover. The file list is
  capped and passed on the command line, because shellcheck has no file-list option and
  an unbounded list would hit `ARG_MAX` on a large repository.
- **`score_reviews.EXTERNAL_TOOLS`** declares which expected-tool names are binaries the
  toolchain must ship; every other name is a probe implemented inside `probes.py`. Four
  tests pin the contract, including that every expected name for a stack we ship has a
  probe — derived from `STACK_TOOLS`, not a hand-written list. The previous hand-written
  list is exactly how the `shellcheck` gap survived.

### Changed

- **The toolchain is split into two lists.** `toolNames` is the centralised QA toolchain
  that ships (devshell, container, `nix shell .#review-council`), and a tool is in it only
  if the gate scores it, a probe runs it, or it provides an output. `devToolNames` is
  contributor DX — the LSPs, the closure browsers and the density meters — and lands in
  the devshell only, so the product carries only what a review runs and a contributor can
  install their own editor tooling without colliding with the framework's. Measured: the
  QA toolchain closure is **919.8 MB / 180 store paths**, down from 983.3 MB / 212.
- **The rubrics that named a devshell-only tool now say so** (`nix-tree`, `nix-diff`,
  `nix-du` in performance; `nix-fast-build` in correctness; `tokei`, `cloc` in
  readability), so a reviewer in the container is not sent looking for a binary that is
  not there.
- **`docs/TOOLCHAIN.md`** records the per-tool verdict: 13 necessary, 9 DX, and the two
  gaps this change closes.
- **`docs/AUTONOMY.md`** carries both lists and the rule that decides membership.

### Fixed

- **The readability rubric's KLOC claim was wrong.** It named `tokei`/`cloc` as "the KLOC
  denominator"; the denominator is computed by `probes.py` over its own source-suffix set
  and neither tool is involved. The line now says so, and the two are devshell
  conveniences for reading a report by hand.
- **`checks.toolchain-built` called bare `gitleaks`/`shellcheck`** in a derivation with no
  `nativeBuildInputs`, so nothing was on PATH. Every other line in that check spells
  `${tc}/bin/...` out; the new ones do too.
- **`checks.probes` had no shell file in its fixture**, so `shellcheck` correctly reported
  "no shell files in the tree" and never ran. That is the check working — it caught the
  fixture gap rather than the probe passing vacuously.

### Fixed

- **The NixOS VM test had been exercising an empty round.** `mkStubHermes` read the
  prompt from `-q` / `--query`, but `council_loop` sends `--query-file` — because a
  reviewer prompt exceeds `ARG_MAX`. The stub therefore found no prompt, printed usage
  and exited 0, and `.#vm-test` passed its own assertions without a review ever running.
  It reads both forms now, verified by building the stub and invoking it with
  `--query-file`: it writes the findings file with all five dimension scores.
- **`doctor.py` pointed at the wrong file.** Three user-facing strings said to declare a
  missing tool in `flake.nix`'s `toolNames`; the tool set moved to `nix/builders.nix`, so
  the advice sent the user to a file that no longer holds it.
- **`reviewer-security`'s whole secret-scanning procedure could not run.** Its seven
  `rg` commands are the rubric's scan for secrets reaching the store, impure eval,
  hash-less fetches, `allowUnfree`, `allow-flake-config` and `trusted-users` — and
  ripgrep is in neither tool list, so in the container every one was "command not found"
  and the dimension reported nothing for the procedure it documents. They use `grep`
  now, which ships in the toolchain's shell dependencies. Verified against planted text
  for all four command shapes (pipe, `-E` alternation, `--` separator, `-v`).
- **`docs/CI.md`'s cache numbers were from the pre-split toolchain.** 925.8 MiB / 238
  paths and "236 of 238 available" are now 919.8 MB / 180 and **178 of 180** — measured
  per path, one at a time. The conclusion is unchanged and now rests on current numbers:
  the only two paths not on `cache.nixos.org` are the two `symlinkJoin`s. The doc also
  records why the measurement must be per-path: a batched query reported 30 absent paths
  where the true figure was 2.
- **`docs/RESEARCH.md` indexed 4 of the 6 reports** in `research/`. The two Nix reports
  are listed now, so the index covers the directory.

### Fixed

- **Three measurements could not be reproduced, so they were replaced.** They were
  flagged rather than left: a number nobody can re-derive is not evidence.
  - `skills/council/SKILL.md` quoted prompt figures measured on "a two-file Python
    fixture" that is not in the repository, against a probe set that has since changed
    (`gitleaks` and `shellcheck` added; `treefmt`, `yamllint`, `tokei` and others
    removed). Re-measured on the shipped `tests/golden/target`: `probe_json` is **60%**
    of a 7,650 B prompt, and compacting it saves **805 B per sample**. The unreproducible
    findings-file breakdown and the n=1 A/B byte counts are gone; the conclusions they
    supported are kept, including that the saving is untested and therefore not applied.
  - `docs/CONTAINER.md` and `docs/OPTIMISATION.md` carried container figures from the
    pre-split toolchain: 333 MiB and a 2.33 GB "loaded image". Measured now: **99
    layers**, tarball **313 MiB** (328,344,703 B), layer content **1.06 GB**
    (1,064,611,840 B). The 2.33 GB figure is gone — it was docker's layer accounting
    quoted from a comment, not a measurement, and the layer content is what can be
    checked without a daemon.
- **Probing a repository MODIFIED it.** `nix flake check` and `nix eval` write
  `flake.lock` into the tree they run against, so a review left a new file in the
  user's working copy. A review is a read. Both now pass `--no-write-lock-file`, and the
  flag must follow the subcommand — `nix flake --no-write-lock-file check` is
  "unrecognised flag", which the first attempt shipped. Caught because probing
  `tests/golden/target` created a `flake.lock` there and the fixture's own hashes
  picked it up; the fixture was restored and the guard is pinned by two tests.

- **`review-council-orchestrator`'s `termination` enum implied a machine contract that
  does not exist.** The rubric asked for `termination ∈ satisfied | continue | blocked |
  escalate`; the loop writes the aggregate reply to the log and **discards it**, and the
  gate decides the verdict with its own vocabulary (`satisfied | not_satisfied`). The
  rubric now says the message is for the log, so a reader is not left assuming something
  parses it.

### Removed

- **`treefmt`** — the `formatter` execs `${nixfmt-tree}/bin/treefmt`, so the standalone
  package was a second copy of the same binary. Measured: removing it frees 0.0 MB.
- **`yamllint`** — nothing used it. It was tested as a flake-check candidate against the
  repo's own workflows and fails on them (line-length errors), so making it pass would
  have meant adding a config file to justify a linter nothing needs. For linting the
  workflows the right tool is `actionlint`, which CI already uses.

## [1.0.0] — 2026-10-11

First release. The framework reviews a git diff, scores it with a hybrid of
deterministic analyzer signals and LLM rubric judgement, and iterates until that
score clears a threshold or the run stalls.

### Added

- **The scored loop** (`scripts/council_loop.py`). Each round: the orchestrator sets
  one goal per dimension, the harness convenes the reviewer, the gate recomputes the
  score from the reviewer files, and the orchestrator judges the round against the
  goals it set. Termination is adaptive — threshold **and** no-improvement detection,
  with a budget and a round cap.
- **The deterministic gate** (`scripts/score_reviews.py`). Reads one JSON file per
  dimension, recomputes the hybrid score itself, and never trusts a number an agent
  asserted. Exit 0 satisfied, 1 not satisfied, 2 error. The pass threshold is read from
  `scripts/calibration.json`, so the number the loop enforces and the number the
  calibration recommends cannot drift.
- **Twelve built-in probes** (`scripts/probes.py`) — stdlib-only and cross-platform, so
  a review has real deterministic signal on a machine where nothing is installed. Each
  third-party analyzer layers on top when present.
- **A pinned toolchain** (`flake.nix`, `flake.lock`) — 24 analyzers from one nixpkgs
  revision, so the whole set moves atomically with a single lock bump.
- **One command** (`nix run .#council`) with verbs for review, gate, doctor, probes,
  inventory and setup; five further verbs for working on the framework are devshell-only.
  `nix shell .#review-council` puts the command and the analyzers on one PATH.
- **Five dimension rubrics** (`skills/reviewer-*/SKILL.md`) — security, correctness,
  readability, architecture, performance — plus the orchestrator rubric.
- **The ablation harness** (`scripts/ablate.py`) and two defect corpora with independent
  ground truth (`council corpus`).
- **Calibration** (`scripts/calibrate.py`) over a graded defect ladder.
- **CI** (`.github/workflows/ci.yml`): a three-OS test matrix on GitHub-hosted runners,
  and the real gate on a self-hosted runner with optional Cachix.

### Changed

- **One reviewer, not five.** The architecture originally called for five isolated
  specialist reviewers, one per dimension. The ablation measured that arrangement
  against one generalist sampled five times, at equal cost, and the specialists lost
  twice — 13/22 and 16/22 injected defects against 22/22 both times, against a
  pre-registered 1.5× rule. The five per-dimension profiles were deleted; their rubrics
  remain and are loaded together by one `council-generalist` profile. See
  `docs/MILESTONES.md` M8.5 and `runs/ablation-22-defect-2026-10-11.md`.
- **`delegation` removed from every profile.** The council originally fanned out with
  `delegate_task`. A delegated child inherits the parent's `HERMES_HOME` and so cannot
  load another profile's rubric, which silently produced five generic subagents wearing
  dimension labels. The harness now spawns the reviewer profile itself.
- **Thirteen apps collapsed to one command.** `council-gate`, `council-doctor`,
  `council-ablate` and the rest are now verbs: `council gate`, `council doctor`, ….
  `audience` decides which surface sees a verb, and a check enforces that dev-only verbs
  stay out of the shipped app.

### Fixed

- **A total reviewer failure scored a clean 100 and passed.** The merge wrote five empty
  dimension files when no sample was readable. It now leaves the dimensions missing, which
  the gate treats as an error.
- **The deployment sync never pruned.** A file deleted in the repo lived on in the skill
  deployment, and `install-bots.sh` run from the skill would have reinstalled deleted
  profiles. The sync now mirrors and reports extras.
- **`--help` was a trap on verbs that act.** `council handoff --help` would have exported
  a bundle rather than explaining itself. The dispatcher answers `--help` for verbs whose
  scripts do not parse arguments.
- **Two scoring bugs that inverted the ablation result**: exclusive nearest-match recall
  split one finding between two adjacent defects and reported one as missed, and a
  distance check that ignored paths let a finding match a defect in a different file —
  which reported zero false positives for every arm. Both are pinned by tests.

### Not built, deliberately

- **M1's Pydantic protocol package and M2's `src/review_council/` adapter tree.** The
  framework works as `scripts/`; those layers would be a rewrite, not an improvement.
  Findings travel as one JSON file per dimension, not the uniform YAML envelope the plan
  drew.
- **M7 durability surfaces** — kanban, cron, GitHub PR integration.
- **The golden end-to-end regression suite**, and the `α_t` weights stay uncalibrated
  until evidence justifies reweighting.
- **The `/goal` binding.** The loop's own goal phase runs; the binding to Hermes' `/goal`
  feature is documented in `docs/AUTONOMY.md` but not wired.

### Known limitations

- The `gate` CI job has never executed: no self-hosted runner is registered yet, so a
  push leaves it queued.
- The ablation rests on **one corpus, run twice**, with the corpus and the scorer written
  by the same author as the rule they test. Recall is location-based, so the
  false-positive counts are a floor.
- A reviewer cannot re-run the pinned probes from inside a run, so β can fall below 1.0
  and pull the LLM score in.

[1.0.0]: https://github.com/washedupdeveloper/agentic-council/releases/tag/v1.0
