"""The check's Lean section holds each checkout to the shared project it resolves (sage#13).

The image carries one shared Lean project -- mathlib4 at the head of its master
branch, on the toolchain that revision pins, with its whole dependency closure
built inside it -- and every Lean checkout under ``/repos`` resolves Mathlib and
its closure from that project: the provisioning sets each checkout's manifest
entries for mathlib and every package of the shared project's manifest to the
shared project's revisions, and links its packages directory to the project's
built copies. The recorded revision is the head the build resolved at build
start, not a committed pin (owner, 2026-11-11): a fixed revision in a
checkout's manifest is not served, and the check compares none.

The check elaborates ``import Mathlib`` through each checkout's own Lake
environment, so a checkout that does not build against the shared Mathlib fails
the image's check loudly, naming the checkout and the revision -- sage#13's
acceptance. The failure today is a bare ``CalledProcessError``: ``lake env lean``
exiting non-zero in the checkout raises before the loud message is reached, and
names neither the checkout nor the revision:

    CalledProcessError: Command '['lake', 'env', 'lean', '/tmp/mathlib-import-…']'
    returned non-zero exit status 1.

This runs the section out of the real check file, in a bubblewrap sandbox whose
``/opt`` and ``/repos`` are a fixture: the shared project with its record and its
toolchain, and real git checkouts whose ``lake`` is a stub that answers for the
project and for one checkout and fails in another. What is pinned is the check's
own verdicts: the lines it prints for a checkout that follows, and the failure it
raises for one that does not.

    pytest docker/tests/test_shared_lean_project_check.py
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
CHECK = REPOSITORY / "docker" / "research-environment-check.py"
BLOCK_START = "# ---- the image's one shared Lean project (sage#13)"
BLOCK_NEXT = "# ---- the document toolchain the project sites build with (sage#22)"
SANDBOX_PYTHON = "/usr/bin/python3"
TOOLCHAIN = "leanprover/lean4:v4.36.0-rc2"
BOUND = 120


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def commit(directory: Path, message: str) -> str:
    """A real commit in a real repository, as the fixture project makes them."""
    (directory / f"{message.replace(' ', '-')}.lean").write_text(
        f"-- {message} --\n", encoding="utf-8",
    )
    git(directory, "add", "-A")
    git(directory, "commit", "--quiet", "-m", message)
    return git(directory, "rev-parse", "HEAD")


def record_block() -> str:
    """The check's Lean section, as the image runs it."""
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index(BLOCK_START):text.index(BLOCK_NEXT)]
    assert "lake env" in block, block[:200]
    return block


