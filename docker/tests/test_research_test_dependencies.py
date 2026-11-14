"""The image installs the test dependencies the research repositories declare (sage#37).

A research checkout's own pytest configuration names the options its suite runs
with -- sage-extensions' addopts pass ``--timeout=60 --timeout-method=signal`` and
``--report-log=...`` -- and pytest refuses an option no installed plugin
registered, before collection:

    python -m pytest: error: unrecognized arguments: --timeout=60 ...

The image carried neither pytest-timeout nor pytest-reportlog, and no hand list of
two names repairs that class: the next repository declares its own. So the set is
derived from the declarations (``docker/research-test-dependencies.py``), written
into pyproject.toml's ``research-environment-tests`` group, and pinned by
``uv.lock``, which is what the image's ``uv sync --frozen`` installs.

These tests run the real script over fixture checkouts and over this tree: which
requirements a declaration produces, how a URL a repository spells resolves
against the image's own sources, that the block it writes is the block it reads
back, and that everything the committed group asks for is pinned by this
repository's lock.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "docker" / "research-test-dependencies.py"
GROUP = "research-environment-tests"

IMAGE_PYPROJECT = """[project]
name = "sagemath"
version = "0.0.0"
requires-python = ">=3.14"

[dependency-groups]
research-environment = ["dzack-research"]

# dzack-research is installed from its checkout under /repos, not from an index.
[tool.uv.sources]
dzack-research = { git = "https://github.com/dzackgarza/research" }
sage-stubs = { git = "https://github.com/dzackgarza/sage-stubs.git" }
"""

REPOSITORIES = """\
https://github.com/dzackgarza/research
https://github.com/dzackgarza/sage-extensions
https://github.com/dzackgarza/jupyter-mcp-server
https://github.com/dzackgarza/lattice-database
https://github.com/dzackgarza/lean-categories
"""

CHECKOUTS = {
    # A `test` group: the suite's, and the linters the same project keeps in `dev`
    # stay out of the image.
    "research": """[project]
name = "dzack-research"
version = "0.1.0"

[dependency-groups]
test = ["coverage>=7.10", "pytest-asyncio"]
dev = ["mdformat>0.7", "ruff"]
""",
    # No `test` group: `dev` is where this repository puts its pytest plugins, and
    # a URL for a package the image sources loses to the image's own source.
    "sage-extensions": """[project]
name = "sage-extensions"
version = "0.1.0"

[dependency-groups]
dev = [
    "pytest-timeout>=2.4.0",
    "sage-stubs @ git+https://github.com/dzackgarza/sage-stubs.git@main",
]
""",
    # A `test` extra and a `test` group, a group included by another, and a URL for
    # a package the image does not source -- which stays as declared. The inclusion
    # is in the group: an extra holds requirements, and PEP 735's `include-group`
    # is a dependency group's entry only.
    "jupyter-mcp-server": """[project]
name = "jupyter-mcp-server"
version = "0.1.0"

[project.optional-dependencies]
test = [
    "microsoft-python-type-stubs @ git+https://github.com/dzackgarza/python-type-stubs.git@main",
]

[dependency-groups]
test = [{ include-group = "unit" }]
unit = ["pytest-cov>=7.0"]
""",
    # Two repositories declaring one requirement: both specifiers hold at once.
    "lattice-database": """[project]
name = "latticedb"
version = "0.1.0"

