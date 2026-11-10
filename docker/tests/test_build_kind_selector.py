"""A moved Mathlib head selects a full build, and the selector says so.

sage#13's decision is that the image is one shared Lean project on the head the
build resolved. An incremental build is `FROM` the published image and can only add
layers, so extending a base that carries another head would leave the old closure
layer underneath the new one. The publish step writes the head it built from as the
label `dev.dzackgarza.mathlib.revision`, and `docker/select-build-kind.sh` -- the
step's own code, run here, not a copy of it -- compares that label with the head this
build resolved and selects `kind=full` when they differ or the label is absent.

`docker` is a stand-in: it answers `buildx imagetools inspect` from a file, which is
the only thing the selector asks it. The source checkout is a real git repository, so
the diff, the deletion rule and the Dockerfile rule are the ones the workflow meets.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SELECTOR = REPOSITORY / "docker" / "select-build-kind.sh"

MATHLIB = "a" * 40
MANIFEST_DIGEST = "sha256:" + "e" * 64
MATHLIB_MOVED = "b" * 40


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.source = root / "sage-source"
        self.source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(self.source)], check=True)
        git(self.source, "config", "user.email", "fixture@example.com")
        git(self.source, "config", "user.name", "fixture")
        (self.source / "README").write_text("base\n", encoding="utf-8")
        git(self.source, "add", "-A")
        git(self.source, "commit", "--quiet", "-m", "base")
        # The base image's revision is what the diff is taken against, and the
        # selector fetches it, so it has to exist in the checkout by name.
        self.base = git(self.source, "rev-parse", "HEAD")
        # actions/checkout gives the job an origin; the selector fetches the base
        # image's revision from it.
        git(self.source, "remote", "add", "origin", str(self.source))
        self.labels = {}
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.calls = root / "docker-calls.txt"
        # `docker buildx imagetools inspect IMAGE --format '{{ index .Image.Config
        # .Labels "name" }}'` prints that label, or `<no value>` when the image does
        # not carry it -- which is what the real one does, and what the selector has
        # to survive.
        stub = self.stubs / "docker"
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, re, sys\n"
            "arguments = ' '.join(sys.argv[1:])\n"
            f"open({str(self.calls)!r}, 'a').write(arguments + '\\n')\n"
            f"labels = json.load(open({str(root / 'labels.json')!r}))\n"
            "if '--raw' in arguments:\n"
            "    target = sys.argv[sys.argv.index('--raw') + 1]\n"
            "    if '@' in target:\n"
            "        print(json.dumps({'layers': [\n"
            "            {'mediaType': 'application/vnd.oci.image.layer.v1.' + t}\n"
            f"            for t in labels.get('layers', [])]}}))\n"
            "    else:\n"
            f"        print(json.dumps({{'manifests': [{{'digest': {MANIFEST_DIGEST!r}}}]}}))\n"
            "    raise SystemExit(0)\n"
            "match = re.search(r'Labels \"([^\"]+)\"', arguments)\n"
            "print(labels.get(match.group(1), '<no value>') if match else '<no value>')\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)

    def image(self, mathlib: str | None, revision: str | None = "BASE",
              layers: tuple[str, ...] = ("tar+zstd",)) -> None:
        """The base image's labels. `revision="BASE"` is this fixture's own base."""
        if revision == "BASE":
            revision = self.base
        labels = {}
        if mathlib is not None:
            labels["dev.dzackgarza.mathlib.revision"] = mathlib
        if revision is not None:
            labels["org.opencontainers.image.revision"] = revision
        labels["layers"] = list(layers)
        (self.root / "labels.json").write_text(json.dumps(labels), encoding="utf-8")

    def change(self, path: str, content: str | None = None) -> None:
        target = self.source / path
        if content is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(self.source, "add", "-A")
        git(self.source, "commit", "--quiet", "-m", f"touch {path}")

    def select(self, mathlib: str = MATHLIB, is_spinor: str = "false") -> subprocess.CompletedProcess:
        output = self.root / "github-output.txt"
        if output.exists():
            output.unlink()
        result = subprocess.run(
            ["bash", str(SELECTOR)],
            capture_output=True, text=True, check=False,
            env={
                "PATH": f"{self.stubs}:/usr/bin:/bin",
                "HOME": str(self.root),
                "BASE_IMAGE": "ghcr.io/example/sage:develop",
                "MATHLIB_REVISION": mathlib,
                "IS_SPINOR": is_spinor,
                "SOURCE": str(self.source),
                "GITHUB_OUTPUT": str(output),
            },
        )
        result.kinds = output.read_text(encoding="utf-8").split() if output.exists() else []
        return result


@pytest.fixture
def fixture(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path / "selector")


def test_the_same_head_on_a_source_change_is_an_incremental_build(fixture):
    fixture.image(MATHLIB)
    fixture.change("docker/notes.md", "an ordinary source change\n")
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=incremental"], result.kinds
    assert f"the base image carries mathlib {MATHLIB}, the head this build resolved" in result.stdout
    assert "incremental build" in result.stdout


def test_a_moved_head_selects_a_full_build(fixture):
    """The base carries one head and this build resolved another: no increment."""
    fixture.image(MATHLIB_MOVED)
    result = fixture.select(mathlib=MATHLIB)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert (
        f"the Mathlib head moved from {MATHLIB_MOVED} to {MATHLIB}" in result.stdout
    ), result.stdout


def test_a_base_without_the_mathlib_label_selects_a_full_build(fixture):
    """An image published before the label existed records no head to keep."""
    fixture.image(None)
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert "records no Mathlib revision" in result.stdout


def test_a_label_that_does_not_carry_a_revision_selects_a_full_build(fixture):
    """docker's `<no value>` must not be compared as if it were a revision."""
    fixture.image("<no value>")
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds


