# review-council — Autonomy & Invocation

How the council runs **fully autonomously** and how to **invoke it manually**.
Implements the locked design in `docs/DECISIONS.md` #6 and #10, and
`docs/FRAMEWORK.md` §7 (the loop), §8 (termination), §12 (autonomy).

`council` is one CLI (`scripts/council.py`), reached as `nix run .#council -- <verb>`
or through the container image; every command below is one of its verbs.

## The two entry points

| Mode | What it does | How to invoke |
|---|---|---|
| **Manual** | Reviews the current stage and reports. Never edits. | `/council [<repo>]` — the `council` skill |
| **Autonomous** | Reviews, applies fixes, re-reviews until the gate passes or the run stalls. | `council review [<repo>] --mode full` |

Both are driven by the same deterministic gate, so a "pass" means the same either way.

## Resolving the target project

The repo argument is **optional**. The run starts from a live session (the desktop
app, the TUI, or the CLI), so the target is resolved from the session, not a shell:

1. An **explicit path** always wins.
2. **The session working directory**, walked up to the nearest `.git` — the
   project boundary Hermes itself uses. If there is no git root, take the nearest
   directory carrying `.hermes.md`, `HERMES.md`, `AGENTS.md`, `CLAUDE.md`,
   `pyproject.toml`, `package.json`, `Cargo.toml`, or `go.mod`. In the desktop app
   a *Project* anchors the chat's workspace, so the session working directory
   follows it.

`resolve_project()` implements both, and the run prints what it inferred and why,
so a wrong inference is visible rather than silent:

```
$ council review --dry-run
inferred project: /home/you/projects/myrepo
  (git repository root at /home/you/projects/myrepo)
```

### When the session is not anchored

With no project (cwd is a home directory, no git root, no marker) and a terminal
attached, the run **asks** for the path. With no terminal — a scheduled job, a
spawned worker, an agent turn — it **refuses** with exit 2 rather than reviewing the
wrong tree, and writing `.review-council/` into it:

```
council_loop: could not identify a project from the session.
  looked in: /home/you
  no git root and no project marker (.hermes.md / AGENTS.md /
  CLAUDE.md / pyproject.toml / package.json / Cargo.toml / go.mod)

Fix one of:
  * pass the path explicitly:  council_loop.py <path/to/project>
  * anchor the session to a project (desktop: the Projects picker;
    CLI/TUI: launch from inside the project (`cd /path/to/project`);
             `--in` is Hermes main only and is absent from the wheel)
```

**Anchoring the session is the recommended setup.** Create or switch a desktop
Project, or launch the TUI/CLI from inside the project (`cd /path/to/project`);
`/council` then reviews the right repo with no argument.

## The loop (FRAMEWORK §7)

```
intake → set goals → convene (each with its goal) → validate → aggregate
       → score → gate → goal review → (fix → re-review)* → terminate
```

**The orchestrator sets the goals; the harness owns the convening.** Each round the
orchestrator decides what the round is *for* — one goal per dimension — and the
harness then spawns **one generalist profile sampled N times**. A reviewer's rubric
is installed into its profile, which is why the harness spawns a profile rather than
delegating.

1. **Intake** (harness). Resolve the target revision, detect the stacks, and run
   every deterministic probe **once** for the whole run.
2. **Goals** (orchestrator). Given the repo and the probe summary, write
   `<run_root>/round-N/goals.json`: one goal per dimension, each an *objective*
   plus the *evidence that would show it is met*, and optionally the paths to focus
   on. Goals are deliberately **qualitative** — the prompt forbids naming a score or
   a threshold, because a goal that names a number invites gaming it and the
   threshold is held out of every child's context.
   **Fail-open:** if the orchestrator cannot produce a *complete* goal set, the
   built-in default set is used and the round proceeds. A goal-setting failure is
   not a review failure. A partial set is treated as absent rather than partially
   applied, so the difference is never invisible in the run report.