[dependency-groups]
dev = ["pytest>=9.1,<10", "types-PyYAML>=6"]
""",
    # A Lean repository with no pyproject.toml declares nothing and is skipped.
}

EXPECTED = [
    "coverage>=7.10",
    "microsoft-python-type-stubs @ git+https://github.com/dzackgarza/python-type-stubs.git@main",
    "pytest>=9.1,<10",
    "pytest-asyncio",
    "pytest-cov>=7.0",
    "pytest-timeout>=2.4.0",
    "sage-stubs",
    "types-pyyaml>=6",
]


def build(root: Path) -> tuple[Path, Path]:
    """A tree with an image pyproject, its repository list, and the checkouts."""
    image = root / "image"
    (image / "docker").mkdir(parents=True)
    (image / "pyproject.toml").write_text(IMAGE_PYPROJECT, encoding="utf-8")
    (image / "docker" / "research-repositories.txt").write_text(REPOSITORIES, encoding="utf-8")
    checkouts = root / "repos"
    checkouts.mkdir()
    for name, pyproject in CHECKOUTS.items():
        (checkouts / name).mkdir()
        (checkouts / name / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return image, checkouts


def run(image: Path, checkouts: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--tree", str(image), "--repositories-root", str(checkouts), *arguments],
        capture_output=True, text=True, check=False,
    )


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path]:
    return build(tmp_path / "fixture")


def test_each_repository_contributes_the_test_dependencies_it_declares(tree):
    """`test` group or extra where declared, `dev` otherwise, merged by package."""
    image, checkouts = tree
    result = run(image, checkouts)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == EXPECTED


def test_the_legacy_dev_dependencies_field_is_the_dev_group(tmp_path):
    """`[tool.uv] dev-dependencies` is where an unmigrated repository keeps its plugins."""
    image, checkouts = build(tmp_path / "fixture")
    (checkouts / "vinal").mkdir()
    (checkouts / "vinal" / "pyproject.toml").write_text(
        '[project]\nname = "vinal"\nversion = "0.1.0"\n\n'
        '[tool.uv]\ndev-dependencies = ["pytest-randomly"]\n',
        encoding="utf-8",
    )
    (image / "docker" / "research-repositories.txt").write_text(
        REPOSITORIES + "https://github.com/dzackgarza/vinal\n", encoding="utf-8",
    )
    result = run(image, checkouts)
    assert result.returncode == 0, result.stderr
    assert "pytest-randomly" in result.stdout.splitlines(), result.stdout
    assert "vinal: 1 from the dev dependency group" in result.stderr, result.stderr


def test_the_provenance_of_each_requirement_is_reported(tree):
    """Every repository says which declaration its requirements came from."""
    image, checkouts = tree
    result = run(image, checkouts)
    assert "sage-extensions: 2 from the dev dependency group" in result.stderr, result.stderr
    assert "research: 2 from the test dependency group" in result.stderr, result.stderr
    assert "lean-categories: no pyproject.toml" in result.stderr, result.stderr


def test_the_block_is_written_into_the_dependency_groups_table(tree):
    """The generated group lands inside the table, above the next table's comment."""
    import re

    image, checkouts = tree
    result = run(image, checkouts, "--write")
    assert result.returncode == 0, result.stderr
    text = (image / "pyproject.toml").read_text(encoding="utf-8")
    document = tomllib.loads(text)
    assert document["dependency-groups"][GROUP] == EXPECTED
    # Not after [tool.uv.sources]: a key there is a source, not a group.
    assert text.index(GROUP) < text.index("[tool.uv.sources]"), text
    assert re.search(rf"{GROUP} = \[\n(  \".*\",\n)+\]", text), text


def test_writing_twice_changes_nothing_and_check_agrees(tree):
    """The generator's own output is what `--check` accepts."""
    image, checkouts = tree
    assert run(image, checkouts, "--write").returncode == 0
    once = (image / "pyproject.toml").read_text(encoding="utf-8")
    assert "already up to date" in run(image, checkouts, "--write").stderr
    assert (image / "pyproject.toml").read_text(encoding="utf-8") == once
    assert run(image, checkouts, "--check").returncode == 0


def test_a_declaration_the_group_does_not_carry_fails_check(tree):
    """A repository that adds a test dependency is a difference `--check` reports."""
    image, checkouts = tree
    assert run(image, checkouts, "--write").returncode == 0
    pyproject = checkouts / "lattice-database" / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace('"types-PyYAML>=6"', '"types-PyYAML>=6", "pytest-randomly"'),
        encoding="utf-8",
    )
    result = run(image, checkouts, "--check")
    assert result.returncode == 1
    assert "pytest-randomly" in result.stderr, result.stderr


