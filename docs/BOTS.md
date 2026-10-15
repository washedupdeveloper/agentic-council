# review-council — The Bots

Two Hermes **profiles** (Bot Mode agents), each with a version-controlled definition and an explicit
capability set. The repo is the source of truth; `council setup bots` materialises them into
`~/.hermes/profiles/`.

## Roster

| Bot | Role | Dimensions | β (deterministic weight) |
|---|---|---|---|
| `council-generalist` | reviewer | all five | per dimension, from the probes that ran |
| `council-orchestrator` | orchestrator | — | sets goals, judges the round; never scores |

Five per-dimension reviewer profiles (`security-reviewer`, `correctness-reviewer`, `readability-reviewer`,
`architecture-reviewer`, `performance-reviewer`) used to sit in this table. M8.5 measured them against
one generalist at equal cost and they lost (below), so they were deleted. The **rubrics** they carried
(`skills/reviewer-*/SKILL.md`) remain: the generalist loads every one of them.

## Capability model

Capabilities are the Hermes **toolsets** enabled for the profile (`platform_toolsets.cli`), declared
per bot in `bots/<name>/bot.yaml` and applied by `council setup bots`.

**The reviewer** — read, analyse, run tools, load its rubrics. It is a **leaf**:

```
file · terminal · code_execution · skills · web · todo · memory · session_search · clarify
```

Deliberately **absent**: `delegation` (a leaf never spawns), `kanban`, `cronjob`, `browser`,
`computer_use`, `vision`, `image_gen`, `tts`.

**Orchestrator** — the reviewer's set **plus** `kanban` and `cronjob`. Neither profile has
`delegation`: the harness owns the convening (see below), so nothing inside a profile can spawn an
agent.

> `kanban` and `cronjob` are declared for M7 (durable and scheduled runs), which is **not built**:
> they are installed but no code path uses them yet. `install_bots.py`'s `ORCH_TOOLSETS` is the
> source of truth for what is actually enabled. An earlier version gave the orchestrator `delegation`
> and fanned out with `delegate_task`; the children inherit the *parent's* `HERMES_HOME`, so they
> loaded none of the rubrics and ran as five generic subagents wearing dimension labels. The
> capability is gone from every profile, which makes the single convening path provable rather than
> merely documented.

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

Only the orchestrator has a `SOUL.md`. It is a **model-facing prompt**, not documentation:

> `council-generalist` has **no** `SOUL.md`: `council setup bots` creates it by copying all five
> rubrics into one profile. That is deliberate and it is measured — the generalist scored 22/22 twice
> with the rubrics alone, so the rubrics carry the instruction and a separate persona adds nothing.

| Section | Purpose |
|---|---|
| *one-line stance* | The identity and default posture. Resolves ambiguity before any rule is read. |
| `## Goal` | The round's objective, handed in by the harness. Two lines; the agent does not invent it. |
| `## Rules` | Numbered. Each is a claim **and** the action it forces. No rule without a consequence. |
| `## Skills` | Which rubric to load, plus `nixos-clan-flake` when the repo is Nix/NixOS/Clan. |
| `## Refusals` | The failure modes the persona must not fall into. Prevents sycophancy and padding. |
| `## Output` | The exact artifact to emit. Without it a persona produces prose, not findings. |

Two sections were **dropped** deliberately: `## Targets` duplicated the rubric checklist (violating
the zero-overlap rule), and `## Iterate until` described the harness loop rather than the agent — the
loop's exit condition is not the reviewer's business.

Rules of the schema: **no ambiguity, no pedanticism, no waste.** Every line must change behaviour or
it is deleted. The doctrine, finding contract, severity taxonomy and score are defined **once** in
[`FRAMEWORK.md`](FRAMEWORK.md) and referenced — never restated per bot.

## What each bot owns

The five **dimensions** are what the reviewer covers — all of them, in one profile, in one pass. They
are not five agents but five rubrics (`skills/reviewer-*/SKILL.md`) the generalist loads together and
the harness buckets findings back into afterwards.

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

In the desktop app both profiles appear in the **Bots** tab (`ui_meta.hermes-bots.title` is set), so
they can be chatted with directly or `@mention`ed in a group chat.

## Layout

```
bots/council-orchestrator/
  bot.yaml      # declared capabilities, model, rubric + soul references
  SOUL.md       # persona + behaviour contract  (copied to the profile)
  profile.yaml  # Bot Mode metadata            (copied to the profile)
skills/reviewer-<dim>/SKILL.md   # the five rubrics (copied into the reviewer's skills/)
scripts/install_bots.py          # materialise/refresh both profiles — `council setup bots`
```

`council-generalist` has no directory here: `council setup bots` creates it, copying all five
`reviewer-*` rubrics into it. See "How the council is convened".

## Editing a bot

1. Edit the file under `bots/` or `skills/` in this repo (the source of truth).
2. Run `council setup bots` to push the change into the profile.
3. Commit.

Never hand-edit a profile's `SOUL.md` or rubric — it will be overwritten on the next install.