3. **Convene** (harness). Spawn the generalist profile N times (5), each sample
   carrying all five rubrics, its probe slice **and the goals**; the harness buckets
   each finding by the dimension it declares, giving
   `<run_root>/round-N/<dimension>.json`. The harness also writes `meta.json` — it
   knows the sha and the stacks, the LLM does not.
4. **Aggregate** (orchestrator). Validates each file's schema and builds the
   evidence matrix. It does **not** fan out, re-review, or score.
5. **Gate.** `council gate` reads the reviewer files and recomputes the hybrid
   score itself. It never trusts a number any agent asserted. Exit 0 = satisfied,
   1 = not satisfied, 2 = error. A reviewer that produced **no file** is an ERROR,
   never a clean bill of health.
6. **Goal review** (orchestrator). Reviews the round against the goals it set:
   MET / PARTIAL / NOT MET per goal, with the evidence, and what the next round
   should target. A dimension whose reviewer produced no file is **UNVERIFIED**,
   never "met". The gate has already decided acceptance — the goal review explains
   it and never overrides it, so the verdict lives in exactly one place.
7. **Fix turn** (`--mode full` only). The gate's stdout — the ranked findings — is
   fed back as the continuation prompt, and the orchestrator applies fixes.
8. **Repeat** until a termination condition fires.

### Why profiles, not `delegate_task`

`delegate_task` spawns **in-process subagents that inherit the parent's
`HERMES_HOME`**. A reviewer rubric lives in the reviewer's *own* profile, so a
delegated child cannot load it. An earlier version fanned out that way and ran five
generic subagents wearing dimension labels — applying none of the rubrics' scoring
anchors, hard gates or checklists — while still producing gate-readable JSON.

Consequences, all enforced rather than merely documented:

- **No agent in the fleet has `delegation`** — not the reviewers, and not the
  orchestrator. The harness is the only thing that spawns agents, so there is
  exactly one fan-out path and it is the one that applies the rubrics.
- The reviewers are therefore **sub-agents of the council**, not free-standing
  agents. Each is a leaf: no `delegation`, no code edits.
- They remain individually invocable for a single-dimension check, but that is a
  debugging affordance; the council is the supported path.

## Autonomy modes (DECISIONS #6, FRAMEWORK §12)

| Mode | Reviews | Applies fixes | Escalates |
|---|---|---|---|
| `full` (default) | yes | yes, autonomously | on block/escalate |
| `semi` | yes | only after approval | at threshold/stall/before edits |
| `advisory` | yes | never | always |

`semi` prompts before each edit and refuses to edit when stdin is not a TTY —
an unattended `semi` run degrades to `advisory` rather than editing unattended.

## Termination — adaptive (FRAMEWORK §8, M8)

**The threshold is the MINIMUM requirement. Everything above it is desirable but
not required.** The loop climbs while it is gaining ground and stops — handing over
a next-steps plan — once the gains stall, the time budget is spent, or the hard
round cap is reached. Chasing the theoretical maximum is explicitly not the goal.

Order of precedence:

| # | Condition | Outcome | Reason string |
|---|---|---|---|
| 1 | round cap reached | `satisfied` if the minimum was met, else `escalate` | `round cap reached (N) …` |
| 2 | wall-clock budget spent | `satisfied` if the minimum was met, else `escalate` | `time budget exhausted` |
| — | *below `--min-rounds`, with no cap/budget binding* | continue | *(the floor)* |
| 3 | minimum met **and** gain `< ε` | `satisfied` | `minimum met; further gain … — stopping and planning the remainder` |
| 4 | minimum met **and** still gaining | continue | — |
| 5 | score regressed across three rounds | `escalate` | `oscillation: …` |
| 6 | improvement `< ε` | `escalate` | `stalled: …` |
| 7 | no new finding id for `k` rounds | `escalate` | `novelty: …` |
| 8 | `advisory`/`semi` declined to edit | `escalate` | `advisory mode: …` / `semi mode: …` |

