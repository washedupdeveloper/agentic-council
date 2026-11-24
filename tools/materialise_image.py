"""Materialise an OCI or Docker image archive into a rootfs.

The shell wrapper extracts the archive to a private work directory. This module
reads either Docker's `manifest.json` or an OCI `index.json`, rejects a layer
entry that leaves the root, applies OCI whiteouts, and extracts the remaining
entries with the standard library's data filter.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path


class ImageError(RuntimeError):
    """The image layout or one of its layers cannot be materialised safely."""


def _blob(work: Path, digest: str) -> Path:
    prefix, _, name = digest.partition(":")
    if prefix != "sha256" or not name or "/" in name:
        raise ImageError(f"not a sha256 blob digest: {digest!r}")
    base = work.resolve()
    target = (base / "blobs" / "sha256" / name).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ImageError(f"missing or escaped OCI blob: {digest}")
    digest_hash = hashlib.sha256()
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest_hash.update(chunk)
    if digest_hash.hexdigest() != name:
        raise ImageError(f"OCI blob digest mismatch: {digest}")
    return target


def _layer(work: Path, entry: object) -> Path:
    if not isinstance(entry, str) or not entry:
        raise ImageError("a Docker layer has no path")
    raw = Path(entry)
    if raw.is_absolute() or ".." in raw.parts or "\\" in entry:
        raise ImageError(f"layer path leaves the image work directory: {entry!r}")
    base = work.resolve()
    target = (base / raw).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ImageError(f"layer path leaves the image work directory: {entry!r}")
    return target


def layers(work: Path) -> list[Path]:
    manifest = work / "manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data:
            raise ImageError("manifest.json has no image")
        image = data[0]
        if not isinstance(image, dict):
            raise ImageError("manifest.json has a non-object image")
        entries = image.get("Layers")
        if not isinstance(entries, list) or not entries:
            raise ImageError("manifest.json has no layers")
        return [_layer(work, entry) for entry in entries]

    index = work / "index.json"
    if not index.is_file():
        raise ImageError("neither manifest.json nor index.json is present")
    data = json.loads(index.read_text(encoding="utf-8"))
    manifests = data.get("manifests") if isinstance(data, dict) else None
    if not isinstance(manifests, list) or not manifests:
        raise ImageError("index.json has no manifest")
    digest = manifests[0].get("digest") if isinstance(manifests[0], dict) else None
    if not isinstance(digest, str):
        raise ImageError("the OCI manifest has no digest")
    descriptor = _blob(work, digest)
    if not descriptor.is_file():
        raise ImageError(f"missing OCI manifest blob: {digest}")
    manifest_data = json.loads(descriptor.read_text(encoding="utf-8"))
    entries = manifest_data.get("layers") if isinstance(manifest_data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ImageError("the OCI manifest has no layers")
    result: list[Path] = []
    for entry in entries:
        layer_digest = entry.get("digest") if isinstance(entry, dict) else None
        if not isinstance(layer_digest, str):
            raise ImageError("an OCI layer has no digest")
        result.append(_blob(work, layer_digest))
    return result


def _target(root: Path, name: str, follow: bool = True) -> Path:
    if not name or name.startswith("/") or "\\" in name:
        raise ImageError(f"layer path is not relative: {name!r}")
    if ".." in Path(name).parts:
        raise ImageError(f"layer path contains a parent segment: {name!r}")
    base = root.resolve()
    if name == ".":
        return base
    raw = base / name
    probe = raw.resolve() if follow else raw.parent.resolve()
    if not probe.is_relative_to(base):
        raise ImageError(f"layer path leaves the root: {name!r}")
    return raw


def _whiteout(root: Path, member: tarfile.TarInfo) -> bool:
    name = Path(member.name).name
    if name == ".wh..wh..opq":
        parent = _target(root, str(Path(member.name).parent))
        if parent.is_dir():
            for child in parent.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
        return True
    if name.startswith(".wh."):
        target = root.resolve() / str(Path(member.name).with_name(name[4:]))
        if not target.resolve().is_relative_to(root.resolve()) and not target.is_symlink():
            raise ImageError(f"whiteout leaves the root: {member.name!r}")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        return True
    return False


def _is_whiteout(member: tarfile.TarInfo) -> bool:
    return Path(member.name).name.startswith(".wh.")


def extract(layer: Path, root: Path) -> None:
    if not layer.is_file():
        raise ImageError(f"missing layer: {layer}")
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(layer) as archive:
        members = archive.getmembers()
        whiteouts: list[tarfile.TarInfo] = []
        entries: list[tarfile.TarInfo] = []
        for member in members:
            _target(root, member.name, follow=False)
            if member.issym() or member.islnk():
                link = member.linkname
                if not link or "\\" in link:
                    raise ImageError(f"layer link is not relative: {member.name!r}")
                if link == "/":
                    # The image root itself: valid, and materialised below.
                    pass
                elif member.islnk():
                    _target(root, link.lstrip("/") if link.startswith("/") else link)
                elif link.startswith("/"):
                    _target(root, link.lstrip("/"))
                else:
                    _target(root, str(Path(member.name).parent / link))
            if _is_whiteout(member):
                whiteouts.append(member)
            else:
                entries.append(member)
        for member in whiteouts:
            _whiteout(root, member)
        for member in entries:
            target = _target(root, member.name, follow=False)
            if member.isdir() and (target.is_file() or target.is_symlink()):
                target.unlink(missing_ok=True)
            elif target.is_dir() and not target.is_symlink() and not member.isdir():
                shutil.rmtree(target)
            if member.issym() and member.linkname.startswith("/"):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.unlink(missing_ok=True)
                target.symlink_to(member.linkname)
                continue
            if member.islnk() and member.linkname.startswith("/"):
                source = _target(root, member.linkname.lstrip("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.unlink(missing_ok=True)
                target.hardlink_to(source)
                continue
            if member.isfile():
                target.unlink(missing_ok=True)
            archive.extract(member, root, filter="data")
            if member.isdir() and member.mode is not None:
                target.chmod(member.mode & 0o777)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: materialise_image.py WORK ROOT", file=sys.stderr)
        return 2
    work, root = Path(argv[1]), Path(argv[2])
    try:
        found = layers(work)
        for layer in found:
            extract(layer, root)
    except (ImageError, json.JSONDecodeError, OSError, tarfile.TarError) as exc:
        print(f"materialise: {exc}", file=sys.stderr)
        return 1
    print(f"layers: {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
