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
# A checkout of the research revision that carries the record is bound over /repos/research.
# Whether the image already carries that revision is not this test's business: an image that
# contains the record would work exactly as well, and the run record states which revisions
# were in force. The same checkout is used for the red and the green run.
RESEARCH = Path(os.environ.get("RESEARCH_CHECKOUT", REPOSITORY / ".scratch" / "wt-research"))

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


# c45b08c1dfb split `consumer-acceptance` into these five, one bounded job per
# consumer call. The chamber step lives in `consumer-chamber`; the lookup reads the
# five by name so a further split fails with the jobs the workflow has, not a KeyError.
CONSUMER_JOBS = (
    "consumer-mathematics",
    "consumer-certify",
    "consumer-records",
    "consumer-contracts",
    "consumer-chamber",
)


def consumer_jobs() -> dict:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    found = {name: jobs[name] for name in CONSUMER_JOBS if name in jobs}
    assert found, f"none of {CONSUMER_JOBS} is in the workflow; it has {sorted(jobs)}"
    return found


def step_body() -> str:
    steps = [
        step
        for definition in consumer_jobs().values()
        for step in definition.get("steps", [])
        if step.get("name") == STEP
    ]
    assert len(steps) == 1, (
        f"{STEP!r} appears {len(steps)} times across {sorted(consumer_jobs())}"
    )
    return steps[0]["run"]


def test_the_five_consumer_jobs_are_the_ones_the_workflow_has() -> None:
    """The names this file reads are the split's, and the chamber step is in the
    job that reads the chamber."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    missing = [name for name in CONSUMER_JOBS if name not in jobs]
    assert not missing, f"{missing} are no longer jobs; the workflow has {sorted(jobs)}"
    carriers = [
        name for name in CONSUMER_JOBS
        if any(step.get("name") == STEP for step in jobs[name].get("steps", []))
    ]
    assert carriers == ["consumer-chamber"], carriers


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
    print(f"sources under test: research {bound} bound over /repos/research, from {RESEARCH}")
