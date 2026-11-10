"""One GAP in the image, and the Sage launcher where an emptied PATH looks (sage#11, sage#24, sage#26).

Run 42910347791 stopped a full build at the environment check with

    AssertionError: a distribution GAP is still installed: ['/usr/bin/gap']

and the file at that path was not Debian's: it was this image's own launcher
(`docker/gap-launcher.sh`, `exec /sage/.venv/bin/gap "$@"`), copied there in
ac455b94fb so that a process with no PATH at all -- Python's `/bin:/usr/bin`
fallback, which is what `env -i` resolves `gap` through -- reaches the Sage-owned
GAP (sage#24). The check asserted the path, so the launcher read as a distribution
GAP; fc971cae answered by deleting the COPY, which removed sage#24's function to
pass a check. That is the wrong trade, and sage#26 reverses it.

What is asserted here, with no image:

* both Dockerfiles copy the launcher to /usr/local/bin/gap *and* /usr/bin/gap, so
  every image -- full or incremental -- carries it;
* the check's GAP decision, run out of the real file against a fake root: a launcher
  at /usr/bin/gap passes, and a distribution GAP fails -- by the package that owns a
  path (`dpkg-query -S`), by the apt package list, by the distribution tree's
  presence, and by /usr/bin/gap holding anything but the launcher;
* the incremental Dockerfile's removal layer takes a base's distro GAP and stops
  when the purge fails or a path survives, and its absence list is the check's own
  distribution tree.

The check's block runs with "/usr/" rebased into a temporary root, and `__file__`
pointing at the check, so its launcher comparison reads this repository's
docker/gap-launcher.sh; the rebase is uniform, so it cannot hide which path is
being decided.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
DOCKER = REPOSITORY / "docker"
FULL = DOCKER / "research-environment.Dockerfile"
INCREMENTAL = DOCKER / "research-environment-incremental.Dockerfile"
CHECK = DOCKER / "research-environment-check.py"
LAUNCHER = DOCKER / "gap-launcher.sh"

REMOVAL_START = 'RUN purged="$(dpkg-query'
CHECK_BLOCK_START = "# Exactly one GAP: the one built from the pinned source"
CHECK_BLOCK_END = "# The probe that found sage#11"
LAUNCHER_PATH = "/usr/bin/gap"


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
    start = next(index for index, line in enumerate(lines) if line.startswith(REMOVAL_START))
    block = []
    for line in lines[start:]:
        block.append(line)
        if not line.endswith("\\"):
            break
    return "\n".join(block)


def one_line(block: str) -> str:
    """The block with continuations and newlines collapsed, for reading its words."""
    return " ".join(block.replace("\\\n", " ").split())


def removal_body(root: Path) -> str:
    """The removal block's shell, with every /usr path under `root`, RUN removed."""
    body = removal_block().split(" ", 1)[1]
    assert body.count("/usr/") >= 4, body
    return body.replace("/usr/", f"{root}/usr/")


def removal_paths() -> list[str]:
    """The paths the removal layer stops on, in the block's order."""
    listed = re.search(r"for path in (.*?); do", one_line(removal_block()))
    assert listed, removal_block()
    return listed.group(1).split()


def check_gap_block(root: Path) -> str:
    """The check's GAP decision, with every /usr path under `root`."""
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index(CHECK_BLOCK_START):text.index(CHECK_BLOCK_END)]
    assert "distribution" in block and "dpkg-query" in block, block[:200]
    return block.replace("/usr/", f"{root}/usr/")


def check_tree_paths() -> list[str]:
    """The distribution GAP tree the check requires absent, in its order."""
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index("debian_gap_tree = ("):]
    block = block[:block.index(")")]
    return re.findall(r'"(/usr/[^"]*)"', block)


def stub(directory: Path, name: str, body: str) -> None:
    """A stand-in for one command: a Python script, so no PATH is needed to run it."""
    path = directory / name
    path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    path.chmod(0o755)


