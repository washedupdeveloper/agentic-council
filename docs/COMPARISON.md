# How council compares

**What this document is.** A comparison between `council` and adjacent
agentic coding/review systems. It explains the problem `council` targets, the
mechanism it uses, and where its documented behaviour differs from the
documented behaviour of the other systems here.

**What this document is not.** A benchmark, a product ranking, or a claim that
one system is better than another. It does not assess model quality, pricing,
latency, security, or real-world defect rates. Those are not measured here.

**Evidence rule.** Statements about another system are limited to what its
official documentation says. When the reviewed documentation does not define a
behaviour, this page says **“the reviewed documentation does not describe …”**
rather than inferring that the behaviour is impossible. The source list and
access date are at the end.

## The problem council targets

A conventional AI review produces prose. That prose can be useful, but it
leaves a merge decision with three unresolved questions:

1. **Is the claim true?** A model can say “this will fail on an empty list”
   without running anything. A confident sentence is not evidence.
2. **Was the claim checked at all?** A missing answer and a clean review can
   look the same if the system only reports what it found.
3. **Can the result be reproduced and audited?** A review that depends on an
   unknown prompt, profile, context and sample set cannot be compared with a
   later review of the same change.

`council` is built around a narrower job than a coding agent: **review a git
change, settle each finding with evidence, and return a merge verdict**. It
does not write the change, edit the repository, or run an open-ended agent
task.

## What council aims to solve

`council` is intended for the moment before a change merges:

- a local pre-merge review;
- a CI gate with a stable exit code;
- a review of an exact GitHub pull-request commit;
- a team’s recorded acceptance of known, proven blocking findings.

It is deliberately **diff-centric**. The unit of work is a base revision and a
head, not a repository-wide question. It is not a general chat assistant, a
code generator, a linter, a formatter, or a test runner. It can run a
repository’s own checks as proofs, but it does not replace those checks.

## How council attempts to solve it

The review is a pipeline with an explicit decision at each step.

### 1. Select the change

`council review` compares a base revision with the working tree, or with the
index when `--staged` is used. `--include` and `--exclude` make the caller’s
scope explicit; an include that matches nothing is a start failure, not an
empty pass. `council pr` resolves a GitHub PR’s base and head and refuses a
checkout that is not the PR head. A PR review is a review of a commit, not of
local edits.

### 2. Bound the prompt

Large changes are sliced by file, then by hunk. A single hunk that cannot fit
at any useful context depth is refused by default; `--window-large-files`
splits it into line windows, each its own unit, with `--max-windows` as the
ceiling. `--plan` prints the units, prompt sizes, context depth and skipped
files without calling the reviewer or writing a run.

This is a cost control with a safety property: an oversized prompt is not
silently truncated into a review of something else.

### 3. Ask a reviewer for claims

Each unit is sent to a configured reviewer, normally a Hermes profile. A
sample returns findings in a closed output schema: each finding has a
dimension, severity, location, claim and a proof from a closed vocabulary.
The reviewer is sampled; `--samples auto` asks once for a clean unit, twice to
confirm a finding, and three times to break a tie. Samples are merged by file
and line, with the most blocking label and highest severity retained.

### 4. Require evidence for each claim

A finding’s proof is executed, not accepted as prose. The proof kinds are:

| proof | what it settles |
|---|---|
| `present` | a line or text exists at the claimed place |
| `absent` | a text or pattern is absent, optionally within a scoped set of paths |
| `command` | an allowlisted command’s result supports the claim |
| `repro` | a command fails in the way the finding claims, demonstrating the defect |
| `json` | a JSON pointer resolves to the expected value |
| `diff` | the diff has the claimed shape |

A finding is `proven` only when its proof holds, `refuted` when the proof ran
and failed, `unrunnable` when the proof could not run in this environment, and
`unsettled` when no proof was attempted. The reviewer’s confidence is not one
of those states.

### 5. Decide from states, not from a score

The verdict is a pure function of the findings:

```text
any blocking finding proven       -> FAIL        exit 1
else any blocking finding open    -> INCOMPLETE  exit 2
else                              -> PASS        exit 0
```

A blocking finding is `high` or `critical`, or any severity in `security` or
`correctness`. A proven `low` security finding still fails; a proven `low`
readability finding does not. There is no numeric score that can override the
states.

`INCOMPLETE` is not a polite `FAIL`. It says the review ran but a blocking
claim was not settled, or a unit/sample was not reviewed. A start failure is
exit `3`: no run and no model call.

