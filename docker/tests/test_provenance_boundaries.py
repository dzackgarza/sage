"""The T_Co step's provenance must verify both boundaries it straddles (image#15/#18).

That step runs inside the published image, but the job installs the workflow's own
sage-extensions checkout editable first (step 5), so **two** revisions are in play and they are
not the same observation:

* the image's provider, `/repos/sage-extensions`, which the image's `/sage/uv.lock` pins;
* the consumer checkout, `${{ github.workspace }}`, which the job deliberately tests in place of
  the image's copy.

A workspace checkout cannot stand in for the image provider, and a provenance line that reports
only one of them leaves the other unverified. This test runs the step's provenance block with the
provider imported from a workspace-style checkout and requires it to report both revisions and
still assert the image's own copy against the lock.

Run 42379122786 died here: the block treated `/__w/sage/sage` as if it were the image's copy and
`git -C` there answered 128. That condition is established from the run's own log -- the runner
adds `safe.directory /__w/sage/sage` on the *host* and creates the workspace `.git` there, so the
tree is foreign-owned inside the container, while `git -C /repos/...` succeeds in the same
container. This test cannot reproduce a foreign owner (the sandbox maps one uid), so it pins the
contract and not the ownership: both revisions reported, the image's copy asserted, and any
required revision that cannot be read fails the step.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOW = Path(os.environ.get("PROVENANCE_WORKFLOW", REPOSITORY / ".github" / "workflows" / "research-environment-image.yml"))
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
RUNNER = REPOSITORY / "docker" / "sage-image.py"
CHECKOUT = Path(os.environ.get("WORKSPACE_CHECKOUT", REPOSITORY / ".scratch" / "se-240c"))
STEP = "Construct T_Co and compute its O(T_Co) generators"
BOUND = 300


def provenance_block() -> str:
    """The step's provenance code, up to the T_Co construction."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for step in document["jobs"]["consumer-acceptance"]["steps"] if step.get("name") == STEP]
    assert len(steps) == 1, f"{STEP!r} appears {len(steps)} times"
    body = steps[0]["run"]
    assert "<<'PY'" in body, "the step no longer opens its provenance process with PY"
    heredoc = body.split("<<'PY'", 1)[1]
    lines = []
    for line in heredoc.splitlines()[1:]:
        if line.strip() == "PY":
            break
        lines.append(line)
    assert lines, "the provenance heredoc is empty"
    return "\n".join(lines) + "\n"


def run(binds: list[str], environment: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run", *binds,
         "--env", "HOME=/root", *environment, "--chdir", "/tmp", "--", "/sage/.venv/bin/python", "-"],
        input=provenance_block(), capture_output=True, text=True, timeout=BOUND, check=False,
    )


requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or shutil.which("bwrap") is None or not (CHECKOUT / ".git").exists(),
    reason="needs the image, bubblewrap, and a sage-extensions checkout (WORKSPACE_CHECKOUT)",
)


@requires_image
def test_the_image_provider_is_asserted_against_its_lock() -> None:
    finished = run([], [])
    output = finished.stdout + finished.stderr
    assert finished.returncode == 0, output[-3000:]
    assert "image checkout /repos/sage-extensions at" in output and "held" in output, output[-3000:]


@requires_image
def test_a_consumer_checkout_is_reported_while_the_image_copy_stays_asserted() -> None:
    finished = run(
        ["--bind", f"{CHECKOUT}:/__w/sage/sage"],
        ["--env", "PYTHONPATH=/__w/sage/sage/src"],
    )
    output = finished.stdout + finished.stderr
    assert finished.returncode == 0, output[-4000:]
    assert "imported from /__w/sage/sage/src/sage_extensions" in output, output[-3000:]
    assert "consumer checkout /__w/sage/sage at" in output, output[-3000:]
    assert "image checkout /repos/sage-extensions at" in output, output[-3000:]


