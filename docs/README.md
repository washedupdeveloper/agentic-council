# Documents

Every document in this repository, what it is for, and which record decides what.
A file that is not linked from here is an orphan, and `tests/test_docs_index.py`
fails the gate when one exists.

## Start here

| document | what it is |
|---|---|
| [`../README.md`](../README.md) | the tool: the rule, the commands, the flags, the exit codes |
| [`../AGENTS.md`](../AGENTS.md) | the working contract: OpenSpec communication and weekly dependency maintenance |
| [`FOUNDATIONS.md`](FOUNDATIONS.md) | the seven decisions the tool rests on, each with its rejected alternative and what would make it wrong |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | the module map, the dependency rule, the run pipeline, the remaining debt |
| [`STATE-MACHINES.md`](STATE-MACHINES.md) | every state the CLI and the run engine can occupy, the invariants, the exit codes |
| [`../GLOSSARY.md`](../GLOSSARY.md) | the vocabulary, fixed: finding, proof, unit, window, sample, verdict, digest |
| [`CLAIMS.md`](CLAIMS.md) | generated: every claim this project makes and the command that would falsify it |
| [`VERIFICATION.md`](VERIFICATION.md) | the verification milestone: what must be proven, how, and what is proven so far |

## Reference

| document | what it is |
|---|---|
| [`SCOPE.md`](SCOPE.md) | what a review looks at, and that only the caller can change it |
| [`PORTABILITY.md`](PORTABILITY.md) | ephemeral execution beyond NixOS, host by host |
| [`SHELLS.md`](SHELLS.md) | bash, fish and PowerShell: how to invoke the scripts, and the shell a predicate runs under |
| [`BASELINE.md`](BASELINE.md) | accepting a proven blocking finding without hiding the evidence |
| [`VERSIONING.md`](VERSIONING.md) | the public surface, the semantic-version policy, the release procedure |
| [`COMPARISON.md`](COMPARISON.md) | how council differs from coding agents, harnesses, workspaces and PR review tools, with dated sources |
| [`FEATURES.md`](FEATURES.md) | scope decisions for features borrowed from adjacent systems: what was adopted, deferred or rejected |
| [`AGENT-SERVER.md`](AGENT-SERVER.md) | install and configure the optional ACP and MCP adapters, with Zed, VS Code and OpenCode examples |
| [`EVIDENCE.md`](EVIDENCE.md) | local screenshots under a kept run: links, hashes, gitignored storage and missing files |
| [`AGENT-ADAPTERS.md`](AGENT-ADAPTERS.md) | add a reviewer agent adapter; the Hermes reference implementation and the protocol |
| [`../skills/council/SKILL.md`](../skills/council/SKILL.md) | the skill an agent follows: how to run a review, read the verdict, and what not to do |
| [`../src/council/prompts/reviewer.md`](../src/council/prompts/reviewer.md) | the reviewer prompt: what the model is asked, the six proof kinds, and the shape of the answer it must return |
| [`../CHANGELOG.md`](../CHANGELOG.md) | what changed, by release |
| [`ADOPTION.md`](ADOPTION.md) | the `pypa/sampleproject` adoption run: the evidence that the tool works on a repository that is not this one |
| [`UNTANGLE.md`](UNTANGLE.md) | the decision log of the first refactor: problems found, what moved, what is still owed |
| [`UNTANGLE2.md`](UNTANGLE2.md) | the second pass: the five-parser diff grammar, the run ledger, the comment ruling, and the two moves it left |
| [`UPSTREAM.md`](UPSTREAM.md) | defects in dependencies that the gate routes around: what we do instead, the measurements, and when to re-check |
| [`sdd.md`](sdd.md) | how a change is authored: the loop, what the gate enforces, and the testing contract that makes a spec real |

## Decision records

Each milestone records the decision, the alternative it rejected, and an
acceptance table whose rows are commands. They are the history of why the tree
looks the way it does.

| record | decision |
|---|---|
| [`M11.md`](M11.md) | the rebuild beside v1.9.0: a verdict derived from evidence states, and the parity corpus |
| [`M12.md`](M12.md) | review any change: slice by file then hunk, and refuse rather than truncate |
| [`M13.md`](M13.md) | bounded runs: a deadline a person chose, and the measurement that makes it honest |
| [`M14.md`](M14.md) | release and adopt: wheel, image, action, and a real external repository |
| [`M15.md`](M15.md) | transport guard: a silent reviewer costs the idle timeout, not the sample |
| [`M16.md`](M16.md) | launch readiness: install, version, types, configuration, CI output, licence |
| [`M17.md`](M17.md) | pull-request entry, and a plan that states the cost before it is paid |
| [`M18.md`](M18.md) | sandboxed, ephemeral execution for the reviewer |
| [`M19.md`](M19.md) | ephemeral by default, and what a host without NixOS can do |
| [`M20.md`](M20.md) | error-driven CLI hardening: every flag, path, base and proof parameter |
| [`M25.md`](M25.md) | evidence that can fail: the proof kinds that a real review exposed as missing |
| [`M26.md`](M26.md) | the third rung: line windows, so an added file is reviewable |
| [`M28.md`](M28.md) | rules, proof strength, atomic publication, a bounded report |
| [`M29.md`](M29.md) | one claim is one finding: the merge keys on `(file, line, claim)` |
| [`M30.md`](M30.md) | every assertion carries its source: findings name their evidence, the skill declares the CLI |
| [`M31.md`](M31.md) | a pull-request target may be a number, URL or branch, resolved by `gh` |
| [`M32.md`](M32.md) | expose V2 to ACP and MCP hosts without changing the core |
| [`M33.md`](M33.md) | one reviewer adapter seam; Hermes is the reference adapter, not the engine |
| [`M34.md`](M34.md) | closing review breakpoints: the verdict on claim merge, two-clean sampling and strict proof mode |
| [`M35.md`](M35.md) | closing the residual breakpoints: both Linux systems, the installed/source doctor, the single-sample opt-in, selector emission and the milestone runner |
| [`M36.md`](M36.md) | closing the Astra review findings: the action manifest, proof-cause classification, rule trust, the sandbox boundary and the container tooling |

The series has gaps — `M21`–`M24` and `M27` have no record here. Those changes
went in without a decision record; this page does not invent one after the fact.

## Retired

Two documents were removed rather than left to drift. Both are in the history
(`git log --diff-filter=D -- docs/GRILL.md HANDOFF.md`):

- `GRILL.md` — an opinion page measured at `18b7043`. Its five points were audited
  and closed in `M29` and `M30`; keeping it meant keeping a second, stale account
  of the same tree.
- `HANDOFF.md` — a "verified state" note. It said 203 claims when the registry
  held 211, which is exactly the drift this repository refuses everywhere else.
  The state is not a document; it is `nix flake check`.

## How this page stays true

`tests/test_docs_index.py` checks both directions: every Markdown file outside
`fixtures/` is linked from this page, and every link on it resolves. Adding a
document without indexing it fails the gate, and so does deleting one and leaving
the link behind.
