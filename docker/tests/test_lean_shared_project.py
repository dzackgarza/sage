"""One shared Lean project serves every checkout, and a pin that disagrees says so.

sage#13 replaces the per-revision provisioning of sage#12 -- `mathlib@<revision>`
checkouts, `/opt/lake-views`, and the launcher's `--lean-view` -- with a single
project at `/opt/mathlib`, on the Mathlib head the build resolved, whose built
closure every Lean checkout under `/repos` resolves through links in the packages
directory its own lakefile declares.

The expensive half of that (clone the head, install the toolchain that revision
pins, `lake exe cache get`, `lake build Mathlib`) only runs where network and Lean
exist, so this test pins the half that decides everything: which package each pin
resolves to, which links are made, and what a disagreement says. It runs the real
script over fixture repositories -- real git checkouts, real manifests, a stand-in
project -- with `MATHLIB_PROJECT`/`MATHLIB_RECORD`/`LAKE_PACKAGES` pointed into a
temporary tree, so the assertions are about the script's own verdicts and not
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
        self.lake_packages = root / "opt" / "lake-packages"
        self.project.mkdir(parents=True)
        (self.project / "lean-toolchain").write_text(TOOLCHAIN + "\n", encoding="utf-8")
        olean = self.project / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean"
        olean.parent.mkdir(parents=True)
        olean.write_text("olean", encoding="utf-8")
        closure = self.project / ".lake" / "packages"
        self.batteries = commit(closure / "batteries", "Batteries")
        (closure / "batteries" / ".lake" / "build" / "lib" / "lean").mkdir(parents=True, exist_ok=True)
        # A Mathlib checkout carries its own manifest, pinning its closure; it does
        # not list itself, which is why the image's project is the one the check
        # reads for everything except mathlib.
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
        git(self.project, "add", "lean-toolchain", "lake-manifest.json")
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
                "LAKE_PACKAGES": str(self.lake_packages),
                "PYTHON": "python3",
            },
        )


@pytest.fixture
def image(tmp_path: Path) -> Image:
    return Image(tmp_path / "image")


def test_the_project_is_linked_in_the_directory_the_lakefile_declares(image):
    """A pin the image carries is linked; the manifest the checkout published is not touched."""
    repository = image.checkout("lean-categories", {"mathlib": image.revision})
    result = image.run()
    assert result.returncode == 0, result.stderr
    link = repository / ".lake" / "packages" / "mathlib"
    assert link.is_symlink(), result.stdout + result.stderr
    assert link.resolve() == image.project.resolve()
    assert json.loads((repository / "lake-manifest.json").read_text())["packages"][0]["rev"] == image.revision


def test_mathlibs_closure_is_the_projects_and_is_linked_too(image):
    """The closure resolves from the one project, not from a copy per checkout."""
    repository = image.checkout(
        "lean-categories", {"mathlib": image.revision, "batteries": image.batteries}
    )
    result = image.run()
    assert result.returncode == 0, result.stderr
    link = repository / ".lake" / "packages" / "batteries"
    assert link.is_symlink(), result.stdout + result.stderr
    assert link.resolve() == (image.project / ".lake" / "packages" / "batteries").resolve()


def test_a_package_no_one_carries_is_fetched_into_one_clone_per_revision(image):
    """checkdecls is neither Mathlib's nor a checkout's: one clone, shared by its pins."""
    # A real repository, so the fetch is exercised rather than described.
    third_party = image.root / "upstream" / "checkdecls"
    revision = commit(third_party, "Checkdecls")
    repository = image.checkout("lean-categories", {"mathlib": image.revision})
    lean_project(
        repository,
        {"mathlib": image.revision, "checkdecls": revision},
        ".lake/packages",
    )
    (repository / "lake-manifest.json").write_text(
        json.dumps(
            {
                "version": "1.1.0",
                "packagesDir": ".lake/packages",
                "packages": [
                    {"name": "mathlib", "type": "git", "url": "https://example.invalid/mathlib4",
                     "rev": image.revision},
                    {"name": "checkdecls", "type": "git", "url": str(third_party), "rev": revision},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = image.run()
    assert result.returncode == 0, result.stderr
    clone = image.lake_packages / f"checkdecls@{revision}"
    assert clone.is_dir(), result.stdout + result.stderr
    assert git(clone, "rev-parse", "HEAD") == revision
    link = repository / ".lake" / "packages" / "checkdecls"
    assert link.is_symlink() and link.resolve() == clone.resolve(), result.stdout + result.stderr
    # A second run reuses the clone instead of fetching it again.
    again = image.run()
    assert again.returncode == 0, again.stderr
    assert "FETCH" not in again.stdout


def test_a_pin_the_image_does_not_carry_is_reported_not_failed(image):
    """The image's own run reports a checkout that lags; it does not fail for it.

    Holding a Lean repository to the image is that repository's CI
    (lean-categories#118, lean-cas-dsl#90), so the image build logs the two
    revisions and carries on.
    """
    other = "b" * 40
    repository = image.checkout("lean-cas-dsl", {"mathlib": other})
    result = image.run()
    assert result.returncode == 0, result.stderr
    assert (
        f"note: {repository} pins mathlib at {other} and the image carries {image.revision}"
        in result.stdout
    ), result.stdout
    assert "does not follow the image" in result.stdout
    assert "1 checkout pin(s) do not follow it" in result.stdout
    assert not result.stderr.strip(), result.stderr
    assert not (repository / ".lake" / "packages" / "mathlib").exists(), (
        "a disagreeing pin must not be linked to the image's revision"
    )


def test_no_second_toolchain(image):
    """A checkout on another Lean release is reported, and no toolchain is installed."""
    repository = image.checkout(
        "lean-old", {"mathlib": image.revision}, toolchain="leanprover/lean4:v4.33.0"
    )
    result = image.run()
    assert result.returncode == 0, result.stderr
    assert (
        f"note: {repository} pins toolchain leanprover/lean4:v4.33.0 and the image has {TOOLCHAIN}"
        in result.stdout
    ), result.stdout
    assert "1 checkout pin(s) do not follow it" in result.stdout


def test_a_stale_link_is_removed_when_the_pin_moves(image):
    """A link left from an earlier run must not serve another revision silently."""
    repository = image.checkout("lean-late", {"mathlib": image.revision})
    assert image.run().returncode == 0
    link = repository / ".lake" / "packages" / "mathlib"
    assert link.is_symlink()
    lean_project(repository, {"mathlib": "c" * 40}, ".lake/packages")
    result = image.run()
    assert result.returncode == 0, result.stderr
    assert not link.is_symlink(), result.stdout + result.stderr


def test_a_project_at_another_revision_is_a_failed_image_not_a_warning(image):
    """The record names one revision, the tree is at another: a broken image."""
    image.checkout("lean-categories", {"mathlib": image.revision})
    moved = commit(image.project, "moved")
    # The build resolved what the record names, and the tree is somewhere else.
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


def test_no_lean_checkout_is_reported_rather_than_passing_quietly(image):
    result = image.run("--dry-run")
    assert result.returncode == 0, result.stderr
    assert "no Lean checkout" in result.stdout


def test_a_build_with_no_project_resolves_the_head_and_records_it(image, tmp_path):
    """The branch a full build runs: resolve the head, and record what was resolved.

    Network and Lean are not available here, so `elan` and `lake` are stand-ins that
    report success and leave the olean `lake build Mathlib` would have written. What
    this asserts is the script's own sequencing -- the head it resolved is the
    revision checked out, the toolchain is the one that revision pins, and the record
    is what the environment check reads -- which is what a broken build would get
    wrong and a green one would not.
    """
    upstream = tmp_path / "mathlib4"
    revision = commit(upstream, "Mathlib")
    (upstream / "lean-toolchain").write_text(TOOLCHAIN + "\n", encoding="utf-8")
    (upstream / "lake-manifest.json").write_text(
        json.dumps({"version": "1.1.0", "packagesDir": ".lake/packages", "packages": []}),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(upstream), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(upstream), "commit", "--quiet", "-m", "project"], check=True)
    revision = git(upstream, "rev-parse", "HEAD")

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in {
        "elan": "#!/bin/sh\nexit 0\n",
        "lake": (
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  \"build Mathlib\") mkdir -p .lake/build/lib/lean && : > .lake/build/lib/lean/Mathlib.olean ;;\n"
            "esac\n"
            "exit 0\n"
        ),
    }.items():
        stub = stubs / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    project = image.root / "fresh" / "mathlib"
    record = image.root / "fresh" / "lean-image.json"
    checkout = image.repos / "lean-categories"
    checkout.mkdir()
    lean_project(checkout, {"mathlib": revision}, ".lake/packages")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(image.repos)],
        capture_output=True, text=True, check=False,
        env={
            "PATH": f"{stubs}:/usr/bin:/bin",
            "MATHLIB_PROJECT": str(project),
            "MATHLIB_RECORD": str(record),
            "MATHLIB_REPOSITORY": str(upstream),
            "LAKE_PACKAGES": str(image.lake_packages),
            "PYTHON": "python3",
            "ELAN_HOME": str(tmp_path / "elan"),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    recorded = json.loads(record.read_text(encoding="utf-8"))
    assert recorded["revision"] == revision, recorded
    assert recorded["master_head_at_resolution"] == revision, recorded
    assert recorded["toolchain"] == TOOLCHAIN, recorded
    assert recorded["project"] == str(project), recorded
    assert git(project, "rev-parse", "HEAD") == revision
    # And the checkout is bound to the project it just resolved.
    link = checkout / ".lake" / "packages" / "mathlib"
    assert link.is_symlink() and link.resolve() == project.resolve(), result.stdout + result.stderr


CHECK = REPOSITORY / "docker" / "research-environment-check.py"
BLOCK_START = "# ---- the image's one shared Lean project (sage#13)"
BLOCK_END = 'print(f"import Mathlib in {project}: {elaborated.splitlines()[-1]}")'



def lean_block(project: Path, record: Path, repos: Path, elan_settings: Path) -> str:
    """The Lean block of the image's check, with the image's paths pointed at a fixture.

    Taken out of the real file rather than copied, so what runs here is the code the
    image runs; only the five absolute paths it names are rewritten.
    """
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index(BLOCK_START):text.index(BLOCK_END) + len(BLOCK_END)]
    for original, replacement in (
        ('Path("/opt/lean-image.json")', f'Path("{record}")'),
        ('Path("/opt/mathlib")', f'Path("{project}")'),
        ('Path("/opt/elan/settings.toml")', f'Path("{elan_settings}")'),
        ('Path("/repos")', f'Path("{repos}")'),
        ('"/opt/mathlib"', f'"{project}"'),
        ('"/repos"', f'"{repos}"'),
    ):
        block = block.replace(original, replacement)
    # No path constant may still name the image: comments and messages may.
    constants = [
        line for line in block.splitlines()
        if 'Path("/opt' in line or '"//opt' in line
    ]
    assert not constants, constants
    return block


def run_check(image: Image, stubs: Path, *arguments: str) -> subprocess.CompletedProcess:
    settings = image.root / "opt" / "elan" / "settings.toml"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(f'default_toolchain = "{TOOLCHAIN}"\n', encoding="utf-8")
    harness = image.root / "check-lean.py"
    harness.write_text(
        "import json, os, subprocess, sys, tempfile\nfrom pathlib import Path\n"
        + lean_block(image.project, image.record, image.repos, settings),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(harness), *arguments],
        capture_output=True, text=True, check=False,
        env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(image.root)},
    )


def fake_lean(stubs: Path) -> Path:
    """`lake` and `elan` that answer what the image's own toolchain would answer."""
    stubs.mkdir(exist_ok=True)
    (stubs / "lake").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "env" ] && [ "$2" = "lean" ]; then\n'
        '  case "$3" in\n'
        '    ""|--version) echo "Lean (version 4.36.0-rc2, x86_64-unknown-linux-gnu)" ;;\n'
        '    *) echo "Nat.add_comm : ∀ (a b : Nat), a + b = b + a" ;;\n'
        "  esac\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (stubs / "elan").write_text(
        "#!/bin/sh\necho \"#check (Nat.add_comm : ∀ a b : Nat, a + b = b + a)\"\n"
        "echo \"Nat.add_comm : ∀ (a b : Nat), a + b = b + a\"\n",
        encoding="utf-8",
    )
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    return stubs


