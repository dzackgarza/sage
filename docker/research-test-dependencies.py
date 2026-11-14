# Writes the test dependencies the research repositories declare into the image's
# own lock input (sage#37).
#
# `/sage/.venv` is built by `uv sync --frozen` from `uv.lock`, so a package is in
# the image only if the lock carries it, and the lock carries only what
# pyproject.toml asks for. The research repositories declare their test tooling
# for their own suites -- sage-extensions' `[dependency-groups] dev` is what makes
# `just test` pass `--timeout` to pytest -- and no such declaration reaches an
# environment built from this tree. Installing the two names the first defect
# happened to name would repair one repository and leave the next one to file its
# own issue, so the set is derived here instead: every repository of
# `docker/research-repositories.txt` that carries a `pyproject.toml` contributes
# the test dependencies it declares, this script writes them into
# `[dependency-groups] research-environment-tests`, and `uv lock` pins them.
#
# Which dependencies are the test ones, per repository:
#
#   * the `test` PEP 735 dependency group and the `test` optional-dependencies
#     extra, when it declares either -- the two spellings a project has for saying
#     which dependencies are its suite's;
#   * otherwise its `dev` group, which is where these repositories put the
#     tooling their own suite runs under (pytest and its plugins, coverage,
#     hypothesis). A repository that declares a `test` group has said which part
#     of `dev` is the suite's, and its linters and formatters stay out of the
#     image.
#
# What is not taken: a repository's runtime dependencies (the lock already takes
# those from its git source), and its other groups (`lint`, `migration`, `typing`
# -- not the suite's).
#
# Requirements that name a package this image sources (`[tool.uv.sources]`) lose
# the URL a repository spelled them as: the image decides where its packages come
# from, and a repository's `sage-stubs @ git+...@main` against the image's own
# source is two URLs for one package, which uv refuses. A URL for a package the
# image does not source is kept as declared: uv locks the commit it resolves, and
# `--frozen` then installs that one.

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

GROUP = "research-environment-tests"
BEGIN = "# >>> generated: research-environment-tests (docker/research-test-dependencies.py)"
END = "# <<< generated: research-environment-tests"


def normalize(name: str) -> str:
    return canonicalize_name(name)


def requirements_of_group(groups: dict, name: str, seen: tuple = ()) -> list[str]:
    """A dependency group's requirements, with PEP 735 `include-group` followed."""
    if name in seen:
        raise SystemExit(f"error: dependency group '{name}' includes itself: {' -> '.join((*seen, name))}")
    declared = groups.get(name)
    if declared is None:
        return []
    requirements = []
    for entry in declared:
        if isinstance(entry, dict):
            if "include-group" not in entry:
                raise SystemExit(f"error: group '{name}' holds {entry!r}, which names neither a requirement nor a group")
            requirements += requirements_of_group(groups, entry["include-group"], (*seen, name))
        else:
            requirements.append(entry)
    return requirements


def declared_test_dependencies(pyproject: Path) -> tuple[list[str], str]:
    """The test dependencies one repository declares, and where they were found."""
    document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    groups = document.get("dependency-groups", {})
    extras = document.get("project", {}).get("optional-dependencies", {})
    found = []
    where = []
    if "test" in groups:
        found += requirements_of_group(groups, "test")
        where.append("the test dependency group")
    if "test" in extras:
        found += list(extras["test"])
        where.append("the test extra")
    if found or where:
        return found, " and ".join(where)
    # `[tool.uv] dev-dependencies` is the spelling uv reads as the `dev` group's
    # (its documentation says the two are combined), and a repository that has not
    # migrated to PEP 735 keeps its suite's tooling there.
    found = requirements_of_group(groups, "dev") + list(
        document.get("tool", {}).get("uv", {}).get("dev-dependencies", [])
    )
    return found, "the dev dependency group" if found else "no test dependencies"


# The order a specifier set is written in: what the package must be, then what it
# must not be above.
CLAUSE_ORDER = {">=": 0, ">": 1, "==": 2, "~=": 2, "<=": 3, "<": 4, "!=": 5}


