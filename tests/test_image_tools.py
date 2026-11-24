"""The image materialiser: Docker and OCI layouts, whiteouts and containment."""

from __future__ import annotations

import hashlib
import io
import os
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "materialise-image.sh"


def layer(path: Path, members: list[tuple[str, bytes | None]]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, data in members:
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))


def outer(path: Path, files: list[tuple[str, bytes | None]]) -> None:
    layer(path, files)


def run(image: Path, root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHON"] = sys.executable
    return subprocess.run(["bash", str(SCRIPT), str(image), str(root)],
                          capture_output=True, text=True, env=env, timeout=60)


def test_materialise_a_docker_layout(tmp_path: Path) -> None:
    image = tmp_path / "docker.tar"
    layer_file = tmp_path / "layer.tar"
    layer(layer_file, [("etc/hello", b"hi\n")])
    manifest = json.dumps([{"Layers": ["layer.tar"]}]).encode()
    outer(image, [("manifest.json", manifest), ("layer.tar", layer_file.read_bytes())])
    root = tmp_path / "root"
    proc = run(image, root)
    assert proc.returncode == 0, proc.stderr
    assert (root / "etc/hello").read_text() == "hi\n"


def test_materialise_an_oci_layout(tmp_path: Path) -> None:
    image = tmp_path / "oci.tar"
    layer_file = tmp_path / "layer.tar"
    layer(layer_file, [("etc/oci", b"oci\n")])
    layer_digest = hashlib.sha256(layer_file.read_bytes()).hexdigest()
    manifest = json.dumps({"layers": [{"digest": f"sha256:{layer_digest}"}]}).encode()
    manifest_digest = hashlib.sha256(manifest).hexdigest()
    index = json.dumps({"manifests": [{"digest": f"sha256:{manifest_digest}"}]}).encode()
    outer(image, [
        ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}\n'),
        ("index.json", index),
        (f"blobs/sha256/{manifest_digest}", manifest),
        (f"blobs/sha256/{layer_digest}", layer_file.read_bytes()),
    ])
    root = tmp_path / "root"
    proc = run(image, root)
    assert proc.returncode == 0, proc.stderr
    assert (root / "etc/oci").read_text() == "oci\n"


def test_a_whiteout_removes_the_lower_layer_file(tmp_path: Path) -> None:
    image = tmp_path / "whiteout.tar"
    first = tmp_path / "first.tar"
    second = tmp_path / "second.tar"
    layer(first, [("dir/file", b"old\n")])
    layer(second, [("dir/.wh.file", None)])
    manifest = json.dumps([{"Layers": ["first.tar", "second.tar"]}]).encode()
    outer(image, [
        ("manifest.json", manifest),
        ("first.tar", first.read_bytes()),
        ("second.tar", second.read_bytes()),
    ])
    root = tmp_path / "root"
    proc = run(image, root)
    assert proc.returncode == 0, proc.stderr
    assert not (root / "dir/file").exists()


def test_a_layer_path_outside_the_root_is_refused(tmp_path: Path) -> None:
    image = tmp_path / "escape.tar"
    layer_file = tmp_path / "layer.tar"
    layer(layer_file, [("../escaped", b"no\n")])
    manifest = json.dumps([{"Layers": ["layer.tar"]}]).encode()
    outer(image, [("manifest.json", manifest), ("layer.tar", layer_file.read_bytes())])
    root = tmp_path / "root"
    proc = run(image, root)
    assert proc.returncode != 0
    assert "parent segment" in proc.stderr
    assert not (tmp_path / "escaped").exists()


def load_materialiser():
    import runpy
    return runpy.run_path(str(ROOT / "tools" / "materialise_image.py"))


def test_target_accepts_a_relative_root() -> None:
    module = load_materialiser()
    module["_target"](Path("rootfs"), "etc/hello")


def test_a_whiteout_removes_the_symlink_not_its_target(tmp_path: Path) -> None:
    module = load_materialiser()
    (tmp_path / "original").touch()
    (tmp_path / "alias").symlink_to("original")
    module["_whiteout"](tmp_path, tarfile.TarInfo(".wh.alias"))
    assert (tmp_path / "original").exists()
    assert not (tmp_path / "alias").is_symlink()


