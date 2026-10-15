# Extending

Three things you can add, and every file each one touches. A dimension is a rubric plus
its tool mapping; a language is a set of markers plus the tools that serve each dimension
in it. Nothing here needs a change to `flake.nix` — adding a *command* rather than a
reviewer or a language is `docs/NIX.md` → "Adding a verb".

---

## Add a language (stack)

A stack is how the framework knows which analyzers to expect, which sets **β** —
`tools_ran / tools_expected`. Add a stack and a repository in that language stops
being scored as "generic".

Four edits, all in `scripts/score_reviews.py` — plus `scripts/probes.py` if the tool is built in.

### 1. Markers — how the stack is recognised

```python
STACK_MARKERS: Dict[str, Tuple[str, ...]] = {
    ...
    "elixir": ("mix.exs",),          # authoritative: presence is proof
}
```

Markers win outright. A stack is also detected from a **count** of matching
extensions if no marker matches:

```python
STACK_EXTENSIONS: Dict[str, Tuple[str, ...]] = {
    ...
    "elixir": (".ex", ".exs"),
}
```

The count path needs at least two files before it counts, so a stray `.ex` in a
mostly-Nix repo does not flip the detection.

### 2. Tools per dimension, for that stack

`STACK_TOOLS[dimension][stack]` is the denominator of β for that dimension. Add an
entry for **every** dimension, even if the list is empty — an absent key and an empty
list both mean "no deterministic tool".

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
ever emits is a permanent β penalty with no visible cause, so prefer names already in
`PROBES`.

### 3. Tell the gate the tool needs no install (if it does not)

Two sets decide whether a tool counts as available:

| Set | Meaning |
|---|---|
| `BUILTIN_TOOLS` | implemented by `scripts/probes.py` — always available, no install |
| `NIX_PROBE_TOOLS` | a wrapper around the pinned toolchain — available whenever the toolchain resolves |

A tool in neither set must be found on `PATH` to count. If your new tool is a thin
wrapper over something already pinned, add it to `NIX_PROBE_TOOLS`.

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
`signal` is a normalised 0–100 score. It must be **stdlib-only and cross-platform**: the
built-in probes are what keep the framework useful on a bare machine, and a probe that
shells out to something uninstalled breaks that promise. Use the pinned toolchain (the way
`probe_statix` does) if you need a pinned binary.

`signal` is a **density**, not a count: `score_from_density(findings, root)` applies the
Hill curve to findings per KLOC (§6). Pass `root` — a raw count scores a 14 KLOC
repository's 16 findings as 16 *per KLOC*, which is about 14× too harsh and penalises a
repository for being large.

### Verify

```bash
nix run .#council -- doctor --repo /path/to/an/elixir/repo   # β should rise from 0
nix develop -c pytest tests/ -q
```

---

## Add a verb

A verb is one module plus one row in `scripts/council.py`. Three things are
**enforced**, so a missed one fails `nix flake check` rather than shipping quietly:

1. **The module needs a guard.** Its `__main__` block calls
   `require_dispatch("<verb>")`, which refuses a bare `python3 scripts/<module>.py`.
   `test_modules.py` fails if a verb's module has no guard, and if the verb the guard
   names is not the one the CLI exposes.
2. **A user verb's module must be in `runtimeModules`** in `flake.nix`; a dev verb's
   must not be. `checks.commands` reads the verb table back from the built app and
   fails if the shipped tree and the table disagree.
3. **`--help` must be safe.** A verb that parses arguments answers it; a verb that
   ACTS has the dispatcher answer it, so `council <verb> --help` never does the thing.
   `checks.commands` runs `--help` on every user verb and fails if any exits non-zero.

Pick the audience deliberately: `"user"` ships in the app and the image, `"dev"` is
the devshell only. Anything that writes outside the run directory, spends agent turns,
or mutates a repository it is pointed at belongs in `"dev"` — that is what keeps
`council` safe to hand to someone else.

---

## Add a reviewer (a dimension)

A dimension is a rubric the reviewer loads plus the tool mapping that scores it. The
reviewer is one generalist profile carrying **every** rubric, so a new dimension is
picked up by reinstalling — there is no profile list to edit.

### 1. The rubric

Create `skills/reviewer-<dim>/SKILL.md`, modelled on an existing one. It needs
frontmatter (`name`, `description`) and the four sections the others have: what counts
as a finding in this dimension, how to score it, what evidence is mandatory, and what
to refuse.

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

The installer globs `reviewer-*/SKILL.md`, so it picks the rubric up with no edit —
and **prunes** a rubric the repo no longer has, because a stale one is worse than an
absent one: the reviewer would keep working that dimension while the merge silently
dropped its findings.

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

The new dimension shows up as a line in the round report and as
`round-N/<dim>.json` in the run directory. If it reads `NO FILE`, the reviewer produced
nothing for it — that is a gap the gate treats as an error, not a clean bill of health.

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
