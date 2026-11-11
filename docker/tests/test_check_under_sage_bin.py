"""The check, run through $SAGE_BIN, reads its launcher from its own tree.

The Dockerfile runs the check as ``RUN "$SAGE_BIN" docker/research-environment-check.py``.
Under ``sage``, ``__file__`` is the sage runner's own module path
(``site-packages/sage/all.py``), not the check's path, so a file read relative to
``__file__`` pointed into site-packages and the image build died at

    FileNotFoundError: [Errno 2] No such file or directory:
    '/sage/.venv/lib/python3.14/site-packages/sage/gap-launcher.sh'

(image run 42948264723, ``docker/research-environment-check.py`` line 128). The
check takes its own path from ``sys.argv[0]`` instead, which the sage runner
forwards, so the launcher is read from beside the check wherever the check is
run from.

This test runs the check the way the Dockerfile runs it -- through
``/sage/.venv/bin/sage``, in the image, from ``/sage`` -- through the
repository's own runner (``docker/sage-image.py``), which gives the guest its
own ``/proc``; a PRoot run with the host's ``/proc`` breaks the check's earlier
libgap-linkage assertion with host-prefixed paths, before the launcher read.

    SAGE_IMAGE_ROOTFS=~/sage-image/rootfs pytest docker/tests/test_check_under_sage_bin.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
RUNNER = REPOSITORY / "docker" / "sage-image.py"
BOUND = 600


def test_the_check_reads_its_launcher_from_its_own_tree_under_sage_bin():
    """The launcher read does not point into site-packages under $SAGE_BIN.

    The image and the runner are prerequisites the test asserts, not ones it
    skips on: an image that is missing is a failure.
    """
    assert ROOTFS.is_dir(), (
        f"no unpacked image at {ROOTFS}: fetch one "
        "(docker/sage-image.py fetch, or SAGE_IMAGE_ROOTFS to point at one)"
    )
    assert shutil.which("bwrap"), (
        "bubblewrap is needed to run the image with its own /proc; install it"
    )
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run",
         "--bind", f"{REPOSITORY}:/work", "--env", "HOME=/root", "--chdir", "/sage",
         "--", "/sage/.venv/bin/sage", "/work/docker/research-environment-check.py"],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )
    # The defect: under $SAGE_BIN, __file__ is the sage runner's module, so the
    # launcher read pointed into site-packages and the build died there. The
    # check's own path comes from sys.argv[0], which the sage runner forwards,
    # so the launcher is read from beside the check.
    assert "site-packages/sage/gap-launcher.sh" not in result.stderr, (
        "the check, run through $SAGE_BIN, read its launcher from wherever Sage "
        "set __file__ to:\n"
        f"{result.stderr[-2000:]}"
    )
