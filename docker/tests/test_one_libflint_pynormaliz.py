"""One libflint in the image: pynormaliz and Sage in one process (sage#31).

pynormaliz's wheel vendors a Normaliz that vendors a libflint
(``site-packages/pynormaliz.libs/libflint-2d14cefb.so.22.0.0``, beside the
vendored ``libnormaliz``), and Sage loads the system one (FLINT 3.1.3,
``libflint-dev``, ``libflint.so.19``): the defect class of sage#25, from a
second wheel. Measured, in the image, a process that imports ``sage.all``
and ``PyNormaliz`` maps both:

    /sage/.venv/lib/python3.14/site-packages/pynormaliz.libs/libflint-2d14cefb.so.22.0.0
    /usr/lib/x86_64-linux-gnu/libflint.so.19.0.0

The repair is one libflint, and the pin that decides it: Sage's tree pins
Normaliz 3.11.1 (build/pkgs/normaliz) with pynormaliz 2.24
(build/pkgs/pynormaliz) as a pair, and pynormaliz 2.24's own source refuses
an older Normaliz -- ``NormalizModule.cpp`` asserts ``NMZ_RELEASE >= 31100``
-- while Debian trixie ships 3.10.4, against its own flint. So the image
builds the Normaliz Sage's package metadata pins into the venv, against the
system flint, and pynormaliz from source against that (its documented
build: Normaliz with headers, then
https://pypi.org/project/pynormaliz/ and PyNormaliz's README, which also
names the requirement the code asserts).

This test runs in the image, through the repository's own runner, so the
process starts with the environment the image declares for itself. It
computes the Hilbert basis of a non-unimodular cone -- [[1,0],[1,2]], whose
basis has a point that is not a ray -- with PyNormaliz and with Sage's own
``Cone``, asserts they agree, and reads the libflints the same process maps.
Unlike sage#25's acceptance command, this one survives in the defective
image, so one process does the computing and reports its own maps; the red
is the two it prints. Green is one: the system library Sage loads.

    pytest docker/tests/test_one_libflint_pynormaliz.py
    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_one_libflint_pynormaliz.py
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

# The Hilbert basis of the cone through (1,0) and (1,2) is (1,0), (1,1),
# (1,2): the middle point is in the cone but not in the monoid the rays
# generate, so both engines must compute it, not echo their input.
COMMAND = """
import sage.all
from PyNormaliz import Cone
from sage.geometry.cone import Cone as SageCone
normaliz = sorted(tuple(int(c) for c in v) for v in Cone(cone=[[1, 0], [1, 2]]).HilbertBasis())
sage = sorted(tuple(int(c) for c in v) for v in SageCone([(1, 0), (1, 2)]).Hilbert_basis())
assert normaliz == sage == [(1, 0), (1, 1), (1, 2)], (normaliz, sage)
print("hilbert basis", normaliz)
print("\\n".join(sorted(set(line.split()[-1] for line in open("/proc/self/maps") if "libflint" in line))))
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
def test_one_libflint_in_one_process() -> None:
    """PyNormaliz's Hilbert basis is Sage's, and the process maps one libflint."""
    result = in_the_image(COMMAND)
    assert result.returncode == 0, (result.returncode, result.stdout[-2000:], result.stderr[-2000:])
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert lines[0] == "hilbert basis [(1, 0), (1, 1), (1, 2)]", (result.stdout, result.stderr)

    mapped = lines[1:]
    assert len(mapped) == 1, (
        f"the process maps {len(mapped)} libflints, and one is the whole point (sage#31): "
        f"{' ; '.join(mapped)}"
    )