DPKG_QUERY = (
    "import os, sys\n"
    "args = sys.argv[1:]\n"
    "if '-S' in args:\n"
    "    path = args[-1]\n"
    "    if path in os.environ.get('DPKG_OWNED', '').split(':'):\n"
    "        print('gap-core: ' + path)\n"
    "        raise SystemExit(0)\n"
    "    print('dpkg-query: no path found matching pattern ' + path, file=sys.stderr)\n"
    "    raise SystemExit(1)\n"
    "if '-W' in args:\n"
    "    if os.environ.get('DPKG_GAP') == 'installed':\n"
    "        print('gap-core install ok installed')\n"
    "        raise SystemExit(0)\n"
    "    print('dpkg-query: no packages found matching gap*', file=sys.stderr)\n"
    "    raise SystemExit(1)\n"
    "raise SystemExit(0)\n"
)

APT_GET = (
    "import os, sys, pathlib, shutil\n"
    "root = pathlib.Path(os.environ['FAKE_ROOT'])\n"
    "assert sys.argv[1] == 'purge', sys.argv\n"
    "if os.environ.get('APT_PURGE_FAILS') == 'true':\n"
    "    print('E: the purge could not run', file=sys.stderr)\n"
    "    raise SystemExit(100)\n"
    "for path in ('usr/bin/gap', 'usr/lib/gap', 'usr/share/gap',\n"
    "             'usr/lib/x86_64-linux-gnu/libgap.so.9'):\n"
    "    target = root / path\n"
    "    if target.is_dir():\n"
    "        shutil.rmtree(target)\n"
    "    else:\n"
    "        target.unlink(missing_ok=True)\n"
    "for name in sys.argv[2:]:\n"
    "    if name != '-y':\n"
    "        print('Removing ' + name)\n"
)


def fake_root(tmp_path: Path, files: dict[str, bytes]) -> tuple[Path, Path]:
    """A published base's filesystem, and the commands the image runs against it."""
    root = tmp_path / "base"
    for path, content in files.items():
        target = root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.decode("utf-8", "replace"), encoding="utf-8")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    stub(stubs, "dpkg-query", DPKG_QUERY)
    stub(stubs, "apt-get", APT_GET)
    return root, stubs


def run_check_gap(root: Path, stubs: Path, monkeypatch, **environment: str) -> None:
    """The check's GAP decision, on the fake root; an AssertionError is its verdict."""
    monkeypatch.setenv("PATH", f"{stubs}:/usr/local/bin:/usr/bin:/bin")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    namespace = {"__file__": str(CHECK), "Path": Path, "subprocess": subprocess}
    exec(compile(check_gap_block(root), "<check-gap>", "exec"), namespace)  # noqa: S102


def run_removal(root: Path, stubs: Path, **environment: str) -> subprocess.CompletedProcess:
    """The removal layer, on the fake base."""
    return subprocess.run(
        ["bash", "-c", removal_body(root)],
        capture_output=True, text=True, check=False,
        env={"PATH": f"{stubs}:/usr/local/bin:/usr/bin:/bin",
             "FAKE_ROOT": str(root), **environment},
    )


def test_both_dockerfiles_install_the_launcher_at_both_paths() -> None:
    """Every build path writes the launcher, at /usr/local/bin and at /usr/bin."""
    for dockerfile in (FULL, INCREMENTAL):
        destinations = copy_destinations(dockerfile)
        assert "/usr/local/bin/gap" in destinations, (dockerfile.name, destinations)
        assert LAUNCHER_PATH in destinations, (dockerfile.name, destinations)


def test_a_launcher_at_usr_bin_is_the_images_gap(tmp_path, monkeypatch) -> None:
    """sage#24's launcher passes the check's distribution-GAP test."""
    root, stubs = fake_root(tmp_path, {LAUNCHER_PATH: LAUNCHER.read_bytes()})
    run_check_gap(root, stubs, monkeypatch)


