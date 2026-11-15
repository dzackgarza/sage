"""The host runner unpacks the layers the image is actually published with (sage#39).

`docker/sage-image.py` is the route this repository documents for a host without
Docker, chroot or PRoot: it fetches the image layer by layer, verifies each digest,
and unpacks it. The image is published with `compression=zstd`, and every layer is
`application/vnd.oci.image.layer.v1.tar+zstd`; `tarfile` reads that only from Python
3.14, while the script runs on the host's interpreter. So `fetch` died on the first
layer of the published image:

    tarfile.ReadError: file could not be opened successfully:
    - method gz: ReadError('not a gzip file') ...

Applying a layer therefore decides by the layer's media type, and a zstd layer is
decompressed by the `zstd` binary or by `compression.zstd` -- never buffered whole,
because the largest layer unpacks to several gigabytes.

`--digest` takes the linux/amd64 manifest digest, `info` prints it, and resolving a
manifest digest as if it were an index answers 404 from the registry: the request
accepts either media type and the answer says which one it is.
"""

import gzip
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "docker" / "sage-image.py"

ZSTD = "application/vnd.oci.image.layer.v1.tar+zstd"
GZIP = "application/vnd.oci.image.layer.v1.tar+gzip"
PLAIN = "application/vnd.oci.image.layer.v1.tar"


def python_reads_zstd() -> bool:
    """Whether this interpreter has zstd itself (Python 3.14's `compression.zstd`)."""
    try:
        importlib.import_module("compression.zstd")
    except ImportError:
        return False
    return True


needs_zstd = pytest.mark.skipif(
    shutil.which("zstd") is None and not python_reads_zstd(),
    reason="this host has neither the zstd binary nor Python 3.14's compression.zstd",
)


def load():
    spec = importlib.util.spec_from_file_location("sage_image", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sage_image = load()


def layer(directory: Path, entries: dict[str, str]) -> Path:
    """A layer tar holding one regular file per entry, plus a whiteout per `.wh.`."""
    directory.mkdir(parents=True, exist_ok=True)
    member = directory / "member"
    archive_path = directory / "layer.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name, text in entries.items():
            member.write_text(text, encoding="utf-8")
            info = archive.gettarinfo(str(member), arcname=name)
            with member.open("rb") as handle:
                archive.addfile(info, handle)
    return archive_path


def as_zstd(tar_path: Path) -> Path:
    """Compress a layer the way the build does: the binary, or this interpreter's zstd."""
    compressed = tar_path.with_name("layer.tar.zst")
    if shutil.which("zstd") is not None:
        subprocess.run(
            ["zstd", "--quiet", "--force", str(tar_path), "-o", str(compressed)],
            check=True,
        )
        return compressed
    from compression import zstd

    compressed.write_bytes(zstd.compress(tar_path.read_bytes()))
    return compressed


def as_gzip(tar_path: Path) -> Path:
    compressed = tar_path.with_name("layer.tar.gz")
    compressed.write_bytes(gzip.compress(tar_path.read_bytes()))
    return compressed


def root_with(directory: Path) -> Path:
    root = directory / "root"
    (root / "opt").mkdir(parents=True)
    (root / "obsolete").write_text("from an earlier layer", encoding="utf-8")
    return root


def with_hard_link(tar_path: Path, name: str, target: str) -> Path:
    """Append a hard-link member, as an image layer that carries one does."""
    info = tarfile.TarInfo(name)
    info.type = tarfile.LNKTYPE
    info.linkname = target
    info.mode = 0o644
    with tarfile.open(tar_path, "a") as archive:
        archive.addfile(info)
    return tar_path


def test_a_hard_link_is_linked_not_copied(tmp_path):
    """A link names an earlier member, and a stream cannot seek back to it."""
    needs_zstd(tmp_path)
    root = root_with(tmp_path)
    tar_path = with_hard_link(
        layer(tmp_path, {"opt/a.txt": "shared"}), "opt/b.txt", "opt/a.txt"
    )
    blob = as_zstd(tar_path)

    assert sage_image.apply_layer(blob, root, ZSTD) == 0
    first, second = root / "opt" / "a.txt", root / "opt" / "b.txt"
    assert second.read_text(encoding="utf-8") == "shared"
    assert first.stat().st_ino == second.stat().st_ino


def test_a_zstd_layer_is_applied(tmp_path):
    """The published form: a layer the image's `compression=zstd` produced."""
    needs_zstd(tmp_path)
    root = root_with(tmp_path)
    blob = as_zstd(layer(tmp_path, {"opt/new.txt": "hello", ".wh.obsolete": ""}))

    assert sage_image.apply_layer(blob, root, ZSTD) == 0
    assert (root / "opt" / "new.txt").read_text(encoding="utf-8") == "hello"
    # The whiteout removes what an earlier layer left, which is what a layer means.
    assert not (root / "obsolete").exists()


def test_an_uncompressed_layer_is_applied(tmp_path):
    """A tar layer takes the reader that does not need a decompressor."""
    root = root_with(tmp_path)
    blob = layer(tmp_path, {"opt/plain.txt": "plain", ".wh.obsolete": ""})

    assert sage_image.apply_layer(blob, root, PLAIN) == 0
    assert (root / "opt" / "plain.txt").read_text(encoding="utf-8") == "plain"
    assert not (root / "obsolete").exists()


def test_a_gzipped_layer_is_still_applied(tmp_path):
    """Transparent stream mode: the reader before this change read gzip too."""
    root = root_with(tmp_path)
    blob = as_gzip(layer(tmp_path, {"opt/gz.txt": "gzip"}))

    assert sage_image.apply_layer(blob, root, GZIP) == 0
    assert (root / "opt" / "gz.txt").read_text(encoding="utf-8") == "gzip"


@needs_zstd
def test_a_zstd_layer_names_the_decompressor_when_there_is_none(tmp_path, monkeypatch):
    """No `zstd` binary and a Python without `compression.zstd`: say so, do not crash."""
    root = root_with(tmp_path)
    blob = as_zstd(layer(tmp_path, {"opt/new.txt": "hello"}))
    monkeypatch.setattr(sage_image.shutil, "which", lambda name: None)

    if python_reads_zstd():
        # This interpreter reads zstd itself, so the layer is still applied.
        assert sage_image.apply_layer(blob, root, ZSTD) == 0
        assert (root / "opt" / "new.txt").read_text(encoding="utf-8") == "hello"
        return
    with pytest.raises(SystemExit) as error:
        sage_image.apply_layer(blob, root, ZSTD)
    assert "zstd" in str(error.value)
    assert "compression.zstd" in str(error.value)


def manifest_document(config: str = "sha256:" + "c" * 64) -> dict:
    return {
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"digest": config},
        "layers": [{"mediaType": ZSTD, "digest": "sha256:" + "d" * 64, "size": 1}],
    }


