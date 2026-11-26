import importlib
import os
import subprocess
import sys
import tempfile
from importlib.metadata import requires as distribution_requires
from pathlib import Path

from sage.features.all import all_features
from sage.features.gap import GapPackage
from sage.features.interfaces import Macaulay2
from sage.all import Graph, graphs, var, ZZ, QQ
from sage_extensions.all import Lattices
from sage_julia_bridge import julia

subprocess.run([
    "python", "-c", "import sys, sage.all; assert sys.prefix == '/sage/.venv'",
], check=True)

registered = {feature.name: feature for feature in all_features()}
features = [registered[name] for name in (
    "4ti2", "bliss", "database_graphs", "giac", "jupymake", "latte_int",
    "libbraiding", "libhomfly", "lrcalc_python", "lrslib", "msolve",
    "pycosat", "pynormaliz", "python_igraph", "rankwidth", "sage.symbolic",
    "topcom",
)]
features.append(Macaulay2())
features += [GapPackage(name) for name in (
    "atlasrep", "design", "genss", "grape", "guava", "hap", "polenta",
    "polycyclic", "recog",
)]
missing = [feature.name for feature in features if not feature.is_present()]
assert not missing, missing

from sage.libs.gap.libgap import libgap
from sage.libs.gap.util import kernel_info

import shutil

declared_gap = Path("build/pkgs/gap/package-version.txt").read_text().strip()
gap_binary = shutil.which("gap")
assert gap_binary is not None, "no gap on PATH"
assert Path(gap_binary).resolve().is_relative_to(Path("/sage/.venv")), gap_binary

launcher_bytes = Path(sys.argv[0]).resolve().with_name("gap-launcher.sh").read_bytes()
every_gap = [
    Path(directory) / "gap"
    for directory in os.environ.get("PATH", "").split(os.pathsep)
    if (Path(directory) / "gap").exists()
]
assert every_gap, "the default PATH carries no gap at all"
for candidate in every_gap:
    assert candidate.read_bytes() == launcher_bytes or candidate.resolve().is_relative_to(
        Path("/sage/.venv")
    ), f"{candidate} is a GAP the image does not own (sage#26)"
print(
    "every gap on the default PATH resolves to the Sage-owned GAP; "
    f"libgap and gap report {declared_gap}"
)

gap_version, gap_arch, gap_roots = kernel_info()
assert gap_version == declared_gap, (gap_version, declared_gap)
assert "/sage/.venv/lib/gap/" in gap_roots, gap_roots
gap_root_list = [root for root in gap_roots.split(";") if root]
for name in ("orb", "forms", "genss", "recog"):
    loaded = libgap.eval(f'LoadPackage("{name}")')
    assert loaded.sage() is True, (name, loaded)
    installed_in = str(libgap.eval(f'PackageInfo("{name}")[1].InstallationPath'))
    assert any(installed_in.startswith(root) for root in gap_root_list), (
        name, installed_in, gap_root_list,
    )
loaded_libgap = [
    line.split()[-1]
    for line in Path("/proc/self/maps").read_text().splitlines()
    if "libgap.so" in line and line.split()[-1].startswith("/")
]
assert loaded_libgap, "no libgap mapped into this process"
assert all(path.startswith("/sage/.venv/lib/") for path in loaded_libgap), loaded_libgap

launcher_path = "/usr/bin/gap"
debian_gap_tree = (
    "/usr/lib/gap",
    "/usr/share/gap",
    "/usr/lib/x86_64-linux-gnu/libgap.so.9",
)
present = [
    path for path in (launcher_path, *debian_gap_tree) if Path(path).exists()
]
owned = []
for path in present:
    ownership = subprocess.run(
        ["dpkg-query", "-S", path], capture_output=True, text=True, check=False,
    )
    if ownership.returncode == 0:
        owned.append(ownership.stdout.strip() or path)
