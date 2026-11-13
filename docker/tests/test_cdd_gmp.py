"""cdd.gmp in the image: pycddlib's exact-rational backend (sage#34).

sage-indefinite-port's facet-orbit route imports ``cdd.gmp``
(``facet_orbits.py:154``, reached from ``lorentzian_cells.py``), and the
published image's interpreter carried no pycddlib at all: sage-extensions run
43445243634 (``coble-kernel-plane-rows.yml``, the O(T_Co) plane row of
sage-extensions#390) ended there with ``ModuleNotFoundError: No module named
'cdd'``. ``uv.lock`` had no pycddlib entry either.

One source tree builds two modules, and which one the route needs matters:
pycddlib's ``setup.py`` builds ``cdd`` against ``libcdd`` -- doubles -- and
``cdd.gmp`` against ``libcddgmp`` and ``libgmp`` -- exact rationals. The image
ships both libraries as part of Sage's own package metadata (``libcdd-dev``,
``libcdd.so.0`` and ``libcddgmp.so.0`` under ``/usr/lib/x86_64-linux-gnu``),
and the PyPI distribution of 3.0.2 carries Windows wheels and an sdist only,
so the lock's install is a source build in the image: a GMP build, and the one
whose ``cdd.gmp`` is linked against the image's own library.

This test runs in the image, through the repository's own runner, so the
process starts with the environment the image declares for itself. It imports
``sage.all`` first, as the port's route does, then computes with ``cdd.gmp``:
the cone of ``[[1,0,0],[1,1,0],[1,0,1]]`` in inequality representation, whose
generators must come back as ``Fraction`` -- a doubles backend cannot.

    pytest docker/tests/test_cdd_gmp.py
    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_cdd_gmp.py
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

# The cone's generators are fixed: the vertex (-1,-1) and the rays (1,0), (0,1).
COMMAND = """
import sage.all
import cdd
import cdd.gmp
from fractions import Fraction

matrix = cdd.gmp.matrix_from_array(
    [[1, 0, 0], [1, 1, 0], [1, 0, 1]], rep_type=cdd.RepType.INEQUALITY,
)
out = cdd.gmp.copy_output(cdd.gmp.polyhedron_from_matrix(matrix))
expected = [
    [Fraction(1), Fraction(-1), Fraction(-1)],
    [Fraction(0), Fraction(1), Fraction(0)],
    [Fraction(0), Fraction(0), Fraction(1)],
]
assert out.array == expected, out.array
print("cdd.gmp", cdd.gmp.__file__)
print("generators", out.array)
"""


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
def test_cdd_gmp_computes_with_exact_rationals() -> None:
    """The port's import resolves to the venv's module and computes in Fractions."""
    result = in_the_image(COMMAND)
    assert result.returncode == 0, (result.returncode, result.stdout[-2000:], result.stderr[-2000:])
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    module = lines[0].split(" ", 1)[1]
    assert module.startswith("/sage/.venv/"), (
        f"cdd.gmp is not the venv's module (sage#34): {module}"
    )
    assert "Fraction" in lines[1], (result.stdout, result.stderr)