def test_a_platform_manifest_digest_resolves_as_the_manifest_it_names(tmp_path, monkeypatch):
    """`--digest` names the linux/amd64 manifest; the registry answers 404 for an index request."""
    body = json.dumps(manifest_document()).encode()
    reference = "sha256:" + hashlib.sha256(body).hexdigest()
    accepted = []

    def read_json(credentials, image, path, accept):
        accepted.append((path, accept))
        assert path == f"manifests/{reference}"
        return body, json.loads(body)

    monkeypatch.setattr(sage_image, "read_json", read_json)
    record = sage_image.resolve("token", "dzackgarza/sage", reference)

    assert record["manifest"] == reference
    assert record["config"] == "sha256:" + "c" * 64
    assert record["layers"][0]["mediaType"] == ZSTD
    # Either media type in the Accept header, and a single request: the index is not
    # asked for and the manifest is fetched once.
    assert len(accepted) == 1
    assert sage_image.ACCEPT_INDEX in accepted[0][1]
    assert sage_image.ACCEPT_MANIFEST in accepted[0][1]


def test_an_index_still_resolves_to_its_linux_amd64_manifest(monkeypatch):
    """The tag's own form: index, then the one platform manifest it names."""
    platform = "sha256:" + "e" * 64
    body = json.dumps({
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"digest": "sha256:" + "f" * 64, "platform": {"os": "unknown", "architecture": "unknown"}},
            {"digest": platform, "platform": {"os": "linux", "architecture": "amd64"}},
        ],
    }).encode()
    asked = []

    def read_json(credentials, image, path, accept):
        asked.append(path)
        if path == "manifests/develop":
            return body, json.loads(body)
        assert path == f"manifests/{platform}"
        document = manifest_document()
        return json.dumps(document).encode(), document

    monkeypatch.setattr(sage_image, "read_json", read_json)
    record = sage_image.resolve("token", "dzackgarza/sage", "develop")

    assert record["manifest"] == platform
    assert record["index"] == "sha256:" + hashlib.sha256(body).hexdigest()
    assert asked == ["manifests/develop", f"manifests/{platform}"]


class Transferred:
    """A registry response body, delivered in chunks like a socket's."""

    def __init__(self, payload: bytes, chunk: int = 4) -> None:
        self.payload = payload
        self.chunk = chunk

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def read(self, size: int) -> bytes:
        taken, self.payload = self.payload[: self.chunk], self.payload[self.chunk :]
        return taken


def test_a_transfer_that_does_not_verify_is_fetched_again(tmp_path, monkeypatch):
    """A short body leaves no trace but the digest, and the second transfer is the layer."""
    payload = b"the layer, whole"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    responses = [Transferred(b"the layer"), Transferred(payload)]
    monkeypatch.setattr(sage_image.urllib.request, "urlopen", lambda request, timeout: responses.pop(0))
    destination = tmp_path / "layer.blob"

    sage_image.fetch_blob("token", "dzackgarza/sage", digest, destination)

    assert destination.read_bytes() == payload
    assert responses == []


def test_a_transfer_that_never_verifies_stops_saying_so(tmp_path, monkeypatch):
    """Three attempts, then the failure names the layer rather than a partial unpack."""
    digest = "sha256:" + hashlib.sha256(b"the layer, whole").hexdigest()
    monkeypatch.setattr(
        sage_image.urllib.request,
        "urlopen",
        lambda request, timeout: Transferred(b"the layer"),
    )
    with pytest.raises(SystemExit) as error:
        sage_image.fetch_blob("token", "dzackgarza/sage", digest, tmp_path / "layer.blob")
    assert digest in str(error.value)


def test_an_interrupted_fetch_resumes_after_the_layers_it_applied(tmp_path):
    """The record is what keeps a dropped transfer from costing the whole download."""
    cache = tmp_path / "cache"
    root = cache / "rootfs"
    root.mkdir(parents=True)

    assert sage_image.resume_point(cache, "sha256:" + "a" * 64, root) == 0
    sage_image.progress_path(cache).write_text(json.dumps({"manifest": "sha256:" + "a" * 64, "layers": 12}))
    assert sage_image.resume_point(cache, "sha256:" + "a" * 64, root) == 12
    # A different image is a different unpack: the layers do not carry over.
    assert sage_image.resume_point(cache, "sha256:" + "b" * 64, root) == 0
    # Nor does a record whose tree is gone.
    shutil.rmtree(root)
    assert sage_image.resume_point(cache, "sha256:" + "a" * 64, root) == 0
