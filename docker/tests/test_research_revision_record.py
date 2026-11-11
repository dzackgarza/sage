"""The check's record block holds each research checkout to the head the build resolved.

Every image build resolves each research repository's main head when it starts,
installs the repository from its ``/repos`` checkout at that head, and records
the head in ``/sage/.research-revisions``, one ``<name> <commit>`` per line
(``docker/install-research-repositories.sh`` writes it; ``docker/
SAGE-ENVIRONMENT.md`` names it as what a consumer reads in the image). The
check's record block still held each checkout to the commit ``uv.lock`` names
-- only where the last relock left it -- so image run 42957383777 (develop
``8dadb73e45``) stopped at ``docker/research-environment-check.py`` line 470 on
a checkout that was exactly where the install had put it:

    AssertionError: ('dzack-research', 'c7d48f1211…', 'dbf178cf30…')

A lock commit is not the source of truth for a research package: the image
installs from the checkout at the head, so the recorded head is. This test is
red against that tree -- the first test fails with the assertion above -- and
green once the block holds each checkout to the record.

The block runs here out of the real check file, in a bubblewrap sandbox whose
``/sage`` and ``/repos`` are a fixture: a lock that pins each repository at a
commit its main branch has moved past, real git checkouts, and the record the
install writes. ``sage-categories`` stands for the lock's subdirectory shape --
two packages, one from a ``?subdirectory=`` of the checkout's URL -- whose
repository the block must read from the URL's path, dropping the query, to find
the checkout at all. What is pinned is the check's own verdicts: the line it
prints for each package, the failure it raises for a checkout that is not at
the recorded head, and the failure it raises for a source with no recorded
head -- which the current check passes whenever the checkout happens to sit at
the locked commit, the very agreement sage#24 retires.

    pytest docker/tests/test_research_revision_record.py
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
CHECK = REPOSITORY / "docker" / "research-environment-check.py"
BLOCK_START = "# The record: the revision of every research package this image actually carries."
BLOCK_NEXT = "# sage-categories runs its finite-category engine on GAP releases allocated to"
SANDBOX_PYTHON = "/usr/bin/python3"
BOUND = 120


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def commit(directory: Path, message: str) -> str:
    """A real commit in a real repository, as the fixture origin makes them.

    The file carries the repository's name, so two repositories do not make the
    same commit: a block that mixed them up would fail loudly instead of
    passing on matching hashes.
    """
    (directory / f"{directory.name}-{message.replace(' ', '-')}.lean").write_text(
        f"-- {directory.name}: {message} --\n", encoding="utf-8",
    )
    git(directory, "add", "-A")
    git(directory, "commit", "--quiet", "-m", message)
    return git(directory, "rev-parse", "HEAD")


def record_block() -> str:
    """The check's record block, as the image runs it."""
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index(BLOCK_START):text.index(BLOCK_NEXT)]
    assert "uv.lock" in block, block[:200]
    return block


class FakeImage:
    """The tree the block reads: /sage with its lock and record, /repos with checkouts.

    Two repositories stand for the two shapes of git source the lock carries.
    ``research`` is the one whose package name differs from its repository's;
    ``sage-categories`` contributes two packages, one from a subdirectory of the
    checkout. Each repository's main branch has moved past the commit the
    fixture lock holds, as every research main had when sage#24 was filed.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sage = root / "sage"
        self.repos = root / "repos"
        self.work = root / "run"
        self.sage.mkdir(parents=True)
        self.repos.mkdir()
        self.work.mkdir()

        research = self.repository("research")
        self.research_locked = commit(research, "where the last relock left it")
        self.research_head = commit(research, "the head this build resolved")
        self.research_moved = commit(research, "pushed past the head this build resolved")
        categories = self.repository("sage-categories")
        self.categories_locked = commit(categories, "where the last relock left it")
        self.categories_head = commit(categories, "the head this build resolved")

        (self.sage / "uv.lock").write_text(
            f"""
[[package]]
name = 'dzack-research'
source = {{ git = 'https://github.com/dzackgarza/research#{self.research_locked}' }}

[[package]]
name = 'python-flint'
version = '0.9.0'

[[package]]
name = 'sage-categories'
source = {{ git = 'https://github.com/dzackgarza/sage-categories#{self.categories_locked}' }}

