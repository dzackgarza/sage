"""The 6JRR step's certify invocation, run by the real CLI in the published image (sage#17).

`sage#17` is a working-directory defect, so what has to be tested is the invocation, not the
workflow's text: a `cd` into the checkout would satisfy any string check while leaving the
behaviour unproven. This test reads the step's `run:` block out of the workflow with the YAML
parser already in use, keeps its `certify` command exactly -- same interpreter, same `PYTHONPATH`
assignment on the same line, so the same provider and source paths -- and changes only the tag,
the deadline and the root, to a small card that already exists in the corpus. A real `latticedb`
process then runs against a corpus assembled from the image's own checkout, from a working
directory that is not that corpus.

The claim is deliberately narrow: **the corpus loads and the named card is reached.** It is not a
certificate of 6JRR, and not a claim about the small card's values.

* Positive: the run gets past `corpus.load` and names `0012` -- either because the card needed
  nothing and the run finished, or because its worker reported on `0012`. Both can only happen
  after the corpus was loaded and the tag selected.
* Control: with `families.yaml` left out of the fixture, the same command cannot get that far: it
  stops at the load, says so, and never names a card. So the positive observation is coupled to
  the file rather than to luck.
* Not the contract: a process still running when a window closes (an earlier version of this test
  accepted that, and it proves only that something had not finished), and not merely the absence
  of an error string.

Recomputing this card is a separate matter and is blocked above this code: `sage_genus.py` calls
`records.derive`, which reaches
`sage_extensions...reflective_root_system_components()` and dies in sage-extensions#291. That is
recorded here, not worked around.

    pytest docker/tests/test_certify_step_in_the_image.py
    CERTIFY_WORKFLOW=<pre-fix workflow> pytest docker/tests/test_certify_step_in_the_image.py
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOW = Path(os.environ.get("CERTIFY_WORKFLOW", REPOSITORY / ".github" / "workflows" / "research-environment-image.yml"))
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
RUNNER = REPOSITORY / "docker" / "sage-image.py"
STEP = "Certify lattice-database card 6JRR"
CARD = "0012"
BOUND = 300


def step_body() -> str:
    """The named step's `run:` block, as the workflow's own YAML says it is."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for step in document["jobs"]["consumer-acceptance"]["steps"] if step.get("name") == STEP]
    assert len(steps) == 1, f"{STEP!r} appears {len(steps)} times in {WORKFLOW}"
    return steps[0]["run"]


def focused_invocation(body: str, families: bool = True) -> str:
    """The step's own command, with only the tag, the deadline and the corpus changed.

    The corpus is a fresh directory per run -- `mktemp -d`, so two tests can never share one and
    nothing existing is touched -- holding one real card, the families file (omitted when
    `families` is false) and an empty retired-tags file, copied from the image's checkout.
    """
    lines = body.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("PYTHONPATH="))
    kept = []
    for line in lines[start:]:
        kept.append(line.rstrip().rstrip("\\"))
        if not line.rstrip().endswith("\\"):
            break
    # Joined into one line on purpose: the step spreads it over continuations, and an assignment
    # left on a line of its own would be a shell variable the command never sees.
    command = " ".join(part.strip() for part in kept)
    command = re.sub(r">\s*\S+.*$", "", command).strip()
    command = re.sub(r"--tag \S+", f"--tag {CARD}", command)
    command = re.sub(r"--minutes \S+", "--minutes 5", command)
    command = re.sub(r"--root \S+", '--root "$corpus"', command)
    checkout = next(line for line in lines if line.startswith("checkout="))

    script = f'''
corpus="$(mktemp -d)"
echo "corpus: $corpus"
mkdir -p "$corpus/lattices"
cp /repos/lattice-database/lattices/{CARD}.md "$corpus/lattices/"
printf '{{}}\\n' > "$corpus/retired-tags.yaml"
'''
    if families:
        script += 'cp /repos/lattice-database/families.yaml "$corpus/"\n'
    return script + checkout + "\n" + command + "\n"


def run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run", "--chdir", "/tmp", "--",
         "timeout", "-s", "TERM", str(BOUND), "/bin/sh", "-c", script],
        capture_output=True, text=True, timeout=BOUND + 180, check=False,
    )


requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or shutil.which("bwrap") is None,
    reason="needs an unpacked image at SAGE_IMAGE_ROOTFS and bubblewrap",
)


@requires_image
def test_the_named_card_is_reached_after_the_corpus_loads() -> None:
    """Positive: the load happened and the tag was selected -- both before any card work."""
    finished = run(focused_invocation(step_body()))
    output = finished.stdout + finished.stderr
    assert "families.yaml" not in output, output[-4000:]
    assert finished.returncode == 0 or f"failed on {CARD}" in output, output[-4000:]


@requires_image
def test_the_same_command_cannot_reach_a_card_without_the_corpus_file() -> None:
    """Control: leave families.yaml out and the command stops at the load, naming no card."""
    finished = run(focused_invocation(step_body(), families=False))
    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, output[-4000:]
    assert "families.yaml" in output, output[-4000:]
    assert f"failed on {CARD}" not in output, output[-4000:]
