# review-council — The Bots

Two Hermes **profiles** (Bot Mode agents). The repo holds their personas and rubrics;
`council setup bots` materialises them into `<HERMES_HOME>/profiles/` (default `~/.hermes/profiles/`).

## Roster

| Bot | Role | Dimensions | β (deterministic weight) |
|---|---|---|---|
| `council-generalist` | reviewer | all five | per dimension, from the probes that ran |
| `council-orchestrator` | orchestrator | — | sets goals, judges the round; never scores |

Five per-dimension reviewer profiles (`security-reviewer`, `correctness-reviewer`,
`readability-reviewer`, `architecture-reviewer`, `performance-reviewer`) used to sit here; M8.5
measured them against one generalist at equal cost and they lost (below), so they were deleted. Their
**rubrics** (`skills/reviewer-*/SKILL.md`) remain: the generalist loads all five.

## Capability model

Capabilities are the Hermes **toolsets** enabled for the profile (`platform_toolsets.cli`), declared
in `review-council.toml` (`scripts/council_config.py` ships the defaults) and applied by
`council setup bots`.

**The reviewer** — read, analyse, run tools, load its rubrics. A **leaf**:

```
file · terminal · code_execution · skills · web · todo · memory · session_search · clarify
```

**Absent**: `delegation` (a leaf never spawns), `kanban`, `cronjob`, `browser`, `computer_use`,
`vision`, `image_gen`, `tts`.

**Orchestrator** — the reviewer's set **plus** `kanban` and `cronjob`. No profile has `delegation`:
the harness owns the convening, so nothing inside a profile can spawn an agent.

> `council_config.ORCHESTRATOR_TOOLSETS` is the source of truth for what is enabled. `kanban` serves
> M7's durable swarm and dispatcher; `cronjob` is declared for scheduled runs, which are **not
> built**. An earlier version fanned out with `delegate_task`, whose children inherit the *parent's*
> `HERMES_HOME` and so load none of the rubrics, running as five generic subagents wearing dimension
> labels.

## How the council is convened

The harness convenes it, not the orchestrator:

```bash
# one generalist profile, sampled N times, bucketed by dimension
nix run .#council -- review <repo> --samples 5
```

M8.5 measured this against five per-dimension profiles at equal cost on a 22-defect corpus: 22/22
injected defects against 13/22. `council-generalist` therefore carries **all five rubrics at once** —
`council setup bots` copies every `reviewer-*` skill into it — and the harness regroups its findings
into the per-dimension files the scorer reads. A finding that names no valid dimension is dropped and
counted, never guessed at; if **no** sample is readable the harness leaves the dimensions missing
rather than writing five empty files, because five empty files would score a clean 100 and report a
total failure as a pass.

## The persona schema

Both profiles ship a `SOUL.md` — a **model-facing prompt**:

| Section | Purpose |
|---|---|
| *one-line stance* | Identity and default posture; resolves ambiguity before any rule is read. |
| `## Goal` | The round's objective, handed in by the harness. Two lines; the agent does not invent it. |
| `## Rules` | Numbered. Each is a claim **and** the action it forces. |
| `## Skills` | Which rubric to load, plus `web-app-security` on demand for a web project. |
| `## Voice` | Answer first, no hedging, every fact kept. |
| `## Output` | The exact artifact to emit (orchestrator only). |

`## Targets` and `## Iterate until` were **dropped** deliberately: the first duplicated the rubric
checklist (violating the zero-overlap rule), the second described the harness loop rather than the
agent.

Schema rules: **no ambiguity, no pedanticism, no waste** — every line must change behaviour or it is
deleted. The doctrine, finding contract, severity taxonomy and score are defined **once** in
[`FRAMEWORK.md`](FRAMEWORK.md) and referenced, never restated per bot.

## What each bot owns

The five **dimensions** are what the reviewer covers — all of them, in one profile, in one pass. They
are five rubrics (`skills/reviewer-*/SKILL.md`) the generalist loads together and the harness buckets
findings back into, not five agents.

- **security** — vulnerabilities, secret leakage, privilege, hardening, exposure, supply chain, purity.
- **performance** — eval cost (IFD, overlays), closure size, build cost, cache-friendliness.
- **readability** — formatting, structure, naming, dead code, idiom, docs.
- **correctness** — evaluation correctness, option types, `mkDefault`/`mkForce` precedence,
  `stateVersion` immutability, tests/CI.
- **architecture** — flake-parts structure, layering, interfaces, reuse, clan topology, separation.
- **orchestrator** — sets each round's goals, then judges the round against them (intake → set goals
  → judge → hand control to the gate). It does not convene, aggregate or score; the harness and the
  gate own those.

## How to invoke

```bash
# the council — the harness drives it
nix run .#council -- review /path/to/repo

# more samples, more recall (and more wall-clock)
nix run .#council -- review /path/to/repo --samples 8
```

`council-orchestrator/profile.yaml` sets `ui_meta.hermes-bots.title`, so it surfaces in the desktop
**Bots** tab and can be chatted with or `@mention`ed in a group chat.

## Layout

```
bots/council-orchestrator/
  bot.yaml      # shipped capability defaults — not read; the config is authoritative
  SOUL.md       # persona + behaviour contract  (copied to the profile)
  profile.yaml  # Bot Mode metadata            (copied to the profile)
bots/council-generalist/
  SOUL.md       # reviewer persona             (copied to the profile)
skills/reviewer-<dim>/SKILL.md   # the five rubrics (copied into the reviewer's skills/)
scripts/install_bots.py          # materialise/refresh both profiles — `council setup bots`
```

## Editing a bot

1. Edit the file under `bots/` or `skills/` (personas and rubrics live here; capabilities live in
   `review-council.toml`).
2. Run `council setup bots` to push the change into the profile.
3. Commit.

Never hand-edit a profile's `SOUL.md` or rubric — it will be overwritten on the next install.