def test_a_debian_gap_fails_on_the_package_that_owns_it(tmp_path, monkeypatch) -> None:
    """A path a Debian package installed is a distribution GAP, whatever it holds."""
    root, stubs = fake_root(tmp_path, {
        LAUNCHER_PATH: b"GAP 4.14 binary\n",
        "/usr/share/gap/lib/init.g": b"",
    })
    with pytest.raises(AssertionError) as failure:
        run_check_gap(root, stubs, monkeypatch,
                      DPKG_OWNED=":".join(
                          str(root / path.lstrip("/"))
                          for path in (LAUNCHER_PATH, "/usr/share/gap")
                      ),
                      DPKG_GAP="installed")
    assert "installed by a Debian package" in str(failure.value)
    assert "gap-core" in str(failure.value)


def test_a_binary_at_usr_bin_that_is_not_the_launcher_fails(tmp_path, monkeypatch) -> None:
    """An unowned /usr/bin/gap that is not this image's launcher is still a GAP."""
    root, stubs = fake_root(tmp_path, {LAUNCHER_PATH: b"GAP 4.14 binary\n"})
    with pytest.raises(AssertionError) as failure:
        run_check_gap(root, stubs, monkeypatch)
    assert "not this image's launcher" in str(failure.value)


def test_a_distribution_tree_without_a_package_still_fails(tmp_path, monkeypatch) -> None:
    """The distribution tree's presence alone fails, package database or not."""
    root, stubs = fake_root(tmp_path, {
        LAUNCHER_PATH: LAUNCHER.read_bytes(),
        "/usr/lib/gap/pkg": b"",
    })
    with pytest.raises(AssertionError) as failure:
        run_check_gap(root, stubs, monkeypatch)
    assert "holds a GAP that is not the image's" in str(failure.value)


def test_a_missing_launcher_fails(tmp_path, monkeypatch) -> None:
    """With no launcher, an emptied environment has no `gap` at all: a failure."""
    root, stubs = fake_root(tmp_path, {})
    with pytest.raises(AssertionError) as failure:
        run_check_gap(root, stubs, monkeypatch)
    assert "/usr/bin/gap is missing" in str(failure.value)


def test_the_removal_layer_asserts_the_checks_distribution_tree() -> None:
    """The layer stops on exactly the distribution tree the check requires absent."""
    assert removal_paths() == check_tree_paths()
    assert LAUNCHER_PATH not in removal_paths()


def test_the_removal_layer_takes_a_debian_gap(tmp_path) -> None:
    """Purged, removed: a base's distro GAP does not survive into the image."""
    root, stubs = fake_root(tmp_path, {
        LAUNCHER_PATH: b"GAP 4.14 binary\n",
        "/usr/lib/gap/pkg": b"",
        "/usr/share/gap/lib/init.g": b"",
        "/usr/lib/x86_64-linux-gnu/libgap.so.9": b"",
    })
    result = run_removal(root, stubs, DPKG_GAP="installed")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.startswith("purging the distribution GAP: gap-core"), result.stdout
    assert not [path for path in removal_paths() if (root / path.lstrip("/")).exists()]
    # /usr/bin/gap goes too: the COPY in the Dockerfile writes this tree's launcher.
    assert not (root / LAUNCHER_PATH.lstrip("/")).exists()


def test_the_layer_stops_when_the_purge_fails(tmp_path) -> None:
    """A distribution GAP apt could not purge stops the build, not slips past it."""
    root, stubs = fake_root(tmp_path, {"/usr/lib/gap": b""})
    result = run_removal(root, stubs, DPKG_GAP="installed", APT_PURGE_FAILS="true")
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert "E: the purge could not run" in result.stderr


def test_the_layer_stops_when_a_path_survives(tmp_path) -> None:
    """A removal that did not take is a failed layer, with the path named."""
    root, stubs = fake_root(tmp_path, {"/usr/lib/gap": b""})
    # rm that removes nothing: a path the layer cannot delete.
    stub(stubs, "rm", "import sys\nprint('rm did not run', file=sys.stderr)\n")
    result = run_removal(root, stubs)
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert "/usr/lib/gap survived the distribution-GAP removal" in result.stderr
