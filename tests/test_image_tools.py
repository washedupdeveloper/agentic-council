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


def test_a_later_layer_adds_a_file_beneath_an_absolute_link(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "usr" / "lib").mkdir(parents=True)
    (root / "lib").symlink_to("/usr/lib")
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo("lib/example"))
    module["extract"](source, root)
    assert (root / "usr" / "lib" / "example").is_file()


def test_a_relative_link_with_a_parent_segment_inside_the_image_is_allowed(
        tmp_path: Path) -> None:
    module = load_materialiser()
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo("lib/app"))
        link = tarfile.TarInfo("bin/app")
        link.type = tarfile.SYMTYPE
        link.linkname = "../lib/app"
        archive.addfile(link)
    root = tmp_path / "root"
    module["extract"](source, root)
    assert (root / "bin" / "app").readlink() == Path("../lib/app")


def test_a_sticky_directory_keeps_its_sticky_bit(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("tmp")
        info.type = tarfile.DIRTYPE
        info.mode = 0o1777
        archive.addfile(info)
    module["extract"](source, root)
    assert (root / "tmp").stat().st_mode & 0o1000


def test_a_parent_segment_in_a_member_name_is_refused(tmp_path: Path) -> None:
    module = load_materialiser()
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo("../escape"))
    try:
        module["extract"](source, tmp_path / "root")
    except module["ImageError"] as exc:
        assert "parent segment" in str(exc)
    else:
        raise AssertionError("a traversing member was accepted")


def test_a_manifest_symlink_outside_the_work_directory_is_refused(tmp_path: Path) -> None:
    module = load_materialiser()
    outside = tmp_path / "outside-manifest.json"
    outside.write_text("[]", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").symlink_to(outside)
    try:
        module["layers"](work)
    except module["ImageError"] as exc:
        assert "manifest" in str(exc)
    else:
        raise AssertionError("escaped manifest was read")


def test_a_parent_segment_in_a_link_target_follows_the_link(tmp_path: Path) -> None:
    """`..` after a symlink applies to the link's target, not the literal parent."""
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "opt" / "place").mkdir(parents=True)
    (root / "a").symlink_to("/opt/place")
    assert module["_resolve"](root.resolve(), "a/../x") == "opt/x"


def test_a_shared_symlink_cache_does_not_loop_on_a_second_layer(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        link = tarfile.TarInfo("lib")
        link.type = tarfile.SYMTYPE
        link.linkname = "/usr/lib"
        archive.addfile(link)
        directory = tarfile.TarInfo("usr/lib")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        archive.addfile(tarfile.TarInfo("lib/example"))
    module["extract"](second, root)
    assert (root / "usr" / "lib" / "example").is_file()


def test_a_hardlink_name_is_archive_root_relative(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("sub/source")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"old"))
        link = tarfile.TarInfo("sub/link")
        link.type = tarfile.LNKTYPE
        link.linkname = "sub/source"
        archive.addfile(link)
    module["extract"](source, root)
    assert (root / "sub" / "link").read_bytes() == b"old"


def test_a_fifo_is_materialised(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("run/pipe")
        info.type = tarfile.FIFOTYPE
        archive.addfile(info)
    module["extract"](source, root)
    import stat
    assert stat.S_ISFIFO((root / "run" / "pipe").stat().st_mode)


def test_a_parent_that_is_a_symlink_to_a_directory_is_accepted(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "run").mkdir(parents=True)
    (root / "var").mkdir()
    (root / "var" / "run").symlink_to("../run")
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo("var/run/example"))
    module["extract"](source, root)
    assert (root / "run" / "example").is_file()


def test_an_empty_layer_list_is_a_valid_image(tmp_path: Path) -> None:
    module = load_materialiser()
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(
        '[{"Layers": []}]', encoding="utf-8")
    module["layers"](work)


def test_a_directory_replacing_a_symlink_clears_the_cached_target(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "opt" / "old").mkdir(parents=True)
    (root / "opt" / "new").mkdir()
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        link = tarfile.TarInfo("place")
        link.type = tarfile.SYMTYPE
        link.linkname = "/opt/old"
        archive.addfile(link)
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        directory = tarfile.TarInfo("place")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("place/moved"))
    module["extract"](second, root)
    assert (root / "opt" / "new" / "moved").is_file() is False
    assert (root / "place" / "moved").is_file()


