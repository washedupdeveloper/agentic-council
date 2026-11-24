import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_the_sandbox_wrapper_leaves_no_writes() -> None:
    if shutil.which("bwrap") is None:
        pytest.skip("bwrap is not available")
    home_marker = Path.home() / "sandbox-wrapper-leak"
    tmp_marker = Path("/tmp/sandbox-wrapper-leak")
    for marker in (home_marker, tmp_marker):
        marker.unlink(missing_ok=True)
    script = ROOT / "tools" / "sandbox.sh"
    proc = subprocess.run(
        ["bash", str(script), "--", "bash", "-c",
         'echo x > "$HOME/sandbox-wrapper-leak"; '
         'echo x > /tmp/sandbox-wrapper-leak'],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert not home_marker.exists()
    assert not tmp_marker.exists()


def test_a_repo_under_tmp_binds_only_the_repo(tmp_path: Path) -> None:
    fake = tmp_path / "bin" / "bwrap"
    fake.parent.mkdir()
    capture = tmp_path / "args.txt"
    fake.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE\"\nexit 0\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    if not os.path.isdir("/tmp") or not os.access("/tmp", os.W_OK):
        pytest.skip("no writable /tmp here")
    under_tmp = Path(tempfile.mkdtemp(dir="/tmp"))
    repo = under_tmp / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{fake.parent}{os.pathsep}{env.get('PATH', '')}"
    env["HOME"] = str(home)
    env["CAPTURE"] = str(capture)
    proc = subprocess.run(
        ["bash", str(ROOT / "tools" / "sandbox.sh"), "--", "true"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    args = capture.read_text(encoding="utf-8").splitlines()
    assert args[args.index("--tmpfs") + 1] == "/tmp"
    index = args.index("--dir")
    assert args[index + 1] == str(repo.parent)
    assert args[index + 2:index + 5] == ["--ro-bind", str(repo), str(repo)]
