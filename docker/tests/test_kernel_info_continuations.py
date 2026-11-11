"""kernel_info() reads GAP's roots record across the breaks GAP prints (sage#20, sage#27).

GAP ends a printed line that reaches its line width with a backslash and breaks
it there, and the roots record begins with ``$HOME/.gap/``, so a long enough
``HOME`` used to split it: ``sage.interfaces.gap`` then failed at import with
``ValueError: too many values to unpack (expected 3)`` (sage#20). The fix
(``src/sage/libs/gap/kernel_info.py``, landed at 2e8306e94cca) joins the
continuation lines, so the length of ``HOME`` cannot decide whether the
interface imports.

This test runs the image's own GAP with ``HOME`` set past GAP's line width and
takes GAP's own output (the roots record is broken at the width), then imports
``sage.interfaces.gap`` under that ``HOME``: the import succeeds, and the roots
record contains ``$HOME/.gap/``. Before the fix (``2e8306e94cca^``) the same
import dies at ``ValueError: too many values to unpack (expected 3)`` -- that
failure was run on the pre-fix code and is recorded in the commit message of
this change.

The two files the fix changed that the import needs are bound over the image's
copies (``sage/interfaces/gap_workspace.py`` and ``sage/libs/gap/kernel_info.py``,
new in the fix): the image's own sage predates the fix, and its compiled
``sage/libs/gap/util.so`` still embeds the pre-fix inline split, so only the
fixed chain -- both files are pure Python -- reads the record across the break.
``src/sage/interfaces/gap.py`` is unchanged by the fix and needs no bind.

    PROOT=/path/to/proot-x86_64 pytest docker/tests/test_kernel_info_continuations.py
    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_kernel_info_continuations.py
"""

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
PROOT = Path(os.environ.get("PROOT", Path.home() / ".udocker" / "bin" / "proot-x86_64"))
# The two files the fix changed that the import needs, bound over the image's
# copies: gap_workspace.py (the fix changed where it reads kernel_info from)
# and kernel_info.py (new in the fix, the parser that joins the break).
FIXED_FILES = [
    REPOSITORY / "src" / "sage" / "interfaces" / "gap_workspace.py",
    REPOSITORY / "src" / "sage" / "libs" / "gap" / "kernel_info.py",
]
GUEST_FIXED = [
    "sage/.venv/lib/python3.14/site-packages/sage/interfaces/gap_workspace.py",
    "sage/.venv/lib/python3.14/site-packages/sage/libs/gap/kernel_info.py",
]
BOUND = 600

# A HOME long enough that GAP's line width breaks the roots record: the
# launcher's own HOME (/workspace/nucleus/work/home, 33 characters) is grown
# past the width, so GAP itself prints the record in two lines.
LONG_HOME = "/workspace/nucleus/work/home" + "/pad" * 20


def launch(home: str, command: list, fixed: bool) -> subprocess.CompletedProcess:
    """A command in the image, under the HOME the launcher gives it.

    With ``fixed``, the two files the fix changed are bound over the image's
    copies, so the import runs the fixed chain; without them the image's own
    pre-fix sage is what runs. ``command`` is the argv env runs.
    """
    binds = []
    if fixed:
        for i in range(2):
            binds += ["-b", f"{FIXED_FILES[i]}:/{GUEST_FIXED[i]}"]
    return subprocess.run(
        [str(PROOT), "-R", str(ROOTFS), "-b", "/proc", "-b", "/dev", "-b", "/sys", *binds,
         "-w", "/", "/usr/bin/env",
         "PATH=/sage/.venv/bin:/usr/local/bin:/usr/bin:/bin", f"HOME={home}", *command],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )


requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or not PROOT.is_file(),
    reason="needs an unpacked image (SAGE_IMAGE_ROOTFS) and PRoot to run it",
)


@requires_image
def test_kernel_info_imports_under_a_home_past_gaps_line_width():
    """The import of sage.interfaces.gap succeeds, and the roots hold $HOME/.gap/."""
    # The image's own GAP, under that HOME, prints the records GAP prints: the
    # roots record is broken at the width, and GAP's own output is what the
    # parser must read.
    gap = launch(
        LONG_HOME,
        ["/sage/.venv/bin/gap", "-q", "--nointeract", "--systemfile",
         "/sage/.venv/lib/python3.14/site-packages/sage/ext_data/gap/kernel-info.g"],
        fixed=False,
    )
    assert gap.returncode == 0, (gap.returncode, gap.stdout[-2000:], gap.stderr[-2000:])
    assert "\\\n" in gap.stdout, "GAP did not break the roots record at its line width"
    assert f"{LONG_HOME}/.gap/" in gap.stdout.replace("\\\n", ""), (
        "GAP's own roots record does not carry $HOME/.gap/"
    )
    # The import of the interface, under the same HOME, with the fix bound over
    # the image's copies: the fix reads the record across the break, so the
    # import succeeds and the roots record contains $HOME/.gap/.
    imported = launch(
        LONG_HOME,
        ["/sage/.venv/bin/python", "-c", "import sage.interfaces.gap; print(\"ok\")"],
        fixed=True,
    )
    assert imported.returncode == 0, (
        imported.returncode, imported.stdout[-2000:], imported.stderr[-2000:]
    )
    # The roots record the fixed parser returns contains $HOME/.gap/.
    roots = launch(
        LONG_HOME,
        ["/sage/.venv/bin/python", "-c",
         "from sage.libs.gap.kernel_info import kernel_info; print(kernel_info()[2])"],
        fixed=True,
    )
    assert roots.returncode == 0, (roots.returncode, roots.stdout[-2000:], roots.stderr[-2000:])
    assert f"{LONG_HOME}/.gap/" in roots.stdout, roots.stdout