Notes on the ordering:

- **Hard limits outrank the `--min-rounds` floor**, or the floor could overrun a
  cap or budget.
- **A specific reason beats a generic one.** If an oscillation and the round cap
  coincide, the reason is `oscillation` — it tells the next iteration what to
  change, where `round cap reached` does not. The decision to stop is the same.
- **Hitting a cap is not a failure** if the minimum was already met; the outcome
  reflects the requirement, not the mechanism that ended the run.

`--k` (default 2) is the novelty window; `--epsilon` (default 0.5) is the
diminishing-returns floor.

## The next-steps plan

A plan is written on **every** termination — satisfied or not — to
`<run-root>/next-steps.md`, and its path is recorded in `outcome.json`. When the
loop stops early (budget spent, gains stalled, cap reached) this is the
deliverable that lets the next iteration pick up instead of starting over.

Structure:

| Part | Content |
|---|---|
| Header | outcome, reason, rounds used, budget, and *separately* the aggregate vs the minimum and what is blocking |
| Score trajectory | the per-round table and the net movement |
| A. Required to meet the minimum | open blocking findings, and (only when the aggregate is short) the dimensions that need to move |
| B. Desirable, in priority order | ranked by `points_potential`, the *weighted* headroom each item can move — priority is a number, not prose |
| C. How to resume | the exact re-run command, plus the cheaper `doctor`/`probes` checks to try first |

The score requirement and the blocking-finding gate are independent: a run whose
aggregate clears the minimum but is blocked by a finding reports **meets the minimum**
plus **blocked by**, never "below the minimum". The same ranking is fed to the fix turn
as a prioritised work list, so an in-flight fix targets the highest-value items rather
than whatever the prose mentioned first.

## Flags

```bash
council review [<repo>] \
  --mode full|semi|advisory \
  --scope diff|working-tree|whole-repo \
  --samples 5 \
  --baseline off|auto|<run-root> \
  --threshold 80 \
  --min-rounds 1 \
  --max-rounds 8 \
  --budget-seconds 0 \
  --k 2 --epsilon 0.5 \
  --timeout 1800 \
  --run-root <dir> \
  --dry-run
```

- `--threshold` is the **minimum** score required to pass; default: the calibrated value in `scripts/calibration.json`.
- `--samples` (default 5) is the generalist sample count — recall versus wall-clock.
- `--baseline auto` reviews only what changed since the newest qualifying whole-repo run, carrying its findings for unchanged files.
- `--budget-seconds 0` means no limit; when spent, the loop stops and hands over the plan rather than being killed mid-round.
- `--max-rounds` is a hard safety cap, not the normal stopping mechanism.

`<repo>` is optional — omit it to infer the project from the session (see above).

Exit codes: `0` satisfied (minimum met) · `1` escalated · `2` error.

## The gate

```bash
council gate <run-dir> [--threshold 80] [--json] \
       [--allow-partial] [--tail-chars 3000] [--quiet]
```

**A partial council cannot certify a pass.** If any dimension's file is missing or
unparseable the gate exits 2, because renormalizing over whatever happened to load
would let a run that omits the hard-gate `correctness` dimension report "satisfied".
Pass `--allow-partial` to opt into scoring a genuinely partial run.

## Scoring (FRAMEWORK §6)

```
det[c]   = weighted_geometric_mean(tool signals, findings density)
llm[c]   = the reviewer's rubric score (0-100)
β[c]     = tools_ran_and_parsed / tools_expected     # MEASURED, not asserted
score[c] = β[c]·det[c] + (1 − β[c])·llm[c]
aggregate = Σ weight[c]·score[c]
```

Weights: security .30, correctness .25, readability .20, architecture .15,
performance .10. With β = 0 the det term is inert by construction, so a vacuous
deterministic signal cannot inflate a score — the failure mode where a zero-Nix
repo makes Nix-pattern greps trivially "clean".

