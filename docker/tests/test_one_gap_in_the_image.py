"""One GAP in the image, and nothing at the path the check forbids (sage#26).

Run 42910347791's full build carried a second GAP: docker/research-environment.Dockerfile
copied the image's launcher to /usr/bin/gap -- ac455b94fb, for the emptied-environment
probe raised in sage#24 -- and docker/research-environment-check.py stopped the build with

    AssertionError: a distribution GAP is still installed: ['/usr/bin/gap']

The check asserts a path, and a launcher at /usr/bin/gap is indistinguishable from
Debian's binary there; the launcher belongs at /usr/local/bin/gap, which the same COPY
also served. So the COPY is deleted (fc971cae) and nothing replaces it -- neither a
"harmless" launcher nor a relaxed check.

What is asserted here needs no image, and covers both ways the artifact can exist:

* no instruction in either Dockerfile writes a file at /usr/bin/gap. The layer that
  installed it was a COPY, so a test that reads the instructions catches the next one;
* the incremental Dockerfile -- a build on a published base, whose layers only add --
  removes a distro GAP and a lone launcher at that path, stops when apt's purge fails or
  when a path survives the removal, and asserts exactly the four paths the check
  asserts. That last equality is by construction, not by memory: the two files failed
  together once already.

The removal block runs verbatim out of the Dockerfile. "/usr" is rebased into a
temporary root and dpkg-query/apt-get are stubs; the rebase is uniform, so it cannot
hide which path the block removes, and the block's own absence loop is rebased with the
rest -- otherwise it would check the host's /usr and pass without asserting anything.
"""

import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
DOCKER = REPOSITORY / "docker"
FULL = DOCKER / "research-environment.Dockerfile"
INCREMENTAL = DOCKER / "research-environment-incremental.Dockerfile"
CHECK = DOCKER / "research-environment-check.py"

BLOCK_START = 'RUN purged="$(dpkg-query'
FORBIDDEN = "/usr/bin/gap"


def instructions(path: Path) -> list[str]:
    """The file's instructions, with continuations joined and comments dropped."""
    joined, current = [], ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not current and (not line.strip() or line.lstrip().startswith("#")):
            continue
        current += line.strip()
        if current.endswith("\\"):
            current = current[:-1] + " "
            continue
        joined.append(" ".join(current.split()))
        current = ""
    return joined


def copy_destinations(path: Path) -> list[str]:
    """Every COPY/ADD destination in the file, as written."""
    destinations = []
    for instruction in instructions(path):
        word = instruction.split(maxsplit=1)
        if word[0].upper() not in ("COPY", "ADD"):
            continue
        # --from=..., --chmod=..., then the sources, then the destination.
        arguments = [item for item in word[1].split() if not item.startswith("--")]
        destinations.append(arguments[-1])
    return destinations


def removal_block() -> str:
    """The incremental Dockerfile's removal layer, as the build runs it."""
    lines = INCREMENTAL.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(BLOCK_START))
    block = []
    for line in lines[start:]:
        block.append(line)
        if not line.endswith("\\"):
            break
    return "\n".join(block)


def removal_body(root: Path) -> str:
    """The block's shell, with every /usr path under `root`, RUN removed."""
    body = removal_block().split(" ", 1)[1]
    assert body.count("/usr/") >= 4, body
    return body.replace("/usr/", f"{root}/usr/")


def one_line(block: str) -> str:
    """The block with continuations and newlines collapsed, for reading its words."""
    return " ".join(block.replace("\\\n", " ").split())


def asserted_paths() -> list[str]:
    """The paths the removal layer stops on, in the block's order."""
    listed = re.search(r"for path in (.*?); do", one_line(removal_block()))
    assert listed, removal_block()
    return listed.group(1).split()


def check_paths() -> list[str]:
    """The paths the environment check treats as a distribution GAP, in its order."""
    text = CHECK.read_text(encoding="utf-8")
    start = text.index("distribution_gap = [")
    end = text.index("if Path(path).exists()", start)
    return re.findall(r'"(/usr/[^"]*)"', text[start:end])


def stub(directory: Path, name: str, body: str) -> None:
    """A stand-in for one command: a Python script, so no PATH is needed to run it."""
    path = directory / name
    path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    path.chmod(0o755)