assert not owned, f"a distribution GAP is installed by a Debian package: {owned}"
apt_gap = sorted(
    line.split()[0]
    for line in subprocess.run(
        ["dpkg-query", "-W", "-f=${Package} ${Status}\n", "gap*", "libgap*"],
        capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    if line.endswith(" install ok installed")
)
assert not apt_gap, f"apt still carries GAP packages: {apt_gap}"
for path in debian_gap_tree:
    assert not Path(path).exists(), f"{path} holds a GAP that is not the image's: {path}"
launcher = Path(sys.argv[0]).resolve().with_name("gap-launcher.sh").read_bytes()
assert Path(launcher_path).is_file(), (
    "/usr/bin/gap is missing: a process whose environment did not come from this image "
    "has no `gap` at all (sage#24)"
)
assert Path(launcher_path).read_bytes() == launcher, (
    "/usr/bin/gap is not this image's launcher (docker/gap-launcher.sh): "
    f"{Path(launcher_path).read_text(errors='replace')[:120]!r}"
)

probe = subprocess.run(
    [
        sys.executable, "-c",
        "from sage.libs.gap.util import kernel_info\n"
        "version, arch, roots = kernel_info()\n"
        "print(version)\n"
        "print(roots)\n"
        "from sage.libs.gap.libgap import libgap\n"
        "print(libgap.eval('1+1'))\n",
    ],
    env={"HOME": os.environ.get("HOME", "/root")},
    capture_output=True,
    text=True,
    check=False,
)
assert probe.returncode >= 0, (
    f"the empty-environment GAP probe died on signal {-probe.returncode}: "
    f"{probe.stdout}{probe.stderr}"
)
assert probe.returncode == 0, (
    "the emptied environment does not reach the image's GAP through /usr/bin/gap: "
    f"{probe.stdout}{probe.stderr}"
)
probed_version, probed_roots, probed_sum = probe.stdout.splitlines()[:3]
assert probed_version == declared_gap, (probed_version, declared_gap)
assert "/sage/.venv/lib/gap/" in probed_roots, probed_roots
assert "/sage/.venv/share/gap/" in probed_roots, probed_roots
assert probed_sum == "2", probed_sum
print(f"kernel_info() under env -i: {probed_version} {probed_roots}; libgap.eval('1+1') = {probed_sum}")

long_home = "/workspace/nucleus/work/home" + "/pad" * 20
long_probe = subprocess.run(
    [
        sys.executable, "-c",
        "import sage.interfaces.gap; "
        "from sage.libs.gap.kernel_info import kernel_info; "
        "print(kernel_info()[2])",
    ],
    env=dict(os.environ, HOME=long_home),
    capture_output=True, text=True, check=False, timeout=600,
)
assert long_probe.returncode == 0, (
    f"the import of sage.interfaces.gap under a HOME past GAP's line width died with "
    f"{long_probe.returncode}: {long_probe.stdout[-2000:]}{long_probe.stderr[-2000:]}"
)
assert f"{long_home}/.gap/" in long_probe.stdout, long_probe.stdout
print(f"import sage.interfaces.gap under a HOME past GAP's line width: ok; "
      f"the roots carry {long_home}/.gap/")

assert libgap.eval("IsBound(RecognizeGroup)").sage() is True

research_revisions = Path("/sage/.research-revisions")
assert research_revisions.is_file(), (
    "the image records no research revisions: /sage/.research-revisions is missing"
)
revisions = research_revisions.read_text(encoding="utf-8").strip().splitlines()
assert revisions, "the image's research-revision record is empty"
for line in revisions:
    name, commit = line.split(" ", 1)
    assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), line
print("the research repositories this image installed, at their main heads (sage#24):")
for line in revisions:
    print(f"  {line}")

flint_probe = subprocess.run(
    [
        sys.executable, "-c",
        "import sage.all; from flint import fmpz_mat; print(fmpz_mat([[2,1],[1,2]]).det())",
    ],
    capture_output=True, text=True, check=False, timeout=600,
)
assert flint_probe.returncode == 0, (
    f"the one-libflint call of sage#25 died with {flint_probe.returncode}: "
    f"{flint_probe.stdout[-2000:]}{flint_probe.stderr[-2000:]}"
)
assert flint_probe.stdout.strip().splitlines()[-1] == "3", (
    flint_probe.stdout, flint_probe.stderr,
)
maps_probe = subprocess.run(
    [
        sys.executable, "-c",
        "import sage.all, flint; "
        "print('\\n'.join(sorted(set(line.split()[-1] for line in open('/proc/self/maps') if 'libflint' in line))))",
    ],
    capture_output=True, text=True, check=False, timeout=600,
)
assert maps_probe.returncode == 0, (maps_probe.stdout, maps_probe.stderr)
mapped = [line for line in maps_probe.stdout.splitlines() if line.strip()]
assert len(mapped) == 1, (
    f"the process maps {len(mapped)} libflints, and one is the whole point (sage#25): "
    f"{' ; '.join(mapped)}"
)
print(f"one libflint in the process: {mapped[0]}")
print("fmpz_mat([[2,1],[1,2]]).det() after import sage.all: 3")

normaliz_probe = subprocess.run(
    [
        sys.executable, "-c",
        "import sage.all; "
        "from PyNormaliz import Cone; "
        "from sage.geometry.cone import Cone as SageCone; "
        "basis = sorted(tuple(int(c) for c in v) for v in Cone(cone=[[1, 0], [1, 2]]).HilbertBasis()); "
        "sage = sorted(tuple(int(c) for c in v) for v in SageCone([(1, 0), (1, 2)]).Hilbert_basis()); "
        "assert basis == sage == [(1, 0), (1, 1), (1, 2)], (basis, sage); "
        "print(basis); "
        "print('\\n'.join(sorted(set(line.split()[-1] for line in open('/proc/self/maps') "
        "if 'libflint' in line))))",
    ],
    capture_output=True, text=True, check=False, timeout=600,
)
assert normaliz_probe.returncode == 0, (
    f"the one-libflint call of sage#31 died with {normaliz_probe.returncode}: "
    f"{normaliz_probe.stdout[-2000:]}{normaliz_probe.stderr[-2000:]}"
)
normaliz_lines = [line for line in normaliz_probe.stdout.splitlines() if line.strip()]
assert normaliz_lines[0] == "[(1, 0), (1, 1), (1, 2)]", (normaliz_probe.stdout, normaliz_probe.stderr)
mapped = normaliz_lines[1:]
assert len(mapped) == 1, (
    f"the pynormaliz process maps {len(mapped)} libflints, and one is the whole point (sage#31): "
    f"{' ; '.join(mapped)}"
)
print(f"one libflint in the pynormaliz process: {mapped[0]}")
print("PyNormaliz and Sage agree on the Hilbert basis of [[1,0],[1,2]]: (1,0), (1,1), (1,2)")