class Merge:
    """One requirement per package name, holding every repository's declaration.

    Two repositories that both declare `pytest` are asking for both specifiers at
    once, and a group entry can carry the conjunction: the clauses are kept in the
    order the declarations reached them, and the extras are united, because an
    extra is code the package only provides when asked and both askers need it.
    """

    def __init__(self, sourced: set[str]) -> None:
        self.sourced = sourced
        self.entries: dict[tuple[str, tuple[str, ...]], dict] = {}

    def add(self, repository: str, text: str) -> None:
        try:
            requirement = Requirement(text)
        except InvalidRequirement as error:
            raise SystemExit(f"error: {repository} declares {text!r}, which is not a requirement: {error}")
        name = normalize(requirement.name)
        # A URL for a package the image sources is the image's to decide: the
        # repository's copy is the one under /repos, installed over it as an
        # editable checkout, and uv refuses two URLs for one name.
        url = None if name in self.sourced else requirement.url
        extras = tuple(sorted({normalize(extra) for extra in requirement.extras}))
        key = (name, extras)
        entry = self.entries.setdefault(key, {
            "name": requirement.name, "url": url, "clauses": [], "markers": set(), "repositories": [],
        })
        entry["repositories"].append(repository)
        if entry["url"] != url and url is not None:
            raise SystemExit(
                f"error: {repository} declares {name} as {url}, but the declarations of "
                f"{', '.join(entry['repositories'][:-1])} name no URL for it: one requirement "
                "cannot be both"
            )
        for written in str(requirement.specifier).split(","):
            if written.strip() and written.strip() not in entry["clauses"]:
                entry["clauses"].append(written.strip())
        entry["markers"].add(str(requirement.marker) if requirement.marker else "")

    def lines(self) -> list[str]:
        lines = []
        for (name, extras), entry in sorted(self.entries.items()):
            # packaging prints a specifier set upper bound first (`<10,>=9.1`);
            # a group reads as the declaration did (`>=9.1,<10`).
            entry["clauses"].sort(key=lambda clause: CLAUSE_ORDER.get(clause[:2], 2))
            if len(entry["markers"]) > 1:
                raise SystemExit(
                    f"error: {name} is declared with different markers by "
                    f"{', '.join(entry['repositories'])} ({', '.join(sorted(entry['markers']))}); "
                    "one group entry cannot hold both"
                )
            marker = next(iter(entry["markers"]))
            line = name
            if extras:
                line += f"[{','.join(extras)}]"
            if entry["clauses"]:
                line += ",".join(entry["clauses"])
            if entry["url"]:
                line += f" @ {entry['url']}"
            if marker:
                line += f"; {marker}"
            lines.append(line)
        return lines


def collect(tree: Path, repositories_root: Path, report=None) -> list[str]:
    """Every research repository's declared test dependencies, merged."""
    image = tomllib.loads((tree / "pyproject.toml").read_text(encoding="utf-8"))
    sourced = {normalize(name) for name in image.get("tool", {}).get("uv", {}).get("sources", {})}
    merge = Merge(sourced)
    urls = [
        line.strip() for line in (tree / "docker" / "research-repositories.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for url in urls:
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        pyproject = repositories_root / name / "pyproject.toml"
        if not pyproject.is_file():
            if report is not None:
                report(f"{name}: no pyproject.toml, so nothing declared")
            continue
        declared, where = declared_test_dependencies(pyproject)
        if report is not None:
            report(f"{name}: {len(declared)} from {where}")
        for text in declared:
            merge.add(name, text)
    return merge.lines()


def block(lines: list[str]) -> str:
    return "\n".join([BEGIN, f"{GROUP} = [", *(f'  "{line}",' for line in lines), "]", END])


def block_in(text: str) -> str | None:
    start = text.find(BEGIN)
    if start < 0:
        return None
    end = text.find(END, start)
    if end < 0:
        raise SystemExit(f"error: pyproject.toml has {BEGIN!r} without {END!r}")
    return text[start:end + len(END)]


def rewrite(tree: Path, lines: list[str]) -> bool:
    """Put the block in the dependency-groups table; say whether it changed."""
    path = tree / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    current = block(lines)
    existing = block_in(text)
    if existing == current:
        return False
    if existing is not None:
        text = text.replace(existing, current, 1)
    else:
        # The block belongs to [dependency-groups], so it goes after that table's
        # last setting -- still inside the table, and above whatever comment
        # introduces the table after it.
        lines = text.split("\n")
        header = lines.index("[dependency-groups]") if "[dependency-groups]" in lines else None
        if header is None:
            raise SystemExit("error: pyproject.toml has no [dependency-groups] table")
        following = next((index for index in range(header + 1, len(lines)) if lines[index].startswith("[")), None)
        if following is None:
            raise SystemExit("error: [dependency-groups] is the last table of pyproject.toml")
        last = following - 1
        while last > header and (not lines[last].strip() or lines[last].lstrip().startswith("#")):
            last -= 1
        # What sits between the table's last setting and the next table header
        # is that next table's own comment, and it stays where it is.
        inserted = lines[: last + 1] + ["", *current.split("\n"), ""] + lines[last + 1:]
        # One blank line after the block, whether or not a comment follows it.
        text = re.sub(re.escape(END) + r"\n\n+", END + "\n\n", "\n".join(inserted))
    path.write_text(text, encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "the research repositories' test dependencies")
    parser.add_argument("--tree", type=Path, default=Path(__file__).resolve().parents[1],
                        help="the image's tree (default: the one this script is in)")
    parser.add_argument("--repositories-root", type=Path, default=None,
                        help="where the research repositories are checked out (default: $REPOSITORIES_ROOT, then /repos)")
    parser.add_argument("--write", action="store_true",
                        help=f"write the requirements into pyproject.toml's {GROUP} group")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when pyproject.toml's group is not what the repositories declare")
    arguments = parser.parse_args(argv)

    root = arguments.repositories_root
    if root is None:
        root = Path(os.environ.get("REPOSITORIES_ROOT", "/repos"))
    tree = arguments.tree.resolve()

    def report(line: str) -> None:
        print(line, file=sys.stderr)

    lines = collect(tree, root, report)
    if arguments.write:
        changed = rewrite(tree, lines)
        print(f"{GROUP}: {len(lines)} requirements, {'written' if changed else 'already up to date'}", file=sys.stderr)
    if arguments.check:
        current = block_in((tree / "pyproject.toml").read_text(encoding="utf-8"))
        if current != block(lines):
            print(f"error: pyproject.toml's {GROUP} is not what the research repositories declare:", file=sys.stderr)
            print(block(lines), file=sys.stderr)
            return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