def test_the_committed_group_is_pinned_by_this_repositorys_lock():
    """Every requirement the image installs is a package uv.lock carries.

    `uv sync --frozen` installs what the lock holds and nothing else, so a group
    entry the lock does not carry is not installed at all -- the shape of the
    defect: a plugin a repository names and the image's environment has not.
    """
    image = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = [Requirement(line) for line in image["dependency-groups"][GROUP]]
    assert requirements, f"pyproject.toml declares no {GROUP} group"
    locked = {
        package["name"]: package["version"]
        for package in tomllib.loads((REPOSITORY / "uv.lock").read_text(encoding="utf-8"))["package"]
        if "version" in package
    }
    unpinned = [requirement.name for requirement in requirements if requirement.name not in locked]
    assert not unpinned, unpinned
    unsatisfied = [
        f"{requirement.name} {locked[requirement.name]} {requirement.specifier}"
        for requirement in requirements
        if not requirement.specifier.contains(locked[requirement.name], prereleases=True)
    ]
    assert not unsatisfied, unsatisfied


def test_the_venv_recipe_syncs_the_generated_group():
    """The group reaches an image only through the sync the build runs."""
    import re

    justfile = (REPOSITORY / "justfile").read_text(encoding="utf-8")
    # The recipe's body: everything after its name, up to the next recipe, which
    # is the next line that starts in the first column.
    recipe = re.split(r"\n(?=\S)", justfile.split("research-environment-venv:", 1)[1])[0]
    assert f"--group {GROUP}" in recipe, recipe


# ---- the check's own block, out of the real file -------------------------------

CHECK = REPOSITORY / "docker" / "research-environment-check.py"
BLOCK_START = "# ---- the research repositories' test dependencies (sage#37)"
BLOCK_END = "# ---- end: the research repositories' test dependencies"

# What the block imports from the check's earlier lines, and what it asks the
# environment: a distribution's version and its entry points, and pytest's own
# report of the plugins it registered. Both are substituted -- the test says which
# packages exist and which plugins pytest loads -- and nothing else is simulated:
# the block runs out of the file, with the image's paths pointed at a fixture.
PRELUDE = '''
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from importlib.metadata import PackageNotFoundError


class EntryPoint:
    def __init__(self, group, value):
        self.group = group
        self.value = value


class Distribution:
    def __init__(self, version, plugins):
        self.version = version
        self.entry_points = [EntryPoint("pytest11", plugin) for plugin in plugins]


def distribution(name):
    if name not in INSTALLED:
        raise PackageNotFoundError(name)
    return INSTALLED[name]


class Probe:
    def __init__(self, stdout):
        self.returncode = 5
        self.stdout = stdout
        self.stderr = ""


def run(arguments, **options):
    return Probe("".join(
        f"PLUGIN registered: <module {module!r} from '/sage/.venv/lib/x.py'>\\n"
        for module in REGISTERED
    ))
'''.lstrip("\n").replace("subprocess.run", "x")

# The pytest probe is what the block calls; `run` stands in for it, and the
# substitution is made explicit here rather than hidden in the prelude.
PROBE_STUB = "subprocess.run = run\n"

GROUP_FIXTURE = '''[project]
name = "sagemath"
version = "0.0.0"
requires-python = ">=3.14"

[dependency-groups]
research-environment-tests = [
  "pytest>=9.1,<10",
  "pytest-timeout>=2.4.0",
  "sage-stubs",
]

[tool.uv.sources]
sage-stubs = { git = "https://github.com/dzackgarza/sage-stubs.git" }
'''

INSTALLED_FIXTURE = (
    'INSTALLED = {\n'
    '    "pytest": Distribution("9.1.1", []),\n'
    '    "pytest-timeout": Distribution("2.4.0", ["pytest_timeout"]),\n'
    '    "sage-stubs": Distribution("10.7.0", []),\n'
    '}\n'
    'REGISTERED = ["pytest_timeout"]\n'
)


def check_block() -> str:
    """The check's test-dependency block, as the image runs it."""
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index(BLOCK_START):text.index(BLOCK_END) + len(BLOCK_END)]
    assert "research-environment-tests" in block, block[:200]
    return block


