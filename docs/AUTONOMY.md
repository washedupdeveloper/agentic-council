# review-council — Autonomy & Invocation

Implements the locked design in `docs/DECISIONS.md` #6 and #10, and
`docs/FRAMEWORK.md` §7 (the loop), §8 (termination), §12 (autonomy).

`council` is one CLI (`scripts/council.py`), reached as `nix run .#council -- <verb>`
or through the container image; every command below is one of its verbs.

## The two entry points

| Mode | What it does | How to invoke |
|---|---|---|
| **Manual** | Reviews the current stage and reports. Never edits. | `/council [<repo>]` — the `council` skill |
| **Autonomous** | Reviews, applies fixes, re-reviews until the gate passes or the run stalls. | `council review [<repo>] --mode full` |

Both run on the same deterministic gate, so "pass" means the same either way.

## Unattended runs

`council cron <repo>` emits the `hermes cron create` job for a scheduled review;
`--install` creates it. The job's prompt tells the agent to **run** the council and report
the gate's numbers verbatim, never to review the code itself — a cron agent reviewing on
its own would be a reviewer outside the framework, and its score would not be the score
the gate enforces.

It prints rather than installs by default: a schedule outlives the session that made it,
so it is something a person opts into. `cron.allow_agent_scheduling` is false, so a
reviewer cannot schedule its own follow-ups.

Durability for a long run is separate: `council swarm` puts the round on the kanban board,
where a dispatcher can reclaim it (`council setup dispatcher`). A cron job starts a run; a
swarm survives one.

## Posting to a pull request

`council pr <run-dir> --repo owner/name --pr N` posts the run's verdict as a PR review.
The numbers come from `score_reviews.evaluate` — the gate's own function — so the comment
and `council gate` cannot disagree about the same run.

It prints the request and posts only with `--post`. The default event is `COMMENT`, which
cannot block a merge; `--event auto` sends `REQUEST_CHANGES` when the gate fails, for a
team that wants the gate enforced on the PR.

Two things it does for you rather than leaving them to the operator:

- **It will not post the same run twice.** GitHub has no idempotency key for reviews, so
  the body carries an HTML-comment marker naming the run and the PR, and an existing
  review carrying it is skipped.
- **It pins `commit_id`** from the run's `meta.json`, so the review attaches to the commit
  the council scored, not the PR's latest one.

The token comes from `GITHUB_TOKEN` or `GH_TOKEN`, never from the command line — argv is
visible in `ps` and in shell history. `--api` (or `GITHUB_API_URL`) points it at GitHub
Enterprise.

## Resolving the target project

The repo argument is **optional**: the run starts from a live session (the desktop
app, the TUI, or the CLI), so the target is resolved from the session, not a shell:

1. An **explicit path** always wins.
2. **The session working directory**, walked up to the nearest `.git` — the project
   boundary Hermes itself uses. With no git root, the nearest directory carrying
   `.hermes.md`, `HERMES.md`, `AGENTS.md`, `CLAUDE.md`, `pyproject.toml`,
   `package.json`, `Cargo.toml`, or `go.mod`. In the desktop app a *Project* anchors
   the chat's workspace, so the session working directory follows it.

`resolve_project()` implements both; the run prints what it inferred and why:

```
$ council review --dry-run
inferred project: /home/you/projects/myrepo
  (git repository root at /home/you/projects/myrepo)
```

### When the session is not anchored

With no project (cwd a home directory, no git root, no marker) and a terminal
attached, the run **asks** for the path. With no terminal — a scheduled job, a
spawned worker, an agent turn — it **refuses** with exit 2 rather than reviewing the
wrong tree and writing `.review-council/` into it:

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

Anchoring the session is the recommended setup: create or switch a desktop Project,
or launch the TUI/CLI from inside the project (`cd /path/to/project`); `/council`
then reviews the right repo with no argument.

## The loop (FRAMEWORK §7)

```
intake → set goals → convene (each with its goal) → validate → aggregate
       → score → gate → goal review → (fix → re-review)* → terminate
```

