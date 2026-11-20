# Screenshot evidence

A screenshot can help a person confirm a review, but it cannot settle a finding.
Council therefore treats screenshots as **local run evidence**: it stores the
bytes, records their hash and exposes a direct link. The reviewer never receives
the image, never interprets it, and the verdict never depends on it.

## Why this is a sidecar

`verdict.json` is a durable, portable contract. A screenshot is often a local
artifact that is deliberately not pushed. Putting an image path into the verdict
would make the verdict wrong on a machine that does not have the image, and
would make the format depend on an optional file.

The sidecar keeps both contracts honest:

```text
.council/runs/<id>/
  verdict.json          unchanged
  sample-1.json
  artifacts.json        links, hashes and labels
  artifacts/
    <sha256>-<name>.png
```

The manifest stores relative paths. Moving the whole run keeps its links
working. Moving or deleting an individual screenshot is not a council fault;
`council evidence list` still prints the link and marks it `[missing]`.

## Add a screenshot

The agent that can see the editor state decides when a screenshot is relevant.
Council does not call a screenshot API and does not ask the reviewer to describe
one: the host agent captures the image with its own tool, then attaches the file.

```sh
council review --no-ephemeral --run-id before-fix --base origin/main
council evidence add before-fix .screens/zed-review.png \
  --label "Zed Agent Panel"
council evidence list before-fix
```

`evidence add` copies the file into `artifacts/`, hashes the bytes and writes
`artifacts.json` last. It refuses:

- a run id that is not a single path segment;
- a run directory or `artifacts/` that is a symlink;
- a source that is a symlink rather than a regular file;
- a manifest that does not have the expected format or a safe relative path.

The same bytes are stored once. Re-adding the same image returns the existing
manifest entry instead of duplicating the file.

For a run retained by the ACP/MCP server, the run lives outside the repository:

```sh
council evidence add <run-id> path/to/shot.png \
  --state-root ~/.cache/council/runs --label "Zed review panel"
```

On Windows the cache is under `%LOCALAPPDATA%\council\runs`; the command works
with native Windows paths and with paths inside WSL. `--json` emits the same
relative path, absolute file link and missing flag for a tool.

## What the link means

`council evidence list` prints a Markdown link for every entry:

```markdown
- [Zed Agent Panel](file:///home/user/project/.council/runs/before-fix/artifacts/…png)
```

The ACP `/review` response names the retained run path so the image can be
attached to that id; `/verdict` appends the same links from the retained run.
The link is computed from the run directory at read time. It does not prove that
the image still exists, and it does not claim that the image proves a finding.
It is a convenience for the person holding the evidence.

The reviewer prompt does not contain the manifest, the image bytes or a
description of the image. Screenshots are for the human confirmation loop, not
for the model's verdict.

## Retention and git

A run is ephemeral by default. Use `--no-ephemeral` or `--keep DIR` if the
screenshots should outlive the command. `.council/` is added to `.gitignore` by
`council init`; the ACP/MCP cache is outside the repository entirely.

Do not commit `artifacts/` or `artifacts.json` by default. They are local
evidence, not part of the pushed review record. If a team later decides to make
screenshots portable, that is a separate contract decision and should change
the verdict format deliberately, not silently.

## Bounded command surface

| command | purpose |
|---|---|
| `council evidence add RUN_ID IMAGE…` | copy images into a kept run |
| `council evidence list RUN_ID` | print direct links and missing markers |

Both commands accept `-C, --repo PATH`, `--state-root DIR` and `--json`. The
`add` command also accepts `--label TEXT`; without it, the file stem is used.

A missing image never changes an exit code. A malformed manifest is a start
failure, because it is a broken evidence record rather than a moved file.
