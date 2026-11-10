"""One libflint in the image: python-flint and Sage in one process (sage#25).

The image carries two libflints: python-flint's wheel vendors one (24.0.0,
``site-packages/python_flint.libs/libflint-6839011d.so.24.0.0``), and Sage
loads the system one (19.0.0, ``libflint-dev``). In one process that imports
``sage.all`` and then computes ``fmpz_mat(...).det()``, the vendored build's
symbols bind to the other build's and the interpreter ends with SIGSEGV
(lattice-database#29 found it in the published image).

The repair is one libflint: python-flint is built against the flint that Sage
uses, which python-flint 0.9's build docs accept -- FLINT 3.0-3.6
(https://pypi.org/project/python-flint/0.9.0) -- so the venv's wheel is
replaced by a source build against the system flint.

This test runs the acceptance command in the unpacked image. It is red until
the image is rebuilt with the source-built python-flint, which is how the
gap-workspace test (sage#19) was introduced too: what is asserted is the
image's own state, not the working tree's.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
PROOT = Path(os.environ.get("PROOT", Path.home() / ".udocker" / "bin" / "proot-x86_64"))
BOUND = 300

COMMAND = "import sage.all; from flint import fmpz_mat; print(fmpz_mat([[2,1],[1,2]]).det())"

requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or not PROOT.is_file(),
    reason="needs an unpacked image (SAGE_IMAGE_ROOTFS) and PRoot to run it",
)


@requires_image
def test_one_libflint_in_one_process() -> None:
    """import sage.all; from flint import fmpz_mat; det([[2,1],[1,2]]) is 3."""
    result = subprocess.run(
        [str(PROOT), "-R", str(ROOTFS), "-b", "/proc", "-b", "/dev", "-b", "/sys",
         "/sage/.venv/bin/python", "-c", COMMAND],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stdout[-2000:], result.stderr[-2000:])
    assert result.stdout.strip().splitlines()[-1] == "3", (result.stdout, result.stderr)