**The orchestrator sets the goals; the harness owns the convening.** Each round the
orchestrator decides what the round is *for* — one goal per dimension — and the
harness spawns **one generalist profile sampled N times**. A reviewer's rubric lives
in its own profile, so only a spawned profile loads it.

1. **Intake** (harness). Resolve the target revision, detect the stacks, run every
   deterministic probe **once** for the whole run.
2. **Goals** (orchestrator). Write `<run_root>/round-N/goals.json`: one goal per
   dimension — an *objective*, the *evidence that would show it is met*, and
   optionally paths to focus on. Goals are deliberately **qualitative**: naming a
   score or threshold is forbidden, and the threshold is held out of every child's
   context. **Fail-open:** an incomplete goal set falls back to the built-in default
   set and the round proceeds — a goal-setting failure is not a review failure — and
   a partial set is treated as absent rather than partially applied.
3. **Convene** (harness). Spawn the generalist profile N times (5), each sample
   carrying all five rubrics, its probe slice **and the goals**; findings are
   bucketed by the dimension each declares into
   `<run_root>/round-N/<dimension>.json`. The harness also writes `meta.json` — it
   knows the sha and the stacks, the LLM does not.
4. **Aggregate** (orchestrator). Validates each file's schema and builds the evidence
   matrix; it does **not** fan out, re-review, or score.
5. **Gate.** `council gate` reads the reviewer files and recomputes the hybrid score
   itself — it never trusts a number any agent asserted. Exit 0 = satisfied, 1 = not
   satisfied, 2 = error. A reviewer that produced **no file** is an ERROR, never a
   clean bill of health.
6. **Goal review** (orchestrator). MET / PARTIAL / NOT MET per goal, with the evidence
   and what the next round should target. A dimension whose reviewer produced no file
   is **UNVERIFIED**, never "met". The gate has already decided acceptance; the goal
   review explains it and never overrides it.
7. **Fix turn** (`--mode full` only). The gate's stdout — the ranked findings — is fed
   back as the continuation prompt, and the orchestrator applies fixes.
8. **Repeat** until a termination condition fires.

### Why profiles, not `delegate_task`

`delegate_task` spawns **in-process subagents that inherit the parent's
`HERMES_HOME`**, so a delegated child cannot load a rubric that lives in the
reviewer's *own* profile. An earlier version fanned out that way and ran five generic
subagents wearing dimension labels, applying none of the rubrics' scoring anchors,
hard gates or checklists, while still producing gate-readable JSON.

- **No agent in the fleet has `delegation`** — not the reviewers, not the
  orchestrator. The harness is the only thing that spawns agents, so there is exactly
  one fan-out path, and it applies the rubrics.
- The reviewers are **sub-agents of the council**, not free-standing agents. Each is
  a leaf: no `delegation`, no code edits.
- They remain individually invocable for a single-dimension check, but that is a
  debugging affordance; the council is the supported path.

## Autonomy modes (DECISIONS #6, FRAMEWORK §12)

| Mode | Reviews | Applies fixes | Escalates |
|---|---|---|---|
| `full` (default) | yes | yes, autonomously | on block/escalate |
| `semi` | yes | only after approval | at threshold/stall/before edits |
| `advisory` | yes | never | always |

`semi` prompts before each edit and refuses to edit when stdin is not a TTY — an
unattended `semi` run degrades to `advisory` rather than editing unattended.

## Termination — adaptive (FRAMEWORK §8, M8)

**The threshold is the MINIMUM requirement; everything above it is desirable but not
required.** The loop climbs while it is gaining ground and stops — handing over a
next-steps plan — once the gains stall, the budget is spent, or the round cap is
reached.

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

- **Hard limits outrank the `--min-rounds` floor**, or the floor could overrun a cap
  or budget.
- **A specific reason beats a generic one.** If an oscillation and the round cap
  coincide, the reason is `oscillation` — it tells the next iteration what to change,
  where `round cap reached` does not. The decision to stop is the same.
