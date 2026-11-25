# Upstream defects this repository routes around

This is not a list of our bugs. Each entry is a defect in a dependency that this
gate could trip over, what we do instead, and the condition that says the workaround
can go. A workaround without a removal condition becomes folklore, so every entry
carries one.

## pytest: temp-directory cleanup leaks a scandir handle, and concurrent sessions race

**State as of 2026-11-25:** open upstream, workaround in place, nothing to write.

### What happens

When no basetemp is given, pytest builds and prunes
`$TMPDIR/pytest-of-<user>/pytest-N`. `_pytest/pathlib.py::find_prefixed` scans with
`os.scandir(root)` and never closes the handle, and `cleanup_candidates` drives that
generator through `itertools.tee` and `zip(strict=True)`, so it can be finalised
rather than exhausted. Two failures follow, independently:

1. The unclosed handle warns from its own finaliser. Under this project's
   `filterwarnings = ["error"]` the session fails, in whatever frame happens to be
   running. Captured traceback:

   ```
   _pytest/pathlib.py:367 in cleanup_numbered_dir
       try_cleanup(path, consider_lock_dead_if_created_before)
   ResourceWarning: unclosed scandir iterator <posix.ScandirIterator object at ...>
   ```

2. Two sessions sharing one temp root can delete each other's numbered or
   `garbage-*` directories, which surfaces as
   `OSError: [Errno 39] Directory not empty`.

### Why it reached us

The gate runs 263 claim sessions and 72 mutant suite sessions per run; a typical
project runs one or two. Measured on 9.1.1, four workers:

| shape | result |
|---|---|
| shared `TMPDIR` | 1 failure in 6 rounds (≈1 in 24 sessions) |
| private `TMPDIR` per worker | 0 failures, repeated |
| shared `TMPDIR`, handle closed on our side | `Directory not empty`, 2 in 10 rounds |
| shared `TMPDIR`, `--basetemp` per worker | 0 in 10 rounds, no `pytest-of-*` created |

### What we do instead

Every pytest this repository launches gets a basetemp inside a temp root it already
owns:

| where | flag |
|---|---|
| the `tests` check | `--basetemp=$TMPDIR/pytest-base` |
| each claim | `--basetemp=<its own temp root>/pytest` |
| each mutant's suite run | `--basetemp=<its own temp root>/base` |

With a basetemp, `TempPathFactory.getbasetemp` returns before
`make_numbered_dir_with_cleanup`, so the leaking path never runs — that is why the
last row above is clean. `tests/test_temp_roots.py` holds all three call sites to it,
and holds a non-pytest claim to being left unedited.

### Upstream

| | |
|---|---|
| [#15169](https://github.com/pytest-dev/pytest/issues/15169) | closed, 2026-10-13 — original report: a `0o000` directory makes later suites fail under `-W error` |
| [#15171](https://github.com/pytest-dev/pytest/pull/15171) | **open PR**, created 2026-10-13, last activity 2026-11-12 — closes the scandir iterator; not merged, `main` still has the bare `os.scandir` |
| [#15435](https://github.com/pytest-dev/pytest/issues/15435) | **open**, created 2026-11-22 — concurrent sessions sharing a temp root warn `Directory not empty` |

### Draft comment for #15435

Not posted. It belongs on the active thread with data rather than a new ticket or a
"+1"; post it when it is worth a maintainer's attention, and delete the fence.

```
Reproducible here on 9.1.1 with concurrent sessions sharing a temp root, and it has
two shapes.

Setup: 263 independent `pytest` invocations, one per entry in a claims registry, run
four at a time on a 4-core runner. Each runs a single node id with
`-q -p no:cacheprovider`, and all of them inherit the same `TMPDIR`. The project sets
`filterwarnings = ["error"]` with no per-test filters.

Shape 1 -- unclosed iterator. One round in six failed (~1 in 24 sessions) with:

    exit 1: pytest.PytestUnraisableExceptionWarning: Exception ignored while
    finalizing scandir iterator <posix.ScandirIterator object at 0x...>: None

Installing `sys.unraisablehook` to capture the traceback gives:

    _pytest/pathlib.py:367 in cleanup_numbered_dir
        try_cleanup(path, consider_lock_dead_if_created_before)
    ResourceWarning: unclosed scandir iterator <posix.ScandirIterator object at ...>

`find_prefixed` uses `os.scandir(root)` without a context manager, and
`cleanup_candidates` drives it through `itertools.tee` + `zip(strict=True)`, so the
generator can be finalised rather than exhausted.

Shape 2 -- after closing that handle locally (`with os.scandir(root) as entries:`),
the warning stops and the failure becomes:

    OSError: [Errno 39] Directory not empty:
      '<tmp>/pytest-of-<user>/garbage-<uuid>'

2 rounds in 10, same concurrency.

Controls: the same 263 invocations at four workers, each with a private `TMPDIR` --
0 failures over repeated runs. And with `--basetemp` per worker, 0 failures in 10
rounds on a shared `TMPDIR`, with no `pytest-of-*` directory created at all, since
`getbasetemp` returns early when a basetemp is given.

Both shapes need two sessions in one numbered root, and each disappears when the
root is private. Posting in case the volume is a useful data point.
```

### When to revisit

Trigger: `flake.lock` brings a pytest whose `find_prefixed` closes its handle. Check
in one line — `True` means the fix has landed:

```bash
nix develop -c python -c "import inspect, _pytest.pathlib as m; print('with os.scandir' in inspect.getsource(m.find_prefixed))"
```

Then confirm which release carried it, and that #15171 is closed. Keep `--basetemp`
either way: a private scratch root per run is correct on its own merits, not only as
a workaround. Re-run the four-worker table above before deleting this entry, because
the second shape is a separate defect and may outlive the first.
