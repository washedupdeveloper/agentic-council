# Feature adoption from adjacent systems

This page records which features from the systems in
[`COMPARISON.md`](COMPARISON.md) make sense for `council`, which do not, and
why. It is a scope decision record, not a roadmap promise.

## The scope test

A feature is eligible only if it strengthens at least one of these:

1. **Review a git change before merge.**
2. **Settle a finding with evidence rather than prose.**
3. **Make the review reproducible or auditable.**
4. **Make the gate cheaper to run without making it less honest.**

It is rejected if it turns the tool into a coding agent, a chat product, a
general workspace, an autonomous merger, or a plugin runtime that can widen its
own proof authority.

The decision must also be testable in this repository’s gate: a claim in
`claims.toml`, a regression test, and a mutation where the rule can be broken.

## Implemented: pull-request target flexibility

`council pr` originally accepted only a pull-request number. Other systems
operate on a pull-request URL or a branch, and operators commonly have the URL
in hand. The command now accepts:

```sh
council pr 123
council pr https://github.com/owner/repo/pull/123
council pr feature-branch
```

The target is passed to `gh pr view`, which resolves the number, URL or branch
to the same base/head pair. `council` still verifies that the checkout is the
resolved head commit with a clean worktree. It never checks out the branch and
never reviews local edits.

Why it fits: it removes a friction point without changing the review contract,
the evidence states, the blocking rule, or the sandbox. The requested PR is
still resolved by GitHub; the target is not trusted as evidence.

Regression tests cover number, URL, branch, empty target and option-like target.
A claim in `claims.toml` binds the URL and branch cases to the gate, and a second
claim binds the CLI's target passthrough. Two mutations prove the tests can
fail: `pr-target-is-ignored` replaces the resolved target with `"7"` before
`gh pr view`, and `pr-cli-target-is-ignored` passes `7` instead of the CLI's
target to the resolver. The decision is recorded in [`M31.md`](M31.md).

## Already present — do not re-add as “new”

Several features visible in adjacent tools already exist here in a
review-specific form:

| Pattern in adjacent tools | What council already has |
|---|---|
| A plan before spending model time | `council review --plan`, which prints units, prompt sizes, context depth, windows and skipped files without a model call |
| Custom reviewer instructions | `--profile` selects a Hermes profile; `--prompt` selects a different shipped/experimental prompt; `[[rules]]` adds repository context documents to the prompt |
| Review scope control | `--include`, `--exclude` and `--staged`; the caller owns the scope |
| Machine-readable review output | `--json` and `--sarif`; `council ci` always prints JSON |
| A machine check before work starts | `council doctor` checks git, reviewer, bwrap and the profile probe |
| Bounded execution | `--sample-timeout`, `--idle-timeout`, `--time-budget`, sample counts and prompt/window ceilings |
| Sandboxing | bubblewrap for reviewer/proof execution; ephemeral run output |
| A record of accepted risk | committed baselines with owner, reason, expiry and base-revision loading |
| Project-defined review policy | `council.toml` can narrow proof tools, timeout and sandbox; it cannot widen them |
| A claim/test contract | `claims.toml`, `council-verify`, generated `docs/CLAIMS.md`, and mutation checks |

## Deferred — plausible, but a milestone of their own

These are not implemented because they change a core contract, not because they
are undesirable.

| Candidate | Source pattern | Why deferred |
|---|---|---|
| GitLab/Bitbucket/Azure PR targets | PR-Agent and T3 document multiple Git hosts | Requires a provider abstraction, authentication and per-host checkout verification; `gh` is not a universal client |
| Incremental review of new PR commits | CodeRabbit describes incremental reviews | Needs durable PR review state and an agreed rule for what “already reviewed” means; the current gate reviews one base/head pair |
| Multiple reviewer profiles in one run | DSH/OpenCode expose configurable agents/subagents | Changes the instrument digest, sample merge and verdict provenance; it deserves a design decision, not a flag |
| Review focus/dimension exclusion | CodeRabbit/PR-Agent expose review focus settings | Excluding a dimension can hide a blocking finding; council’s blocking rule assumes every dimension is in scope |
| Review comments posted to a PR | CodeRabbit/PR-Agent integrate with the PR conversation | Writes to an external system, needs token and idempotency rules, and changes the gate from a local/CI verdict into a bot |
| Suggested patches or fix generation | CodeRabbit and PR-Agent offer fixes/improvements | Council’s contract is a verdict, not an editor; applying a patch would need a separate authorization boundary |

## Rejected — does not fit the product

| Candidate | Why rejected |
|---|---|
| A general coding agent that edits the repository | Council reviews a change; changing the tree would make the reviewer the author and destroy the independence the verdict relies on |
| Chat/ask about a PR | A conversational product is a different interface and evidence model |
| Desktop/mobile agent control surface | Out of scope for a CLI/CI review gate |
| A self-hosted workspace with email, notes and calendar | Out of scope; Odysseus is the broader workspace category |
| Plugin-defined proof executors | The proof executor and allowlist are a security boundary; a plugin could widen it. A future extension would need explicit trust, sandbox and review rules |
| A numeric score or threshold | Already rejected in `FOUNDATIONS.md`: a number cannot override missing evidence or a proven blocking finding |
| Automatic merge on PASS | Council returns evidence and an exit code; a person or pipeline still decides |

## What would make a deferred feature eligible

- **Provider support** needs a provider capability table and a verifier that
  proves the checkout is the remote PR head, not just a branch name.
- **Incremental review** needs a durable identity for a PR review and a rule
  that prevents a later run from treating an unreviewed earlier unit as clean.
- **Multiple profiles** needs a defined merge rule across instruments and a
  digest that records every profile, not just one.
- **Fix generation** needs a separate write authorization, a diff review and a
  clear statement that a generated patch is not evidence.

Until one of those contracts exists, adding the feature would make the tool
broader but less trustworthy.

## Sources and maintenance

The adjacent-system patterns are documented in
[`COMPARISON.md`](COMPARISON.md), with dated source links. This page records
scope decisions only; it does not claim that a vendor feature is good or bad.
Revisit a deferred item when its contract is designed and a regression test can
prove it.