- **Hitting a cap is not a failure** if the minimum was already met; the outcome
  reflects the requirement, not the mechanism that ended the run.

`--k` (default 2) is the novelty window; `--epsilon` (default 0.5) is the
diminishing-returns floor.

## The next-steps plan

A plan is written on **every** termination — satisfied or not — to
`<run-root>/next-steps.md`, and its path is recorded in `outcome.json`; when the loop
stops early (budget spent, gains stalled, cap reached) it is the deliverable that lets
the next iteration pick up instead of starting over.

| Part | Content |
|---|---|
| Header | outcome, reason, rounds used, budget, and *separately* the aggregate vs the minimum and what is blocking |
| Score trajectory | the per-round table and the net movement |
| A. Required to meet the minimum | open blocking findings, and (only when the aggregate is short) the dimensions that need to move |
| B. Desirable, in priority order | ranked by `points_potential`, the *weighted* headroom each item can move — priority is a number, not prose |
| C. How to resume | the exact re-run command, plus the cheaper `doctor`/`probes` checks to try first |

The score requirement and the blocking-finding gate are independent: a run whose
aggregate clears the minimum but is blocked by a finding reports **meets the minimum**
plus **blocked by**, never "below the minimum". The same ranking feeds the fix turn.

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
deterministic signal cannot inflate a score — the failure mode where a zero-Nix repo
makes Nix-pattern greps trivially "clean".

**The threshold is re-derived at β=1** — `80.0`, 2.31 under the measured clean baseline of
82.31, with its provenance in `scripts/calibration.json` — and the `α_t` weights remain
uncalibrated defaults. On another repository neither is a pass mark.

## The deterministic toolchain (β)

β is the fraction of a dimension's *expected* tools that actually ran. A missing
analyzer doesn't fail the run — it silently drops β, so the dimension is scored on
reviewer judgement alone.

### Nix is the provisioning path (pinned, declarative)

`nix/builders.nix` declares the tool set; `flake.lock` pins the exact nixpkgs
revision. `nix build .#toolchain` yields the same store path on every machine, so
every reviewer runs identical tool versions; nothing is installed imperatively and
nothing drifts.

```bash
council setup toolchain --path        # the toolchain store path
council setup toolchain --inventory   # pinned tool versions as JSON
council setup toolchain -- statix check . -o json
council setup toolchain --which ruff
```

`REVIEW_COUNCIL_TOOLCHAIN` wins when set — the container image bakes it in and the
devshell exports it — so nothing builds the toolchain at run time.

The tool list is `research/nix-tooling.md` §0 plus the Python toolchain DECISIONS #3
requires. **Two lists, and the split is the point** — see `docs/TOOLCHAIN.md` for the
per-tool verdict.

**QA toolchain (14 tools, ships in the container and the app):** `nix`, `nixfmt`,
`nixfmt-tree`, `statix`, `deadnix`, `vulnix` (on demand), `gitleaks`, `osv-scanner`,
`zizmor`, `ruff`, `mypy`, `pytest`, `bandit`, `shellcheck`. A tool is in this list only if the
gate scores it (`score_reviews.expected_tools`), a probe runs it (`scripts/probes.py`),
or it is the mechanism that provides an output (the `formatter`).

**Contributor DX (9 tools, devshell only):** `nixd`, `nil`, `nix-tree`, `nix-diff`,
`nix-fast-build`, `nix-du`, `tokei`, `cloc`, `jq` — a language server, a closure
browser and the density meters. No probe runs them and the gate does not score them,
so they are not part of the product.

**`vulnix` ships but is not probed — on demand only.** It is in the toolchain so
closure CVEs can be asked when that is the question, and absent from `probes.py` so no
routine review pays for it. Running it is the expensive half: it fetches NVD data over
the network (minutes, and the answer moves with the date), it is unmaintained, and it
matches name+version against NVD so backported fixes are invisible — whitelisting is
mandatory to make the output usable, and no whitelist ships. Its closure is 193.3 MB,
19.7% of the toolchain and 26 MB of the container. `tests/test_probes.py` pins both halves: shipped, and not probed.