def test_the_checks_lean_block_validates_the_images_own_project(image, tmp_path):
    image.checkout("lean-categories", {"mathlib": image.revision})
    result = run_check(image, fake_lean(tmp_path / "stubs"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"the shared Lean project: mathlib {image.revision[:12]}" in result.stdout
    assert f"lake env lean --version in {image.project}" in result.stdout
    assert f"lake build Mathlib in {image.project}: exit 0" in result.stdout
    assert f"import Mathlib in {image.project}: Nat.add_comm" in result.stdout
    assert "lean-categories" not in result.stdout, "the check no longer reads the checkouts"
    assert not result.stderr.strip(), result.stderr


def test_a_lagging_checkout_is_not_the_images_failure(image, tmp_path):
    """Item 2: a repository that lags fails in its own CI, never in the image's run."""
    other = "d" * 40
    image.checkout("lean-cas-dsl", {"mathlib": other})
    result = run_check(image, fake_lean(tmp_path / "stubs"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "does not follow" not in result.stdout + result.stderr
    assert other not in result.stdout + result.stderr


def test_the_removed_flag_is_no_longer_accepted(image, tmp_path):
    result = run_check(image, fake_lean(tmp_path / "stubs"), "--allow-lagging-lean-checkouts")
    assert result.returncode != 0
    assert "unknown argument" in result.stderr, result.stderr


def test_a_project_whose_record_disagrees_with_the_tree_fails_the_check(image, tmp_path):
    """The check validates what the image carries, and a broken project is a failure."""
    moved = commit(image.project, "moved")
    assert moved != image.revision
    result = run_check(image, fake_lean(tmp_path / "stubs"))
    assert result.returncode != 0, result.stdout
    assert image.revision in result.stderr, result.stderr