def run_check_block(tmp_path: Path, installed: str = INSTALLED_FIXTURE,
                    checkouts: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """The block over a fixture image tree, with the environment it reads stubbed."""
    tree = tmp_path / "sage"
    (tree / "docker").mkdir(parents=True)
    (tree / "pyproject.toml").write_text(GROUP_FIXTURE, encoding="utf-8")
    (tree / "docker" / "research-repositories.txt").write_text(
        "https://github.com/dzackgarza/sage-extensions\n", encoding="utf-8",
    )
    repos = tmp_path / "repos"
    for name, pyproject in (checkouts if checkouts is not None else
                            {"sage-extensions": '[project]\nname = "sage-extensions"\n'}).items():
        (repos / name).mkdir(parents=True, exist_ok=True)
        (repos / name / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    block = check_block().replace(
        '"/sage/pyproject.toml"', repr(str(tree / "pyproject.toml"))
    ).replace(
        '"/sage/docker/research-test-dependencies.py"',
        repr(str(REPOSITORY / "docker" / "research-test-dependencies.py")),
    ).replace(
        'Path("/sage")', f"Path({str(tree)!r})"
    ).replace(
        'Path("/repos")', f"Path({str(repos)!r})"
    )
    for image_path in ('Path("/repos")', 'Path("/sage")', '"/sage/pyproject.toml"'):
        assert image_path not in block, (image_path, block)
    harness = tmp_path / "check-test-dependencies.py"
    harness.write_text(PRELUDE + PROBE_STUB + installed + "\n" + block, encoding="utf-8")
    return subprocess.run([sys.executable, str(harness)], capture_output=True, text=True, check=False)


def test_the_check_passes_and_reports_the_declared_dependencies(tmp_path):
    result = run_check_block(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "the research test dependencies: 3 installed" in result.stdout, result.stdout
    assert "pytest loads 1 of them as plugins: pytest-timeout" in result.stdout, result.stdout


def test_a_declared_dependency_the_venv_lacks_fails_the_check_naming_it(tmp_path):
    """The defect: a plugin a repository declares and the environment has not."""
    installed = INSTALLED_FIXTURE.replace(
        '    "pytest-timeout": Distribution("2.4.0", ["pytest_timeout"]),\n', ""
    ).replace('REGISTERED = ["pytest_timeout"]', "REGISTERED = []")
    result = run_check_block(tmp_path, installed=installed)
    assert result.returncode != 0, result.stdout
    assert "pytest-timeout" in result.stderr, result.stderr
    assert "the venv does not have it" in result.stderr, result.stderr


def test_a_version_the_declaration_forbids_fails_the_check(tmp_path):
    installed = INSTALLED_FIXTURE.replace('Distribution("2.4.0"', 'Distribution("1.0.0"')
    result = run_check_block(tmp_path, installed=installed)
    assert result.returncode != 0, result.stdout
    assert "does not satisfy >=2.4.0" in result.stderr, result.stderr


def test_a_plugin_pytest_does_not_register_fails_the_check(tmp_path):
    """Installed is not loaded: pytest refuses the option of an unregistered plugin."""
    installed = INSTALLED_FIXTURE.replace('REGISTERED = ["pytest_timeout"]', "REGISTERED = []")
    result = run_check_block(tmp_path, installed=installed)
    assert result.returncode != 0, result.stdout
    assert "pytest-timeout (pytest_timeout)" in result.stderr, result.stderr


def test_a_declaration_the_group_does_not_carry_is_a_note_not_a_failure(tmp_path):
    """A repository's new plugin is a relock, and must not stop a build publishing."""
    checkouts = {"sage-extensions": '[project]\nname = "sage-extensions"\n\n'
                                    '[dependency-groups]\ndev = ["pytest-timeout>=2.4.0", "pytest-randomly"]\n'}
    result = run_check_block(tmp_path, checkouts=checkouts)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "note:" in result.stdout and "pytest-randomly" in result.stdout, result.stdout