def fake_base(tmp_path: Path, present: list[str]) -> tuple[Path, Path]:
    """A published base's filesystem, and the commands the layer runs against it.

    `present` is what the base carries: a distro GAP's files, a lone launcher at
    /usr/bin/gap, or nothing. dpkg-query reports a distro GAP only when the run is told
    to, and apt-get purge deletes the four files, as the real one's postrm does.
    """
    root = tmp_path / "base"
    for path in present:
        target = root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    stub(stubs, "dpkg-query", (
        "import os, sys\n"
        "if os.environ.get('DPKG_GAP') != 'installed':\n"
        "    print('dpkg-query: no packages found matching gap*', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "for name in ('gap-core', 'gap-libs', 'gap-online-help'):\n"
        "    print(name, 'install ok installed')\n"
    ))
    stub(stubs, "apt-get", (
        "import os, sys, pathlib\n"
        "root = pathlib.Path(os.environ['FAKE_ROOT'])\n"
        "assert sys.argv[1] == 'purge', sys.argv\n"
        "if os.environ.get('APT_PURGE_FAILS') == 'true':\n"
        "    print('E: the purge could not run', file=sys.stderr)\n"
        "    raise SystemExit(100)\n"
        "for path in ('usr/bin/gap', 'usr/lib/gap', 'usr/share/gap',\n"
        "             'usr/lib/x86_64-linux-gnu/libgap.so.9'):\n"
        "    (root / path).unlink(missing_ok=True)\n"
        "for name in sys.argv[2:]:\n"
        "    if name != '-y':\n"
        "        print('Removing ' + name)\n"
    ))
    return root, stubs


def run_removal(root: Path, stubs: Path, **environment: str) -> subprocess.CompletedProcess:
    """The removal layer, on the fake base."""
    return subprocess.run(
        ["bash", "-c", removal_body(root)],
        capture_output=True, text=True, check=False,
        env={"PATH": f"{stubs}:/usr/local/bin:/usr/bin:/bin",
             "FAKE_ROOT": str(root), **environment},
    )


def test_no_dockerfile_writes_usr_bin_gap() -> None:
    """Neither build path puts a file at /usr/bin/gap, and the launcher is one path."""
    for dockerfile in (FULL, INCREMENTAL):
        destinations = copy_destinations(dockerfile)
        assert FORBIDDEN not in destinations, (dockerfile.name, destinations)
    # Not vacuous: the launcher is copied, at the one path that is not asserted against.
    assert "/usr/local/bin/gap" in copy_destinations(FULL)


def test_the_removal_asserts_the_checks_own_paths() -> None:
    """The layer stops on exactly the four paths the environment check asserts."""
    assert asserted_paths() == check_paths()
    assert FORBIDDEN in asserted_paths()
    removal = re.search(r"rm -rf (.*?) &&", one_line(removal_block()))
    assert removal and FORBIDDEN in removal.group(1), removal_block()


def test_a_distribution_gap_is_gone_after_the_block(tmp_path) -> None:
    """Debian's GAP: purged, removed, and none of the four paths survives."""
    root, stubs = fake_base(tmp_path, check_paths())
    result = run_removal(root, stubs, DPKG_GAP="installed")
    assert result.returncode == 0, (result.stdout, result.stderr)
    # The purged set is one line per package, printf printing it as it comes.
    assert result.stdout.split()[:7] == [
        "purging", "the", "distribution", "GAP:", "gap-core", "gap-libs", "gap-online-help",
    ], result.stdout
    assert not [path for path in check_paths() if (root / path.lstrip("/")).exists()]


def test_a_lone_launcher_at_usr_bin_is_gone_after_the_block(tmp_path) -> None:
    """The base run 42910347791 hit: no apt package, and the launcher at that path."""
    root, stubs = fake_base(tmp_path, [FORBIDDEN])
    launcher = root / FORBIDDEN.lstrip("/")
    launcher.write_text('#!/bin/sh\nexec /sage/.venv/bin/gap "$@"\n', encoding="utf-8")
    result = run_removal(root, stubs)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not launcher.exists()
    assert "purging" not in result.stdout


def test_the_layer_stops_when_the_purge_fails(tmp_path) -> None:
    """A distribution GAP apt could not purge stops the build, not slips past it."""
    root, stubs = fake_base(tmp_path, check_paths())
    result = run_removal(root, stubs, DPKG_GAP="installed", APT_PURGE_FAILS="true")
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert "E: the purge could not run" in result.stderr


def test_the_layer_stops_when_a_path_survives(tmp_path) -> None:
    """A removal that did not take is a failed layer, with the path named."""
    root, stubs = fake_base(tmp_path, check_paths())
    # rm that removes nothing: a path the layer cannot delete.
    stub(stubs, "rm", "import sys\nprint('rm did not run', file=sys.stderr)\n")
    result = run_removal(root, stubs)
    assert result.returncode != 0, (result.stdout, result.stderr)
    # The rebase makes the named path the fake root's; the message is the block's.
    assert f"{FORBIDDEN} survived the distribution-GAP removal" in result.stderr