### 6. Make the run auditable

`verdict.json` records the base and head, diff digest, skipped files, context
spans, unresolved calls, references, sample results, findings, proof states,
and the run’s instrument digest. The digest covers the prompt template, the
profile name and the profile’s configuration bytes; two runs are comparable
only when the instrument matches. A run also records what it did **not**
review.

Runs are ephemeral by default. `--keep DIR` retains the run deliberately;
`--no-ephemeral` writes `.council/runs`. `--no-ephemeral` is also how a team
creates a baseline from an accepted run.

### 7. Make acceptance explicit

A baseline is a committed list of proven blocking findings a team has accepted,
with an owner, reason and expiry. It is applied after the evidence verdict and
never suppresses missing evidence. `ci` and `pr` read the baseline from the base
revision by default, so a change cannot edit the policy that judges it.

### 8. Keep the reviewer from being steered by the reviewed code

The reviewer prompt is shipped with the tool, not read from the repository
under review. A repository can supply rules that add context documents to the
prompt, but those documents are marked as repository context, not instructions.
The reviewer and its proof commands run under a bubblewrap sandbox when
available; without it, command-shaped proofs are `UNRUNNABLE` rather than run
unsandboxed.

### 9. Make the project’s own claims executable

The repository’s `claims.toml` ties each documented claim to a command that
must pass. `council-verify` executes the registry, `docs/CLAIMS.md` is generated
from it, and the mutation check deliberately breaks rules to prove the test
suite can fail. At the commit this page was written, the registry held **214
claims**, with **48 mutations** caught.

## What council does not do

- **It does not write or edit code.** It reports findings; it does not apply a
  patch, create a branch, or open a PR.
- **It does not replace tests, linters, or static analysis.** It can run a
  repository’s commands as proofs, but the repository still owns those tools
  and their configuration.
- **It does not guarantee a defect-free merge.** A `PASS` means no blocking
  finding was proven in the reviewed units and no blocking evidence was
  missing. It is not a proof of absence.
- **It does not audit a whole repository in one run.** It reviews a selected
  diff. The base and scope decide what is seen.
- **It does not provide a general agent loop, desktop UI, mobile app, or agent
  control plane.** It is a CLI/CI review gate.
- **It does not provide a model marketplace.** It asks a Hermes-compatible
  reviewer; the provider and model are configured through the reviewer
  profile.
- **It does not make the merge decision for you.** It returns evidence and an
  exit code; a person or pipeline still decides what to do with them.

## The comparison set

The named systems are not all direct substitutes. They fall into three groups:

- **Agent harnesses and coding agents:** DeepSeek Harness (DSH), OpenCode.
- **An agent control surface:** T3 Code.
- **A self-hosted AI workspace:** Odysseus.
- **Dedicated pull-request review tools:** CodeRabbit and PR-Agent, included
  because they are closer to `council`’s review job than the harnesses are.

The comparison asks what each system’s documentation says it is for, how it
handles a change, and whether it documents an evidence-based review decision.
It does not claim that a system cannot do something merely because its
documentation does not mention it.

## At a glance

| System | Documented category | Primary job in its docs | Changes code? | Documented review decision | License |
|---|---|---|---|---|---|
| **council** | Review gate | Review a git diff and return PASS/FAIL/INCOMPLETE | No | Closed proof kinds, four finding states, blocking rule, exit codes | MIT |
| **DeepSeek Harness** | Agent harness | Run coding, everyday, research and background tasks through plugins and tools | Through its coding agent/tools | Not documented as an evidence-state merge gate | MIT |
| **T3 Code** | Agent control surface | Control external coding agents from desktop, web and mobile; inspect diffs and manage source control | Through the agents it controls | Review UI and permission modes; no proof-state gate documented | MIT |
| **OpenCode** | Coding agent | Build, plan and explore code in a terminal, desktop or web app | Yes, through its build agent | Custom reviewer agents are documented; no proof-state gate documented | MIT |
| **Odysseus** | Self-hosted AI workspace | Chat, agents, research, documents, email, notes and local-model workflows | Agents can use files, shell and tools | No review gate documented | AGPL-3.0-or-later |
| **CodeRabbit** | AI PR review | Automated pull-request reviews, issue context and one-click fixes | Can generate/apply fixes | AI review comments and analysis; no proof-state gate documented | Not stated in reviewed docs |
| **PR-Agent** | Open-source PR reviewer | `/review`, `/describe`, `/ask` and `/improve` on pull requests | Suggests changes; does not document direct edits | LLM review feedback; no proof-state gate documented | MIT |