cdd_probe = subprocess.run(
    [
        sys.executable, "-c",
        "import sage.all, cdd, cdd.gmp; "
        "from fractions import Fraction; "
        "out = cdd.gmp.copy_output(cdd.gmp.polyhedron_from_matrix("
        "cdd.gmp.matrix_from_array([[1, 0, 0], [1, 1, 0], [1, 0, 1]], "
        "rep_type=cdd.RepType.INEQUALITY))); "
        "assert out.array == [[Fraction(1), Fraction(-1), Fraction(-1)], "
        "[Fraction(0), Fraction(1), Fraction(0)], [Fraction(0), Fraction(0), Fraction(1)]], "
        "out.array; "
        "print(cdd.gmp.__file__); "
        "print(out.array); "
        "print('\\n'.join(sorted(set(line.split()[-1] for line in open('/proc/self/maps') "
        "if '/libcdd' in line))))",
    ],
    capture_output=True, text=True, check=False, timeout=600,
)
assert cdd_probe.returncode == 0, (
    f"import cdd.gmp in the image's interpreter died with {cdd_probe.returncode}: "
    f"{cdd_probe.stdout[-2000:]}{cdd_probe.stderr[-2000:]}"
)
cdd_lines = [line for line in cdd_probe.stdout.splitlines() if line.strip()]
assert cdd_lines[0].startswith("/sage/.venv/"), (
    f"cdd.gmp is not the venv's module (sage#34): {cdd_lines[0]}"
)
mapped = cdd_lines[2:]
vendored = [path for path in mapped if "site-packages" in path]
cdd_gmp_libs = [path for path in mapped if "libcddgmp" in path.rsplit("/", 1)[-1]]
cdd_libs = []
for path in mapped:
    name = path.rsplit("/", 1)[-1]
    if "libcdd" in name and "libcddgmp" not in name:
        cdd_libs.append(path)
assert not vendored, (
    f"cdd.gmp binds a cddlib from site-packages, not one this image installs (sage#41): "
    f"{' ; '.join(vendored)}"
)
assert len(cdd_gmp_libs) == 1, (
    f"the cdd process maps {len(cdd_gmp_libs)} libcddgmp, and one is the whole point (sage#41): "
    f"{' ; '.join(mapped) or 'none'}"
)
assert len(cdd_libs) == 1, (
    f"the cdd process maps {len(cdd_libs)} libcdd, and one is the whole point (sage#41): "
    f"{' ; '.join(mapped) or 'none'}"
)
print(f"cdd.gmp, pycddlib's exact-rational backend: {cdd_lines[0]}")
print("the cone of [[1,0,0],[1,1,0],[1,0,1]] comes back as exact rationals")
print(f"one libcdd and one libcddgmp, both the image's: {cdd_libs[0]} and {cdd_gmp_libs[0]}")

pari_probe = subprocess.run(
    [
        sys.executable, "-c",
        "from sage.all import QuadraticForm, ZZ; "
        "print(QuadraticForm(ZZ, 3, [1, 1, 0, 1, 0, 9]).number_of_automorphisms())",
    ],
    capture_output=True, text=True, check=False, timeout=600,
)
assert pari_probe.returncode == 0, (
    f"the automorphism count of sage#32 died with {pari_probe.returncode}: "
    f"{pari_probe.stdout[-2000:]}{pari_probe.stderr[-2000:]}"
)
assert pari_probe.stdout.strip().splitlines()[-1] == "24", (
    pari_probe.stdout, pari_probe.stderr,
)
pari_maps = subprocess.run(
    [
        sys.executable, "-c",
        "import sage.all; "
        "print('\\n'.join(sorted(set(line.split()[-1] for line in open('/proc/self/maps') "
        "if 'libpari' in line))))",
    ],
    capture_output=True, text=True, check=False, timeout=600,
)
assert pari_maps.returncode == 0, (pari_maps.stdout, pari_maps.stderr)
mapped_pari = [line for line in pari_maps.stdout.splitlines() if line.strip()]
assert len(mapped_pari) == 1, (
    f"the process maps {len(mapped_pari)} libparis, and one is the whole point (sage#32): "
    f"{' ; '.join(mapped_pari)}"
)
assert mapped_pari[0].startswith("/sage/.venv/lib/"), (
    f"the image's one PARI is not the build the venv carries (sage#32): {mapped_pari[0]}"
)
print(f"one PARI in the process: {mapped_pari[0]}")
print("QuadraticForm(ZZ, 3, [1,1,0,1,0,9]).number_of_automorphisms(): 24")

borel = libgap.function_factory(
    "function(d) local F, g, i, m; F := GF(5); g := []; "
    "for i in [1..d-1] do m := IdentityMat(d, F); m[i][i+1] := One(F); Add(g, m); od; "
    "m := IdentityMat(d, F); m[1][1] := Z(5); Add(g, m); return Group(g); end"
)
stabilizer_chain = libgap.function_factory(
    "function(G) return StabilizerChain(G, rec(ErrorBound := 1/10^6)); end"
)
gap_size = libgap.function_factory("Size")
order = gap_size(stabilizer_chain(borel(4))).sage()
assert order == 4 * 5**6, order

