"""Materialise an OCI or Docker image archive into a rootfs.

The shell wrapper extracts the archive to a private work directory. This module
reads either Docker's `manifest.json` or an OCI `index.json`, verifies blob
digests, rejects an entry that leaves the root, applies OCI whiteouts, and
extracts the remaining entries with its own writer.

Resolution is against the rootfs on disk, exactly as a chroot would do it: a
layer's symlink to `/usr/lib` is followed *inside the image*, so a later layer
can add a file beneath an absolute link, and no resolution step can reach a host
file. Nothing is cached, so there is no invalidation to get wrong: when an entry
replaces a link with a directory, the next resolution sees the directory.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

#: How many symlink hops one resolution may take before it is refused.
LINK_DEPTH = 40

#: Bits that grant their holder the owner's authority. They mean nothing without
#: the archive's ownership, which an unprivileged extraction cannot reproduce:
#: keeping them would hand this user the original owner's rights on the file.
_OWNER_BITS = 0o6000


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


def _read_blob_json(path: Path, digest: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ImageError(f"OCI blob {digest} is not valid UTF-8: {exc}") from exc


def _read_image_json(work: Path, name: str) -> object:
    """Read a manifest from inside the unpacked image, never through a link out."""
    base = work.resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ImageError(f"{name} is missing or leaves the image work directory")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ImageError(f"{name} is not valid UTF-8: {exc}") from exc


def layers(work: Path) -> list[Path]:
    """The layer blobs, from an OCI layout when present, else from Docker's manifest.

    An OCI index names each layer by digest, which is verified. A Docker
    manifest names a path, which is only contained. When an archive carries
    both, the verified description is the one to trust.
    """
    index = work / "index.json"
    if index.is_file():
        return _oci_layers(work)

    manifest = work / "manifest.json"
    if manifest.is_file():
        data = _read_image_json(work, "manifest.json")
        if not isinstance(data, list) or not data:
            raise ImageError("manifest.json has no image")
        image = data[0]
        if not isinstance(image, dict):
            raise ImageError("manifest.json has a non-object image")
        entries = image.get("Layers")
        if not isinstance(entries, list):
            raise ImageError("manifest.json has no Layers list")
        return [_layer(work, entry) for entry in entries]

    raise ImageError("neither manifest.json nor index.json is present")


def _oci_layers(work: Path) -> list[Path]:
    data = _read_image_json(work, "index.json")
    manifests = data.get("manifests") if isinstance(data, dict) else None
    if not isinstance(manifests, list) or not manifests:
        raise ImageError("index.json has no manifest")
    digest = manifests[0].get("digest") if isinstance(manifests[0], dict) else None
    if not isinstance(digest, str):
        raise ImageError("the OCI manifest has no digest")
    descriptor = _blob(work, digest)
    manifest_data = _read_blob_json(descriptor, digest)
    nested = manifest_data.get("manifests") if isinstance(manifest_data, dict) else None
    if isinstance(nested, list):
        # An index of one image: the OCI layout allows a descriptor to point at
        # another index. Follow it, and require it to name exactly one image.
        if len(nested) != 1 or not isinstance(nested[0], dict):
            raise ImageError("a nested OCI index must name exactly one manifest")
        inner = nested[0].get("digest")
        if not isinstance(inner, str):
            raise ImageError("the nested OCI manifest has no digest")
        manifest_data = _read_blob_json(_blob(work, inner), inner)
    entries = (manifest_data.get("layers")
               if isinstance(manifest_data, dict) else None)
    if not isinstance(entries, list):
        raise ImageError("the OCI manifest has no layers list")
    result: list[Path] = []
    for entry in entries:
        layer_digest = entry.get("digest") if isinstance(entry, dict) else None
        if not isinstance(layer_digest, str):
            raise ImageError("an OCI layer has no digest")
        result.append(_blob(work, layer_digest))
    return result


def _resolve(root: Path, name: str, depth: int = 0,
             follow_final: bool = True) -> str:
    """Resolve a layer path to a path relative to `root`, following image links.

    Every symlink consulted is one already written into the rootfs, so the walk
    stays inside the image: an absolute target restarts at the image root and a
    relative target is relative to the link's directory. `..` clamps at the root,
    as it does in a chroot.

    `follow_final=False` resolves the parent only. A whiteout, a hardlink source
    and any write must act on the entry itself, never on what it points at.
    """
    if depth > LINK_DEPTH:
        raise ImageError(f"symlink loop while resolving {name!r}")
    parts = name.split("/")
    if not follow_final and parts:
        head = "/".join(parts[:-1])
        parent = _resolve(root, head, depth) if head else ""
        return f"{parent}/{parts[-1]}" if parent else parts[-1]
    base = root.resolve()
    out: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part in ("", "."):
            index += 1
            continue
        if part == "..":
            if out:
                out.pop()
            index += 1
            continue
        candidate = "/".join([*out, part])
        entry = base / candidate
        if entry.is_symlink():
            target = os.readlink(entry)
            rest = parts[index + 1:]
            prefix = out if not target.startswith("/") else []
            combined = [*prefix, *target.split("/"), *rest]
            return _resolve(root, "/".join(combined), depth + 1)
        out.append(part)
        index += 1
    return "/".join(out)


def _target(root: Path, name: str, follow_final: bool = True) -> Path:
    if not name or name.startswith("/") or "\\" in name:
        raise ImageError(f"layer path is not relative: {name!r}")
    if ".." in Path(name).parts:
        raise ImageError(f"layer path contains a parent segment: {name!r}")
    base = root.resolve()
    resolved = _resolve(base, name, follow_final=follow_final)
    return base / resolved if resolved else base


def _validate(member: tarfile.TarInfo) -> None:
    """Reject only what is unsound on its own terms.

    The name must be relative, carry no parent segment, and name something. The
    *parents* are not resolved here: an earlier member of this same layer may
    replace a loop with a real directory before a later one writes beneath it,
    and a name that would land on the image root is refused when it is written.
    """
    if not member.name or member.name.startswith("/") or "\\" in member.name:
        raise ImageError(f"layer path is not relative: {member.name!r}")
    if ".." in Path(member.name).parts:
        raise ImageError(f"layer path contains a parent segment: {member.name!r}")


def _is_whiteout(member: tarfile.TarInfo) -> bool:
    return Path(member.name).name.startswith(".wh.")


def _remove(path: Path) -> None:
    """Delete one entry, never what it points at."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _empty(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        for child in path.iterdir():
            _remove(child)


