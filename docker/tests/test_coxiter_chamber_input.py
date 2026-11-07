"""CoxIter must read the record's labelled chamber graph, not the record (image#18).

The step used to pipe the research record itself into CoxIter. That file is not a graph: the
engine takes the digits of its first line as a vertex count and one `<a> <b> <order>` per edge,
and every other line is echoed as `Unread line`. Run 42362483952 therefore read an eight-vertex
simplex and exited 0.

A vertex count, or the field of the Gram entries, cannot establish what was read: different
graphs can share both. What is compared here is CoxIter's `-pcm` output, the Coxeter matrix of
the graph it parsed -- its own representation, `m_ij` being 2 where there is no edge -- held
entry by entry to the matrix the record's `edges (i, j, label)` list defines.

The test takes the input from the *step*: it runs the step's `run:` block in the published image,
takes the graph the step says it handed over, and asks the engine to print its matrix for that
input. Against the original step the input is the record itself, the matrix is not the record's,
and the test fails -- which is the point of keeping it.

    pytest docker/tests/test_coxiter_chamber_input.py
    COXITER_WORKFLOW=<pre-fix workflow> pytest docker/tests/test_coxiter_chamber_input.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOW = Path(os.environ.get("COXITER_WORKFLOW", REPOSITORY / ".github" / "workflows" / "research-environment-image.yml"))
ROOTFS = Path(os.environ.get("SAGE_IMAGE_ROOTFS", Path.home() / "sage-image" / "rootfs"))
RUNNER = REPOSITORY / "docker" / "sage-image.py"
STEP = "Read the I_{1,8} chamber with CoxIter"
BOUND = 300
# The record is **not in the published image**: that image's own /repos/research is at ec1333ee
# and has no `computations/` directory. This test therefore binds a checkout of the pinned
# research revision over /repos/research, and says so: a local image with a bound checkout is not
# a published-image workflow run. The same checkout is used for the red and the green run, and
# both the image's own revision and the bound one are read at run time and reported.
RESEARCH = Path(os.environ.get("RESEARCH_CHECKOUT", REPOSITORY / ".scratch" / "wt-research"))
DIGEST = os.environ.get("SAGE_IMAGE_DIGEST", "sha256:220293469c53eef012ce94ed52795216ff5b27f65a1f401a41864f45967d3851")

COMPARE = r"""
set -u
coxiter="$(command -v coxiter)"
record=/repos/research/computations/reports/coble_I18_vinberg-chamber-run.txt
test -f "${record}"
bash /step.sh > /tmp/step.out 2>&1
status=$?
echo "--- the step exited ${status}"
tail -n 25 /tmp/step.out
test "${status}" -eq 0
# The input the step itself says it handed over; the original step hands over the record.
if grep -q '^--- the graph handed to CoxIter$' /tmp/step.out; then
  sed -n '/^--- the graph handed to CoxIter$/,/^coxiter exited/p' /tmp/step.out \
    | sed '1d;$d' | sed '/^$/d' > /tmp/input.graph
else
  cp "${record}" /tmp/input.graph
fi
echo "--- the matrix the engine parses from that input"
"${coxiter}" -pcm < /tmp/input.graph > /tmp/matrix.out 2>&1 || true
cat /tmp/matrix.out
/sage/.venv/bin/python - "${record}" /tmp/matrix.out <<'PY'
import ast
import re
import sys

record, printed = sys.argv[1:3]
text = open(record, encoding="utf-8").read()
walls = int(re.search(r"^\s*walls:\s*(\d+)", text, re.M).group(1))
edges = ast.literal_eval(re.search(r"^\s*edges \(i, j, label\):\s*(\[.*\])", text, re.M).group(1))
expected = [[1 if i == j else 2 for j in range(walls)] for i in range(walls)]
for first, second, label in edges:
    expected[first - 1][second - 1] = expected[second - 1][first - 1] = label
rows = [
    [int(entry) for entry in line.split(",")]
    for line in open(printed, encoding="utf-8")
    if re.fullmatch(r"[0-9]+(,[0-9]+)+", line.strip())
]
assert rows, "the engine printed no Coxeter matrix for that input"
assert rows == expected, "the parsed labelled adjacencies are not the record's edge list"
print("the engine's parsed adjacencies equal the record's edge list")
PY
"""


def image_research_revision() -> str:
    """The research revision the image itself carries, read with nothing bound over it."""
    finished = subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run", "--chdir", "/tmp", "--",
         "git", "-C", "/repos/research", "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=BOUND, check=False,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    return finished.stdout.strip()


def step_body() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for step in document["jobs"]["consumer-acceptance"]["steps"] if step.get("name") == STEP]
    assert len(steps) == 1, f"{STEP!r} appears {len(steps)} times in {WORKFLOW}"
    return steps[0]["run"]


requires_image = pytest.mark.skipif(
    not ROOTFS.is_dir() or shutil.which("bwrap") is None or not (RESEARCH / "computations" / "reports").is_dir(),
    reason="needs the image, bubblewrap, and a research checkout with the record (RESEARCH_CHECKOUT)",
)


@requires_image
def test_the_engine_parses_the_records_labelled_adjacencies(tmp_path: Path) -> None:
    step = tmp_path / "step.sh"
    step.write_text(step_body(), encoding="utf-8")
    script = tmp_path / "compare.sh"
    script.write_text(COMPARE, encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, str(RUNNER), "--rootfs", str(ROOTFS), "run",
         "--bind", f"{step}:/step.sh", "--bind", f"{script}:/compare.sh",
         "--bind", f"{RESEARCH}:/repos/research", "--chdir", "/tmp", "--",
         "timeout", "-s", "TERM", str(BOUND), "/bin/sh", "/compare.sh"],
        capture_output=True, text=True, timeout=BOUND + 180, check=False,
    )
    output = finished.stdout + finished.stderr
    assert finished.returncode == 0, output[-4000:]
    assert "the engine's parsed adjacencies equal the record's edge list" in output, output[-4000:]

    bound = subprocess.run(["git", "-C", str(RESEARCH), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert len(bound) == 40, bound
    inside = image_research_revision()
    assert inside != bound, (
        "this test is meant to run a checkout bound over an image that does not carry the record; "
        f"the image's own /repos/research is already {inside}"
    )


@requires_image
def test_the_provenance_is_reported_with_the_check(tmp_path: Path) -> None:
    """A bound checkout over a local image is not a published-image run; say which is which."""
    bound = subprocess.run(["git", "-C", str(RESEARCH), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    print(f"image digest:      {DIGEST}")
    print(f"image research:    {image_research_revision()}  (the record is not in that tree)")
    print(f"bound research:    {bound}  ({RESEARCH} over /repos/research)")
    print(f"image rootfs:      {ROOTFS}")
    assert DIGEST.startswith("sha256:") and len(DIGEST) == len("sha256:") + 64
    assert len(bound) == 40
