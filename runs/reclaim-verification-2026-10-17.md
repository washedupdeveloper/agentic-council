# Re-claim verification — 2026-10-17

**Purpose.** M7 listed one durability branch as never exercised: *"the re-claim path (a
worker that genuinely dies and is retried)"*. Everything else in M7 had a run behind it —
the swarm end to end, restart survival, the dispatcher. This closes the last one.

**What "dies" means.** A worker takes a claim on a kanban card and then stops: killed,
OOM, host reboot, gateway restart. The claim is a lock with an expiry, so the board holds
a card that is `running` with a dead holder. Recovery is `hermes kanban reclaim`, which
releases the claim and returns the card to `ready`.

**Setup.** A throwaway board (`rc-reclaim-probe`), deleted afterwards, so the real board's
seven completed tasks were untouched. The card's assignee was a profile that does not
exist, so the dispatcher recorded `skipped_nonspawnable` and **no agent turn could be
spent** — the state machine was exercised without paying for a review.

**Commands.**

```bash
hermes kanban boards create rc-reclaim-probe --name "reclaim probe"
hermes kanban boards switch rc-reclaim-probe
hermes kanban create "reclaim probe card" \
  --assignee profile-that-does-not-exist \
  --idempotency-key probe-dedup-1 --json
hermes kanban claim  t_8103529d
hermes kanban reclaim t_8103529d --reason "probe: simulate a worker that died mid-task"
hermes kanban claim  t_8103529d
```

**Result — the branch works.**

| step | observed |
|---|---|
| created | `status: ready`, `max-retries: 2 (default)` |
| claimed | `running`, `[run 1] claimed {lock: workstation:548458, run_id: 1}` |
| reclaimed | `ready` again; `[run 1] reclaimed {manual: True, reason: …}` |
| dispatcher | `skipped_nonspawnable {assignee: profile-that-does-not-exist}` — no turn spent |
| re-claimed | `running`, `[run 2] claimed {run_id: 2}` |

The board's own event log is the evidence, and it distinguishes the two attempts by
`run_id`. A retry is a **new run**, not a resurrection of the old one, which is what makes
`max_retries: 2` a bound rather than a suggestion.

**The half the council owns.** A reclaim means the round may be dispatched twice, so the
guard that matters is not Hermes's — it is that a second `council swarm` cannot fork a
duplicate round. `swarm.py` puts an idempotency key on the **root** card only
(`<repo-slug>-r<round>`), because the children are created once, after it. Verified:

```bash
hermes kanban create "reclaim probe card" --assignee … \
  --idempotency-key probe-dedup-1 --json      # returns t_8103529d, the SAME id
hermes kanban list                            # still one card
```

So a reclaimed dispatch re-runs the same root rather than creating a second round.

**Cleanup.** Board switched back to `default` and the probe board deleted; the real board
still reports `done=7`.

**What this does NOT prove.** The reclaim was manual. A claim that *expires* on its own
(the lock carries `expires`) was not waited out, and a worker that dies mid-`council
sample` — leaving a half-written JSON — was not exercised; `merge` and the gate handle a
missing sample by reporting it, which is a different branch. Both are stated rather than
implied.