class FakeImage:
    """The tree the section reads: /opt with the shared project and its record, /repos with the checkouts.

    The shared project is a real git repository at the recorded revision, with
    the toolchain that revision pins, a manifest pinning one package, Mathlib's
    olean and that package's own checkout at its pin with its build directory --
    the state the provisioning leaves. Each checkout carries the manifest the
    binding resolved: mathlib at the recorded revision, the shared package at
    its pin, and an extra package the shared project does not carry at the
    checkout's own pin, which the binding leaves alone.
    """

    def __init__(self, root: Path, checkouts: tuple[str, ...]) -> None:
        self.root = root
        self.work = root / "run"
        self.opt = root / "opt"
        self.repos = root / "repos"
        self.work.mkdir(parents=True)
        self.opt.mkdir()
        self.repos.mkdir()

        project = self.opt / "mathlib"
        project.mkdir()
        (project / "lean-toolchain").write_text(TOOLCHAIN + "\n", encoding="utf-8")
        olean = project / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean"
        olean.parent.mkdir(parents=True)
        olean.write_text("olean", encoding="utf-8")
        batteries = project / ".lake" / "packages" / "batteries"
        subprocess.run(["git", "init", "--quiet", str(batteries)], check=True)
        git(batteries, "config", "user.email", "fixture@example.com")
        git(batteries, "config", "user.name", "fixture")
        self.batteries = commit(batteries, "batteries")
        (batteries / ".lake" / "build" / "lib" / "lean").mkdir(parents=True)
        (project / "lake-manifest.json").write_text(
            "{\n"
            '  "version": "1.1.0",\n'
            '  "packagesDir": ".lake/packages",\n'
            '  "packages": [\n'
            "    {\n"
            '      "name": "batteries",\n'
            '      "type": "git",\n'
            '      "url": "https://example.invalid/batteries",\n'
            f'      "rev": "{self.batteries}"\n'
            "    }\n"
            "  ]\n"
            "}\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "--quiet", str(project)], check=True)
        git(project, "config", "user.email", "fixture@example.com")
        git(project, "config", "user.name", "fixture")
        git(project, "add", "-A")
        git(project, "commit", "--quiet", "-m", "mathlib")
        self.revision = git(project, "rev-parse", "HEAD")
        (self.opt / "lean-image.json").write_text(
            "{\n"
            f'  "project": "/opt/mathlib",\n'
            '  "repository": "https://github.com/leanprover-community/mathlib4",\n'
            f'  "revision": "{self.revision}",\n'
            f'  "master_head_at_resolution": "{self.revision}",\n'
            f'  "toolchain": "{TOOLCHAIN}",\n'
            '  "cache": "lake exe cache get (official Mathlib cache)",\n'
            '  "resolved": "2026-11-11T00:00:00Z"\n'
            "}\n",
            encoding="utf-8",
        )
        elan = self.opt / "elan"
        elan.mkdir()
        (elan / "settings.toml").write_text(
            f'default_toolchain = "{TOOLCHAIN}"\n', encoding="utf-8",
        )

        for name in checkouts:
            directory = self.repos / name
            directory.mkdir()
            (directory / "lake-manifest.json").write_text(
                "{\n"
                '  "version": "1.1.0",\n'
                '  "packagesDir": ".lake/packages",\n'
                '  "packages": [\n'
                "    {\n"
                '      "name": "mathlib",\n'
                '      "type": "git",\n'
                '      "url": "https://github.com/leanprover-community/mathlib4",\n'
                f'      "rev": "{self.revision}"\n'
                "    },\n"
                "    {\n"
                '      "name": "batteries",\n'
                '      "type": "git",\n'
                '      "url": "https://example.invalid/batteries",\n'
                f'      "rev": "{self.batteries}"\n'
                "    },\n"
                "    {\n"
                '      "name": "extra-package",\n'
                '      "type": "git",\n'
                '      "url": "https://example.invalid/extra-package",\n'
                '      "rev": "e33a000000000000000000000000000000000000"\n'
                "    }\n"
                "  ]\n"
                "}\n",
                encoding="utf-8",
            )

    def run(self) -> subprocess.CompletedProcess:
        """The Lean section, run where /opt and /repos are this fixture's.

        The sandbox gives the section the absolute paths it reads --
        /opt/lean-image.json, /opt/mathlib, /opt/elan/settings.toml, /repos --
        by binding this fixture over them in a throwaway mount namespace;
        everything else it needs is the host's /usr, read-only. The `lake` the
        section calls is a stub on the sandbox's PATH: it answers for the
        project and for one checkout, and fails in any other, which is the
        checkout that does not build against the shared Mathlib.
        """
        stubs = self.work / "stubs"
        stubs.mkdir()
        (stubs / "lake").write_text(
            "#!/bin/bash\n"
            "if [ \"$1\" = \"env\" ] && [ \"$2\" = \"lean\" ] && [ \"$3\" = \"--version\" ]; then\n"
            "    printf 'Lean (version 4.36.0-rc2, x86_64-unknown-linux-gnu)\\n'\n"
            "    exit 0\n"
            "fi\n"
            "if [ \"$1\" = \"build\" ] && [ \"$2\" = \"Mathlib\" ]; then\n"
            "    exit 0\n"
            "fi\n"
            "if [ \"$1\" = \"env\" ] && [ \"$2\" = \"lean\" ]; then\n"
            "    case \"${PWD}\" in\n"
            "        /opt/mathlib|/repos/lean-follower)\n"
            "            printf 'Nat.add_comm : ∀ a b : Nat, a + b = b + a\\n'\n"
            "            exit 0\n"
            "            ;;\n"
            "        *)\n"
            "            printf 'error: lake env lean failed in %s: the checkout does not "
            "build against the shared Mathlib\\n' \"${PWD}\" >&2\n"
            "            exit 1\n"
            "            ;;\n"
            "    esac\n"
            "fi\n"
            "printf 'unhandled: %s\\n' \"$*\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        (stubs / "lake").chmod(0o755)
        harness = self.work / "harness.py"
        harness.write_text(
            "import subprocess, sys, tempfile\nfrom pathlib import Path\n" + record_block(),
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
                "--ro-bind", str(self.opt), "/opt",
                "--ro-bind", str(self.repos), "/repos",
                "--ro-bind", str(self.work), "/work",
                "--symlink", "usr/bin", "/bin",
                "--symlink", "usr/lib", "/lib",
                "--symlink", "usr/lib64", "/lib64",
                "--symlink", "usr/sbin", "/sbin",
                "--clearenv",
                "--setenv", "PATH", "/work/stubs:/usr/bin:/bin",
                "--", SANDBOX_PYTHON, "/work/harness.py",
            ],
            capture_output=True, text=True, check=False, timeout=BOUND,
        )


requires_bwrap = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="needs bubblewrap to give the section a /opt and /repos of its own",
)


@pytest.fixture
def image(tmp_path: Path) -> FakeImage:
    return FakeImage(tmp_path, ("lean-follower", "lean-laggard"))


@requires_bwrap
def test_a_checkout_resolved_at_the_shared_project_passes(image: FakeImage):
    """The checkout that follows elaborates, and the check prints its import.

    The recorded revision is the head the build resolved, not a committed pin:
    the check holds the checkout to nothing its repository published, only to
    the Mathlib the image carries (sage#13).
    """
    shutil.rmtree(image.repos / "lean-laggard")
    result = image.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "import Mathlib in /repos/lean-follower: " in result.stdout, result.stdout
    assert f"mathlib {image.revision[:12]} on {TOOLCHAIN}" in result.stdout, result.stdout


@requires_bwrap
def test_a_checkout_that_does_not_build_fails_naming_the_checkout_and_the_revision(image: FakeImage):
    """A checkout that does not build fails the check, naming the checkout and the revision.

    The loud failure is the acceptance (sage#13): today the non-zero exit of
    `lake env lean` raises a bare `CalledProcessError` first, which names
    neither the checkout nor the revision the image carries.
    """
    result = image.run()
    assert result.returncode != 0, result.stdout
    assert "/repos/lean-laggard" in result.stderr, result.stderr
    assert image.revision in result.stderr, result.stderr
