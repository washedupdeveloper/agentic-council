# Proofs — the closed vocabulary a claim must speak

A finding is prose: *"this export is unused"*, *"this handler is injectable"*, *"the dashboard never
mounts"*. Prose cannot be checked, and a review whose findings cannot be checked is an opinion with
a score attached. A **proof** is the checkable half: one of seven kinds, executed by the
orchestrator, with three possible outcomes.

| Outcome | Means | What it may do |
|---|---|---|
| `supported` | the check passed | count as evidence; block only with a control |
| `refuted` | the check failed | drop the claim, and charge the reviewer (metrics) |
| `unrunnable` | the check could not run | keep the claim **open**; never a pass, never a failure |

`unrunnable` is not `refuted`. A missing browser, an absent server or an unrunnable command proves
nothing about the code, and folding it into "false" would let a missing tool certify a repository.

## The seven kinds

Declared once, in `protocol/proofs.json`. `scripts/proofs.py` refuses a kind it does not find there,
and `tests/test_proofs.py` asserts the registry and the file agree **in both directions** — so a
kind cannot exist in code without being declared, or be declared without an executor.

| Kind | Proves | Example |
|---|---|---|
| `absent` | no file matches a pattern outside an exclude set | an export with no call site |
| `present` | a cited line exists and says what was claimed | kills a hallucinated citation |
| `command` | a command's exit status or output | a test fails; a build breaks; an analyzer hits |
| `dom` | a page, loaded headless, has or lacks an element | the dashboard mounted |
| `http` | a **loopback** endpoint answers as claimed | the API contract, not the source's promise of it |
| `json` | a value sits at an RFC 6901 pointer | a dependency, a version, a config key |
| `diff` | a line is part of this change | the defect is new, not inherited |

`http` refuses any non-loopback host: a proof that reaches the network is not reproducible. `command`
allows an allowlisted executable (the project's own toolchain) or a script inside the repository;
anything else is `unrunnable`, because a proof must not quietly become "run something arbitrary and
report success".

## The control: a check never observed to fail is a guess

`adjudicate()` runs the claim's proof, then its **control** — a second proof the orchestrator
requires to be *refuted*. That is what separates a check from a tautology.

| Control result | Admission | May block a merge? |
|---|---|---|
| refuted | `proven` | **yes** |
| supported | `control_did_not_fail` | no — the check cannot tell the claim from its negation |
| unrunnable | `uncontrolled` | no — settle it first |
| absent | `uncontrolled` | no — reportable, not blockable |

A pattern that matches nothing anywhere "supports" both *"this symbol is unused"* and *"this symbol
is everywhere"*. Without a control there is no way to tell those apart, which is why an uncontrolled
claim is admissible as a note and never as a defect.

### The orchestrator writes the control when the reviewer does not

A control the reviewer writes about its own check is a promise, not a demonstration. So when a claim
arrives without one, `synthesise_control()` derives it from the proof itself, in one of two shapes:

| proof kind | synthesised control | what it establishes |
|---|---|---|
| `absent`, `present`, `command`, `json` | the **same check, run against the base revision** | the check discriminates *this change*: it holds here and not there |
| `dom`, `http` | the same observation with the **opposite expectation** | the observation can come out the other way |
| `diff` | the same line with the **opposite mode** (`added` ↔ `removed`) | the diff reading is not one-sided |

The base-revision control is the strong one. A test that fails on the branch and passes on the base
is evidence about the change; a test that fails on both is evidence about the repository, and the
claim comes back `control_did_not_fail` — unproven, and correctly so. Absolute paths inside the tree
are rebased into the base checkout, so the control cannot accidentally execute the defective tree's
own script.

`control_source` records which happened: `reviewer`, `orchestrator:base-revision`,
`orchestrator:expectation-flip`, `orchestrator:mode-flip`, or `none`. A reviewer control is never
replaced. With no base revision supplied, a tree-reading claim stays `uncontrolled` and says so —
the absence of a control is not a control.

## What this is not, yet

- **Not a sandbox.** `command` runs with the invoking user's privileges. It restricts *which*
  executables run, not what a permitted one does. The reviewer already has this access; the
  vocabulary does not pretend to remove it.
- **Enforced by default.** A blocking finding counts only once a proof refutes it; anything
  unsettled makes the run `unprovable`. `--allow-unproven` opts out to reproduce an old score, and
  the mode is recorded in `meta.json` so a re-run recomputes the same rule the run used.
- **The score is earned by the proofs too, and says which scale it is on.** See
  [ADJUDICATION.md § The score, and its scale](ADJUDICATION.md).
- **A reviewer-written control is still trusted when it is offered.** Synthesis fills a gap; it does
  not audit a control the reviewer did write. Measured over two calibration runs: the first reviewer
  pass wrote controls with an inverted `expect` and every one was caught; after the rule was
  sharpened — *keep `expect` identical, change only what it looks at* — four of seven findings came
  back `confirmed` with controls that genuinely failed. Passing `--base-tree` makes that unnecessary
  for the four tree-reading kinds.
- **Adjudication needs the tools where the claims were made.** A `command` proof naming `gitleaks`
  is `unrunnable` on a host without the pinned toolchain. That is the correct answer, and it is why
  the adjudication runs inside the same environment as the reviewer.

## Commands

```bash
council proofs --list                 # the vocabulary, with what each kind requires
council proofs --self-test            # every kind, both directions, on this host
council proofs --file claim.json --root .   # adjudicate one claim; exit 0 only if proven
```

`--self-test` builds its own fixture tree rather than reading `tests/`, so it works inside the
container image where the test suite is not shipped.

**It has three outcomes, because "did not run" is not "passed":**

| Exit | Means |
|---|---|
| `0` | every kind was exercised on this host, and none failed |
| `3` | **INCOMPLETE** — a kind was never exercised (no browser for `dom`, no git for `diff`); it names which |
| `1` | a kind ran and failed |

A host that has one exits **0**, and that is checkable without the image:
`nix shell nixpkgs#chromium -c council proofs --self-test` reports `10/10 exercised and
passed`, `dom` included. Measured on a host with chromium on `PATH`; the image ships the
same browser so the lane runs there too.

A host with no headless browser therefore exits **3**, not 0. That change came from a real failure:
the self-test used to count a skipped `dom` as a pass and printed `10/10` inside a container whose
chromium was aborting, so a green summary carried no information about the lane.