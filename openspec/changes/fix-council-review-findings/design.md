# Design

## Context

See `proposal.md` for motivation and `specs/` for the behavior contract. The
proof engine already distinguishes `PROVEN`, `REFUTED` and `UNRUNNABLE`; the
failure is in how it classifies a command that failed for a reason unrelated to
the claim, and in how a line-anchored quote is checked. The action manifest is a
hand-written YAML file with no parser in the gate. The sandbox builds its argv in
a pure module (`src/council/domain/sandbox.py`) and a shell mirror
(`tools/sandbox.sh`); both need the same ordering rule.

## Goals / Non-Goals

**Goals:**

- Make the shipped action loadable and make its inputs data, not shell source.
- Make proof infrastructure failures and stale line references fail closed
  instead of refuting a finding.
- Keep the reviewed change from supplying its own rule documents.
- Keep user home paths out of the command proof's view.
- Make the task predicate use the same guard as the worker.
- Make the container tools own their workspace and accept OCI layouts.

**Non-Goals:**

- Changing the reviewer prompt or the model.
- Reworking the sandbox's bwrap dependency or the claim/mutation registry.
- Fixing the unrelated medium findings in the three project reviews.

## Decisions

**Classify proof failures by cause, not by exit code.** `repro` and `command`
keep their existing meaning, but a non-zero command whose output contains
`ModuleNotFoundError`, `ImportError` or `No module named` is a proof-environment
failure: the command could not attempt the claim. It becomes `UNRUNNABLE`.
Alternative considered: treat every unexpected failure as `REFUTED`; rejected
because it turns a missing dependency into a false negative.

**A present proof searches for its quote before refuting.** If the cited line
does not match, the engine looks for the same stripped text elsewhere in the
file. Found: `UNRUNNABLE` with the actual line, because the location is stale.
Absent everywhere: `REFUTED`, because the quote is not in the file. Alternative:
trust the line number strictly; rejected because a one-line drift suppressed a
true finding.

**Refuse rule-document changes unless explicitly allowed.** `prepare` already
refuses a changed baseline unless `--allow-baseline-change`; the rules use the
same pattern with `--allow-rules-change`. The guard runs before the reviewer is
asked, so an unreviewed rule cannot weaken its own review. Alternative: read
rules from the base commit; more correct for a changed rule, but it would hide a
deliberate maintenance change and requires a second reader path. The opt-in is
narrower and matches the existing baseline behavior.

**Mask `/home` and `/root` in the command sandbox.** The command sandbox keeps a
read-only root for toolchain paths, then overlays private tmpfs mounts for the
user home directories. A repository under a home directory is bound back
read-only before the overlay. The reviewer sandbox intentionally keeps host
read access; this change is scoped to command proofs. Alternative: replace the
root bind with an allowlist of toolchain paths; rejected as a larger portability
change that would require per-distro path discovery.

**Fix the shell mirror by ordering, not by a second policy.** In
`tools/sandbox.sh`, a repository under `/tmp` gets a private mountpoint and a
read-only bind of only that repository after `--tmpfs /tmp`; the rest of host
`/tmp` stays hidden. The same rule is expressed once in the Python argv builder.

**Use a green baseline as the mutation gate's precondition.** `mutation_check`
runs the unmodified suite in a writable copy first. A red baseline stops the
tool before it scores any mutation, so a pre-existing failure cannot certify a
mutation as caught.

**Validate a run id at the MCP boundary.** `validate_run_id` already owns the
naming rule; the resource resolves the candidate and checks containment before
reading. Alternative: sanitise only `..`; rejected because an absolute path and
an empty id need the same refusal.

## Risks / Trade-offs

- **The action lint adds PyYAML to the test environment.** It is a development
  dependency only; the core package keeps no runtime dependencies. Mitigation:
  add it to `pythonEnv` and the `dev` extra, and run the action test in the
  ordinary suite.
- **Masking `/home` can break a proof that legitimately needs a tool installed
  under a user profile.** The command sandbox's contract is repository plus
  toolchain; a proof that needs a user-local tool should be `UNRUNNABLE` and the
  caller can install it in the toolchain. Name the refusal in the detail.
- **The rule-change guard can refuse a legitimate rule maintenance review.** The
  opt-in mirrors the baseline flag and is recorded in the request; the error
  names the flag.
- **A stale line that occurs at another line could still be a different
  statement.** The engine reports the actual line and returns `UNRUNNABLE`; a
  caller can re-issue a precise quote rather than accepting a false proof.