def test_a_build_that_resolved_no_head_selects_a_full_build(fixture):
    fixture.image(MATHLIB)
    result = fixture.select(mathlib="")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert "resolved no Mathlib head" in result.stdout
    assert fixture.calls.exists() is False, "nothing to compare, so nothing is inspected"


def test_a_dockerfile_change_selects_a_full_build(fixture):
    fixture.image(MATHLIB)
    fixture.change("docker/research-environment.Dockerfile", "FROM debian:trixie\n")
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert "the system layers" in result.stdout


def test_a_deleted_file_selects_a_full_build(fixture):
    """The incremental copy rsyncs and deletes nothing."""
    fixture.image(MATHLIB)
    fixture.change("README")
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds


def test_an_isolated_spinor_image_is_always_full_and_asks_the_registry_nothing(fixture):
    fixture.image(MATHLIB)
    result = fixture.select(is_spinor="true")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert "isolated spinor image" in result.stdout
    assert fixture.calls.exists() is False, "a spinor image needs no comparison"


def test_a_base_with_gzip_layers_selects_a_full_build(fixture):
    """#9: recompressing an increment over a gzip base leaves its big layer gzip."""
    fixture.image(MATHLIB, layers=("tar+gzip", "tar+gzip"))
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert "carries no zstd layer" in result.stdout


def test_a_base_with_a_zstd_layer_is_incremental_when_nothing_else_forces_full(fixture):
    fixture.image(MATHLIB, layers=("tar+zstd", "tar+gzip"))
    fixture.change("docker/notes.md", "a source change\n")
    result = fixture.select()
    assert result.kinds == ["kind=incremental"], result.kinds
    assert "the base image carries zstd layers" in result.stdout


def test_a_base_revision_that_cannot_be_read_selects_a_full_build(fixture):
    """No diff means no evidence that an increment is safe, so it is not chosen."""
    fixture.image(MATHLIB, revision="d" * 40)
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=full"], result.kinds
    assert "cannot be read" in result.stdout


def test_a_base_without_a_source_revision_still_builds_incrementally(fixture):
    """No revision to diff means no evidence against the increment, so it stands."""
    fixture.image(MATHLIB, revision=None)
    result = fixture.select()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.kinds == ["kind=incremental"], result.kinds