def test_an_opaque_whiteout_does_not_delete_a_same_layer_file(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        for name in ("dir/new", "dir/.wh..wh..opq"):
            archive.addfile(tarfile.TarInfo(name))
    module["extract"](source, root)
    assert (root / "dir/new").is_file()


def test_a_docker_layer_path_outside_the_work_directory_is_refused(tmp_path: Path) -> None:
    image = tmp_path / "escape-docker.tar"
    manifest = json.dumps([{"Layers": ["../escape.tar"]}]).encode()
    outer(image, [("manifest.json", manifest), ("layer.tar", b"not a layer")])
    root = tmp_path / "root"
    proc = run(image, root)
    assert proc.returncode != 0
    assert "leaves the image work directory" in proc.stderr


def test_an_oci_blob_outside_the_work_directory_is_refused(tmp_path: Path) -> None:
    module = load_materialiser()
    blobs = tmp_path / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"x")
    (blobs / "deadbeef").symlink_to(outside)
    try:
        module["_blob"](tmp_path, "sha256:deadbeef")
    except module["ImageError"] as exc:
        assert "OCI blob" in str(exc)
    else:
        raise AssertionError("escaped blob was accepted")


def test_a_malformed_manifest_reports_an_image_error(tmp_path: Path) -> None:
    module = load_materialiser()
    (tmp_path / "manifest.json").write_text("[null]", encoding="utf-8")
    assert module["main"](["tool", str(tmp_path), str(tmp_path / "root")]) == 1


def test_a_blob_digest_mismatch_is_refused(tmp_path: Path) -> None:
    module = load_materialiser()
    blobs = tmp_path / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    (blobs / "deadbeef").write_bytes(b"wrong")
    try:
        module["_blob"](tmp_path, "sha256:deadbeef")
    except module["ImageError"] as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("bad digest was accepted")


def test_an_absolute_symlink_inside_the_image_root_is_allowed(tmp_path: Path) -> None:
    module = load_materialiser()
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo("store/app"))
        link = tarfile.TarInfo("bin/app")
        link.type = tarfile.SYMTYPE
        link.linkname = "/store/app"
        archive.addfile(link)
    root = tmp_path / "root"
    module["extract"](source, root)
    assert (root / "bin/app").is_symlink()
    assert (root / "bin/app").readlink() == Path("/store/app")


def test_a_hardlink_sibling_is_not_overwritten(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    root.mkdir()
    (root / "a").write_bytes(b"old")
    os.link(root / "a", root / "b")
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("a")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"new"))
    module["extract"](source, root)
    assert (root / "b").read_bytes() == b"old"


def test_a_quoted_predicate_with_a_comma_survives(tmp_path: Path) -> None:
    import runpy
    parse = runpy.run_path(str(ROOT / "tools" / "milestone.py"))["_inline_list"]
    assert parse('["true", "echo a,b"]') == ["true", "echo a,b"]


def test_a_root_symlink_is_materialised(tmp_path: Path) -> None:
    module = load_materialiser()
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        link = tarfile.TarInfo("bin/root")
        link.type = tarfile.SYMTYPE
        link.linkname = "/"
        archive.addfile(link)
    module["extract"](source, tmp_path / "root")
    assert (tmp_path / "root" / "bin/root").readlink() == Path("/")


def test_a_file_can_replace_a_lower_layer_directory(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "name").mkdir(parents=True)
    (root / "name" / "child").write_text("old")
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("name")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"new"))
    module["extract"](source, root)
    assert (root / "name").read_text() == "new"


def test_a_whiteout_removes_an_absolute_symlink_not_its_target(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "store").mkdir(parents=True)
    (root / "store" / "app").write_text("payload")
    (root / "bin").mkdir()
    (root / "bin" / "app").symlink_to("/store/app")
    module["_whiteout"](root, tarfile.TarInfo("bin/.wh.app"))
    assert not (root / "bin" / "app").is_symlink()
    assert (root / "store" / "app").read_text() == "payload"