@requires_image
def test_an_unreadable_required_revision_fails_the_step(tmp_path: Path) -> None:
    """A revision the step cannot read is a failed obligation, not a line in the log.

    The tree here has a `.git` git will not describe; the step must print git's own words and
    exit non-zero, rather than reporting the revision as unknown and carrying on.
    """
    broken = tmp_path / "checkout"
    (broken / ".git").mkdir(parents=True)
    (broken / "src" / "sage_extensions").mkdir(parents=True)
    (broken / "src" / "sage_extensions" / "__init__.py").write_text("")
    shutil.copytree(CHECKOUT / "src" / "sage_extensions", broken / "src" / "sage_extensions", dirs_exist_ok=True)
    finished = run(
        ["--bind", f"{broken}:/__w/sage/sage"],
        ["--env", "PYTHONPATH=/__w/sage/sage/src"],
    )
    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, output[-3000:]
    assert "unreadable" in output, output[-3000:]
    assert "fatal" in output or "git" in output.lower(), output[-3000:]


def compute_imports() -> str:
    """The compute block's import preamble: the part that decides which copies are imported."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for step in document["jobs"]["consumer-acceptance"]["steps"] if step.get("name") == STEP]
    body = steps[0]["run"]
    assert "<<'COMPUTE'" in body, "the step no longer computes in its own process"
    block = body.split("<<'COMPUTE'", 1)[1]
    lines = []
    for line in block.splitlines():
        lines.append(line)
        if 'print(f"{module.__name__}: {path}")' in line:
            break
    return "\n".join(lines).lstrip("\n") + "\n"


@requires_image
def test_the_generator_call_imports_the_images_pinned_copies() -> None:
    """The job installs a workspace provider for the owner-contract observation; it must not
    shadow the copies this call is a statement about."""
    script = (
        "import sys\n"
        "sys.path[:0] = ['/repos/sage-extensions/src', '/repos/sage-indefinite-port/src']\n"
        + compute_imports()
    )
    finished = subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run",
         "--bind", f"{CHECKOUT}:/__w/sage/sage", "--chdir", "/tmp", "--",
         "/sage/.venv/bin/python", "-c", script],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )
    output = finished.stdout + finished.stderr
    assert finished.returncode == 0, output[-3000:]
    assert "sage_extensions: /repos/sage-extensions/src/" in output, output[-3000:]
    assert "sage_indefinite_port: /repos/sage-indefinite-port/src/" in output, output[-3000:]
    assert "/__w/sage/sage" not in output, output[-3000:]


def whole_step() -> str:
    """The step's entire run block, as the shell receives it."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for step in document["jobs"]["consumer-acceptance"]["steps"] if step.get("name") == STEP]
    assert len(steps) == 1
    return steps[0]["run"]


@requires_image
def test_the_whole_step_runs_as_shell_and_imports_the_images_copies(tmp_path: Path) -> None:
    """The heredoc boundary itself, which no extracted-fragment test can see.

    An earlier version of this step opened the provenance heredoc and never closed it, so the
    shell command that follows was parsed as Python. Asserting on slices of the block could not
    catch that; running the block can -- and it runs with `bash -e -o pipefail`, as GitHub
    runs a step, so a provenance assertion that fails cannot fall through into the computation and
    still satisfy the printed-output assertions below. The step is allowed to fail here -- this image's port is
    older than the pin and its `group_generators` raises -- but it must fail *inside* the
    computation, after the shell boundary, with the image's copies imported.
    """
    script = tmp_path / "step.sh"
    script.write_text(whole_step(), encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run",
         "--bind", f"{script}:/step.sh", "--bind", f"{CHECKOUT}:/__w/sage/sage",
         "--env", "PYTHONPATH=/__w/sage/sage/src", "--chdir", "/tmp", "--",
         "timeout", "-s", "TERM", "600", "/bin/bash", "-e", "-o", "pipefail", "/step.sh", ],
        capture_output=True, text=True, timeout=900, check=False,
    )
    output = finished.stdout + finished.stderr
    assert "SyntaxError" not in output, output[-3000:]
    assert "Traceback (most recent call last):\n  File \"<stdin>\", line 1," not in output, output[-3000:]
    # the provenance heredoc ran, and asserted the image's revisions
    assert "image checkout /repos/sage-extensions at" in output, output[-3000:]
    assert "image checkout /repos/sage-indefinite-port at" in output, output[-3000:]
    # the compute heredoc ran in its own process, importing the image's copies
    assert "sage_extensions: /repos/sage-extensions/src/" in output, output[-3000:]
    assert "sage_indefinite_port: /repos/sage-indefinite-port/src/" in output, output[-3000:]
    # and the computation itself was reached
    assert "T_Co: rank 11, determinant -2048, signature (2, 9)" in output, output[-3000:]
