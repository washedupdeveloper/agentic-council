# Extending

Three things you can add, and every file each touches. A dimension is a rubric plus
its tool mapping; a language is a set of markers plus the tools each dimension uses in
it. Nothing here needs a change to `flake.nix` — adding a *command* is `docs/NIX.md` →
"Adding a verb".

---

## Add a language (stack)

A stack sets **β** — `tools_ran / tools_expected` — by declaring which analyzers to
expect.

Four edits, all in `scripts/score_reviews.py` — plus `scripts/probes.py` if the tool is built in.

### 1. Markers — how the stack is recognised

```python
STACK_MARKERS: Dict[str, Tuple[str, ...]] = {
    ...
    "elixir": ("mix.exs",),          # authoritative: presence is proof
}
```

Markers win outright. With no marker, a stack is detected from a **count** of matching
extensions:

```python
STACK_EXTENSIONS: Dict[str, Tuple[str, ...]] = {
    ...
    "elixir": (".ex", ".exs"),
}
```

The count path needs at least two files, so a stray `.ex` in a mostly-Nix repo does not
flip the detection.

### 2. Tools per dimension, for that stack

`STACK_TOOLS[dimension][stack]` is the denominator of β. Add an entry for **every**
dimension, even empty — an absent key and an empty list both mean "no deterministic
tool".

```python
STACK_TOOLS = {
    "security": {
        ...
        "elixir": ["mix-audit"],
    },
    "correctness": {
        ...
        "elixir": ["mix-test"],
    },
    "readability":   {..., "elixir": ["mix-format"]},
    "performance":   {..., "elixir": ["mix-bench"]},
    "architecture":  {..., "elixir": ["dep-graph", "declared-rules"]},
}
```

Use the **exact tool name** the probe reports — β matches on the string. A name no probe
emits is a permanent β penalty with no visible cause; prefer names already in `PROBES`.

### 3. Tell the gate the tool needs no install (if it does not)

| Set | Meaning |
|---|---|
| `BUILTIN_TOOLS` | implemented by `scripts/probes.py` — always available, no install |
| `NIX_PROBE_TOOLS` | a wrapper around the pinned toolchain — available whenever the toolchain resolves |

A tool in neither set must be on `PATH` to count. A wrapper over something already
pinned goes in `NIX_PROBE_TOOLS`; a new external binary must ship — add it to
`EXTERNAL_TOOLS` (`score_reviews.py`) and `toolNames` (`nix/builders.nix`).

### 4. If the tool is built in, write the probe

```python
def probe_mix_format(root: Path) -> Dict[str, Any]:
    ...  # return result(name, ran, signal, findings, note)

PROBES: Dict[str, Callable[[Path], Dict[str, Any]]] = {
    ...
    "mix-format": probe_mix_format,
}
```

A probe returns `{"tool", "ran", "parsed", "signal", "findings", "note"}`, where
`signal` is a normalised 0–100 score. It must be **stdlib-only and cross-platform**: a
probe that shells out to something uninstalled breaks the bare-machine promise the
built-ins exist to keep. For a pinned binary, use the pinned toolchain (the way
`probe_statix` does).

`signal` is a **density**, not a count: `score_from_density(len(findings), root)` applies
the Hill curve to findings per KLOC (§6). Pass `root` — a raw count scores a 14 KLOC
repository's 16 findings as 16 *per KLOC*, ~14× too harsh.

### Verify

```bash
nix run .#council -- doctor --repo /path/to/an/elixir/repo   # β should rise from 0
nix develop -c pytest tests/ -q
```

---

## Add a verb

A verb is one module plus one row in `scripts/council.py`. Three things are **enforced**
(a miss fails `nix flake check`):

1. **The module needs a guard.** Its `__main__` block calls
   `require_dispatch("<verb>")`, which refuses a bare `python3 scripts/<module>.py`.
   `test_modules.py` fails if a verb's module has no guard, and if the verb the guard
   names is not the one the CLI exposes.