[[package]]
name = 'sage-categories-homotopy'
source = {{ git = 'https://github.com/dzackgarza/sage-categories?subdirectory=native%2Fhomotopy-python#{self.categories_locked}' }}
""",
            encoding="utf-8",
        )
        self.at_heads()

    def repository(self, name: str) -> Path:
        """A checkout under /repos, as the install leaves one: a real git tree."""
        directory = self.repos / name
        subprocess.run(["git", "init", "--quiet", str(directory)], check=True)
        git(directory, "config", "user.email", "fixture@example.com")
        git(directory, "config", "user.name", "fixture")
        return directory

    def at_heads(self) -> None:
        """Each checkout at its head, and the record naming those heads."""
        git(self.repos / "research", "checkout", "--quiet", self.research_head)
        git(self.repos / "sage-categories", "checkout", "--quiet", self.categories_head)
        self.record(f"research {self.research_head}\n"
                    f"sage-categories {self.categories_head}\n")

    def without_a_head_recorded_for(self, name: str) -> None:
        """The checkouts at the locked commits, and a record that names no head
        for one repository: a build that recorded every repository but one."""
        git(self.repos / "research", "checkout", "--quiet", self.research_locked)
        git(self.repos / "sage-categories", "checkout", "--quiet", self.categories_locked)
        self.record(f"sage-categories {self.categories_locked}\n")
        assert name == "research"

    def record(self, text: str) -> None:
        (self.sage / ".research-revisions").write_text(text, encoding="utf-8")

    def run(self) -> subprocess.CompletedProcess:
        """The record block, run where /sage and /repos are this fixture's.

        The sandbox gives the block the absolute paths it reads -- /sage/uv.lock,
        /sage/.research-revisions, /repos/<repository> -- by binding this
        fixture over them in a throwaway mount namespace; everything else it
        needs is the host's /usr, read-only.
        """
        probe = subprocess.run(
            [SANDBOX_PYTHON, "-c", "import tomllib"], capture_output=True, check=False,
        )
        assert probe.returncode == 0, (
            f"{SANDBOX_PYTHON} cannot import tomllib, which the record block reads the lock with"
        )
        harness = self.work / "harness.py"
        harness.write_text(
            "import subprocess\nfrom pathlib import Path\n" + record_block(),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                "bwrap",
                "--tmpfs", "/",
                "--ro-bind", "/usr", "/usr",
                "--ro-bind", "/etc", "/etc",
                "--proc", "/proc",
                "--dev", "/dev",
                "--tmpfs", "/tmp",
                "--ro-bind", str(self.sage), "/sage",
                "--ro-bind", str(self.repos), "/repos",
                "--ro-bind", str(self.work), "/work",
                "--symlink", "usr/bin", "/bin",
                "--symlink", "usr/lib", "/lib",
                "--symlink", "usr/lib64", "/lib64",
                "--symlink", "usr/sbin", "/sbin",
                "--clearenv",
                "--setenv", "PATH", "/usr/bin:/bin",
                "--", SANDBOX_PYTHON, "/work/harness.py",
            ],
            capture_output=True, text=True, check=False, timeout=BOUND,
        )


requires_bwrap = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="needs bubblewrap to give the block a /sage and /repos of its own",
)


@pytest.fixture
def image(tmp_path: Path) -> FakeImage:
    return FakeImage(tmp_path)


@requires_bwrap
def test_each_checkout_is_held_to_the_recorded_head_and_the_print_names_it(image: FakeImage):
    """The checkout at the head the record names passes, and names that head.

    The locked commit is nowhere in the print: a lock commit is not the source
    of truth for a research package (sage#24).
    """
    result = image.run()
    assert result.returncode == 0, result.stdout + result.stderr
    for name, head in (
        ("dzack-research", image.research_head),
        ("sage-categories", image.categories_head),
        ("sage-categories-homotopy", image.categories_head),
    ):
        assert f"research {name}: {head} (checkout, installed {head})" in result.stdout, (
            result.stdout + result.stderr
        )
    assert image.research_locked not in result.stdout, result.stdout
    assert image.categories_locked not in result.stdout, result.stdout


@requires_bwrap
def test_a_checkout_moved_off_the_recorded_head_fails_naming_both(image: FakeImage):
    """A checkout that is not at the recorded head fails, naming both revisions."""
    git(image.repos / "research", "checkout", "--quiet", image.research_moved)
    result = image.run()
    assert result.returncode != 0, result.stdout
    assert image.research_moved in result.stderr, result.stderr
    assert image.research_head in result.stderr, result.stderr


@requires_bwrap
def test_a_source_with_no_recorded_head_fails_even_at_the_locked_commit(image: FakeImage):
    """No recorded head for a source is a failed obligation, not a lock question.

    The checkout sits at the commit the lock holds, so the check that held
    checkouts to the lock passes this image; the record is the source of truth,
    and a source it names no head for fails the check.
    """
    image.without_a_head_recorded_for("research")
    result = image.run()
    assert result.returncode != 0, result.stdout
    assert "records no head for research" in result.stderr, result.stderr
