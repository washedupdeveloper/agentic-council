# Foundations

The seven decisions this tool is built on. Each one is stated as a decision, the
alternative it rejects, what would make it wrong, and where in the tree it
lives. The last section is the list of things this page cannot defend, which is
the part worth reading first if you are deciding whether to trust the tool.

Numbers in this page are measured at the commit that added `format: 1` to
`verdict.json`: 44 modules, 5,515 lines under `src/council`, 40 test files, 203
claims, 43 mutations.

---

## 1. A finding is a claim until a check settles it

**Decision.** Every finding carries a proof from a closed set — `absent`,
`present`, `command`, `repro`, `json`, `diff` — and the tool executes it. A
finding's state is `PROVEN` only when a proof held, `REFUTED` when one ran and
failed, `UNRUNNABLE` when none could run here, `UNSETTLED` when it was never
asked.

**Alternative rejected.** Prose review: a model states a defect, a human decides
whether to believe it. That is every code-review product before this one, and it
fails in the direction that matters — a confident sentence costs nothing to
produce, so the reviewer's output is dominated by sentences, not by defects.

**What would make it wrong.** If the proof set cannot express most real defects,
the rule turns into a filter for what is easy to prove: unused imports and
`TODO`s pass, race conditions do not. This is a live risk, and §8 says how live.

**Where.** `src/council/proofs.py` (executors), `domain/adjudication.py:decide`
(state from outcomes), `findings.py:State`.

---

## 2. The verdict is a pure function of states

**Decision.** `judge(findings)` reads the findings' states and decides. No
threshold, no score, no clock, no model call. The same findings and the same
repository produce the same verdict.

**Alternative rejected.** A weighted score with a cut-off — v1 had one, plus
curves and a calibration set. A score lets a bad finding be averaged away by
good ones, which is exactly the arithmetic a merge decision must not do.

**What would make it wrong.** If two runs disagree because the *inputs* differ in
a way the function cannot see (different model, different profile, different
prompt), then "pure" only means "deterministic given a black box". Hence
decision 5: the instrument is recorded, so a disagreement is attributable.

**Where.** `src/council/verdict.py:judge` (three rules, five lines of logic),
`verdict.py:Result`.

---

## 3. Three outcomes, not two

**Decision.** `PASS` (exit 0), `FAIL` (1), `INCOMPLETE` (2). A blocking finding
whose proof could not run, a sample that returned nothing usable, or a unit the
time budget never reached makes the run `INCOMPLETE`, never `PASS`.

**Alternative rejected.** Boolean pass/fail with a warning list. A boolean forces
the missing evidence into one of two lies: "fine" or "broken". The distinction is
the difference between a defect to fix and evidence to obtain.

**What would make it wrong.** If `INCOMPLETE` becomes the normal outcome, a gate
that reports it is useless — a check that always says "could not tell" is a check
nobody wires into CI. The mitigation is measurement, not hope: `council doctor`
fails before a run when the machine cannot produce evidence, and the time budget
exists so a slow provider cannot silently convert every run to `INCOMPLETE`.

**Where.** `verdict.py:Verdict`, `verdict.py:exit_code`, `domain/adjudication.py:verdict`
(the sample-failure addition), `cli.py` exit paths.

---

## 4. Severity ranks a defect; the tool decides what blocks

**Decision.** `BLOCKING = {high, critical}`; `ALWAYS_BLOCKING = {security,
correctness}` — a proven finding in those two dimensions blocks at any severity.
The model may rank a defect; it may not decide that a proven security or
correctness defect is mergeable.

**Alternative rejected.** Let the model say whether a finding should block. That
imports the model's judgement into the one place the tool exists to keep it out
of.

**What would make it wrong.** Two things, both real:

- *Misclassification.* Nothing checks that a finding's `dimension` is apt: a model
  that files a style nit under `correctness` makes it blocking, and the proof
  cannot help — it settles existence, not category. The merge cannot fix that for
  a single finding, but it no longer compounds it: one place is one finding, and
  its label is the most blocking dimension any sample used (M29), so a second
  opinion can neither duplicate nor weaken a defect.
- *Severity inflation by omission.* A model that never writes `low` for a
  correctness finding turns every typo into a gate failure.

Both are reasons this rule needs a **counterweight** the tool does not have yet:
a per-run count of blocking findings by dimension, and a baseline that can carry
an accepted `low` correctness finding. `--baseline` exists; an adjudicated
"accepted" state does not.

**Where.** `findings.py:BLOCKING`, `findings.py:ALWAYS_BLOCKING`, `findings.py:Finding.blocks`,
`verdict.py:judge`.

---

## 5. The instrument is part of the evidence

**Decision.** A run records a digest over the reviewer prompt, the profile name,
the profile's configuration bytes, the reasoning level, and the diff's sha256. A
second run against a different model is a different instrument and says so.

**Alternative rejected.** Record the model name only. Two runs of the same prompt
against the same model at different reasoning levels are not the same evidence,
and a verdict that cannot tell them apart invites comparing them.

**What would make it wrong.** If the digest covers things that do not change the
answer, it is noise that makes every run look unique. The rule is: hash what
changes the prompt or the decoding, nothing else. Transport (`stream`/`plain`)
is deliberately excluded and recorded separately.