**The threshold is calibrated to this repository from one sample** — `87.1141`,
marked `PROVISIONAL` in `scripts/calibration.json` — and the `α_t` weights remain
uncalibrated defaults. On another repository neither is a pass mark.

## The deterministic toolchain (β)

β is the fraction of a dimension's *expected* tools that actually ran. A missing
analyzer doesn't fail the run — it silently drops β, so the dimension is scored on
reviewer judgement alone.

### Nix is the provisioning path (pinned, declarative)

`flake.nix` declares the tool set; `flake.lock` pins the exact nixpkgs revision.
`nix build .#toolchain` yields the same store path on every machine, so every reviewer
runs identical tool versions. Nothing is installed imperatively and nothing drifts.

```bash
council setup toolchain --path        # the toolchain store path
council setup toolchain --inventory   # pinned tool versions as JSON
council setup toolchain -- statix check . -o json
council setup toolchain --which ruff
```

`REVIEW_COUNCIL_TOOLCHAIN` wins when it is set — the container image bakes it in
and the devshell exports it — so nothing builds the toolchain at run time.

The tool list is `research/nix-tooling.md` §0 plus the Python toolchain DECISIONS #3
requires. Current set (23 tools): `nix`, `nixfmt`, `nixfmt-tree`, `treefmt`, `statix`,
`deadnix`, `nixd`, `nil`, `nix-tree`, `nix-diff`, `nix-fast-build`, `nix-du`,
`gitleaks`, `osv-scanner`, `tokei`, `cloc`, `jq`, `ruff`, `mypy`, `pytest`, `bandit`,
`shellcheck`, `yamllint`.

**`vulnix` is deliberately NOT in the set** (24 -> 23). It is unmaintained upstream;
it needs a maintained whitelist this repo does not ship, so its own rubric line
could not run; and `--system` scans the closure of the machine RUNNING it rather
than the repository under review. Advisory CVEs for the pinned nixpkgs come from
the Nixpkgs security tracker instead. Measured: removing it frees 193.3 MB, 19.7%
of the toolchain closure and 26 MB off the container.

**semgrep is deliberately excluded**: it is not in the §0 inventory, and it does not
build on this nixpkgs revision (`pyjwt~=2.13.0 not satisfied by 2.14.0`). A tool that
cannot build is worse than an absent one — it fails the whole toolchain, taking every
other analyzer with it.

### Per-stack tool tables

`STACK_TOOLS` in `score_reviews.py` keys expected tools by **language stack**, not by
a single fixed toolchain. A Nix-only table makes β structurally 0 on a Python repo no
matter how many analyzers run, which makes the deterministic half of the hybrid
decorative. Stacks are detected from marker files and source extensions
(`detect_stacks`), and a dimension's expected set is the union across every stack present.

```bash
council gate <run-dir> --repo <repo>        # auto-detect
council gate <run-dir> --stacks nix,python  # force
```

### Built-in probes — zero installs

`scripts/probes.py` implements the checks the framework owns, so a review has
real deterministic signal even on a machine with no Nix:

| Probe | Dimension | What it checks |
|---|---|---|
| `secret-grep` | security | hardcoded credentials in source |
| `py-compile` | correctness | Python syntax, via stdlib `compile()` |
| `bash-n` | correctness | shell syntax, via `bash -n` |
| `complexity` | performance | cyclomatic complexity per function (`ast`) |
| `dep-graph` | architecture | intra-repo import graph, fan-out coupling |
| `declared-rules` | architecture | presence of declared architecture rules |
| `statix` | security, readability | `statix check . -o json` |
| `deadnix` | readability | `deadnix --output-format json .` |
| `nixfmt` | readability | `nixfmt --check` (binary gate, per §1) |
| `flake-check` | correctness | `nix flake check --no-build --keep-going` (hard gate, §2) |
| `nix-eval` | correctness | `nix-instantiate --parse` per file (§2) |
| `nix-eval-time` | performance | `nix eval` wall-clock, as a ratio vs a pinned baseline (§3) |

