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
"""

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "research-environment-image.yml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMMITTED = FIXTURES / "coble_plane-half-f2-run.txt"
RERUN = FIXTURES / "coble_plane-half-f2-rerun.txt"
TIMING = re.compile(r"\s*\(\s*\d+(?:\.\d+)?\s*s\s*\)")
RECORD = "coble_plane-half-f2"


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


def compare(comparator: str, expected: Path, actual: Path) -> subprocess.CompletedProcess:
    """Run one embedded comparator exactly as the step does: two paths and a name."""
    return subprocess.run(
        [sys.executable, "-", str(expected), str(actual), RECORD],
        input=comparator, capture_output=True, text=True, check=False,
    )


def results(path: Path) -> list[str]:
    """The record's lines without the provenance block and without timing annotations."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "provenance":
        while lines and lines[0].strip():
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return [TIMING.sub("", line).rstrip() for line in lines if line.strip()]


def rewritable(tmp_path: Path, name: str, was: str, now: str) -> Path:
    """A copy of the rerun body with one exact piece of text replaced."""
    text = RERUN.read_text(encoding="utf-8")
    assert text.count(was) == 1, f"{was!r} occurs {text.count(was)} times"
    destination = tmp_path / name
    destination.write_text(text.replace(was, now), encoding="utf-8")
    return destination


def test_the_workflow_still_embeds_two_record_comparators() -> None:
    assert len(COMPARATORS) == 2, sorted(COMPARATORS)


def test_the_fixtures_differ_only_in_timing_annotations() -> None:
    committed, rerun = results(COMMITTED), results(RERUN)
    assert committed == rerun
    assert COMMITTED.read_text() != RERUN.read_text(), "the fixtures are meant to differ, in their annotations"
    moved = [
        (TIMING.search(was).group(0), TIMING.search(now).group(0))
        for was, now in zip(COMMITTED.read_text().splitlines(), RERUN.read_text().splitlines())
        if was != now
    ]
    assert len(moved) == 3, moved


@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_rerun_that_moved_only_its_timings_is_reproduced(name: str) -> None:
    """sage#16: every value matched and the record was still reported as differing."""
    finished = compare(COMPARATORS[name], COMMITTED, RERUN)
    assert finished.returncode == 0, finished.stdout + finished.stderr


@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_changed_mathematical_value_is_rejected(name: str, tmp_path: Path) -> None:
    """`|O(q)|` is the same number on two lines; only the first is the one under test."""
    changed = rewritable(tmp_path, "value.txt", "|O(q)| = 46998591897600", "|O(q)| = 46998591897601")
    finished = compare(COMPARATORS[name], COMMITTED, changed)
    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert "46998591897601" in finished.stdout


@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_changed_value_is_rejected_even_beside_a_moved_annotation(name: str, tmp_path: Path) -> None:
    """The anchor stops at the annotation so the test does not depend on its value."""
    changed = rewritable(tmp_path, "value-and-timing.txt", "|O(q)| = 46998591897600   (", "|O(q)| = 46998591897601   (")
    finished = compare(COMPARATORS[name], COMMITTED, changed)
    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert "46998591897601" in finished.stdout


@pytest.mark.parametrize("name", sorted(COMPARATORS))
def test_a_missing_line_is_rejected(name: str, tmp_path: Path) -> None:
    text = RERUN.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if "|Stab| * |orbit|" not in line]
    assert len(kept) == len(text.splitlines()) - 1
    missing = tmp_path / "missing-line.txt"
    missing.write_text("\n".join(kept) + "\n", encoding="utf-8")
    finished = compare(COMPARATORS[name], COMMITTED, missing)
    assert finished.returncode == 1, finished.stdout + finished.stderr
