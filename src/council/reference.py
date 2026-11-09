"""Fetch reference material the caller names.

Never a proof and never model-chosen: a reviewer that can pick URLs can make the
tool reach anything the host can reach. The caller supplies them with
`--context-url`; the text is reference, and the prompt says so.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass

MAX_BYTES = 64_000


class FetchError(ValueError):
    """The reference could not be fetched, or is not text."""


@dataclass(frozen=True, slots=True)
class Reference:
    url: str
    text: str
    sha256: str


def fetch(url: str, *, timeout: int = 30, limit: int = MAX_BYTES) -> Reference:
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "council"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"{url} could not be fetched: {exc}") from exc
    if len(data) > limit:
        raise FetchError(f"{url} is larger than {limit} bytes; a reference is context, not a corpus")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FetchError(f"{url} is not UTF-8 text") from exc
    return Reference(url, text, hashlib.sha256(data).hexdigest()[:16])