def _whiteout(root: Path, member: tarfile.TarInfo) -> None:
    name = Path(member.name).name
    if name == ".wh..wh..opq":
        _empty(_target(root, str(Path(member.name).parent)))
        return
    _remove(_target(root, str(Path(member.name).with_name(name[4:])),
                    follow_final=False))


def _parents(path: Path) -> None:
    """Create a parent directory, tolerating a link that resolves to one."""
    if path.is_dir():
        return
    path.mkdir(parents=True, exist_ok=True)


def _mode(mode: int, dropped: list[int]) -> int:
    bits = mode & 0o7777
    if bits & _OWNER_BITS:
        dropped.append(bits & _OWNER_BITS)
    return bits & ~_OWNER_BITS


def _finish_directory(root: Path, relative: str, mode: int | None, mtime: float,
                      dropped: list[int]) -> None:
    """Apply a directory's final mode and mtime through an open descriptor.

    The path is walked one component at a time from an open descriptor on the
    image root, with `O_NOFOLLOW` at every step. A saved absolute path could be
    redirected by a link a later member put in place of an *ancestor*; a walk
    from the root descriptor cannot leave the image.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        handle = os.open(root.resolve(), flags)
    except OSError:
        return
    try:
        for part in relative.split("/") if relative else ():
            try:
                child = os.open(part, flags, dir_fd=handle)
            except OSError:
                return
            os.close(handle)
            handle = child
        if mode is not None:
            os.fchmod(handle, _mode(mode, dropped))
        with contextlib.suppress(OSError):
            os.utime(handle, (mtime, mtime))
    finally:
        os.close(handle)


def extract(layer: Path, root: Path, dropped: list[int] | None = None) -> None:
    if not layer.is_file():
        raise ImageError(f"missing layer: {layer}")
    root.mkdir(parents=True, exist_ok=True)
    dropped = dropped if dropped is not None else []
    #: Directory modes, applied after every member so a read-only directory can
    #: still be populated. A later header for the same path wins, as it does in
    #: tar, and the deepest path is applied first.
    directories: dict[str, tuple[int | None, float]] = {}
    with tarfile.open(layer) as archive:
        members = archive.getmembers()
        for member in members:
            _validate(member)
        for member in members:
            if _is_whiteout(member):
                _whiteout(root, member)
        for member in members:
            if _is_whiteout(member):
                continue
            relative = _resolve(root.resolve(), member.name, follow_final=False)
            dest = root.resolve() / relative if relative else root.resolve()
            if dest == root.resolve() and not member.isdir():
                raise ImageError(
                    f"layer entry would replace the image root: {member.name!r}")
            if member.isdir():
                if not dest.is_dir() or dest.is_symlink():
                    _remove(dest)
                dest.mkdir(parents=True, exist_ok=True)
                directories[relative] = (member.mode, float(member.mtime))
            elif member.issym():
                _parents(dest.parent)
                _remove(dest)
                dest.symlink_to(member.linkname)
            elif member.islnk():
                source = _target(root, member.linkname.lstrip("/"), follow_final=False)
                _parents(dest.parent)
                _remove(dest)
                os.link(source, dest, follow_symlinks=False)
            elif member.isfile():
                _parents(dest.parent)
                _remove(dest)
                handle = archive.extractfile(member)
                if handle is None:
                    raise ImageError(f"layer entry has no data: {member.name!r}")
                with open(dest, "wb") as out:
                    shutil.copyfileobj(handle, out)
                if member.mode is not None:
                    dest.chmod(_mode(member.mode, dropped))
                os.utime(dest, (float(member.mtime), float(member.mtime)))
            elif member.isfifo():
                _parents(dest.parent)
                _remove(dest)
                mode = _mode(0o644 if member.mode is None else member.mode, dropped)
                os.mkfifo(dest, mode)
                dest.chmod(mode)
            else:
                raise ImageError(f"unsupported layer entry type: {member.name!r}")
    for relative in sorted(directories, key=lambda item: item.count("/"), reverse=True):
        mode, mtime = directories[relative]
        _finish_directory(root, relative, mode, mtime, dropped)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: materialise_image.py WORK ROOT", file=sys.stderr)
        return 2
    work, root = Path(argv[1]), Path(argv[2])
    dropped: list[int] = []
    try:
        found = layers(work)
        root.mkdir(parents=True, exist_ok=True)
        for layer in found:
            extract(layer, root, dropped)
    except (ImageError, json.JSONDecodeError, OSError, tarfile.TarError) as exc:
        print(f"materialise: {exc}", file=sys.stderr)
        return 1
    print(f"layers: {len(found)}")
    if dropped:
        print(f"setuid/setgid bits dropped (ownership is not preserved): "
              f"{len(dropped)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))




