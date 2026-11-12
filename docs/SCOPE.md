# Scoped and staged review

The caller owns the scope. A repository cannot narrow or widen what a review
looks at by editing `council.toml`; only the command line can.

```sh
council review --include 'src/**' --exclude 'src/generated/**'
council ci --include 'src/**/*.py' --include 'migrations/*.sql'
council review --staged
```

## Patterns

Patterns are repository-relative POSIX globs, repeated with `--include` and
`--exclude`:

- `*` and `?` stay inside one path segment;
- a `**` segment matches zero or more segments, so `src/**` includes
  `src/a.py` and `src/deep/a.py`;
- a pattern with an empty segment, `.`, `..`, an absolute prefix or a backslash
  is a start failure;
- the pattern is not a regular expression and is not shell-expanded.

An empty include list means "everything". An exclude always wins over an
include. If the include list matches nothing, the review is refused rather than
sent as an empty prompt.

## What was left out

A path that does not pass the scope is not silently dropped. The applied
patterns are recorded under `scope`, and every dropped path is listed in
`verdict.json`:

```json
"scope_ignored": [
  {"path": "docs/guide.md", "reason": "outside include", "pattern": null},
  {"path": "src/generated/api.py", "reason": "excluded", "pattern": "src/generated/**"}
]
```

`--plan` prints the same list as "outside scope" and includes it in its JSON
payload. A review whose scope removes every file is a start failure (exit 3)
before the reviewer is called.

## Staged review

`--staged` asks a different question: *what would the next commit contain?* It
reads the index against the base and deliberately excludes unstaged edits and
untracked files. `worktree` is recorded as `false` and `staged` as `true` in
`verdict.json`.

`--staged` is available on `review` and `ci`, not on `pr`: a pull request is a
committed revision, not an index.

## Interaction with a baseline

Scope filtering happens before the prompt is built, but the baseline-edit guard
checks the **unfiltered** diff. Excluding the baseline file does not let the
diff edit it unnoticed. A baseline only suppresses evidence that was actually
reviewed; a file outside the scope contributes no finding and no waiver.