GAP_WORKSPACE_PROBE = r'''
import os, sys
import sage.interfaces.gap_workspace as gap_workspace
if sys.argv[1] == "short-of-room":
    gap_workspace.GAP_WORKSPACE_MIN_FREE = 1 << 62
from sage.interfaces.gap import gap, WORKSPACE
print("workspace", os.path.basename(WORKSPACE))
print("order", gap.Order(gap.SymmetricGroup(4)))
print("inode", os.stat(WORKSPACE).st_ino)
'''


def gap_workspace_probe(home, cache, mode="ordinary"):
    """Run the ordinary GAP call with the environment a launcher would supply."""
    return subprocess.run(
        [sys.executable, "-c", GAP_WORKSPACE_PROBE, mode],
        env={"HOME": str(home), "DOT_SAGE": str(cache),
             "PATH": "/usr/local/bin:/usr/bin:/bin"},
        capture_output=True, text=True, check=False,
    )


def gap_workspace_result(probe):
    """The three lines the probe prints, or the failure that replaced them."""
    assert probe.returncode == 0, (probe.returncode, probe.stdout, probe.stderr)
    fields = dict(line.split(" ", 1) for line in probe.stdout.splitlines())
    assert fields["order"] == "24", (fields, probe.stderr)
    return fields


assert Path("/usr/local/bin/gap").is_file(), "no /usr/local/bin/gap launcher"
with tempfile.TemporaryDirectory() as launcher_environment:
    cache = Path(launcher_environment, "dot-sage")
    home_a = Path(launcher_environment, "home-a")
    home_b = Path(launcher_environment, "home-b")
    home_a.mkdir()
    home_b.mkdir()
    first = gap_workspace_result(gap_workspace_probe(home_a, cache))
    written = sorted(path.name for path in (cache / "gap").glob("*workspace*"))
    assert written == [first["workspace"]], written
    second = gap_workspace_result(gap_workspace_probe(home_b, cache))
    assert second["workspace"] == first["workspace"], (first, second)
    assert second["inode"] == first["inode"], "the workspace was rewritten, not reused"
    foreign = cache / "gap" / f"libgap-workspace-{os.uname().nodename}-{'0' * 40}"
    foreign.write_bytes(b"a workspace of another GAP build\n")
    (cache / "gap" / first["workspace"]).unlink()
    third = gap_workspace_result(gap_workspace_probe(home_b, cache, "short-of-room"))
    assert not foreign.exists(), "a workspace of another GAP build was kept for room"
    assert (cache / "gap" / third["workspace"]).is_file(), third
    print(
        f"external GAP: {first['workspace']} written from a clean environment, "
        f"reused from a second HOME, and its cache made room for it "
        f"({third['workspace']})"
    )

GAP_IMPORT_PROBE = r'''
from sage.interfaces.gap import gap
print("order", gap.Order(gap.SymmetricGroup(4)))
'''
with tempfile.TemporaryDirectory() as home_root:
    from importlib.resources import files
    systemfile = files("sage").joinpath("ext_data/gap/kernel-info.g")
    long_home = Path(home_root)
    for _ in range(8):
        printed = subprocess.run(["gap", "--systemfile", str(systemfile)],
                                 env={**os.environ, "HOME": str(long_home)},
                                 capture_output=True, text=True, check=True)
        if "\\\n" in printed.stdout:
            break
        long_home = long_home / "a-home-directory-with-a-name-long-enough-that-gap-breaks-its-record-of-roots"
        long_home.mkdir(parents=True, exist_ok=True)
    else:
        raise AssertionError(f"GAP never broke the roots record: {printed.stdout!r}")
    imported = subprocess.run(
        [sys.executable, "-c", GAP_IMPORT_PROBE],
        env={"HOME": str(long_home),
             "DOT_SAGE": str(Path(home_root, "dot-sage")),
             "PATH": "/sage/.venv/bin:/usr/local/bin:/usr/bin:/bin"},
        capture_output=True, text=True, check=False,
    )
    assert imported.returncode == 0, (imported.returncode, imported.stdout, imported.stderr)
    assert imported.stdout.strip().splitlines()[-1] == "order 24", imported.stdout
    print(f"the GAP interface imported with a {len(str(long_home))}-character HOME, "
          f"at which GAP breaks its roots record")

import sage.env

maxima_prefix = Path(sage.env.MAXIMA_PREFIX) if sage.env.MAXIMA_PREFIX else None
assert maxima_prefix is not None and maxima_prefix.is_dir(), (
    "MAXIMA_PREFIX",
    sage.env.MAXIMA_PREFIX,
)
assert list(
    maxima_prefix.glob("share/maxima/*/share/linearalgebra/linearalgebra.mac")
), maxima_prefix
assert str((var("x") + 1) ** 2) == "(x + 1)^2"

labelled = Graph([(0, 1, "a"), (2, 3, None), (1, 2, "a"), (3, 0, None)])
relabelled = labelled.relabel({0: 2, 1: 0, 2: 3, 3: 1}, inplace=False)
for algorithm in ("bliss", "sage"):
    assert labelled.canonical_label(algorithm=algorithm, edge_labels=True) == (
        relabelled.canonical_label(algorithm=algorithm, edge_labels=True)
    ), algorithm
assert Graph([[0, 1]]).canonical_label(edge_labels=True) == Graph([[0, 1]])
assert graphs.PetersenGraph().automorphism_group().order() == 120