**Where.** `prompt.py:instrument_digest`, `runner.py:profile_fingerprint`,
`prepare.py`, `verdict.json:digest`, `profile_config_sha256`.

---

## 6. Refuse rather than degrade

**Decision.** A prompt over the budget is not sent. A file too large for one
prompt is refused unless the caller opts into windows. A rule whose document
cannot be read stops the run. A sandbox requested but unavailable is a start
failure. A proof that cannot run is `UNRUNNABLE`, not "assume fine". A missing
reviewer is exit 3 before any sample.

**Alternative rejected.** Best-effort: truncate the prompt, skip the unreadable
document, run unsandboxed, treat a timeout as a pass. Every one of those makes
the tool's output cheaper to obtain and worth less.

**What would make it wrong.** If refusal is the common case, the tool is
unusable and people route around it. This is why the refusal must always name
the cost and the way out — `--max-prompt-bytes`, `--window-large-files`,
`--base` — and why the interactive dialogue exists. A refusal that does not say
what would work is a bug, not a stance.

**Where.** `planning.py:PromptTooLarge`, `planning.py:_windowed`,
`planning.py:rules_block`, `cli_parser.py` (`--sandbox`), `repo.py:ReviewError`,
`cli.py` start failures.

---

## 7. The tool must be able to fail its own tests

**Decision.** 203 claims, each naming a command that decides it, 49 of them
naming a *falsifier*; 43 mutations of the rules the claims protect, run against a
copy of the source, with the requirement that every mutation break at least one
claim and every declared falsifier break its own.

**Alternative rejected.** Coverage. A line can be executed by a test that asserts
nothing about it. A mutation that survives is a rule nobody is checking, which is
strictly more informative than 100 % coverage of a decorative suite.

**What would make it wrong.** If the mutations are chosen to be easy — mutate a
`>=` to `>`, never restructure — the check measures the mutation author, not the
suite. The honest form is to mutate the rule that a claim exists to protect, and
to add a mutation whenever a claim is added. Both are habits, not gates.

**Where.** `claims.toml`, `docs/CLAIMS.md` (generated), `tools/mutation_check.py`,
`bin/council-verify`.

---

## 8. What this page cannot defend

Listed because a foundations document that only lists strengths is marketing.

1. **Proof coverage is uneven.** `present`, `absent`, `json`, `diff` are text
   proofs; they establish that a line or a pattern exists, not that the code
   misbehaves. Only `command` and `repro` demonstrate behaviour, and they need a
   runnable command — which on a TypeScript repository means `pnpm`, and on a
   repository with no test runner means nothing. The default still lets a
   quotation block a merge; `--require-executed-proofs` is the strict reading,
   and it is not the default.
2. **Context is Python-only.** The context builder parses Python (`ast`,
   `python_files`). On any other language, depth silently collapses to 0: the
   reviewer sees the diff and nothing else. This is recorded in `context_depth`,
   but nothing warns that a run on a TypeScript tree is single-file by
   construction.
3. **Dimension classification is unchecked, and bounded.** One place is now one
   finding, labelled with the most blocking dimension any sample used, with the
   highest severity (M29) — a merge cannot duplicate a defect or weaken it. A
   single mislabelled finding still blocks, and no proof can independently
   classify a defect: the model chooses the category.
4. **The 32 KiB prompt default is one provider's measurement** — a 2.8 KB prompt
   was answered, a 60 KB prompt was not, on one profile on one day. It is a
   starting point, not a property of models.
5. **The ADR series stopped at M20.** M25–M28 changed the proof set, the unit
   ladder, the prompt contents and the verdict document without a decision
   record. Those three are written now (`docs/M25.md`, `docs/M26.md`,
   `docs/M28.md`); the gap is named rather than backfilled with fiction.
6. **`verdict.json` has a format number and no schema.** Consumers are told to
   refuse a format they do not know, and there is no published JSON Schema to
   validate against. `docs/VERSIONING.md` is prose.
7. **Ephemeral is the default, and evidence is the product.** A default run
   removes its own run directory, so the artefact that makes a verdict auditable
   is opt-in (`--no-ephemeral`, `--keep`). M19 argues this is right because the
   verdict is what people want; that argument is defensible and it makes audits
   the exception. A third-party reviewer cannot re-examine a run nobody kept.

## 9. The documents and what owns what

| Question | Document |
|---|---|
| What does the tool do, and how do I run it? | `README.md` |
| Why is it built this way? | this page |
| What was decided, when, and what did it cost? | `docs/M11.md` … `docs/M28.md` |
| What does each state mean? | `docs/STATE-MACHINES.md` |
| What is in scope, and what is silently dropped? | `docs/SCOPE.md` |
| What is public and may not change silently? | `docs/VERSIONING.md` |
| What is accepted, and by what evidence? | `docs/BASELINE.md`, `claims.toml` |
| What is true of this machine? | `council doctor`, `docs/PORTABILITY.md` |
| What has been reviewed with it, and what did it find? | `docs/ADOPTION.md`, `fixtures/adoption/` |
