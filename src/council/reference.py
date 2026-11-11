"""Fetch reference material the caller names.

Never a proof and never model-chosen: a reviewer that can pick URLs can make the
tool reach anything the host can reach. The caller supplies them with
`--context-url`; the text is reference, and the prompt says so.
"""

from __future__ import annotations

import hashlib
import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

MAX_BYTES = 64_000


class FetchError(ValueError):
    """The reference could not be fetched, or is not text."""


@dataclass(frozen=True, slots=True)
class Reference:
    url: str
    text: str
    sha256: str


def fetch(url: str, *, timeout: int = 30, limit: int = MAX_BYTES) -> Reference:
    try:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            local = Path(unquote(parsed.path))
            if not local.is_file():
                raise FetchError(f"{url} is not a regular file")
        request = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "council"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except FetchError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        raise FetchError(f"{url} could not be fetched: {exc}") from exc
    if len(data) > limit:
        raise FetchError(f"{url} is larger than {limit} bytes; a reference is context, not a corpus")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FetchError(f"{url} is not UTF-8 text") from exc
    return Reference(url, text, hashlib.sha256(data).hexdigest()[:16])