for module in (
    "dzack_research", "latticedb", "pandoc_config", "sage_categories", "sage_extensions",
    "sage_indefinite_port", "sage_julia_bridge", "sage_lsp", "tree_sitter_sage",
    "vinal",
):
    origin = importlib.import_module(module).__file__
    assert origin.startswith("/repos/"), (module, origin)
importlib.import_module("sage_categories_homotopy")

import json
import tomllib
from importlib.metadata import PackageNotFoundError, distribution

research_list = Path("/sage/docker/research-repositories.txt")
assert research_list.is_file(), (
    f"{research_list} is missing: it names the repositories the install checks out, "
    "and both the install and this block read it"
)
research_locations = {
    location.rstrip("/").removesuffix(".git")
    for location in (
        line.strip() for line in research_list.read_text(encoding="utf-8").splitlines()
    )
    if location and not location.startswith("#")
}
assert research_locations, f"{research_list} names no repository"
installed = dict(
    line.split(" ", 1)
    for line in Path("/sage/.research-revisions").read_text(encoding="utf-8").strip().splitlines()
)
lock = tomllib.loads(Path("/sage/uv.lock").read_text(encoding="utf-8"))
for package in sorted(lock["package"], key=lambda entry: entry["name"]):
    source = package.get("source", {}).get("git")
    if source is None:
        continue
    name = package["name"]
    observed = None
    location = source.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0].rstrip("/").removesuffix(".git")
    repository = location.rsplit("/", 1)[-1]
    if location not in research_locations:
        assert not location.startswith("https://github.com/dzackgarza/"), (
            f"dependency {name}: {location} is a repository of the owner, which the image takes "
            f"at the head of its main branch; {research_list} does not name it, so the image "
            "installs it at the commit of uv.lock"
        )
        pinned = source.rsplit("#", 1)[-1]
        try:
            direct = distribution(name).read_text("direct_url.json")
        except PackageNotFoundError:
            direct = None
        observed = json.loads(direct).get("vcs_info", {}).get("commit_id") if direct else None
        if observed is None:
            print(f"dependency {name}: not installed")
            continue
        assert observed == pinned, (
            f"dependency {name}: installed from {observed}, and uv.lock pins {pinned}"
        )
        print(f"dependency {name}: {observed} (git wheel, the lock's commit)")
        continue
    checkout = Path("/repos") / repository
    if (checkout / ".git").is_dir():
        observed = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        kind = "checkout"
    else:
        try:
            direct = distribution(name).read_text("direct_url.json")
        except PackageNotFoundError:
            direct = None
        if direct:
            observed = json.loads(direct).get("vcs_info", {}).get("commit_id")
            kind = "git wheel"
    if observed is None:
        print(f"research {name}: not installed")
        continue
    recorded = installed.get(repository)
    assert recorded is not None, (
        f"research {name}: /sage/.research-revisions records no head for {repository}"
    )
    print(f"research {name}: {observed} ({kind}, installed {recorded})")
    assert observed == recorded, (name, observed, recorded)


import ast
import re

from sage_categories.engines.gap import GapPackage, load_packages

categories_root = Path("/repos/sage-categories")
allocation = categories_root / ".gap" / "pkg"
assert allocation.is_dir(), allocation
declared = re.search(
    r"^packages := \[(.*?)^\];",
    (categories_root / ".gap-packages.g").read_text(encoding="utf-8"),
    re.DOTALL | re.MULTILINE,
)
assert declared is not None, "no `packages := [ ... ];` in .gap-packages.g"
pinned = tuple(
    GapPackage(name, version)
    for name, version, _url in ast.literal_eval(f"[{declared.group(1)}]")
)
assert len(pinned) == len({package.name for package in pinned}), pinned
assert len(load_packages(pinned)) == len(pinned), len(pinned)

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

test_dependencies = [
    Requirement(line) for line in tomllib.loads(
        Path("/sage/pyproject.toml").read_text(encoding="utf-8")
    )["dependency-groups"]["research-environment-tests"]
]
for requirement in test_dependencies:
    try:
        observed = distribution(requirement.name).version
    except PackageNotFoundError:
        raise AssertionError(
            f"{requirement.name}: a research repository declares it among its test "
            "dependencies and the venv does not have it; uv.lock's "
            "research-environment-tests group is where it comes from"
        )
    assert requirement.specifier.contains(observed, prereleases=True), (
        f"{requirement.name} {observed} does not satisfy {requirement.specifier}"
    )
print(f"the research test dependencies: {len(test_dependencies)} installed")

plugin_modules = {
    canonicalize_name(requirement.name): entry_point.value.split(":")[0].strip()
    for requirement in test_dependencies
    for entry_point in distribution(requirement.name).entry_points
    if entry_point.group == "pytest11"
}
with tempfile.TemporaryDirectory() as probe_directory:
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "--trace-config", "--collect-only", "-q",
         "--noconftest", "-p", "no:cacheprovider"],
        cwd=probe_directory, capture_output=True, text=True, check=False,
    )
assert probe.returncode in (0, 5), (probe.returncode, probe.stdout[-2000:], probe.stderr[-2000:])
registered = set()
for line in probe.stdout.splitlines():
    if line.startswith("PLUGIN registered: <module "):
        registered.add(
            line.removeprefix("PLUGIN registered: <module ").lstrip("'").split("'")[0].split(" ")[0].rstrip(">")
        )
