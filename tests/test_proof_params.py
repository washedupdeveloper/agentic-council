"""Property tests for proof-parameter normalisation.

`run_proof` promises that malformed parameters cannot run: they settle as
UNRUNNABLE, never as an exception and never as a pass. These tests state that
promise over arbitrary input, and pin the coercion rules for `int`, `str` and
JSON pointers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from council.findings import State
from council.schema import PROOF_KINDS
from council.proofs import ProofContext, ProofOutcome, _BadParams, _int_param, _pointer, _str_param, run_proof

ALLOW = frozenset({"true", "false"})

SCALAR = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=10))


def ctx(repo: Path) -> ProofContext:
    return ProofContext(repo=repo, allow=ALLOW, timeout=5, sandbox=False)


@given(value=st.integers())
def test_every_int_is_accepted(value: int) -> None:
    assert _int_param({"line": value}, "line") == value


@given(value=st.booleans())
def test_a_bool_is_not_an_int(value: bool) -> None:
    with pytest.raises(_BadParams):
        _int_param({"line": value}, "line")


@given(value=st.one_of(st.none(), st.text(max_size=10), st.floats()))
def test_a_non_int_is_refused(value: object) -> None:
    with pytest.raises(_BadParams):
        _int_param({"line": value}, "line")


@given(key=st.text(max_size=20))
def test_every_key_survives_a_json_pointer(key: str) -> None:
    pointer = "/" + key.replace("~", "~0").replace("/", "~1")
    assert _pointer({key: 42}, pointer) == 42


@given(value=st.text(max_size=10))
def test_str_param_returns_what_it_was_given(value: str) -> None:
    if value:
        assert _str_param({"path": value}, "path") == value
    else:
        with pytest.raises(_BadParams):
            _str_param({"path": value}, "path")


@given(
    kind=st.text(max_size=12),
    params=st.dictionaries(st.text(max_size=10), SCALAR, max_size=5),
)
def test_run_proof_is_total_over_malformed_parameters(
    kind: str, params: dict[str, Any]
) -> None:
    """No input may raise: a proof that cannot be made is UNRUNNABLE, not a crash."""
    with tempfile.TemporaryDirectory() as directory:
        outcome = run_proof(kind, params, ctx(Path(directory)))
    assert isinstance(outcome, ProofOutcome)
    if kind not in PROOF_KINDS:
        assert outcome.state is State.UNRUNNABLE
