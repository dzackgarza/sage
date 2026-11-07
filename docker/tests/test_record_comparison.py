"""The record comparison the consumer-acceptance job runs, exercised as it is written.

The job reproduces each research record inside the image and holds the rerun to the
committed `-run.txt` line by line. That comparison is not a module: it is a heredoc inside
a `run:` block in `.github/workflows/research-environment-image.yml`, so these tests
extract it from there and run it as the job does. A test carrying its own copy of the
comparison would keep passing while the job's own drifted away from it.

The fixtures are the bodies the comparison saw for `coble_plane-half-f2`, both from the
pinned image (`research dbf178cf30`, sage-extensions `3e4812618c`, port `991b88b0`):

    fixtures/coble_plane-half-f2-run.txt     the committed record, as the comparison sees it
                                             (its provenance block already dropped)
    fixtures/coble_plane-half-f2-rerun.txt   a rerun of it inside the image

The rerun printed the identical 26 result lines and three different annotations: `(49 s)`
became `(77 s)`, `(2 s)` became `(1 s)` and `(152 s)` became `(154 s)`. An earlier rerun in
the consumer-acceptance job moved the same record's annotations to `(61 s)`, `(179 s)` and
`(1 s)` -- different again, so what moves is the timing and not one particular line. That
earlier run is sage#16: the comparison failed a record whose every mathematical value
reproduced, because a rerun on a busier machine spends a different number of seconds.

`coble_isotropic_orbits` is the second pair, and its rerun is not reconstructed: it is the file
run 42362483952 uploaded as artifact 13574428772 (`research-stage1-records`, 1804 bytes, zip
sha256 dd60d3beaf88fc04…), kept unmodified (sha256 3ab1b0f8c8a7ad4a…) beside the committed
record (sha256 dd7043af…). That run's consumer image was index digest
sha256:db78c6de3d08ad09…, and it moved one annotation on this record -- `materialised in
29.8s` became `in 56.0s` -- which is prose rather than the parenthesised form, so a comparator
that handles only `(152 s)` still fails it.
"""

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "research-environment-image.yml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TIMING = re.compile(r"\s*\(\s*\d+(?:\.\d+)?\s*s\s*\)")
INLINE_TIMING = re.compile(r"\bin \d+(?:\.\d+)?\s*s\b")

# Each pair: the committed record of the pinned research checkout, and the output a run
# actually uploaded for it. Both forms of elapsed annotation occur across these pairs.
RECORDS = {
    "coble_plane-half-f2": (FIXTURES / "coble_plane-half-f2-run.txt", FIXTURES / "coble_plane-half-f2-rerun.txt"),
    "coble_isotropic_orbits": (FIXTURES / "coble_isotropic_orbits-run.txt", FIXTURES / "coble_isotropic_orbits-rerun.txt"),
}


def comparators() -> dict[str, str]:
    """Every record comparison embedded in the workflow, by the step that runs it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for index, chunk in enumerate(text.split("<<'COMPARE'")[1:], start=1):
        body = chunk.split("\n", 1)[1]
        lines = []
        for line in body.splitlines():
            if line.strip() == "COMPARE":
                break
            lines.append(line)
        found[f"comparator {index}"] = textwrap.dedent("\n".join(lines)) + "\n"
    return found


COMPARATORS = comparators()


def compare(comparator: str, expected: Path, actual: Path, record: str) -> subprocess.CompletedProcess:
    """Run one embedded comparator exactly as the step does: two paths and a name."""
    return subprocess.run(
        [sys.executable, "-", str(expected), str(actual), record],
        input=comparator, capture_output=True, text=True, check=False,
    )


def without_annotations(line: str) -> str:
    return INLINE_TIMING.sub("in <elapsed>", TIMING.sub("", line))


def results(path: Path) -> list[str]:
    """The record's lines without the provenance block and without timing annotations."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "provenance":
        while lines and lines[0].strip():
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return [without_annotations(line).rstrip() for line in lines if line.strip()]