unloaded = sorted(
    f"{name} ({module})"
    for name, module in plugin_modules.items()
    if module not in registered and module.split(".")[0] not in registered
)
assert not unloaded, (unloaded, probe.stdout, probe.stderr)
print(f"pytest loads {len(plugin_modules)} of them as plugins: {' '.join(sorted(plugin_modules))}")

import importlib.util

generator = importlib.util.spec_from_file_location(
    "research_test_dependencies", "/sage/docker/research-test-dependencies.py"
)
assert generator is not None and generator.loader is not None, generator
module = importlib.util.module_from_spec(generator)
generator.loader.exec_module(module)
try:
    declared_now = module.collect(Path("/sage"), Path("/repos"))
except SystemExit as error:
    print(f"note: the checkouts' test dependencies could not be read whole: {error}")
else:
    carried = {canonicalize_name(requirement.name) for requirement in test_dependencies}
    absent = [
        line for line in declared_now
        if canonicalize_name(Requirement(line).name) not in carried
    ]
    if absent:
        print(
            "note: the checkouts declare test dependencies uv.lock does not carry, so "
            "this image's `just test` in those repositories will not have them "
            "(relock: docker/research-test-dependencies.py --write, then uv lock): "
            + " ".join(absent)
        )

requirements = distribution_requires("sage-indefinite-port") or []
assert any("sage-extensions" in line for line in requirements), requirements
assert not any("research" in line for line in requirements), requirements
assert Lattices.__module__ == "sage_extensions.categories.lattices", Lattices.__module__

lattices = Lattices(ZZ)
plane = lattices([[0, 1], [1, 0]])
assert not plane.Isom(plane).is_empty()
assert lattices([[2, 1], [1, 2]]).Isom(lattices([[1, 0], [0, 1]])).is_empty()
assert plane.O().cardinality() == 4
assert plane.Aut().cardinality() == 4
assert plane.stable_orthogonal_group().order() == 4

assert julia.sage("1 // 2") == QQ(1) / 2
julia.eval("using Oscar")
assert julia.sage("ZZ(2)^10") == 1024
assert julia.eval("using JSON; JSON.json((a=1,))") == '{"a":1}'
julia.quit()

without_depot = {name: value for name, value in os.environ.items() if name != "JULIA_DEPOT_PATH"}
subprocess.run(
    [
        "python",
        "-c",
        "from sage_julia_bridge import Julia; j = Julia();"
        " assert j.eval('using JSON; JSON.json((a=1,))') == '{\"a\":1}'; j.quit()",
    ],
    env=without_depot,
    check=True,
)

from jupyter_client.manager import start_new_kernel


def kernel_stdout(name: str, code: str) -> str:
    manager, client = start_new_kernel(kernel_name=name, startup_timeout=600)
    chunks: list[str] = []

    def collect(message: dict[str, dict[str, str] | str]) -> None:
        content = message["content"]
        if message["msg_type"] == "stream" and isinstance(content, dict) and content["name"] == "stdout":
            chunks.append(content["text"])

    try:
        reply = client.execute_interactive(code, output_hook=collect, timeout=900)
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)
    assert reply["content"]["status"] == "ok", (name, reply["content"])
    return "".join(chunks).strip()


assert kernel_stdout("sagemath", "print(matrix(QQ, [[2, 1], [1, 2]]).det())") == "3"
oscar_stdout = kernel_stdout(
    "julia",
    'using Oscar; Qx, x = polynomial_ring(QQ, :x); K, a = number_field(x^2 - 2); println(degree(K), " ", a^2 == 2)',
)
assert oscar_stdout.splitlines()[-1] == "2 true", oscar_stdout

import json

unknown = [word for word in sys.argv[1:] if word.startswith("-")]
assert not unknown, f"unknown argument(s): {unknown}"

record_path = Path("/opt/lean-image.json")
record = json.loads(record_path.read_text(encoding="utf-8"))
project = Path(record["project"])
assert project == Path("/opt/mathlib"), (
    f"the image's Lean project is {project}, not /opt/mathlib", record,
)
assert record["master_head_at_resolution"] == record["revision"], (
    "the build resolved one Mathlib revision and checked out another",
    record["master_head_at_resolution"], record["revision"],
)