**semgrep is deliberately excluded**: it is not in the §0 inventory, and it does not
build on this nixpkgs revision (`pyjwt~=2.13.0 not satisfied by 2.14.0`). A tool that
cannot build is worse than an absent one — it fails the whole toolchain, taking every
other analyzer with it.

### Per-stack tool tables

`STACK_TOOLS` in `score_reviews.py` keys expected tools by **language stack**, not by
a single fixed toolchain: a Nix-only table makes β structurally 0 on a Python repo no
matter how many analyzers run, which makes the deterministic half decorative. Stacks
come from marker files and source extensions (`detect_stacks`), and a dimension's
expected set is the union across every stack present.

```bash
council gate <run-dir> --repo <repo>        # auto-detect
council gate <run-dir> --stacks nix,python  # force
```

### Built-in probes — zero installs

`scripts/probes.py` implements the checks the framework owns, so a review has real
deterministic signal even on a machine with no Nix:

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
| `ifd` | performance | `nix flake check --no-build --option allow-import-from-derivation false`; IFD breaks eval caching |
| `ci-cache` | performance | workflows that build Nix but configure no store cache (pure text) |
| `ci-concurrency` | performance | workflows with no `concurrency:` key (pure text) |

```bash
council probes --all --repo <repo>
council probes statix --repo <repo>
```

Each emits `{"tool","ran","parsed","signal","findings","note"}`; `signal` is a
normalized 0-100 deterministic score the gate feeds into the geometric mean. A probe
that cannot run reports `ran: false` — it never invents a result, because that would
inflate β.

The parser: statix pretty-prints each JSON object across many lines while deadnix
emits one object per line. `_json_objects` uses `raw_decode` over the whole stream so
both parse — a line-based parser works for one and silently returns **zero** for the
other, which reads as a clean bill of health on a file that does not even parse.

### doctor — what's missing and how to get it

```bash
council doctor --repo <repo>            # report
council doctor --repo <repo> --json     # machine-readable
council doctor --repo <repo> --install  # install what's missing (asks first)
```

It reports the detected stacks, whether Nix is available, the pinned nixpkgs revision
and toolchain store path, β now vs reachable, and how to get anything missing. With
Nix available the advice is **always declarative**: add the tool to
`nix/builders.nix`'s `toolNames` and rebuild. The pip/brew/scoop hints appear only for
hosts without Nix, and only for installers that are actually present.

It also reports **Hermes**: β says how much of the score is deterministic and nothing
about whether a review can run at all, so a machine with no Hermes and β 1.00 cannot
review.

### Finding Hermes — and what can actually be known

The council does **not** talk to a Hermes *gateway*. It shells out to the `hermes`
launcher (`hermes -p <profile> chat --query-file <path>`) and reads the file that turn
writes. `hermes serve` — the backend the desktop app and remote clients connect to —
is a different thing, and a reachable port on it is **not** evidence that the council
can run an agent.

| Layer | Kind | What it establishes |
|---|---|---|
| **L0 launcher** | deterministic, local | `HERMES_BIN`, then `PATH`, then known locations. `which` proves *presence*. |
| **L1 version** | deterministic, local | `hermes --version` — proves it **executes**. A file that cannot run resolves fine and then fails every turn. |
| **L2 profiles** | deterministic, local | the council's profiles exist **and carry a provider**. Hermes keeps credentials per profile and does not share them. |
| **L3 gateway** | optimistic, network | something is listening where a backend would be. A **hint**, and never part of the verdict. |
| **L4 capability** | authoritative, costly | one real minimal turn. The only layer that proves anything, and the only one that costs money — so it is opt-in, behind `council doctor --probe`. |

The verdict names the **first** thing that would stop a review, because that is the
one worth fixing:

