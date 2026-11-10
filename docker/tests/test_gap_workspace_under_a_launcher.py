"""The ordinary GAP-interface call under a launcher that brings its own environment (sage#19).

The research project runs this image through PRoot over the unpacked filesystem, binds a
checkout at `/repo`, and inherits its own `PATH` and `HOME`; the image's environment — the one
a container runtime applies — never reaches the process. Under those conditions the ordinary
call `gap.Order(gap.SymmetricGroup(4))` has to save the workspace the interface starts GAP
from (`SaveWorkspace`, then `gap -L <workspace>`) and reuse it on the next call. It did not:
the workspace was named after the caller's `$HOME/.gap/`, so every `HOME` over one `DOT_SAGE`
wrote another 70 MB image of the same GAP instead of reusing the one already there, and a
caller whose `PATH` had no `$SAGE_LOCAL/bin` got `FileNotFoundError: 'gap'` before any
mathematics ran.

What is asserted: in the launcher's conditions — a fresh `DOT_SAGE`, a `PATH` without the
venv, a `HOME` of its own — the call returns 24, writes exactly one workspace, and a second
call from a *different* `HOME` reuses that file rather than writing a second one. Against the
image as published before the fix the two names differ, so this test is red until the image
carries this tree's `src/sage/interfaces/gap_workspace.py`.

Two deliberate scopes:

* the two files under test are the working tree's, bound over the image's copies. The image is
  rebuilt from them, and a test that could only run after the rebuild would say nothing while
  the fix is being written.
* the `gap` the caller's `PATH` resolves is this tree's `docker/gap-launcher.sh`, placed in a
  directory of the test's own. So what this test covers is the workspace the interface writes
  with a GAP that resolves through `PATH`; whether the *image* ships that launcher at
  `/usr/local/bin/gap` is the environment check's assertion
  (`docker/research-environment-check.py`), made where the image is built.

    pytest docker/tests/test_gap_workspace_under_a_launcher.py
    PROOT=/path/to/proot-x86_64 pytest docker/tests/test_gap_workspace_under_a_launcher.py
    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_gap_workspace_under_a_launcher.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
RUNNER = REPOSITORY / "docker" / "sage-image.py"
LAUNCHER = REPOSITORY / "docker" / "gap-launcher.sh"
PROOT = Path(os.environ.get("PROOT", Path.home() / ".udocker" / "bin" / "proot-x86_64"))
BOUND = 300
INSTALLED = "/sage/.venv/lib/python3.14/site-packages/sage/interfaces"
SOURCES = ("gap_workspace.py", "gap.py")

PROBE = r'''
import os
from sage.interfaces.gap import gap, WORKSPACE
print("workspace", os.path.basename(WORKSPACE))
print("order", gap.Order(gap.SymmetricGroup(4)))
print("inode", os.stat(WORKSPACE).st_ino)
'''


def environment(inside, kernel: str) -> list[str]:
    """What a PRoot launcher gives the process: its own PATH, HOME and cache."""
    return [f"PATH={inside}/bin:/usr/bin:/bin", f"HOME={inside}/{kernel}",
            f"DOT_SAGE={inside}/dot-sage", "PYTHONDONTWRITEBYTECODE=1"]


def launch(work: Path, kernel: str) -> subprocess.CompletedProcess:
    """The ordinary call in the image, with HOME=<work>/<kernel> and DOT_SAGE=<work>/dot-sage."""
    sources = [f"{REPOSITORY / 'src' / 'sage' / 'interfaces' / name}:{INSTALLED}/{name}"
               for name in SOURCES]
    if PROOT.is_file():
        # PRoot's -R already exposes the host's /tmp, so the work tree is used where it
        # is; a binding of it would have PRoot create the mount point in the image tree.
        inside = work
        command = [str(PROOT), "-R", str(ROOTFS), "-b", "/proc", "-b", "/dev", "-b", "/sys"]
        for binding in sources:
            command += ["-b", binding]
        command += ["-w", str(inside), "/usr/bin/env", *environment(inside, kernel),
                    "/sage/.venv/bin/python", str(inside / "probe.py")]
    else:
        # bubblewrap: the image's /tmp is a tmpfs, so the work tree is bound in.
        inside = Path("/work")
        command = [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run"]
        for binding in sources + [f"{work}:/work"]:
            command += ["--bind", binding]
        for entry in environment(inside, kernel):
            command += ["--env", entry]
        command += ["--chdir", str(inside), "--", "/sage/.venv/bin/python", str(inside / "probe.py")]
    return subprocess.run(command, capture_output=True, text=True, timeout=BOUND, check=False)


def result(finished: subprocess.CompletedProcess) -> dict:
    assert finished.returncode == 0, (finished.returncode, finished.stdout[-2000:], finished.stderr[-2000:])
    fields = dict(line.split(" ", 1) for line in finished.stdout.splitlines())
    assert fields["order"] == "24", (fields, finished.stderr[-2000:])
    return fields


requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or not (PROOT.is_file() or shutil.which("bwrap")),
    reason="needs an unpacked image (SAGE_IMAGE_ROOTFS) and PRoot or bubblewrap to run it",
)


@requires_image
def test_the_workspace_is_written_and_reused_across_homes() -> None:
    # A short work path on purpose.  This image's kernel_info() still cannot read the
    # roots GAP wraps at the 80th column, which a HOME of about 75 characters or more
    # produces; that is a second defect, measured and reported with sage#19, and it is
    # not this test's claim.  The launcher's own HOME is short too.
    work = Path(tempfile.mkdtemp(prefix="gapwork-", dir="/tmp"))
    try:
        (work / "home-a").mkdir()
        (work / "home-b").mkdir()
        (work / "bin").mkdir()
        launcher = work / "bin" / "gap"
        shutil.copy(LAUNCHER, launcher)
        launcher.chmod(0o755)
        (work / "probe.py").write_text(PROBE, encoding="utf-8")
        runner = "PRoot" if PROOT.is_file() else "the repository's own runner"
        print(f"launcher: {runner} over {ROOTFS}; PATH={work}/bin:/usr/bin:/bin; "
              f"sources from {REPOSITORY / 'src' / 'sage' / 'interfaces'}")

        first = result(launch(work, "home-a"))
        written = sorted(path.name for path in (work / "dot-sage" / "gap").glob("*workspace*"))
        assert written == [first["workspace"]], written
        second = result(launch(work, "home-b"))
        assert second["workspace"] == first["workspace"], (
            "the workspace name follows HOME, so every launcher writes another copy: "
            f"{first['workspace']} from home-a, {second['workspace']} from home-b"
        )
        assert second["inode"] == first["inode"], "the workspace was rewritten, not reused"
        assert len(written) == 1, written
        print(f"reused {first['workspace']} in {work / 'dot-sage' / 'gap'}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