## DeepSeek Harness (DSH)

**Documented role.** DSH is “an open-source agent harness” built on an
“everything-is-a-plugin” architecture. Its product page describes coding,
everyday work, research, background tasks and plugins; it runs as a desktop app
or web UI. The README labels it a developer preview with compatibility-breaking
changes. [S1][S2]

**Where it overlaps with council.** Both put a model in front of repository
work, and both expose tool execution and extensibility. DSH is broader: its
documented job is to run agent tasks, including coding work, not to return a
merge verdict on a diff.

**Where it differs.** DSH is an execution environment. Its documentation
describes an agent that can explore repositories, fix bugs, build features and
run tests; it does not document a closed proof vocabulary, four evidence
states, a blocking rule or PASS/FAIL/INCOMPLETE exit semantics. The reviewed
docs describe review-adjacent work as agent tasks; they do not define a
built-in evidence gate. [S1][S2]

**What the reviewed docs do not establish.** They do not define an evidence
ledger, accepted-risk baseline, reviewer-profile digest, or a deterministic
proof executor as a review gate.

## T3 Code

**Documented role.** T3 Code calls itself an “agent harness control surface.”
It controls coding agents already installed on your machine — the README names
Claude Code, Codex, Cursor, Grok Build, OpenCode and Google Antigravity — and
provides desktop, web and mobile clients. It is MIT-licensed and explicitly
early (“expect bugs”). [S3]

**Where it overlaps with council.** Both deal with a git change and both care
about review. T3’s source-control documentation describes reviewing a turn’s
changed files and diff, reviewing commits, and committing, pushing and opening
a pull request. Its permission modes control when an agent may run commands or
edit files. [S3][S4]

**Where it differs.** T3 is a control surface over other agents, not a reviewer
with its own evidence model. Its documented review surface is a human diff and
commit view plus provider-specific permission/approval behaviour. The reviewed
docs do not define finding states, proof execution, a blocking rule, a proof
vocabulary, or a merge exit code. [S3][S4]

**What the reviewed docs do not establish.** They do not define a
repository-independent proof vocabulary, a review baseline, or an auditable
instrument digest. The provider’s own “auto” review is a permission mechanism,
not the same decision as a proof-backed merge verdict.

## OpenCode

**Documented role.** OpenCode is “an open source coding agent” available as a
terminal interface, desktop app and web app. It supports many model providers,
ships a full-access `build` agent and a read-only `plan` agent, and documents
custom agents, subagents, plugins and MCP servers. It is MIT-licensed. [S5][S6]

**Where it overlaps with council.** OpenCode’s documentation includes a
read-only reviewer subagent example: a custom agent with edit and shell
permissions denied, asked to “review the current changes” and list findings
with file and line references. That is the closest documented overlap with a
review workflow. [S6]

**Where it differs.** The reviewer is a configured agent with a prompt and
permission rules. OpenCode does not document a closed proof set, deterministic
proof execution, four finding states, a blocking rule or a PASS/FAIL/INCOMPLETE
gate. Its primary job is to write, understand and modify code; review is a
custom agent pattern inside that coding environment. [S5][S6]

**What the reviewed docs do not establish.** They do not define an evidence
ledger, accepted-risk baseline, instrument digest, or a review-specific CI exit
contract.

## Odysseus

**Documented role.** Odysseus is a “self-hosted AI workspace for chat, agents,
research, documents, email, notes, calendar, and local model workflows.” Its
documented features include local/API models, tools, MCP, files, shell, skills
and memory. It is AGPL-3.0-or-later and is deployed with Docker Compose. [S7][S8]

**Where it overlaps with council.** Both can put model-driven tools in front of
repository files and shell commands, and both care about self-hosting and
private operation. Odysseus is much broader: it is a workspace for many kinds
of work, not a repository review gate.

**Where it differs.** Odysseus’s documented features are chat, agents,
research, documents, email, notes, tasks and calendar. The reviewed
documentation does not describe a proof-based code-review verdict, a review
baseline, or a merge gate. It is an environment in which an agent might perform
a review as one task among many, not a review-specific decision system. [S7][S8]

**What the reviewed docs do not establish.** They do not define finding
states, a closed proof vocabulary, a blocking rule, or a review-specific exit
code.

## Dedicated pull-request review tools

These are closer to `council`’s job than the harnesses, but their documented
model is still different.

### CodeRabbit

