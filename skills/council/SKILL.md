---
name: council
description: Use when a change needs a blocking-defect verdict. Runs `council review` and reports the states behind the verdict.
commands: [review, ci, pr, baseline, init, agents, evidence, doctor, setup]
flags: [--plan, --include, --exclude, --samples, --allow-single-sample, --report, --json, --sarif, --no-ephemeral, --keep, --require-executed-proofs, --base, --library, --dest, --agent, --list, --force, --dry-run, --label, --state-root, --source]
artefacts: [verdict.json, sample-N.json, artifacts.json]
---

# council

`council review` diffs a change against a base, asks the configured reviewer
agent for findings, executes each finding's proof, and derives the verdict from
the states those proofs reached. Hermes is the only adapter shipped today; the
`--agent` flag selects an adapter, and `council agents` lists what this build
carries. A finding counts only once its proof holds.

## Run

    council review                        # gate: 0 pass, 1 fail, 2 incomplete, 3 could not start
    council review --plan                 # units, bytes, rules, samples: no model call, no run
    council review --include 'src/**' --exclude 'vendor/**'
    council review --samples 3            # per unit; merged by file, line and claim
    council review --samples 1 --allow-single-sample  # deliberate one-sample review
    council review --report               # advice only: always exits 0
    council ci --sarif council.sarif      # headless: JSON, exit code, SARIF
    council pr 1234                       # base and head come from `gh pr view`
    council pr https://github.com/o/r/pull/1234  # URL or branch also work
    council agents                        # reviewer adapters in this build
    council doctor                        # can this machine produce evidence at all?
    council doctor --source .             # installed version vs this source tree

A review is **ephemeral by default**: the run directory is removed after the
verdict. Pass `--no-ephemeral` to keep `.council/runs/<id>/`, or `--keep DIR` to
copy it before the temporary tree goes.

Screenshots are local evidence, not reviewer input. Attach one to a kept run
and print its direct link:

    council evidence add <run-id> .screens/zed-review.png --label "Zed review panel"
    council evidence list <run-id>

The sidecar is `artifacts.json`; the image is copied under `artifacts/`. A moved
or deleted image is reported as missing, not treated as a failed review. Use
`--state-root <runs-dir>` for a run retained by the ACP/MCP server outside the
repository.

## Install the skill

The skill that teaches an agent to run this tool is a directory, so installing it is a copy
into a directory the agent already reads. `setup skill` installs skills from a *library* —
any directory carrying `library/contract.json` — and names no agent of its own:

    council setup skill --list                        # what the library holds
    council setup skill probe --dest ~/my-agent/skills
    council setup skill probe --agent claude          # a conventional location, if it exists
    council setup skill probe --dest ./skills --dry-run

`--library` picks the library, else `$SKILLS_LIBRARY`, else the nearest ancestor holding a
contract. `--dest` picks the destination, else `$SKILLS_DIR`, else the directory `--agent`
resolves to — and `--agent` refuses to invent one that is not already on disk, so a machine
without that agent gets a message rather than a stray directory. A skill is overwritten only
when the copy is identical (reported as unchanged) or when you pass `--force`.

## Read

`verdict.json` is the evidence; read `verdict`, `exit_code` and `reason` first
and do not re-derive them from `findings`.

- `format` — a consumer must refuse a format it does not know.
- `findings[]` — `id`, `dimension`, `severity`, `state`, `proof_strength`,
  `location`, `claim`, `detail` (what the proof actually found), `proof`
  (the canonical proof that was run), and `evidence` (the sample files whose
  answer produced it — open one and the claim is there).
- `units[]` — one row per reviewed slice, with ranges, prompt bytes, depth,
  samples and its own verdict. A windowed file appears as several units.
- `rules[]` — the repository documents that governed this change.
- `digest`, `profile_config_sha256` — the instrument. Two runs with different
  digests are not the same evidence.
- `scope_ignored[]` and `scope_ignored_omitted` — what was **not** looked at.

## The trail

Every claim in the verdict resolves to a file you can open:

    finding → findings[].evidence → sample-N.json (or units/<id>/sample-N.json)
            → the raw answer → prompt.md → digest (prompt + profile + diff)

Nothing in the verdict is asserted without that chain. If an `evidence` path
does not exist, the run is broken, not merely incomplete.

## Decide

- **PASS** — no blocking finding was proven. `reason` names any proven
  non-blocking finding and any that were proven by quotation only.
- **FAIL** — a blocking finding was proven: `security` or `correctness` at any
  severity, anything else at `high` or `critical`. Cite `id`, `location` and
  `claim`; the line that held is in `detail`.
- **INCOMPLETE** — the evidence did not arrive: a sample returned nothing, a
  blocking proof is `UNRUNNABLE` here, a unit was never reached, or the reviewer
  is missing. Say what is missing. Never report it as a pass.

## Rules

- A finding without a proof is not a finding; do not restate one from the output.
- `proof_strength: static` means the proof quoted code (`present`, `absent`,
  `json`, `diff`); `executed` means it ran something (`command`, `repro`). A
  quotation proves a line exists, not that the code misbehaves — say which one
  you are relying on, and prefer `repro` for a behavioural claim. Under
  `--require-executed-proofs` a quotation-only blocker is INCOMPLETE.
- `--require-executed-proofs` is the strict reading when a merge turns on a
  claim about behaviour.
- A one-sample review is refused unless `--allow-single-sample` is passed;
  the automatic policy is two clean samples, and the shipped gate uses it.
- Do not weaken the prompt, the budget or the proof to clear a verdict; fix the
  code, add the proof, or report `INCOMPLETE` honestly.
- There is no score. Do not invent a threshold, an average, or a percentage.
- A refusal is actionable: it names the budget, the window count, or the base
  that would let the review run. Report that, not "the tool failed".