def test_a_hardlink_to_a_symlink_links_the_link(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        link = tarfile.TarInfo("original")
        link.type = tarfile.SYMTYPE
        link.linkname = "/nowhere"
        archive.addfile(link)
        hard = tarfile.TarInfo("alias")
        hard.type = tarfile.LNKTYPE
        hard.linkname = "original"
        archive.addfile(hard)
    module["extract"](source, root)
    assert (root / "alias").is_symlink()
    assert os.readlink(root / "alias") == "/nowhere"


def test_an_owner_bit_is_dropped_and_reported(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("setuid-tool")
        info.size = 2
        info.mode = 0o4755
        archive.addfile(info, io.BytesIO(b"#!"))
    dropped: list[int] = []
    module["extract"](source, root, dropped)
    mode = (root / "setuid-tool").stat().st_mode
    assert not mode & 0o4000
    assert mode & 0o111
    assert dropped == [0o4000]


def test_a_member_naming_the_root_is_refused(tmp_path: Path) -> None:
    module = load_materialiser()
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        link = tarfile.TarInfo(".")
        link.type = tarfile.SYMTYPE
        link.linkname = "/tmp/elsewhere"
        archive.addfile(link)
    root = tmp_path / "root"
    root.mkdir()
    try:
        module["extract"](source, root)
    except module["ImageError"] as exc:
        assert "image root" in str(exc)
    else:
        raise AssertionError("a member replacing the root was accepted")
    assert root.is_dir() and not root.is_symlink()


def test_a_whiteout_forgets_the_cached_target_of_the_entry(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "opt" / "old").mkdir(parents=True)
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        link = tarfile.TarInfo("place")
        link.type = tarfile.SYMTYPE
        link.linkname = "/opt/old"
        archive.addfile(link)
        directory = tarfile.TarInfo("opt/old")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        archive.addfile(tarfile.TarInfo(".wh.place"))
        directory = tarfile.TarInfo("opt/new")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("place/moved"))
    module["extract"](second, root)
    assert not (root / "opt" / "old" / "moved").exists()
    assert (root / "place" / "moved").is_file()


def test_a_fifo_honours_an_explicit_zero_mode(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("run/sealed")
        info.type = tarfile.FIFOTYPE
        info.mode = 0
        archive.addfile(info)
    module["extract"](source, root)
    assert (root / "run" / "sealed").stat().st_mode & 0o777 == 0


def test_an_image_with_no_layers_still_creates_the_root(tmp_path: Path) -> None:
    script = ROOT / "tools" / "materialise_image.py"
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text('[{"Layers": []}]', encoding="utf-8")
    root = tmp_path / "root"
    proc = subprocess.run([sys.executable, str(script), str(work), str(root)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert root.is_dir()


def test_the_cli_reports_a_dropped_owner_bit(tmp_path: Path) -> None:
    script = ROOT / "tools" / "materialise_image.py"
    work = tmp_path / "work"
    work.mkdir()
    layer = work / "layer.tar"
    with tarfile.open(layer, "w") as archive:
        info = tarfile.TarInfo("setuid-tool")
        info.size = 2
        info.mode = 0o4755
        archive.addfile(info, io.BytesIO(b"#!"))
    (work / "manifest.json").write_text(
        '[{"Layers": ["layer.tar"]}]', encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), str(work), str(tmp_path / "root")],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "setuid/setgid bits dropped" in proc.stderr


def test_a_dot_directory_header_is_accepted(tmp_path: Path) -> None:
    """`tar -cf x.tar .` writes a `.` directory member; it is the root itself."""
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        header = tarfile.TarInfo(".")
        header.type = tarfile.DIRTYPE
        header.mode = 0o755
        archive.addfile(header)
        archive.addfile(tarfile.TarInfo("file"))
    module["extract"](source, root)
    assert (root / "file").is_file()


def test_a_root_opaque_whiteout_clears_the_lower_layer(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        archive.addfile(tarfile.TarInfo("old"))
        directory = tarfile.TarInfo("sub")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("sub/old"))
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        archive.addfile(tarfile.TarInfo(".wh..wh..opq"))
        archive.addfile(tarfile.TarInfo("new"))
    module["extract"](second, root)
    assert not (root / "old").exists()
    assert not (root / "sub").exists()
    assert (root / "new").is_file()


def test_a_directory_replaces_a_fifo(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        info = tarfile.TarInfo("node")
        info.type = tarfile.FIFOTYPE
        archive.addfile(info)
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        directory = tarfile.TarInfo("node")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("node/inside"))
    module["extract"](second, root)
    assert (root / "node" / "inside").is_file()


def test_a_read_only_directory_can_still_be_populated(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        directory = tarfile.TarInfo("data")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o555
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("data/item"))
    try:
        module["extract"](source, root)
        populated = (root / "data" / "item").is_file()
        mode = (root / "data").stat().st_mode & 0o777
    finally:
        target = root / "data"
        if target.exists():
            target.chmod(0o755)
    assert populated
    assert mode == 0o555


def test_a_regular_file_keeps_its_archived_mtime(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        info = tarfile.TarInfo("source")
        info.size = 2
        info.mtime = 1_000_000_000
        archive.addfile(info, io.BytesIO(b"#!"))
    module["extract"](source, root)
    assert (root / "source").stat().st_mtime == 1_000_000_000


def test_a_root_opaque_whiteout_leaves_no_stale_destination(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "old").mkdir(parents=True)
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        link = tarfile.TarInfo("place")
        link.type = tarfile.SYMTYPE
        link.linkname = "/old"
        archive.addfile(link)
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        archive.addfile(tarfile.TarInfo(".wh..wh..opq"))
        directory = tarfile.TarInfo("place")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("place/moved"))
    module["extract"](second, root)
    assert (root / "place" / "moved").is_file()
    assert not (root / "old" / "moved").exists()


def test_a_whiteout_for_a_directory_does_not_misdirect_a_recreated_one(
        tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "keep").mkdir(parents=True)
    first = tmp_path / "first.tar"
    with tarfile.open(first, "w") as archive:
        directory = tarfile.TarInfo("etc")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        link = tarfile.TarInfo("etc/alias")
        link.type = tarfile.SYMTYPE
        link.linkname = "/keep"
        archive.addfile(link)
    module["extract"](first, root)
    second = tmp_path / "second.tar"
    with tarfile.open(second, "w") as archive:
        archive.addfile(tarfile.TarInfo("etc/.wh.alias"))
        directory = tarfile.TarInfo("etc/alias")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("etc/alias/new"))
    module["extract"](second, root)
    assert (root / "etc" / "alias" / "new").is_file()
    assert not (root / "keep" / "new").exists()


def test_a_cyclic_link_elsewhere_does_not_block_a_layer(tmp_path: Path) -> None:
    """Nothing is resolved speculatively: an unrelated loop cannot be reached."""
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "loop").mkdir(parents=True)
    (root / "loop" / "a").symlink_to("b")
    (root / "loop" / "b").symlink_to("a")
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo(".wh..wh..opq"))
        archive.addfile(tarfile.TarInfo("fine"))
    module["extract"](source, root)
    assert (root / "fine").is_file()


