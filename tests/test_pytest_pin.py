"""The pinned pytest must close the directory handle its temp cleanup opens.

`_pytest.pathlib.find_prefixed` scans with `os.scandir` and, unpatched, leaves the
handle to the garbage collector. An unclosed scandir warns from its own finaliser,
and this project runs pytest with `filterwarnings = ["error"]`, so that warning
fails whichever test happens to be executing -- measured, one claim in six rounds
of four concurrent runs.

The fix is `patches/pytest-close-scandir.patch`. This test is the alarm for the pin
moving: a bump that stops the patch applying fails the build, and a dropped patch
fails here.
"""

from __future__ import annotations

import gc
import warnings
from pathlib import Path

from _pytest.pathlib import find_prefixed


def test_the_pinned_pytest_closes_the_handle_it_scans(tmp_path: Path) -> None:
    """An abandoned scan must not leave a handle for the collector to warn about."""
    (tmp_path / "pytest-0").mkdir()
    (tmp_path / "pytest-1").mkdir()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        entries = find_prefixed(tmp_path, "pytest-")
        next(iter(entries))  # take one entry, then abandon the scan
        del entries
        gc.collect()

    leaks = [str(w.message) for w in caught if "scandir" in str(w.message)]
    assert not leaks, leaks


def test_the_pinned_pytest_closes_the_handle_when_the_scan_finishes(tmp_path: Path) -> None:
    """The exhausted path closes too, not only the abandoned one."""
    (tmp_path / "pytest-0").mkdir()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        list(find_prefixed(tmp_path, "pytest-"))
        gc.collect()

    leaks = [str(w.message) for w in caught if "scandir" in str(w.message)]
    assert not leaks, leaks
