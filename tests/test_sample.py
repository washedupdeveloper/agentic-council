"""One sample's life: a good run, a retry, a refusal, and what lands on disk."""

from __future__ import annotations

import json
from pathlib import Path

from council.sample import run_sample, write_sample
from council.schema import DIMENSIONS

VALID = json.dumps({"sections": {name: [] for name in DIMENSIONS}})
BROKEN = "not json at all"


def test_a_good_sample_runs_once() -> None:
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return VALID

    result = run_sample("prompt", runner)
    assert result.ok
    assert result.attempts == 1
    assert calls == ["prompt"]


def test_a_bad_sample_is_retried_once() -> None:
    replies = iter([BROKEN, VALID])
    result = run_sample("prompt", lambda _: next(replies))
    assert result.ok
    assert result.attempts == 2


def test_a_sample_that_never_parses_reports_why() -> None:
    result = run_sample("prompt", lambda _: BROKEN)
    assert not result.ok
    assert result.attempts == 2
    assert result.error is not None and "JSON" in result.error


def test_a_runner_that_cannot_start_is_a_failure_not_a_crash() -> None:
    def runner(_: str) -> str:
        raise OSError("hermes not found")

    result = run_sample("prompt", runner)
    assert not result.ok
    assert result.error is not None and "could not run" in result.error


def test_attempts_can_be_one() -> None:
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return BROKEN

    result = run_sample("prompt", runner, attempts=1)
    assert result.attempts == 1
    assert len(calls) == 1


def test_a_written_sample_carries_its_error(tmp_path: Path) -> None:
    path = write_sample(tmp_path, run_sample("prompt", lambda _: BROKEN, attempts=1))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["error"]
    assert payload["findings"] == []


def test_a_written_sample_round_trips_its_findings(tmp_path: Path) -> None:
    body = json.dumps({"sections": {**{n: [] for n in DIMENSIONS},
                                    "security": [{"severity": "critical", "file": "a.py",
                                                  "line": 2, "claim": "A secret is committed.",
                                                  "proof": {"kind": "absent",
                                                            "params": {"pattern": "AKIA"}}}]}})
    path = write_sample(tmp_path, run_sample("prompt", lambda _: body))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["error"] is None
    assert payload["findings"][0]["severity"] == "critical"
    assert payload["findings"][0]["proof"]["kind"] == "absent"