def git_head(directory: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def pins_of(directory: Path) -> dict[str, str]:
    """Every git package a project's manifest pins, by name: one flat closure."""
    manifest = json.loads((directory / "lake-manifest.json").read_text(encoding="utf-8"))
    return {
        package["name"]: package["rev"]
        for package in manifest["packages"]
        if package.get("type") == "git"
    }


def build_dir(directory: Path) -> Path:
    return directory / ".lake" / "build" / "lib" / "lean"


head = git_head(project)
assert head == record["revision"], (
    "the shared project is not the revision the image recorded",
    head, record["revision"],
)

pinned_toolchain = (project / "lean-toolchain").read_text(encoding="utf-8").strip()
assert pinned_toolchain == record["toolchain"], (
    "the toolchain the recorded Mathlib revision pins is not the one the image records",
    pinned_toolchain, record["toolchain"],
)
settings = Path("/opt/elan/settings.toml")
assert settings.is_file(), settings
assert f'default_toolchain = "{record["toolchain"]}"' in settings.read_text(
    encoding="utf-8"
), (
    "the image's default toolchain is not the one its shared Mathlib project pins",
    settings.read_text(encoding="utf-8").strip(), record["toolchain"],
)

mathlib_olean = build_dir(project) / "Mathlib.olean"
assert mathlib_olean.is_file(), (
    f"{project} carries no built Mathlib; docker/provision-lean-packages.sh did not finish"
)
closure = {}
for name, revision in sorted(pins_of(project).items()):
    directory = project / ".lake" / "packages" / name
    assert directory.is_dir(), (f"{directory} is missing from the shared project", name)
    found = git_head(directory)
    assert found == revision, (
        f"{directory} is at {found}, not the {revision} the shared project pins", name,
    )
    assert build_dir(directory).is_dir(), (
        f"{directory} carries no build directory; the closure was not built in the one project",
        name,
    )
    closure[name] = directory
print(
    f"the shared Lean project: mathlib {record['revision'][:12]} on {record['toolchain']}"
    f" (head resolved at {record.get('resolved', 'an unrecorded time')}),"
    f" closure built in {project}: {', '.join(sorted(closure))}"
)

lake_env_version = subprocess.run(
    ["lake", "env", "lean", "--version"], cwd=project, capture_output=True, text=True,
    check=True, timeout=900,
).stdout.strip()
expected_version = record["toolchain"].rsplit(":", 1)[-1].lstrip("v")
assert expected_version in lake_env_version, (lake_env_version, record["toolchain"])
print(f"lake env lean --version in {project}: {lake_env_version.splitlines()[0]}")

built = subprocess.run(
    ["lake", "build", "Mathlib"], cwd=project, capture_output=True, text=True,
    check=False, timeout=3600,
)
if built.returncode != 0:
    raise SystemExit(
        f"lake build Mathlib failed in {project} (exit {built.returncode}):\n"
        f"{built.stdout[-4000:]}{built.stderr[-4000:]}"
    )
print(f"lake build Mathlib in {project}: exit 0")

with tempfile.NamedTemporaryFile(
    "w", suffix=".lean", prefix="mathlib-import-", delete=False
) as handle:
    handle.write("import Mathlib\n#check (Nat.add_comm : \u2200 a b : Nat, a + b = b + a)\n")
    import_file = handle.name
try:
    elaborated = subprocess.run(
        ["lake", "env", "lean", import_file], cwd=project,
        capture_output=True, text=True, check=True, timeout=1800,
    ).stdout.strip()
    assert "Nat.add_comm" in elaborated, elaborated
finally:
    Path(import_file).unlink()
print(f"import Mathlib in {project}: {elaborated.splitlines()[-1]}")

image_revision = record["revision"]
checkouts = [
    directory for directory in sorted(Path("/repos").iterdir())
    if directory.is_dir() and not directory.name.startswith(".")
    and (directory / "lake-manifest.json").is_file()
]
assert checkouts, "the image carries no Lean checkout under /repos"
for directory in checkouts:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".lean", prefix="mathlib-import-", delete=False
    ) as handle:
        handle.write("import Mathlib\n#check (Nat.add_comm : \u2200 a b : Nat, a + b = b + a)\n")
        checkout_file = handle.name
    try:
        elaborated = subprocess.run(
            ["lake", "env", "lean", checkout_file], cwd=directory,
            capture_output=True, text=True, check=False, timeout=1800,
        )
        if elaborated.returncode != 0:
            raise SystemExit(
                f"{directory} does not build against the Mathlib the image carries, and "
                f"the image's check fails loudly for it (sage#13): lake env lean exited "
                f"{elaborated.returncode} there, and the image carries {image_revision}:"
                f"\n{elaborated.stdout[-2000:]}{elaborated.stderr[-2000:]}"
            )
        if "Nat.add_comm" not in elaborated.stdout:
            raise SystemExit(
                f"{directory} does not build against the Mathlib the image carries, and "
                f"the image's check fails loudly for it (sage#13): it carries "
                f"{image_revision}"
            )
    finally:
        Path(checkout_file).unlink()
    print(f"import Mathlib in {directory}: {elaborated.stdout.strip().splitlines()[-1]}")

import shutil

document_tools = ["quarto", "pandoc", "pdf2svg", "pdftoppm", "kpsewhich", "node", "lualatex"]
absent = [tool for tool in document_tools if shutil.which(tool) is None]
assert not absent, f"the image carries no {absent}"

pandoc_templates = Path("/repos/pandoc-config/templates")
pandoc_scratch = Path(tempfile.mkdtemp(prefix="pandoc-template-"))
(pandoc_scratch / "chapter.md").write_text("# A chapter\n\nThe form $x^2$.\n", encoding="utf-8")
for template in ("uga-dissertation.tex", "research_draft.tex"):
    rendered = subprocess.run(
        ["pandoc", str(pandoc_scratch / "chapter.md"), "--to", "latex",
         "--template", str(pandoc_templates / template), "-o", str(pandoc_scratch / template)],
        capture_output=True, text=True, check=False,
    )
    assert rendered.returncode == 0, (
        f"the pandoc on PATH cannot render pandoc-config's {template}", rendered.stderr,
    )
pandoc_version = subprocess.run(
    ["pandoc", "--version"], capture_output=True, text=True, check=True,
).stdout.splitlines()[0]
print(f"{pandoc_version} renders pandoc-config's dissertation and draft templates")

