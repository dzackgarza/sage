"""Every `latticedb certify` the consumer job runs must name its corpus (sage#17).

`latticedb`'s CLI takes `root: Root = Path()`, and `Path()` is the *process's* working
directory. The consumer-acceptance job runs its steps in `${{ github.workspace }}`, which for
that job is a sage-extensions checkout — not the lattice-database checkout the corpus lives in.
So a `certify` that does not name `--root` looks for `families.yaml` in the wrong tree and dies
before it computes anything:

    FileNotFoundError: [Errno 2] No such file or directory: 'families.yaml'

That is what run 42362483952 hit at 12:28:20Z: exit 1 within three seconds, no card diff, no
certificate written, and an uploaded archive of the certificates directory exactly as it
already was. An upload is not a certification.

These tests read the workflow rather than the CLI: the defect is in the step, and a step that
relies on the job's working directory is wrong even when that directory happens to be right.
"""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "research-environment-image.yml"
CERTIFY = re.compile(r"latticedb\s+certify\b")


def steps_running_the_cli() -> list[tuple[str, str]]:
    """Every step of the consumer job whose run block invokes the latticedb CLI."""
    text = WORKFLOW.read_text(encoding="utf-8")
    found: list[tuple[str, str]] = []
    current = "?"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            current = stripped.split(":", 1)[1].strip()
        elif CERTIFY.search(line) and not stripped.startswith("#"):
            # the whole step body: this line plus the continuation lines of the command
            found.append((current, line))
    return found


def command_of(step_name: str) -> str:
    """The run block of the named step, as the shell sees it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = f"- name: {step_name}"
    assert text.count(marker) == 1, f"{step_name!r} occurs {text.count(marker)} times"
    body = text.split(marker, 1)[1]
    lines = []
    for line in body.splitlines():
        if line.strip().startswith("- name:") or line.strip().startswith("uses:"):
            break
        lines.append(line)
    return "\n".join(lines)


def test_the_job_certifies_a_card() -> None:
    assert steps_running_the_cli(), "no step runs `latticedb certify`; the step was renamed or removed"


def test_every_certify_invocation_names_its_root() -> None:
    """`--root` is the only thing that ties the CLI to the corpus the job means."""
    missing = [name for name, line in steps_running_the_cli() if "--root" not in command_of(name)]
    assert missing == [], (
        "these steps run `latticedb certify` without --root, so the CLI reads the job's working "
        f"directory as the corpus: {missing}"
    )


def test_the_6jrr_step_names_the_lattice_database_checkout() -> None:
    body = command_of("Certify lattice-database card 6JRR")
    assert "--tag 6JRR" in body
    assert '--root "${checkout}"' in body, body
