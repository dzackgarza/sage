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

A git source of the lock is not always a repository of the image. Image run
43535626055 (develop ``828086aa8f``) stopped its publish at the check on
``microsoft-python-type-stubs``, a declared test dependency that ``uv.lock``
takes from ``github.com/dzackgarza/python-type-stubs`` and that
``docker/research-repositories.txt`` does not name: no build checks it out, so
the /repos checkout and the recorded head the block demanded of every git source
are things no build writes. The block now classifies each source by that list --
the install's own input -- and holds a dependency to the commit ``uv.lock`` pins,
which is what ``uv sync --frozen`` installs it at. The fixture here is the one
that run's lock was: ``microsoft-python-type-stubs`` installed from a git commit
and no record line, and the last test here is against this tree's own
``uv.lock`` and ``docker/research-repositories.txt`` rather than a made-up pair.

    pytest docker/tests/test_research_revision_record.py
"""

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
CHECK = REPOSITORY / "docker" / "research-environment-check.py"
BLOCK_START = "# The record: the revision of every research package this image actually carries."
BLOCK_NEXT = "# sage-categories runs its finite-category engine on GAP releases allocated to"
SANDBOX_PYTHON = "/usr/bin/python3"
BOUND = 120

# A dependency the image installs from a git URL that is not one of its research
# repositories: uv.lock carries it, no build checks it out under /repos, and
# /sage/.research-revisions records no head for it (sage#37).
STUBS_URL = "https://github.com/dzackgarza/python-type-stubs"
STUBS_PINNED = "f7474b297f8764ad96db2e0ce9c0a7bd27fd8d59"


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


def git_source(text: str) -> tuple[str, str]:
    """A lock git source split the way the block splits it: repository, commit."""
    location = text.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0]
    return location.rsplit("/", 1)[-1].removesuffix(".git"), text.rsplit("#", 1)[-1]


def git_location(text: str) -> str:
    """A lock git source's URL as the block classifies it: query and commit dropped."""
    return text.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0].rstrip("/").removesuffix(".git")


def research_locations() -> set[str]:
    """The URLs the install checks out, normalised as the block normalises the lock's."""
    return {
        location.rstrip("/").removesuffix(".git")
        for location in (
            line.strip()
            for line in (REPOSITORY / "docker" / "research-repositories.txt").read_text(
                encoding="utf-8"
            ).splitlines()
        )
        if location and not location.startswith("#")
    }


def installed_as_a_git_wheel(work: Path, name: str, commit: str, url: str) -> None:
    """A distribution the sandbox's interpreter finds, installed from a git commit.

    ``work`` is on the interpreter's path, so a ``.dist-info`` directory there is
    what ``importlib.metadata.distribution`` answers with -- the metadata a git
    install leaves, ``direct_url.json`` carrying the commit it was installed from.
    """
    directory = work / f"{name.replace('-', '_')}-0.0.0.dist-info"
    directory.mkdir(exist_ok=True)
    (directory / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.0\n", encoding="utf-8",
    )
    (directory / "direct_url.json").write_text(
        json.dumps(
            {
                "url": url,
                "vcs_info": {"vcs": "git", "commit_id": commit, "requested_revision": "main"},
            }
        ),
        encoding="utf-8",
    )


class FakeImage:
    """The tree the block reads: /sage with its lock and record, /repos with checkouts.

    Two repositories stand for the shapes of git source the lock carries.
    ``research`` is the one whose package name differs from its repository's;
    ``sage-categories`` contributes two packages, one from a subdirectory of the
    checkout. Each repository's main branch has moved past the commit the
    fixture lock holds, as every research main had when sage#24 was filed. The
    third shape is ``microsoft-python-type-stubs``, a git source the image
    installs and never checks out (sage#37).
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

        (self.sage / "docker").mkdir()
        (self.sage / "docker" / "research-repositories.txt").write_text(
            "# The repositories the install checks out under /repos.\n"
            "https://github.com/dzackgarza/research\n"
            "https://github.com/dzackgarza/sage-categories\n",
            encoding="utf-8",
        )
        (self.sage / "uv.lock").write_text(
            f"""
[[package]]
name = 'dzack-research'
source = {{ git = 'https://github.com/dzackgarza/research#{self.research_locked}' }}

[[package]]
name = 'microsoft-python-type-stubs'
source = {{ git = '{STUBS_URL}?rev=main#{STUBS_PINNED}' }}

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
        installed_as_a_git_wheel(self.work, "microsoft-python-type-stubs", STUBS_PINNED, STUBS_URL)
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
        return run_block(self.sage, self.repos, self.work)


def run_block(sage: Path, repos: Path, work: Path) -> subprocess.CompletedProcess:
    """The record block, run where /sage and /repos are this fixture's.

    The sandbox gives the block the absolute paths it reads -- /sage/uv.lock,
    /sage/.research-revisions, /sage/docker/research-repositories.txt,
    /repos/<repository> -- by binding this fixture over them in a throwaway mount
    namespace; everything else it needs is the host's /usr, read-only. /work is the
    interpreter's own directory, so a distribution written there -- what a git
    install of a dependency leaves -- is one ``importlib.metadata`` finds.
    """
    probe = subprocess.run(
        [SANDBOX_PYTHON, "-c", "import tomllib"], capture_output=True, check=False,
    )
    assert probe.returncode == 0, (
        f"{SANDBOX_PYTHON} cannot import tomllib, which the record block reads the lock with"
    )
    harness = work / "harness.py"
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
            "--ro-bind", str(sage), "/sage",
            "--ro-bind", str(repos), "/repos",
            "--ro-bind", str(work), "/work",
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