def rewritable(tmp_path: Path, record: str, name: str, was: str, now: str) -> Path:
    """A copy of the record's rerun with one exact piece of text replaced."""
    text = RECORDS[record][1].read_text(encoding="utf-8")
    assert text.count(was) == 1, f"{was!r} occurs {text.count(was)} times"
    destination = tmp_path / name
    destination.write_text(text.replace(was, now), encoding="utf-8")
    return destination


# One value per record that the record states and that this test may move.
ANCHORS = {
    "coble_plane-half-f2": ("|O(q)| = 46998591897600", "|O(q)| = 46998591897601", 3),
    "coble_isotropic_orbits": ("isotropic classes: 528", "isotropic classes: 529", 1),
}


def test_the_workflow_still_embeds_two_record_comparators() -> None:
    assert len(COMPARATORS) == 2, sorted(COMPARATORS)


@pytest.mark.parametrize("record", sorted(RECORDS))
def test_the_fixtures_differ_only_in_timing_annotations(record: str) -> None:
    committed, rerun = RECORDS[record]
    assert results(committed) == results(rerun)
    assert committed.read_text() != rerun.read_text(), "the fixtures are meant to differ, in their annotations"
    moved = [
        (was, now)
        for was, now in zip(committed.read_text().splitlines(), rerun.read_text().splitlines())
        if was != now
    ]
    assert len(moved) == ANCHORS[record][2], moved
    for was, now in moved:
        assert was != INLINE_TIMING.sub("", was) or was != TIMING.sub("", was), "a moved line carries no annotation"
        assert now != INLINE_TIMING.sub("", now) or now != TIMING.sub("", now), "a moved line carries no annotation"


@pytest.mark.parametrize("record", sorted(RECORDS))
@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_rerun_that_moved_only_its_timings_is_reproduced(name: str, record: str) -> None:
    """sage#16: every value matched and the record was still reported as differing."""
    committed, rerun = RECORDS[record]
    finished = compare(COMPARATORS[name], committed, rerun, record)
    assert finished.returncode == 0, finished.stdout + finished.stderr


@pytest.mark.parametrize("record", sorted(RECORDS))
@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_changed_mathematical_value_is_rejected(name: str, record: str, tmp_path: Path) -> None:
    was, now, _ = ANCHORS[record]
    changed = rewritable(tmp_path, record, "value.txt", was, now)
    finished = compare(COMPARATORS[name], RECORDS[record][0], changed, record)
    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert now in finished.stdout


@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_changed_value_is_rejected_even_beside_a_moved_annotation(name: str, tmp_path: Path) -> None:
    """The anchor stops at the annotation so the test does not depend on its value."""
    record = "coble_plane-half-f2"
    changed = rewritable(tmp_path, record, "value-and-timing.txt", "|O(q)| = 46998591897600   (", "|O(q)| = 46998591897601   (")
    finished = compare(COMPARATORS[name], RECORDS[record][0], changed, record)
    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert "46998591897601" in finished.stdout


@pytest.mark.parametrize("record", sorted(RECORDS))
@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_changed_inline_elapsed_removed_but_a_changed_value_kept_is_rejected(name: str, record: str, tmp_path: Path) -> None:
    """Stripping the prose annotation must not carry a value change with it."""
    text = RECORDS[record][1].read_text(encoding="utf-8")
    was, now, _ = ANCHORS[record]
    assert text.count(was) == 1
    destination = tmp_path / "inline-and-value.txt"
    destination.write_text(text.replace(was, now).replace("in 56.0s", "in 60.0s"), encoding="utf-8")
    finished = compare(COMPARATORS[name], RECORDS[record][0], destination, record)
    assert finished.returncode == 1, finished.stdout + finished.stderr


@pytest.mark.parametrize("record", sorted(RECORDS))
@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_missing_line_is_rejected(name: str, record: str, tmp_path: Path) -> None:
    text = RECORDS[record][1].read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if "|Stab| * |orbit|" not in line and "orbit (size, q)" not in line]
    assert len(kept) == len(text.splitlines()) - 1
    missing = tmp_path / "missing-line.txt"
    missing.write_text("\n".join(kept) + "\n", encoding="utf-8")
    finished = compare(COMPARATORS[name], RECORDS[record][0], missing, record)
    assert finished.returncode == 1, finished.stdout + finished.stderr
