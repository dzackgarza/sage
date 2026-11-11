"""kernel_info() reads GAP's roots record across the breaks GAP prints (sage#20, sage#27).

GAP ends a printed line that reaches its line width with a backslash and breaks
it there, and the roots record begins with ``$HOME/.gap/``, so a long enough
``HOME`` used to split it: ``sage.interfaces.gap`` then failed at import with
``ValueError: too many values to unpack (expected 3)`` (sage#20). The fix
(``src/sage/libs/gap/kernel_info.py``, landed at 2e8306e94cca) joins the
continuation lines, so the length of ``HOME`` cannot decide whether the
interface imports.

This test runs the image as built -- no binds, no source-tree substitution: an
image that ships the defect fails it. It runs the image's own GAP with ``HOME``
set past GAP's line width, takes GAP's own output (the roots record is broken
at the width, and carries ``$HOME/.gap/``), and imports ``sage.interfaces.gap``
under that ``HOME``: the import succeeds, and the roots record contains
``$HOME/.gap/``. The image and the runner are the test's own prerequisites: a
missing one is a failure, not a skip (sage#27). The image without the fix dies
at ``ValueError: too many values to unpack (expected 3)`` -- the red run,
recorded in the commit message; the image of run 42933294270 (21faab6bc2,
which contains 2e8306e94c) is the green run.

    PROOT=/path/to/proot-x86_64 pytest docker/tests/test_kernel_info_continuations.py
    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_kernel_info_continuations.py
"""

import os
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
PROOT = Path(os.environ.get("PROOT", Path.home() / ".udocker" / "bin" / "proot-x86_64"))
BOUND = 600

# A HOME long enough that GAP's line width breaks the roots record: the
# launcher's own HOME (/workspace/nucleus/work/home, 33 characters) is grown
# past the width, so GAP itself prints the record in two lines.
LONG_HOME = "/workspace/nucleus/work/home" + "/pad" * 20


def launch(home: str, command: list) -> subprocess.CompletedProcess:
    """A command in the image as built, under the HOME the launcher gives it."""
    return subprocess.run(
        [str(PROOT), "-R", str(ROOTFS), "-b", "/proc", "-b", "/dev", "-b", "/sys",
         "-w", "/", "/usr/bin/env",
         "PATH=/sage/.venv/bin:/usr/local/bin:/usr/bin:/bin", f"HOME={home}", *command],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )


def test_kernel_info_imports_under_a_home_past_gaps_line_width():
    """The import of sage.interfaces.gap succeeds, and the roots hold $HOME/.gap/.

    The image and the runner are prerequisites the test asserts, not ones it
    skips on (sage#27): an image that is missing is a failure.
    """
    assert ROOTFS.is_dir(), (
        f"no unpacked image at {ROOTFS}: fetch one "
        "(docker/sage-image.py fetch, or SAGE_IMAGE_ROOTFS to point at one)"
    )
    assert PROOT.is_file(), f"no PRoot at {PROOT}: install one, or set PROOT"
    # The image's own GAP, under that HOME, prints the records GAP prints: the
    # roots record is broken at the width, and GAP's own output is what the
    # parser must read.
    gap = launch(
        LONG_HOME,
        ["/sage/.venv/bin/gap", "-q", "--nointeract", "--systemfile",
         "/sage/.venv/lib/python3.14/site-packages/sage/ext_data/gap/kernel-info.g"],
    )
    assert gap.returncode == 0, (gap.returncode, gap.stdout[-2000:], gap.stderr[-2000:])
    assert "\\\n" in gap.stdout, "GAP did not break the roots record at its line width"
    assert f"{LONG_HOME}/.gap/" in gap.stdout.replace("\\\n", ""), (
        "GAP's own roots record does not carry $HOME/.gap/"
    )
    # The import of the interface, under the same HOME, in the image as built.
    imported = launch(
        LONG_HOME,
        ["/sage/.venv/bin/python", "-c", "import sage.interfaces.gap; print('ok')"],
    )
    assert imported.returncode == 0, (
        imported.returncode, imported.stdout[-2000:], imported.stderr[-2000:]
    )
    # The roots record the image's own parser returns contains $HOME/.gap/.
    roots = launch(
        LONG_HOME,
        ["/sage/.venv/bin/python", "-c",
         "from sage.libs.gap.kernel_info import kernel_info; print(kernel_info()[2])"],
    )
    assert roots.returncode == 0, (roots.returncode, roots.stdout[-2000:], roots.stderr[-2000:])
    assert f"{LONG_HOME}/.gap/" in roots.stdout, roots.stdout
