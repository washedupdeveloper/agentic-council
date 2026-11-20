# Design

## Merge order

1. Confirm `agent-adapters` and `kernel-move` are ancestors of `v2`; no merge
   commit is needed for already-integrated history.
2. Merge `origin/dependabot/github_actions/actions-640176b5ab`.
3. Merge `origin/dependabot/pip/python-411bd075af`.
4. Resolve conflicts by taking the dependency update and re-running the gate;
   do not discard either branch's intent.
5. Push the resulting `v2`; do not delete the source branches.

## Verification

The full gate is the acceptance criterion: pytest, mypy, pyright, ruff F/E9,
claims, mutations, `openspec validate --all --strict`, and the Nix checks. The
dependency branches are merged only if the integrated tree is green.

## Rollback

If a dependency branch cannot pass the gate, stop and report the failing check
instead of forcing the merge. The pre-merge `v2` commit remains available in
history.