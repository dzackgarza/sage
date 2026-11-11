"""The install step checks out each repository's main head, not a stored commit (sage#24).

Every image build resolves each git source of ``[tool.uv.sources]`` to its main
head at build time and installs it from the ``/repos`` checkout at that head, so
the code the image runs is the code that repository's main branch carried when
the build started. The commit ``uv.lock`` holds is only where the last relock
left it: a checkout held there leaves the image behind the repository's main
(``sage-extensions`` was 291 commits behind when sage#24 was filed), and the
``relock: true`` dispatch that moved the lock was a second path rather than the
default one.

The real script runs here, over a fixture lock that pins a commit the fixture
origin's main branch has already moved past, a fixture repositories list, a
fixture venv, and stubs for the tools the script calls after the checkout. The
assertions are about the script's own verdicts -- which commit each checkout
ends at, and what the image records -- and not about a reimplementation of them.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "docker" / "install-research-repositories.sh"


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def commit(directory: Path, message: str) -> str:
    """A real commit in a real repository, as the fixture origin makes them."""
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(directory)], check=True)
    git(directory, "config", "user.email", "fixture@example.com")
    git(directory, "config", "user.name", "fixture")
    (directory / f"{message}.lean").write_text(f"-- {message}\n", encoding="utf-8")
    git(directory, "add", "-A")
    git(directory, "commit", "--quiet", "-m", message)
    return git(directory, "rev-parse", "HEAD")


class Install:
    """The tree the script reads: a lock, a list, a venv, and stubbed tools."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sage = root / "sage"
        self.repos = root / "repos"
        self.bin = root / "bin"
        self.calls = root / "calls"

        # A fixture origin whose main branch has moved past the commit the
        # fixture lock holds: the locked commit is the first one, and the head
        # is whatever the origin's main branch ends on after the metadata
        # commit the verify block needs.
        self.origin = root / "origin" / "sage-extensions"
        self.locked = commit(self.origin, "first")
        (self.origin / "second.lean").write_text("-- second\n", encoding="utf-8")
        git(self.origin, "add", "-A")
        git(self.origin, "commit", "--quiet", "-m", "second")
        (self.origin / "pyproject.toml").write_text(
            '[project]\nname = "sage-extensions"\nversion = "0.1.0"\n', encoding="utf-8",
        )
        git(self.origin, "add", "-A")
        git(self.origin, "commit", "--quiet", "-m", "metadata")
        self.head = git(self.origin, "rev-parse", "HEAD")
        assert self.head != self.locked

        self.url = f"file://{self.origin}"
        self.sage.mkdir(parents=True)
        (self.sage / "uv.lock").write_text(
            f"\n[[package]]\nname = 'sage-extensions'\n"
            f"source = {{ git = '{self.url}#{self.locked}' }}\n",
            encoding="utf-8",
        )
        docker = self.sage / "docker"
        docker.mkdir()
        (docker / "research-repositories.txt").write_text(f"{self.url}\n", encoding="utf-8")
        # The real provisioning script is not under test here; a stub records
        # the call so the assertion can see what the script handed it.
        stub = docker / "provision-lean-packages.sh"
        stub.write_text(
            f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"{self.calls}\"\n", encoding="utf-8",
        )
        stub.chmod(0o755)
        venv_bin = self.sage / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        venv_bin.joinpath("python").symlink_to("/opt/math/bin/python3")
        gap = venv_bin / "gap"
        gap.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gap %s\\n' \"$*\" >> \"{self.calls}\"\n",
            encoding="utf-8",
        )
        gap.chmod(0o755)

        # The GAP step cds into the checkout before it starts; the stub never
        # reads what is there, but the directory must exist.
        (self.repos / "sage-categories").mkdir(parents=True)

        self.bin.mkdir()
        for name in ("uv", "just"):
            self.stub(name)
        self.calls.write_text("", encoding="utf-8")

    def stub(self, name: str) -> None:
        """A tool the script calls after the checkout: it records the call."""
        body = "#!/usr/bin/env bash\n"
        if name == "uv":
            body += (
                'if [ "$1" = "pip" ] && [ "$2" = "list" ]; then\n'
                '    printf "Package\\n-\\nsage-extensions\\n"\n'
                "    exit 0\n"
                "fi\n"
            )
        body += f"printf '{name} %s\\n' \"$*\" >> \"{self.calls}\"\n"
        path = self.bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def run(self) -> subprocess.CompletedProcess:
        """The script as the image build runs it, over the fixture tree."""
        environment = dict(os.environ)
        environment.update({
            "PATH": f"{self.bin}:{environment['PATH']}",
            "SAGE_ROOT": str(self.sage),
            "REPOSITORIES_ROOT": str(self.repos),
        })
        return subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True, check=False, env=environment,
        )

    def run_with_revisions(self, revisions: str) -> subprocess.CompletedProcess:
        """The script with the heads the workflow resolved, passed as the build argument."""
        environment = dict(os.environ)
        environment.update({
            "PATH": f"{self.bin}:{environment['PATH']}",
            "SAGE_ROOT": str(self.sage),
            "REPOSITORIES_ROOT": str(self.repos),
            "RESEARCH_REVISIONS": revisions,
        })
        return subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True, check=False, env=environment,
        )


@pytest.fixture
def install(tmp_path: Path) -> Install:
    return Install(tmp_path / "fixture")


def test_the_install_step_checks_out_the_current_head(install: Install):
    """The checkout lands on the origin's head, not on the commit the lock holds."""
    result = install.run()
    assert result.returncode == 0, result.stderr
    checkout = install.repos / "sage-extensions"
    assert git(checkout, "rev-parse", "HEAD") == install.head, result.stdout + result.stderr
    assert git(checkout, "rev-parse", "HEAD") != install.locked


def test_the_head_check_passes_after_checkout_on_a_fresh_root(install: Install):
    """The check compares the checked-out commit with the head the workflow resolved.

    On a fresh root the checkouts do not exist before the install runs, so the
    check must run after the checkout loop (sage#24's defect 1). The script's
    own checkout is the head the workflow resolved, so the check passes; a
    mismatch between the two names both commits and fails the build.
    """
    # The head the workflow resolved is the fixture origin's head.
    result = install.run_with_revisions(f"sage-extensions={install.head}")
    assert result.returncode == 0, result.stderr
    # A mismatch: the passed-in head is the fixture's LOCKED commit, not its
    # head, so the check fails and names both commits.
    mismatch = install.run_with_revisions(f"sage-extensions={install.locked}")
    assert mismatch.returncode != 0
    assert f"{install.locked}" in mismatch.stderr or "is at" in mismatch.stderr


def test_the_image_records_the_commit_of_each_repository_it_installed(install: Install):
    """The record names the head the checkout was installed at (sage#24)."""
    result = install.run()
    assert result.returncode == 0, result.stderr
    revisions = (install.sage / ".research-revisions").read_text(encoding="utf-8")
    assert f"sage-extensions {install.head}" in revisions, revisions
    assert install.locked not in revisions, revisions
