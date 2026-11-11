"""One shared Lean project serves every checkout, resolved at its revisions (sage#13).

The image carries a single Lean project -- mathlib4 at the head of its master
branch, on the toolchain that revision pins, with its whole dependency closure
built inside it and Mathlib's oleans from the official cache. Every checkout
under /repos resolves Mathlib and its closure at the revision the shared
project carries: the provisioning sets each checkout's manifest entries for
mathlib and every package of the shared project's manifest to the shared
project's revisions, and links its packages directory to the project's built
copies -- the mechanism Lake itself documents, in the Lean Language
Reference's Lake chapter: "a manifest tracks the specific versions of other
packages that are used in a package ... Before building, Lake synchronizes
the local copy of each dependency with the version specified in the
manifest", and "packagesDir: The directory to which Lake should download
remote dependencies". A fixed revision in a checkout's manifest is not
served by the image (owner, 2026-11-11).

The real script runs here, over fixture repositories, with the record the
image carries. The assertions are about the script's own verdicts and not
about a reimplementation of them.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "docker" / "provision-lean-packages.sh"

TOOLCHAIN = "leanprover/lean4:v4.36.0-rc2"


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def commit(directory: Path, name: str) -> str:
    """A real checkout at a real revision, as a package the image carries looks."""
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(directory)], check=True)
    git(directory, "config", "user.email", "fixture@example.com")
    git(directory, "config", "user.name", "fixture")
    (directory / f"{name}.lean").write_text(f"-- {name}\n", encoding="utf-8")
    git(directory, "add", "-A")
    git(directory, "commit", "--quiet", "-m", name)
    return git(directory, "rev-parse", "HEAD")


def lean_project(directory: Path, pinned: dict[str, str], packages_dir: str,
                 toolchain: str = TOOLCHAIN) -> None:
    """A checkout as its repository publishes it: a toolchain and a flat manifest."""
    (directory / "lean-toolchain").write_text(toolchain + "\n", encoding="utf-8")
    (directory / "lake-manifest.json").write_text(
        json.dumps(
            {
                "version": "1.1.0",
                "packagesDir": packages_dir,
                "packages": [
                    {
                        "name": name,
                        "type": "git",
                        "url": f"https://example.invalid/{name}",
                        "rev": revision,
                    }
                    for name, revision in pinned.items()
                ],
            }
        ),
        encoding="utf-8",
    )


class Image:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.project = root / "opt" / "mathlib"
        self.record = root / "opt" / "lean-image.json"
        self.repos = root / "repos"
        self.project.mkdir(parents=True)
        (self.project / "lean-toolchain").write_text(TOOLCHAIN + "\n", encoding="utf-8")
        olean = self.project / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean"
        olean.parent.mkdir(parents=True)
        olean.write_text("olean", encoding="utf-8")
        closure = self.project / ".lake" / "packages"
        self.batteries = commit(closure / "batteries", "Batteries")
        (closure / "batteries" / ".lake" / "build" / "lib" / "lean").mkdir(parents=True, exist_ok=True)
        (self.project / "lake-manifest.json").write_text(
            json.dumps(
                {
                    "version": "1.1.0",
                    "packagesDir": ".lake/packages",
                    "packages": [
                        {"name": "batteries", "type": "git",
                         "url": "https://example.invalid/batteries", "rev": self.batteries}
                    ],
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True)
        git(self.project, "config", "user.email", "fixture@example.com")
        git(self.project, "config", "user.name", "fixture")
        git(self.project, "add", "-A")
        git(self.project, "commit", "--quiet", "-m", "mathlib")
        self.revision = git(self.project, "rev-parse", "HEAD")
        self.record.write_text(
            json.dumps(
                {
                    "project": str(self.project),
                    "repository": "https://example.invalid/mathlib4",
                    "revision": self.revision,
                    "master_head_at_resolution": self.revision,
                    "toolchain": TOOLCHAIN,
                    "resolved": "2026-11-10T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        self.repos.mkdir()

    def checkout(self, name: str, pinned: dict[str, str], packages_dir: str = ".lake/packages",
                 toolchain: str = TOOLCHAIN) -> Path:
        directory = self.repos / name
        directory.mkdir()
        lean_project(directory, pinned, packages_dir, toolchain)
        return directory

    def run(self, *arguments: str, revision: str | None = None,
            path: str = "/usr/bin:/bin:/usr/local/bin") -> subprocess.CompletedProcess:
        """The script as the image build runs it: this build's resolved head passed in."""
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.repos), *arguments],
            capture_output=True, text=True, check=False,
            env={
                "PATH": path,
                "MATHLIB_REVISION": revision if revision is not None else self.revision,
                "MATHLIB_PROJECT": str(self.project),
                "MATHLIB_RECORD": str(self.record),
                "PYTHON": "python3",
            },
        )


@pytest.fixture
def image(tmp_path: Path) -> Image:
    return Image(tmp_path / "image")


def test_the_plan_names_each_checkout_for_the_binding(image):
    """The plan emits one RESOLVE row per checkout under /repos, the binding that resolves it."""
    repository = image.checkout("lean-categories", {"mathlib": image.revision})
    result = image.run("--dry-run")
    assert result.returncode == 0, result.stderr
    assert f"RESOLVE\t{repository}" in result.stdout, result.stdout


def test_no_lean_checkout_is_reported_rather_than_passing_quietly(image):
    result = image.run("--dry-run")
    assert result.returncode == 0, result.stderr
    assert "no Lean checkout" in result.stdout


def test_the_record_and_the_head_that_the_image_carries_are_still_the_gate(image):
    """The provisioning's first half -- the record comparison -- is unchanged."""
    repository = image.checkout("lean-categories", {"mathlib": image.revision})
    bin = image.root / "bin"
    bin.mkdir()
    stub = bin / "lake"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'lake %s\\n\' "$*" >> "{image.root / "calls"}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    (image.root / "calls").write_text("", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(image.repos)],
        capture_output=True, text=True, check=False,
        env={
            "PATH": f"{bin}:/usr/bin:/bin",
            "MATHLIB_REVISION": image.revision,
            "MATHLIB_PROJECT": str(image.project),
            "MATHLIB_RECORD": str(image.record),
            "PYTHON": "python3",
        },
    )
    assert result.returncode == 0, result.stderr
    assert f"the image carries mathlib {image.revision}" in result.stdout
    assert f"resolving {repository} at the revisions of the shared project" in result.stdout


def test_a_project_at_another_revision_is_a_failed_image_not_a_warning(image):
    """The record names one revision, the tree is at another: a broken image."""
    image.checkout("lean-categories", {"mathlib": image.revision})
    moved = commit(image.project, "moved")
    result = image.run(revision=image.revision)
    assert moved != image.revision
    assert result.returncode == 1
    assert "does not carry one built project" in result.stderr, result.stderr


def test_a_project_without_its_olean_is_a_failed_image(image):
    """A record that claims a build the tree does not hold stops the run."""
    image.checkout("lean-categories", {"mathlib": image.revision})
    (image.project / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean").unlink()
    result = image.run()
    assert result.returncode == 1
    assert "carries no built Mathlib" in result.stderr, result.stderr
