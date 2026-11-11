"""One libflint in the image: python-flint and Sage in one process (sage#25).

The image carries two libflints: python-flint's wheel vendors one (FLINT 3.6.0,
``site-packages/python_flint.libs/libflint-6839011d.so.24.0.0``), and Sage
loads the system one (FLINT 3.1.3, ``libflint-dev``, ``libflint.so.19``). In
one process that imports ``sage.all`` and then computes ``fmpz_mat(...).det()``,
the vendored build's symbols bind to the other build's library and the
interpreter ends with SIGSEGV -- exit 139, at ``libflint.so.19``'s
``fmpz_set``, called from python-flint's ``fmpz_mat`` module
(lattice-database#29 found it in the published image).

The repair is one libflint: python-flint is built against the flint that Sage
uses, which python-flint 0.9's build docs accept -- FLINT 3.0-3.6
(https://pypi.org/project/python-flint/0.9.0, the compatibility table and the
build-from-source instructions) -- so the venv's wheel is replaced by a source
build against the system flint.

This test runs the acceptance command in the image, through the repository's
own runner, so the process starts with the environment the image declares for
itself rather than the host's -- the condition the issue states ("a process in
the image"), and the one a bare PRoot invocation with an inherited PATH does
not give: without the image's PATH, `import sage.all` dies on a missing `gap`
before any flint call runs, a red for the wrong reason. It is red until the
image is rebuilt with the source-built python-flint, which is how the
gap-workspace test (sage#19) was introduced too: what is asserted is the
image's own state, not the working tree's.

    pytest docker/tests/test_one_libflint.py
    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_one_libflint.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY / "docker" / "sage-image.py"
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
BOUND = 300

COMMAND = "import sage.all; from flint import fmpz_mat; print(fmpz_mat([[2,1],[1,2]]).det())"

# The acceptance process itself dies at the det() before it could report its
# own maps, so this one repeats its imports and reports the libflints it maps:
# measured, the same two the acceptance process maps. After the repair both
# loads are the system library and the count is one.
MAPS = (
    "import sage.all, flint; "
    "print('\\n'.join(sorted(set(line.split()[-1] for line in open('/proc/self/maps') "
    "if 'libflint' in line))))"
)


def in_the_image(code: str) -> subprocess.CompletedProcess:
    """`python -c <code>` in the image, with the environment it declares for itself."""
    return subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run", "--chdir", "/tmp", "--",
         "/sage/.venv/bin/python", "-c", code],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )


requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or shutil.which("bwrap") is None,
    reason="needs an unpacked image (SAGE_IMAGE_ROOTFS) and bubblewrap to run it",
)


@requires_image
def test_one_libflint_in_one_process() -> None:
    """import sage.all; from flint import fmpz_mat; det([[2,1],[1,2]]) is 3."""
    result = in_the_image(COMMAND)
    assert result.returncode == 0, (result.returncode, result.stdout[-2000:], result.stderr[-2000:])
    assert result.stdout.strip().splitlines()[-1] == "3", (result.stdout, result.stderr)

    maps = in_the_image(MAPS)
    assert maps.returncode == 0, (maps.stdout, maps.stderr)
    mapped = [line for line in maps.stdout.splitlines() if line.strip()]
    assert len(mapped) == 1, (
        f"the process maps {len(mapped)} libflints, and one is the whole point (sage#25): "
        f"{' ; '.join(mapped)}"
    )
