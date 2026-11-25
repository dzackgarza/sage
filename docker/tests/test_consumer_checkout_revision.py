"""A consumer job's sage-extensions checkout names its own revision in the container (sage#43).

The runner makes the checkout as the uid of the host runner, and the job's container runs as
root. git refuses a repository that another user owns ("dubious ownership"), so
`sage_extensions.timing.current_commit` finds no checkout and each timed stage of the job
stops. This test runs the job's own `git config` steps before its install and the install,
on a checkout that another uid owns, in the published image, and then asks for the revision.

    SAGE_IMAGE=<image reference> pytest docker/tests/test_consumer_checkout_revision.py
    CONSUMER_WORKFLOW=<pre-fix workflow> SAGE_IMAGE=... pytest ...
"""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOW = Path(
    os.environ.get(
        "CONSUMER_WORKFLOW", REPOSITORY / ".github" / "workflows" / "research-environment-image.yml"
    )
)
INSTALL = "Install the checked-out sage-extensions source"
WORKSPACE = "/__w/sage/sage"
RUNNER_UID = "1001"


def jobs_installing_the_checkout() -> dict[str, list[dict[str, str]]]:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    found = {
        name: definition["steps"]
        for name, definition in jobs.items()
        if any(step.get("name") == INSTALL for step in definition.get("steps", []))
    }
    assert found, f"no job of {WORKFLOW} has the step {INSTALL!r}"
    return found


def git_configuration_and_install(steps: list[dict[str, str]]) -> list[str]:
    install = next(index for index, step in enumerate(steps) if step.get("name") == INSTALL)
    blocks = [
        step["run"]
        for step in steps[:install]
        if "run" in step and step["run"].lstrip().startswith("git config")
    ]
    blocks.append(steps[install]["run"])
    assert all("${{" not in block for block in blocks), blocks
    return blocks


def revision_after(blocks: list[str]) -> subprocess.CompletedProcess:
    image = os.environ.get("SAGE_IMAGE")
    assert image, "SAGE_IMAGE names the published image this test runs the steps in"
    script = "\n".join(
        [
            "set -eu",
            f"mkdir -p {os.path.dirname(WORKSPACE)} \"$HOME\"",
            f"cp -a /repos/sage-extensions {WORKSPACE}",
            f"chown -R {RUNNER_UID}:{RUNNER_UID} {WORKSPACE}",
            f"cd {WORKSPACE}",
            *blocks,
            "git -c safe.directory='*' rev-parse HEAD",
            "/sage/.venv/bin/python -c "
            "'from sage_extensions.timing import current_commit; print(current_commit())'",
        ]
    )
    return subprocess.run(
        [
            "docker", "run", "--rm", "-u", "0",
            "-e", "HOME=/github/home", "-e", f"GITHUB_WORKSPACE={WORKSPACE}",
            image, "bash", "-c", script,
        ],
        capture_output=True, text=True, timeout=600, check=False,
    )


@pytest.mark.parametrize("job", sorted(jobs_installing_the_checkout()))
def test_the_installed_checkout_names_its_head(job: str) -> None:
    finished = revision_after(git_configuration_and_install(jobs_installing_the_checkout()[job]))
    lines = finished.stdout.split()
    assert finished.returncode == 0, finished.stderr[-3000:]
    assert len(lines[-1]) == 40 and lines[-1] == lines[-2], finished.stdout[-2000:]