CodeRabbit’s documentation describes automated AI review of pull requests,
using repository context, issue links, review comments and one-click fixes. It
also documents IDE and CLI entry points. The reviewed pages do not describe a
closed proof vocabulary, evidence states, or a proof-backed merge verdict; they
describe AI review feedback and suggested or applied changes. [S9]

**Difference from council.** CodeRabbit is a review product with a
conversational PR workflow and fix generation. `council` is a self-hosted CLI
gate whose central object is a finding with a proof state; it does not generate
fixes or host a PR conversation.

### PR-Agent

PR-Agent describes itself as an open-source, AI-powered code review agent and a
community-maintained legacy project of Qodo. Its documented commands include
`/review` for feedback, `/describe` for PR descriptions and `/improve` for code
suggestions, across GitHub, GitLab, Bitbucket, Azure DevOps and Gitea. It is
MIT-licensed. [S10][S11]

**Difference from council.** PR-Agent’s documented review output is LLM
feedback and suggestions. The reviewed documentation does not define a closed
proof set or evidence-state verdict. `council` does not describe itself as a PR
comment bot; it returns a local/CI verdict and an evidence document.

## Choosing between them

This section is an **assessment**, not a claim from the vendors’ documentation.

- **Choose `council`** when the question is “may this change merge?” and the
  answer must name the evidence, distinguish a defect from missing evidence,
  and produce a stable exit code in CI.
- **Choose DSH or OpenCode** when the question is “perform the work”: explore a
  repository, write a change, run tests, or build a feature. They are coding
  agents/harnesses; review is a task you can ask them to perform.
- **Choose T3 Code** when you already use several coding agents and want one
  remote/desktop/mobile control surface with diff review and permission
  handling.
- **Choose Odysseus** when you want a self-hosted workspace for chat, research,
  documents and agents, not a narrow merge gate.
- **Choose CodeRabbit or PR-Agent** when you want review comments and fix
  suggestions inside a pull-request workflow, rather than a local proof-backed
  gate.

None of these choices is exclusive. A coding agent can produce a change and
`council` can review that change as a separate step; that is a workflow
composition, not a documented integration between the products.

## What council does not claim

`council` does not claim that:

- every defect can be expressed as one of its proof kinds;
- a `PASS` proves the absence of defects;
- a model review is deterministic;
- a proof command is safe merely because it is allowlisted;
- a sandbox is a complete security boundary;
- a baseline makes a defect acceptable outside the team that accepted it;
- a green review replaces tests, static analysis, or human judgement.

The detailed contract is in [`FOUNDATIONS.md`](FOUNDATIONS.md),
[`ARCHITECTURE.md`](ARCHITECTURE.md) and the generated [`CLAIMS.md`](CLAIMS.md).

## Sources

All sources were accessed **2026-11-17**. The facts above are limited to these
pages.

- **[S1]** DeepSeek Harness README:
  <https://github.com/deepseek-ai/deepseek-harness>
- **[S2]** DeepSeek Harness product page:
  <https://www.deepseek.com/harness/en/>
- **[S3]** T3 Code README:
  <https://github.com/pingdotgg/t3code>
- **[S4]** T3 Code source-control documentation:
  <https://github.com/pingdotgg/t3code/blob/main/docs/user/source-control.md>;
  permission modes:
  <https://github.com/pingdotgg/t3code/blob/main/docs/user/permission-modes.md>
- **[S5]** OpenCode introduction:
  <https://opencode.ai/docs/>
- **[S6]** OpenCode agents documentation:
  <https://opencode.ai/docs/agents/>
- **[S7]** Odysseus README:
  <https://github.com/odysseus-dev/odysseus>
- **[S8]** Odysseus license:
  <https://github.com/odysseus-dev/odysseus/blob/dev/LICENSE>
- **[S9]** CodeRabbit pull-request review documentation:
  <https://docs.coderabbit.ai/overview/pull-request-review>
- **[S10]** PR-Agent README:
  <https://github.com/qodo-ai/pr-agent>
- **[S11]** PR-Agent license:
  <https://github.com/qodo-ai/pr-agent/blob/main/LICENSE>

License facts were verified from each project’s `LICENSE` file. CodeRabbit’s
reviewed documentation did not state a source license, so no license is
asserted here.

## Keeping this document true

This is a dated comparison, not a permanent description of another project.
Vendor documentation changes. When a cited page changes, update the claim or
remove it; do not strengthen a claim beyond what the new source says. The
repository’s docs index test requires this page to stay linked from
[`README.md`](README.md).
