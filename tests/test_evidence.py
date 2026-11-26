"""Screenshots are local run evidence with a sidecar link, never model input."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import council.cli as cli
from council import artifacts
from council.repo import ReviewError


PNG = b"\x89PNG\r\n\x1a\n" + b"not interpreted by council"


def make_run(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    run = repo / ".council" / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "verdict.json").write_text("{}", encoding="utf-8")
    return repo, run


def test_adding_a_screenshot_writes_a_relative_link(tmp_path: Path) -> None:
    repo, run = make_run(tmp_path)
    shot = tmp_path / "Zed Review.png"
    shot.write_bytes(PNG)
    added = artifacts.add(run, [shot], label="Zed Review")
    assert len(added) == 1
    entry = added[0]
    assert entry.path.startswith("artifacts/")
    assert len(entry.sha256) == 64
    assert all(char in "0123456789abcdef" for char in entry.sha256)
    assert (run / entry.path).read_bytes() == PNG
    manifest = json.loads((run / "artifacts.json").read_text(encoding="utf-8"))
    assert manifest["format"] == 1
    assert manifest["run"] == "run-1"
    assert manifest["artifacts"][0]["path"] == entry.path
    assert "file://" in artifacts.markdown(run, entry)
    assert artifacts.resolve_run("run-1", repo=repo) == run.resolve()


def test_adding_the_same_bytes_twice_keeps_one_file(tmp_path: Path) -> None:
    _, run = make_run(tmp_path)
    shot = tmp_path / "screen.png"
    shot.write_bytes(PNG)
    first = artifacts.add(run, [shot])
    second = artifacts.add(run, [shot])
    assert len(first) == 1
    assert first[0].sha256 == second[0].sha256
    assert len(artifacts.read(run)) == 1


def test_a_deleted_screenshot_is_listed_as_missing_without_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    repo, run = make_run(tmp_path)
    shot = tmp_path / "screen.png"
    shot.write_bytes(PNG)
    monkeypatch.chdir(repo)
    assert cli.main(["evidence", "add", "run-1", str(shot),
                     "--label", "Zed Review"]) == 0
    capsys.readouterr()
    (run / artifacts.read(run)[0].path).unlink()
    assert cli.main(["evidence", "list", "run-1"]) == 0
    output = capsys.readouterr().out
    assert "[missing]" in output
    assert "[Zed Review](file://" in output


def test_a_state_root_can_find_a_server_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "cache"
    run = root / "run-2"
    run.mkdir(parents=True)
    shot = tmp_path / "screen.png"
    shot.write_bytes(PNG)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["evidence", "add", "run-2", str(shot),
                     "--state-root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"] == str(run.resolve())
    assert payload["artifacts"][0]["path"].startswith("artifacts/")


def test_a_run_id_cannot_escape_the_state_root(tmp_path: Path) -> None:
    with pytest.raises(ReviewError, match="run id"):
        artifacts.resolve_run("../outside", repo=tmp_path)


def test_a_missing_source_is_a_start_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    repo, _run = make_run(tmp_path)
    monkeypatch.chdir(repo)
    assert cli.main(["evidence", "add", "run-1", str(tmp_path / "missing.png")]) == 3
    assert "not a regular file" in capsys.readouterr().err


def test_a_manifest_cannot_point_outside_artifacts(tmp_path: Path) -> None:
    _, run = make_run(tmp_path)
    (run / artifacts.MANIFEST).write_text(json.dumps({
        "format": 1,
        "run": "run-1",
        "artifacts": [{
            "path": "../outside.png",
            "sha256": "0" * 64,
            "bytes": 1,
            "media_type": "image/png",
            "label": "outside",
            "captured_at": "2026-01-01T00:00:00Z",
        }],
    }), encoding="utf-8")
    with pytest.raises(ReviewError, match="outside"):
        artifacts.read(run)


def test_a_symlinked_source_is_refused(tmp_path: Path) -> None:
    _, run = make_run(tmp_path)
    source = tmp_path / "real.png"
    source.write_bytes(PNG)
    linked = tmp_path / "linked.png"
    linked.symlink_to(source)
    with pytest.raises(ReviewError, match="symlink"):
        artifacts.add(run, [linked])


def test_the_verdict_can_append_the_direct_link(tmp_path: Path) -> None:
    from council_acp.agent import _verdict_text

    _, run = make_run(tmp_path)
    shot = tmp_path / "screen.png"
    shot.write_bytes(PNG)
    entry = artifacts.add(run, [shot], label="Zed Review")[0]
    text = _verdict_text({"verdict": "FAIL", "exit_code": 1,
                          "reason": "proven", "findings": []}, run)
    assert "artifacts:" in text
    assert entry.path in text
    assert "file://" in text