```
hermes    : Hermes Agent v0.0.0 (2026.9.24)  (/home/you/.nix-profile/bin/hermes)
  profiles: council-generalist, council-orchestrator  (provider configured: both)
  gateway : 127.0.0.1:9119 reachable  (a hint only; the council drives the launcher, not this)
  verdict : ready — a review can run
```

**The port is not the availability test.** The requirement is "a launcher that can
complete a turn", and a listening socket is neither necessary nor sufficient for it:
the gateway can be up while the launcher is absent (the desktop case), and the launcher
can work with no gateway at all (the CLI case, every ordinary install). The port is a
useful diagnostic when a *remote* setup misbehaves. `tests/test_hermes.py` pins both
directions: a live listener must not turn a missing launcher into `ready`, and a dead
port must not spoil a working one.

**Reaching a host from a VM or container — measured, not assumed.** A `127.0.0.1`
inside a guest is the guest. In a NixOS VM test:

| probe from the VM | sandbox ON | sandbox OFF |
|---|---|---|
| control: a listener *inside* the VM | OPEN | OPEN |
| host service via `127.0.0.1` | CLOSED | CLOSED |
| host service via `10.0.2.2` | CLOSED | **OPEN** |

1. **`127.0.0.1` is the guest.** It never reaches the host, in any configuration; the
   control line makes that a measurement rather than an assertion.
2. **`10.0.2.2` is QEMU's SLIRP gateway** — the loopback of whatever network namespace
   the QEMU process is in. The test driver's own listener is reachable there in both
   columns, so the gateway works; what differs is *which* namespace it points at.
3. **The Nix build sandbox gives the build its own network namespace**, so by default
   that gateway is the sandbox's loopback and the host's services are invisible.
   `--option sandbox false` makes the host's `127.0.0.1` reachable at `10.0.2.2`.

So a VM reaches the host at **`10.0.2.2`, and only with the sandbox off** — not at
`127.0.0.1`. Under WSL's mirrored networking `127.0.0.1` *does* reach the Windows host:
a property of that setup, not of guests in general. A container sharing the host's
network namespace (`--network host`) gets a host process's reach; a VM does not.

`--option sandbox false` alone changes nothing on a second run — it is not part of the
derivation, so nix returns the cached result and the option looks inert. Force it with
`--rebuild`.

### Tool-name matching is fuzzy on purpose

A reviewer may report `py_compile`, `py-compile`, `python -m py_compile`,
`python3 -m py_compile`, `/usr/bin/ruff`, `ruff.exe`, or `cargo test`; all resolve to
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
hermes cron add --name council-nightly "0 2 * * *" \
  "council review <repo> --mode full --max-rounds 2"
```

For unattended runs that must survive restarts, `council swarm` builds the durable
council as a kanban graph and `council setup dispatcher` runs it as a systemd user
service.

## Distribution: repo ↔ skill

This repo is the **source of truth**; the `council` skill is the **distribution**. It
is self-contained — it bundles the scripts, the orchestrator bot definition and the six
rubrics under its own directory, so installing it on a new machine needs no clone:

```
<skill_dir>/scripts/*.py
<skill_dir>/assets/bots/council-orchestrator/{SOUL.md, bot.yaml, profile.yaml}
<skill_dir>/assets/rubrics/<name>/SKILL.md
```

`council setup skill` pushes repo changes into the installed skill; it resolves the
destination from the live Hermes config (`skills.external_dirs`, else the Hermes
home), so it is portable across Windows/macOS/Linux. `council setup bots` (the
installer) reads either layout — `<root>/bots` + `<root>/skills` (repo) or
`<root>/assets/bots` + `<root>/assets/rubrics` (skill) — so the same installer
bootstraps profiles from whichever tree it lives in.

**Nothing in this framework hardcodes a machine path.** Every location is derived at
runtime from the skill's own directory, the Hermes home, or the session.

## Testing

```bash
python tests/test_council_loop.py          # termination paths (§7/§8)
python -m pytest tests/test_score_reviews.py   # scoring + gate contract
```

Both suites stub the orchestrator and exercise the **real** gate, so the continue/stop
decisions are tested against the real scoring code.