def test_the_last_directory_header_wins(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        for mode in (0o700, 0o750):
            header = tarfile.TarInfo("data")
            header.type = tarfile.DIRTYPE
            header.mode = mode
            archive.addfile(header)
    module["extract"](source, root)
    assert (root / "data").stat().st_mode & 0o777 == 0o750


def test_a_deferred_mode_does_not_follow_a_replacement_link(tmp_path: Path) -> None:
    """A directory replaced by a link must not chmod what the link points at."""
    module = load_materialiser()
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o755)
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        header = tarfile.TarInfo("data")
        header.type = tarfile.DIRTYPE
        header.mode = 0o700
        archive.addfile(header)
        link = tarfile.TarInfo("data")
        link.type = tarfile.SYMTYPE
        link.linkname = str(outside)
        archive.addfile(link)
    module["extract"](source, root)
    assert outside.stat().st_mode & 0o777 == 0o755


def test_a_layer_replacing_a_loop_with_a_directory_is_accepted(tmp_path: Path) -> None:
    """Validation must not resolve parents against the layer that is being replaced."""
    module = load_materialiser()
    root = tmp_path / "root"
    (root / "loop").mkdir(parents=True)
    (root / "loop" / "a").symlink_to("b")
    (root / "loop" / "b").symlink_to("a")
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        archive.addfile(tarfile.TarInfo("loop/.wh.a"))
        archive.addfile(tarfile.TarInfo("loop/.wh.b"))
        directory = tarfile.TarInfo("loop")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        archive.addfile(tarfile.TarInfo("loop/child"))
    module["extract"](source, root)
    assert (root / "loop" / "child").is_file()