tex_packages = [
    "amsmath", "amsthm", "amssymb", "amsfonts", "mathtools", "mathrsfs",
    "bm", "esint", "stmaryrd", "bbm", "upgreek", "iftex", "fontenc",
    "graphicx", "subcaption", "xcolor", "amscd", "centernot", "slashed",
    "tikz", "tikz-cd", "tikz-3dplot", "etoolbox", "xparse",
    "dynkin-diagrams", "quiver", "pgfplots", "luatex85", "luahyperbolic",
    "xy", "microtype", "hyperref", "bookmark", "enumitem",
    "standalone",
    "ebgaramond", "geometry", "setspace", "nowidow", "sectsty", "appendix",
    "marginfix", "sidenotes", "ragged2e", "inputenc", "array", "biblatex",
    "booktabs", "caption", "cleveref", "csquotes", "float", "longtable",
    "tabularx", "todonotes", "xspace",
]
for package in tex_packages:
    found = subprocess.run(
        ["kpsewhich", f"{package}.sty"], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert found, f"kpsewhich found no {package}.sty: the image does not carry it"

tikz_libraries = [
    "tikzlibrarycd.code.tex",
    "tikzlibraryfadings.code.tex",
    "tikzlibrarypatterns.code.tex",
    "tikzlibrarycalc.code.tex",
    "tikzlibrarymatrix.code.tex",
    "tikzlibrarypositioning.code.tex",
    "tikzlibrarydecorations.code.tex",
    "tikzlibraryshapes.code.tex",
    "tikzlibrarybackgrounds.code.tex",
    "tikzlibraryfit.code.tex",
    "tikzlibraryintersections.code.tex",
    "tikzlibraryhobby.code.tex",
    "tikzlibrarygraphs.code.tex",
    "tikzlibraryexternal.code.tex",
    "pgflibraryarrows.meta.code.tex",
]
for library in tikz_libraries:
    found = subprocess.run(
        ["kpsewhich", library], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert found, f"kpsewhich found no {library}: the image does not carry it"

quarto_version = subprocess.run(
    ["quarto", "--version"], capture_output=True, text=True, check=True
).stdout.strip()
assert quarto_version, "quarto --version printed nothing"
print(f"quarto {quarto_version}")

texlive = subprocess.run(
    ["dpkg-query", "-W", "-f=${Status}", "texlive-full"], capture_output=True, text=True, check=False,
)
assert texlive.stdout.strip() == "install ok installed", (
    "texlive-full is not installed", texlive.stdout, texlive.stderr,
)
tex_files = [
    "tikz.sty", "tikz-cd.sty", "pgfplots.sty", "standalone.cls", "luahyperbolic.sty",
    "booktabs.sty", "microtype.sty", "fontspec.sty", "unicode-math.sty",
    "siunitx.sty", "amsmath.sty", "mathtools.sty",
]
missing_tex = [
    name for name in tex_files
    if subprocess.run(["kpsewhich", name], capture_output=True, text=True, check=False).stdout.strip() == ""
]
assert not missing_tex, f"TeX Live does not find {missing_tex}"
lualatex_version = subprocess.run(
    ["lualatex", "--version"], capture_output=True, text=True, check=False
).stdout.strip()
assert "LuaHBTeX" in lualatex_version or "LuaTeX" in lualatex_version, lualatex_version
print(f"texlive-full with {len(tex_files)} files the sites load, on {lualatex_version.splitlines()[0]}")

render = Path(tempfile.mkdtemp(prefix="quarto-render-"))
(render / "page.qmd").write_text(
    "---\n"
    "title: A one-page document\n"
    "header-includes: |\n"
    "  \\usepackage{tikz}\n"
    "---\n"
    "\n"
    "\\begin{tikzpicture}\n"
    "  \\draw (0,0) circle (1);\n"
    "\\end{tikzpicture}\n",
    encoding="utf-8",
)
quarto_rendered = subprocess.run(
    ["quarto", "render", str(render / "page.qmd"), "--to", "pdf"], cwd=render,
    capture_output=True, text=True, check=False, timeout=900,
)
assert quarto_rendered.returncode == 0, (quarto_rendered.stdout, quarto_rendered.stderr)
assert (render / "page.pdf").is_file(), "quarto rendered no PDF"
subprocess.run(["pdf2svg", str(render / "page.pdf"), str(render / "page.svg")], check=True)
svg = (render / "page.svg").read_text(encoding="utf-8", errors="replace")
assert "<svg" in svg, svg[:400]
poppler_version = subprocess.run(
    ["pdftoppm", "-v"], capture_output=True, text=True, check=False
).stderr.strip() or subprocess.run(
    ["pdftoppm", "-v"], capture_output=True, text=True, check=False
).stdout.strip()
assert "pdftoppm" in poppler_version, poppler_version
subprocess.run(
    ["pdftoppm", "-r", "10", "-png", str(render / "page.pdf"), str(render / "thumb")], check=True
)
assert list(render.glob("thumb*.png")), "pdftoppm wrote no image"
print(
    f"quarto rendered a page with a TikZ figure through pdf2svg: "
    f"{len(svg)} bytes of SVG; {poppler_version.splitlines()[0]}"
)

node_version = subprocess.run(
    ["node", "--version"], capture_output=True, text=True, check=True
).stdout.strip()
assert node_version.startswith("v"), node_version
print(f"node {node_version}")


print(version())