```bash
council probes --all --repo <repo>
council probes statix --repo <repo>
```

Each emits `{"tool","ran","parsed","signal","findings"}` where `signal` is a
normalized 0-100 deterministic score the gate feeds into the geometric mean. A
probe that cannot run reports `ran: false` — it never invents a result, because
that would inflate β.

Note the parser: statix pretty-prints each JSON object across many lines while deadnix
emits one object per line. `_json_objects` uses `raw_decode` over the whole stream so
both shapes parse — a line-based parser works for one and silently returns **zero**
for the other, which reads as a clean bill of health on a file that does not even parse.

### doctor — what's missing and how to get it

```bash
council doctor --repo <repo>            # report
council doctor --repo <repo> --json     # machine-readable
council doctor --repo <repo> --install  # install what's missing (asks first)
```

It reports the detected stacks, whether Nix is available, the pinned nixpkgs revision
and toolchain store path, β now vs reachable, and how to get anything missing. With
Nix available the advice is **always declarative**: add the tool to `flake.nix`'s
`toolNames` and rebuild. The pip/brew/scoop hints appear only for hosts without Nix,
and only for installers that are actually present.

It also reports **Hermes**, because β answers "how much of the score is deterministic"
and says nothing about whether a review can run at all. A machine with no Hermes and
β 1.00 is a machine that cannot review, and reporting only the second number is how a
user discovers the first from a failed run.

### Finding Hermes — and what can actually be known

The council does **not** talk to a Hermes *gateway*. It shells out to the `hermes`
launcher (`hermes -p <profile> chat -q <prompt>`) and reads the file that turn writes.
`hermes serve` — the backend the desktop app and remote clients connect to — is a
different thing, and a reachable port on it is **not** evidence that the council can
run an agent. Conflating the two is how a host reports "Hermes available" and then
fails every review.

So the question is answered in layers, cheapest and most certain first, and a weak
signal is never promoted into a strong claim:

| Layer | Kind | What it establishes |
|---|---|---|
| **L0 launcher** | deterministic, local | `HERMES_BIN`, then `PATH`, then known locations. `which` proves *presence*. |
| **L1 version** | deterministic, local | `hermes --version` — proves it **executes**. A file that cannot run resolves fine and then fails every turn. |
| **L2 profiles** | deterministic, local | the council's profiles exist **and carry a provider**. Hermes keeps credentials per profile and does not share them. |
| **L3 gateway** | optimistic, network | something is listening where a backend would be. A **hint**, and never part of the verdict. |
| **L4 capability** | authoritative, costly | one real minimal turn. The only layer that proves anything, and the only one that costs money — so it is opt-in, behind `council doctor --probe`. |

The verdict names the **first** thing that would stop a review, because that is the one
worth fixing:

```
hermes    : Hermes Agent v0.0.0 (2026.9.24)  (/home/you/.nix-profile/bin/hermes)
  profiles: council-generalist, council-orchestrator  (provider configured: both)
  gateway : 127.0.0.1:9119 reachable  (a hint only; the council drives the launcher, not this)
  verdict : ready — a review can run
```

**Why not just check the port?** Because it answers a question nobody asked. The
requirement is "a launcher that can complete a turn", and a listening socket is neither
necessary nor sufficient for it: the gateway can be up while the launcher is absent (the
desktop case), and the launcher can work with no gateway at all (the CLI case, which is
every ordinary install). The port is a useful diagnostic when a *remote* setup
misbehaves; it is not the availability test. `tests/test_hermes.py` pins both directions:
a live listener must not turn a missing launcher into `ready`, and a dead port must not
spoil a working one.

**Reaching a host from a VM or container — measured, not assumed.** A `127.0.0.1`
inside a guest is the guest. In a NixOS VM test:

