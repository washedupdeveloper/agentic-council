"""Pure run-id validation.

A run id is a directory name on every host. The file-system guard that refuses
a symlinked `.council` lives in `council.paths`; this module only decides
whether the name is legal.
"""

from __future__ import annotations

from .text import printable

MAX_RUN_ID = 128
#: Characters a run id may not contain: separators, control characters, and the
#: set Windows refuses in a file name.
_FORBIDDEN = set('/\\<>:"|?*')


def validate_run_id(run_id: str) -> str:
    """One portable path segment, or a ValueError that names the problem."""
    if not run_id or not run_id.strip():
        raise ValueError("run id must not be empty")
    if run_id in {".", ".."}:
        raise ValueError(f"invalid run id {run_id!r}: expected one path segment")
    if any(ch in _FORBIDDEN for ch in run_id):
        raise ValueError(f"invalid run id {run_id!r}: expected one path segment")
    if not printable(run_id):
        raise ValueError(f"invalid run id {run_id!r}: control or format characters are not allowed")
    if len(run_id) > MAX_RUN_ID:
        raise ValueError(f"invalid run id: longer than {MAX_RUN_ID} characters")
    return run_id
