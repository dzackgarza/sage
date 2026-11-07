"""The 6JRR step, executed in the supported image from a directory that is not its corpus (sage#17).

`sage#17` is a working-directory defect, and a test that reads the workflow's text cannot see it:
a `cd` into the checkout would satisfy any string check while leaving the real behaviour
unproven. This test therefore runs the step's own `run:` block, extracted from the workflow, in
the published image with the working directory set to `/tmp` — a directory that is not the
lattice-database checkout, exactly the situation the job is in, where `${{ github.workspace }}`
is a sage-extensions checkout.

`latticedb`'s CLI takes `root: Root = Path()`, and `Path()` is the process's working directory,
so a step that does not name `--root` looks for `families.yaml` there:

    FileNotFoundError: [Errno 2] No such file or directory: 'families.yaml'

That is what run 42362483952 printed at 12:28:20Z, three seconds in, before computing anything.
The step must get past that load; once it does it spends the whole 20-minute deadline computing
6JRR, so this test bounds it and reads the outcome from *how* the run ended: a corpus that is not
found ends in about three seconds with exit 1 and that message, while a corpus that is found is
still computing when the window closes.

This repository's pytest configuration names test files `*_test.py` and lists `docker` among
`norecursedirs`, so these tests are run by explicit path, as the others in this directory are.

Run it against a copy of an earlier workflow to see the failure:

    CERTIFY_WORKFLOW=/path/to/research-environment-image.yml pytest docker/tests/test_certify_step_in_the_image.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOW = Path(
    os.environ.get("CERTIFY_WORKFLOW", REPOSITORY / ".github" / "workflows" / "research-environment-image.yml")
)
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
RUNNER = REPOSITORY / "docker" / "sage-image.py"
STEP = "Certify lattice-database card 6JRR"
WINDOW = int(os.environ.get("CERTIFY_WINDOW", "45"))


def step_body() -> str:
    """The named step's `run:` block, dedented, as the shell is given it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = f"- name: {STEP}"
    assert text.count(marker) == 1, f"{STEP!r} occurs {text.count(marker)} times in {WORKFLOW}"
    block = text.split(marker, 1)[1].split("run: |", 1)[1]
    lines = []
    for line in block.splitlines():
        if line.strip() and not line.startswith("        "):
            break
        lines.append(line)
    return "\n".join(line[8:] for line in lines) + "\n"


@pytest.mark.skipif(not ROOTFS.is_dir(), reason="no unpacked image at SAGE_IMAGE_ROOTFS")
@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap is not installed")
def test_the_step_loads_the_corpus_from_wherever_it_stands() -> None:
    body = step_body()
    assert "latticedb certify" in body, body
    finished = subprocess.run(
        [
            sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run",
            "--chdir", "/tmp", "--",
            "timeout", "-s", "KILL", str(WINDOW), "/bin/sh", "-c", body,
        ],
        capture_output=True, text=True, timeout=WINDOW + 240, check=False,
    )
    output = finished.stdout + finished.stderr
    assert "families.yaml" not in output, (
        "the step let the CLI read its corpus from the working directory:\n" + output[-3000:]
    )
    assert finished.returncode != 1, output[-3000:]
    assert finished.returncode in (124, 137), (
        f"the step ended ({finished.returncode}) instead of still computing, so it is not shown to "
        "have found its corpus and gone on:\n" + output[-3000:]
    )
