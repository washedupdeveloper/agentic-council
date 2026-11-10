import shutil
import subprocess
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