@requires_bwrap
def test_a_dependency_outside_the_image_is_held_to_the_locks_commit_only(image: FakeImage):
    """sage#37: a git source the image never checks out is no failed obligation.

    microsoft-python-type-stubs is uv.lock's source of a declared test
    dependency, and no repository of docker/research-repositories.txt. The image
    installs it from its URL and records no head for it, so the check must hold
    it to the lock's commit and nothing else -- the image run that held it to a
    checkout and a record stopped a publish on a repository the image does not
    carry.
    """
    assert not (image.repos / "python-type-stubs").exists()
    result = image.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        f"dependency microsoft-python-type-stubs: {STUBS_PINNED} "
        "(git wheel, the lock's commit)"
    ) in result.stdout, result.stdout
    assert "records no head for python-type-stubs" not in result.stderr, result.stderr


@requires_bwrap
def test_a_dependency_installed_at_another_commit_than_the_lock_pins_fails(image: FakeImage):
    """The lock is what a dependency's provenance is, so a moved install fails."""
    moved = "0" * 40
    installed_as_a_git_wheel(image.work, "microsoft-python-type-stubs", moved, STUBS_URL)
    result = image.run()
    assert result.returncode != 0, result.stdout
    assert moved in result.stderr, result.stderr
    assert STUBS_PINNED in result.stderr, result.stderr


class RealImage:
    """The block against this repository's own lock and repository list (sage#37).

    The fixture lock is the one every build of the image syncs and the list is
    the one ``docker/install-research-repositories.sh`` reads, so what the block
    classifies here is what the image classifies: a checkout per research
    repository the lock sources, at the head the install records, and one
    dependency from a git URL the image does not carry.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sage = root / "sage"
        self.repos = root / "repos"
        self.work = root / "run"
        (self.sage / "docker").mkdir(parents=True)
        self.repos.mkdir()
        self.work.mkdir()

        self.research = research_locations()
        self.sources: dict[str, dict[str, str]] = {}
        for package in tomllib.loads(
            (REPOSITORY / "uv.lock").read_text(encoding="utf-8")
        )["package"]:
            source = package.get("source", {}).get("git")
            if source is None:
                continue
            repository, pinned = git_source(source)
            self.sources[package["name"]] = {
                "repository": repository,
                "pinned": pinned,
                "location": git_location(source),
            }
        self.dependency = {
            name: source
            for name, source in self.sources.items()
            if source["location"] not in self.research
        }
        self.heads = {
            repository: commit(self.checkout(repository), "the head this build resolved")
            for repository in sorted(
                {source["repository"] for source in self.sources.values()}
                - {source["repository"] for source in self.dependency.values()}
            )
        }
        shutil.copy(
            REPOSITORY / "docker" / "research-repositories.txt",
            self.sage / "docker" / "research-repositories.txt",
        )
        shutil.copy(REPOSITORY / "uv.lock", self.sage / "uv.lock")
        (self.sage / ".research-revisions").write_text(
            "".join(f"{name} {head}\n" for name, head in sorted(self.heads.items())),
            encoding="utf-8",
        )
        for name, source in self.dependency.items():
            installed_as_a_git_wheel(self.work, name, source["pinned"], source["location"])

    def checkout(self, name: str) -> Path:
        directory = self.repos / name
        subprocess.run(["git", "init", "--quiet", str(directory)], check=True)
        git(directory, "config", "user.email", "fixture@example.com")
        git(directory, "config", "user.name", "fixture")
        return directory

    def run(self) -> subprocess.CompletedProcess:
        return run_block(self.sage, self.repos, self.work)


def test_the_lock_carries_a_git_source_that_is_not_a_research_repository() -> None:
    """The condition sage#37 was filed under, out of the repository's own files.

    The recorded revision of a research repository is the head the install
    checked out; a dependency the image takes from a git URL has no such head,
    and treating the two alike is what failed the publish.
    """
    sources = {
        git_location(package["source"]["git"])
        for package in tomllib.loads(
            (REPOSITORY / "uv.lock").read_text(encoding="utf-8")
        )["package"]
        if package.get("source", {}).get("git")
    }
    outside = sources - research_locations()
    assert outside, "the lock sources only research repositories again; sage#37's case is gone"


@requires_bwrap
def test_the_repositorys_own_lock_holds_with_its_dependency_outside_the_image(tmp_path: Path):
    """The block against develop's own uv.lock and research-repositories.txt."""
    image = RealImage(tmp_path)
    assert image.dependency, sorted(image.sources)
    result = image.run()
    assert result.returncode == 0, result.stdout + result.stderr
    for name, source in image.sources.items():
        if source["location"] in image.research:
            head = image.heads[source["repository"]]
            assert f"research {name}: {head} (checkout, installed {head})" in result.stdout, (
                result.stdout + result.stderr
            )
        else:
            assert (
                f"dependency {name}: {source['pinned']} (git wheel, the lock's commit)"
                in result.stdout
            ), result.stdout + result.stderr