2. **A user verb's module must be in `runtimeModules`** in `nix/builders.nix`; a dev
   verb's must not be. `checks.commands` reads the verb table back from the built app
   and fails if the shipped tree and the table disagree.
3. **`--help` must be safe.** A verb that parses arguments answers it; a verb that
   ACTS has the dispatcher answer it, so `council <verb> --help` never does the thing.
   `checks.commands` runs `--help` on every user verb and fails if any exits non-zero.

Audience: `"user"` ships in the app and image, `"dev"` is devshell-only. Anything that
writes outside the run directory, spends agent turns, or mutates a repo it is pointed at
belongs in `"dev"`.

---

## Add a reviewer (a dimension)

The reviewer is one generalist profile carrying **every** rubric, so a new dimension is
picked up by reinstalling — no profile list to edit.

### 1. The rubric

Create `skills/reviewer-<dim>/SKILL.md`, modelled on an existing one: frontmatter
(`name`, `description`) plus the four sections the others have — what counts as a
finding, how to score it, mandatory evidence, what to refuse.

Keep it narrow: a rubric that overlaps an existing dimension produces findings that
compete for the same defect, and the score counts them once.

### 2. Register it in the loop

`scripts/council_loop.py`:

```python
DIMENSION_SPEC: Dict[str, Dict[str, str]] = {
    ...
    "accessibility": {"rubric": "reviewer-accessibility", "prefix": "A11Y"},
}

DEFAULT_GOALS: Dict[str, Dict[str, str]] = {
    ...
    "accessibility": {
        "objective": "No new barrier for a keyboard or screen-reader user.",
        "acceptance": "Every interactive element is reachable and labelled, "
                      "or the exception is recorded.",
    },
}
```

`DIMENSIONS` is derived from `DIMENSION_SPEC`, so the round, the bucketing and the
report pick the new dimension up automatically. `prefix` is the finding-id prefix —
keep it short and unique.

### 3. Register it in the gate

`scripts/score_reviews.py`:

- `STACK_TOOLS["accessibility"]` — one entry per stack (see above)
- `GENERIC_TOOLS["accessibility"]` — stack-independent tools, or `[]`
- `WEIGHTS["accessibility"]` — the aggregate weight. **`WEIGHTS` must sum to 1.0**;
  adding a dimension means rebalancing the others, not appending.

### 4. Reinstall, so the profile carries the new rubric

```bash
nix run .#council -- setup bots
```

The installer globs `reviewer-*/SKILL.md`, so it picks the rubric up with no edit — and
**prunes** a rubric the repo no longer has, because a stale one is worse than an absent
one: the reviewer would keep working that dimension while the merge silently dropped
its findings.

### 5. Expect the weights to matter

`WEIGHTS` is a working default; `docs/CALIBRATION.md` covers recalibrating. Adding a
dimension changes the aggregate, so re-run the gate on a known run and check the score
moved the way you expect before trusting it.

### Verify

```bash
nix develop -c pytest tests/ -q
nix run .#council -- doctor --repo /path/to/repo     # the new dimension appears, with its β
nix run .#council -- review /path/to/repo --samples 1
```

The new dimension shows up as a line in the round report and as `round-N/<dim>.json` in
the run directory. If it reads `NO FILE`, the reviewer produced nothing for it — a gap
the gate treats as an error, not a clean bill of health.

---

## What not to add

- **A second fan-out mechanism.** The harness spawns the reviewer; no profile carries
  `delegation`, because a delegated child inherits the parent's `HERMES_HOME` and
  cannot load another profile's rubric. Adding it back restores a path that looks like
  it works and silently runs generic subagents.
- **A per-dimension profile.** M8.5 measured five of them losing to one generalist
  sampled N times, at equal cost. See `docs/MILESTONES.md` M8.5 before reintroducing
  the shape that measurement rejected.
- **A `council-test` / `council-lint` command.** `nix flake check` already runs the
  suite, the formatter, statix and deadnix; `nix develop -c pytest` runs the suite
  against your working tree.