| probe from the VM | sandbox ON | sandbox OFF |
|---|---|---|
| control: a listener *inside* the VM | OPEN | OPEN |
| host service via `127.0.0.1` | CLOSED | CLOSED |
| host service via `10.0.2.2` | CLOSED | **OPEN** |

Three separate facts, and the middle one is the one that surprises people:

1. **`127.0.0.1` is the guest.** It never reaches the host, in any configuration. The
   control line is what makes that a measurement rather than an assertion.
2. **`10.0.2.2` is QEMU's SLIRP gateway** — the loopback of whatever network namespace
   the QEMU process is in. The test driver's own listener is reachable there in both
   columns, so the gateway works; what differs is *which* namespace it points at.
3. **The Nix build sandbox gives the build its own network namespace**, so by default
   that gateway is the sandbox's loopback and the host's services are invisible.
   `--option sandbox false` makes the host's `127.0.0.1` reachable at `10.0.2.2`.

So a VM reaches the host at **`10.0.2.2`, and only with the sandbox off** — not at
`127.0.0.1`. Under WSL's mirrored networking `127.0.0.1` *does* reach the Windows host,
which is exactly why the assumption is easy to make: it is a property of that setup,
not of guests in general. A container sharing the host's network namespace
(`--network host`) gets a host process's reach; a VM does not.

Note that `--option sandbox false` alone changes nothing on a second run — it is not
part of the derivation, so nix returns the cached result and the option looks inert.
Force it with `--rebuild`, or the experiment will "confirm" whatever it did last time.

### Tool-name matching is fuzzy on purpose

A reviewer may report `py_compile`, `py-compile`, `python -m py_compile`,
`python3 -m py_compile`, `/usr/bin/ruff`, `ruff.exe`, or `cargo test`. All resolve to
the expected tool (`tool_name_candidates`). Without that, one character or one
invocation style silently zeros a dimension's β.

## Where the state lives

```
<repo>/.review-council/<timestamp>/
  council.log          full transcript of every turn
  outcome.json         {outcome, reason, scores, threshold, mode, repo}
  round-N/<dim>.json   the reviewer output the gate reads
  round-N/meta.json    {target_sha, mode, round}
```

`.review-council/` is git-ignored machine scratch; curated, human-readable reports
belong in `runs/`, which **is** committed.

## Unattended runs

For a schedule that survives restarts, use cron rather than a live session:

```bash
hermes cron add --name council-nightly --schedule "0 2 * * *" \
  --command "council review <repo> --mode full --max-rounds 2"
```

For unattended runs that must survive restarts, `council swarm` builds the durable
council as a kanban graph and `council setup dispatcher` runs it as a systemd user service.

## Distribution: repo ↔ skill

This repo is the **source of truth**; the `council` skill is the **distribution**. It
is self-contained — it bundles the scripts, the orchestrator bot definition and the six
rubrics under its own directory, so installing it on a new machine needs no clone:

```
<skill_dir>/scripts/*.py
<skill_dir>/assets/bots/council-orchestrator/{SOUL.md, bot.yaml, profile.yaml}
<skill_dir>/assets/rubrics/<name>/SKILL.md
```

Push repo changes into the installed skill with `council setup skill`; it resolves the
destination from the live Hermes config (`skills.external_dirs`, else the Hermes
home), so it is portable across Windows/macOS/Linux. `council setup bots` (the
installer) reads from either layout — `<root>/bots` + `<root>/skills` (repo) or
`<root>/assets/bots` + `<root>/assets/rubrics` (skill) — so the same installer
bootstraps profiles from whichever tree it lives in.

**Nothing in this framework hardcodes a machine path.** Every location is derived
at runtime from the skill's own directory, the Hermes home, or the session.

## Testing

```bash
python tests/test_council_loop.py          # termination paths (§7/§8)
python -m pytest tests/test_score_reviews.py   # scoring + gate contract
```

Both suites stub the orchestrator and exercise the **real** gate, so the continue/stop
decisions are tested against the real scoring code.