def test_a_directory_keeps_its_archived_mtime(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        header = tarfile.TarInfo("data")
        header.type = tarfile.DIRTYPE
        header.mode = 0o755
        header.mtime = 1_000_000_000
        archive.addfile(header)
        archive.addfile(tarfile.TarInfo("data/item"))
    module["extract"](source, root)
    assert (root / "data").stat().st_mtime == 1_000_000_000


def test_a_deferred_mode_does_not_follow_a_replaced_ancestor(tmp_path: Path) -> None:
    """The walk starts at a descriptor on the root, so no saved path is reopened."""
    module = load_materialiser()
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (outside / "deep").mkdir(parents=True, mode=0o755)
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        for name in ("outer", "outer/deep"):
            header = tarfile.TarInfo(name)
            header.type = tarfile.DIRTYPE
            header.mode = 0o700
            archive.addfile(header)
        link = tarfile.TarInfo("outer")
        link.type = tarfile.SYMTYPE
        link.linkname = str(outside)
        archive.addfile(link)
    module["extract"](source, root)
    assert (outside / "deep").stat().st_mode & 0o777 == 0o755


def test_an_oci_index_is_used_even_when_a_docker_manifest_exists(tmp_path: Path) -> None:
    """An index names layers by digest, so its description is the verified one."""
    module = load_materialiser()
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text('[{"Layers": ["docker-layer.tar"]}]',
                                        encoding="utf-8")
    (work / "docker-layer.tar").write_bytes(b"not a layer")
    (work / "index.json").write_text(
        '{"manifests": [{"digest": "sha256:' + "0" * 64 + '"}]}', encoding="utf-8")
    try:
        module["layers"](work)
    except module["ImageError"] as exc:
        assert "blob" in str(exc)
    else:
        raise AssertionError("the unverified Docker manifest was preferred")


def test_a_manifest_that_is_not_utf8_is_a_materialise_error(tmp_path: Path) -> None:
    script = ROOT / "tools" / "materialise_image.py"
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_bytes(bytes([255]))
    proc = subprocess.run(
        [sys.executable, str(script), str(work), str(tmp_path / "root")],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "not valid UTF-8" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_a_root_directory_header_keeps_its_mode(tmp_path: Path) -> None:
    module = load_materialiser()
    root = tmp_path / "root"
    root.mkdir()
    source = tmp_path / "layer.tar"
    with tarfile.open(source, "w") as archive:
        header = tarfile.TarInfo(".")
        header.type = tarfile.DIRTYPE
        header.mode = 0o755
        header.mtime = 1_000_000_000
        archive.addfile(header)
        archive.addfile(tarfile.TarInfo("inside"))
    module["extract"](source, root)
    assert root.stat().st_mode & 0o777 == 0o755
    assert root.stat().st_mtime == 1_000_000_000


def test_a_nested_oci_index_is_followed(tmp_path: Path) -> None:
    module = load_materialiser()
    work = tmp_path / "work"
    blobs = work / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    layer = blobs / ("a" * 64)
    layer.write_bytes(b"layer-bytes")
    layer_digest = hashlib.sha256(b"layer-bytes").hexdigest()
    (blobs / layer_digest).write_bytes(b"layer-bytes")
    manifest = json.dumps({"layers": [{"digest": f"sha256:{layer_digest}"}]}).encode()
    manifest_digest = hashlib.sha256(manifest).hexdigest()
    (blobs / manifest_digest).write_bytes(manifest)
    inner = json.dumps({"manifests": [{"digest": f"sha256:{manifest_digest}"}]}).encode()
    inner_digest = hashlib.sha256(inner).hexdigest()
    (blobs / inner_digest).write_bytes(inner)
    (work / "index.json").write_text(
        json.dumps({"manifests": [{"digest": f"sha256:{inner_digest}"}]}),
        encoding="utf-8")
    assert module["layers"](work) == [blobs / layer_digest]


def test_an_oci_manifest_that_is_not_utf8_reports_an_error(tmp_path: Path) -> None:
    script = ROOT / "tools" / "materialise_image.py"
    work = tmp_path / "work"
    blobs = work / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    data = bytes([255])
    digest = hashlib.sha256(data).hexdigest()
    (blobs / digest).write_bytes(data)
    (work / "index.json").write_text(
        json.dumps({"manifests": [{"digest": f"sha256:{digest}"}]}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), str(work), str(tmp_path / "root")],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "not valid UTF-8" in proc.stderr
    assert "Traceback" not in proc.stderr
