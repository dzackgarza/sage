# Fails the image build if any system the research image exists to provide is
# absent. Run with the image's sage: `sage docker/research-environment-check.py`.
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

# Those two are only there if the GAP that libgap drives can see them, and that
# instance is the system GAP: kernel_info runs the same `gap` binary and hands
# libgap the roots it reports, which is why the packages are installed into
# /usr/share/gap/pkg (docker/research-environment.Dockerfile) and why Sage's
# gap_packages spkg, which fills $SAGE_LOCAL/lib/gap/pkg, would not be enough
# here. Both halves are asserted: the roots, and each package loading in it.
from sage.libs.gap.libgap import libgap
from sage.libs.gap.util import kernel_info

# GAP is now built from the pinned source into SAGE_LOCAL (Dockerfile), so the
# executable libgap drives, the root it searches and the version it reports are
# all declared inputs rather than whatever the distribution shipped.
import shutil

declared_gap = Path("build/pkgs/gap/package-version.txt").read_text().strip()
gap_binary = shutil.which("gap")
assert gap_binary is not None, "no gap on PATH"
assert Path(gap_binary).resolve().is_relative_to(Path("/sage/.venv")), gap_binary

gap_version, gap_arch, gap_roots = kernel_info()
assert gap_version == declared_gap, (gap_version, declared_gap)
assert "/sage/.venv/lib/gap/" in gap_roots, gap_roots
# Do not pin the packages to one owner's tree. They may sit in the system GAP's
# /usr/share/gap/pkg or in Sage's own $SAGE_LOCAL/lib/gap/pkg; what has to hold is
# that the directory GAP resolves each package from is one GAP actually searches.
# Naming a single path here would enshrine whichever GAP the image happens to use.
gap_root_list = [root for root in gap_roots.split(";") if root]
for name in ("orb", "forms", "genss", "recog"):
    loaded = libgap.eval(f'LoadPackage("{name}")')
    assert loaded.sage() is True, (name, loaded)
    installed_in = str(libgap.eval(f'PackageInfo("{name}")[1].InstallationPath'))
    assert any(installed_in.startswith(root) for root in gap_root_list), (
        name, installed_in, gap_root_list,
    )
# kernel_info runs the `gap` *binary*; it says nothing about which libgap this
# process actually loaded. Assert the linkage itself: a libgap mapped from
# $SAGE_LOCAL, not one from /usr/lib.
loaded_libgap = [
    line.split()[-1]
    for line in Path("/proc/self/maps").read_text().splitlines()
    if "libgap.so" in line and line.split()[-1].startswith("/")
]
assert loaded_libgap, "no libgap mapped into this process"
assert all(path.startswith("/sage/.venv/lib/") for path in loaded_libgap), loaded_libgap

# Exactly one GAP: the one built from the pinned source. No Debian package the
# image installs depends on Debian's GAP, so a build from debian:trixie has none,
# and research-environment-incremental.Dockerfile purges what a published base
# carries. It has to be gone rather than merely unused: kernel_info() runs the bare
# command `gap` through PATH, so a second copy turns any PATH that does not resolve
# $SAGE_LOCAL/bin/gap first into GAP 4.14's library read by libgap.so.11 -- which is
# a segfault in DoOperation1Args, not an exception (sage#11).
distribution_gap = [
    path for path in (
        "/usr/bin/gap",
        "/usr/lib/gap",
        "/usr/share/gap",
        "/usr/lib/x86_64-linux-gnu/libgap.so.9",
    ) if Path(path).exists()
]
assert not distribution_gap, f"a distribution GAP is still installed: {distribution_gap}"
apt_gap = sorted(
    line.split()[0]
    for line in subprocess.run(
        ["dpkg-query", "-W", "-f=${Package} ${Status}\n", "gap*", "libgap*"],
        capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    if line.endswith(" install ok installed")
)
assert not apt_gap, f"apt still carries GAP packages: {apt_gap}"

# The probe that found sage#11: an emptied environment leaves PATH unset, so a bare
# `gap` resolves through Python's own /bin:/usr/bin, and libgap is then initialised
# on whatever library that GAP reports. Either the Sage-owned roots are the ones
# found and the session works, or the probe fails as a Python error; dying on a
# signal is the crash this asserts against.
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
if probe.returncode:
    assert "Traceback" in probe.stderr, (probe.returncode, probe.stdout, probe.stderr)
    print(f"kernel_info() under env -i raised: {probe.stderr.strip().splitlines()[-1]}")
else:
    probed_version, probed_roots, probed_sum = probe.stdout.splitlines()[:3]
    assert probed_version == declared_gap, (probed_version, declared_gap)
    assert "/sage/.venv/lib/gap/" in probed_roots, probed_roots
    assert "/sage/.venv/share/gap/" in probed_roots, probed_roots
    assert probed_sum == "2", probed_sum
    print(f"kernel_info() under env -i: {probed_version} {probed_roots}; libgap.eval('1+1') = {probed_sum}")

assert libgap.eval("IsBound(RecognizeGroup)").sage() is True

# A generated matrix subgroup over F_5, ordered by genss's stabilizer chain in
# the matrix action rather than through a permutation representation. This is
# capability evidence and not a certificate: the chain is Monte Carlo bounded by
# ErrorBound, VerifyStabilizerChainMC has no method for a plain matrix group, and
# nothing here claims that any degree-10 image order is exact or cheap.
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

# Maxima's package files are found through MAXIMA_PREFIX, and in a tree where
# Maxima was staged into SAGE_LOCAL they live under it. A reconfigure must not
# leave the prefix empty merely because the system ECL can already load
# maxima.fas: sage.symbolic then dies in load(linearalgebra), which the
# symbolic check below reproduces.
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

# Both canonical-label backends return the same label for a relabelled copy of
# a labelled graph, and the bliss automorphism search finishes.  A system
# libbliss built with a different BigNum representation than its headers
# segfaults on the first assertion, and one whose bliss::Stats is copied
# instead of referenced aborts on a double free in the last: this image
# installs that library, so its build has to link it the way the library's
# pkg-config file asks.
labelled = Graph([(0, 1, "a"), (2, 3, None), (1, 2, "a"), (3, 0, None)])
relabelled = labelled.relabel({0: 2, 1: 0, 2: 3, 3: 1}, inplace=False)
for algorithm in ("bliss", "sage"):
    assert labelled.canonical_label(algorithm=algorithm, edge_labels=True) == (
        relabelled.canonical_label(algorithm=algorithm, edge_labels=True)
    ), algorithm
assert Graph([[0, 1]]).canonical_label(edge_labels=True) == Graph([[0, 1]])
assert graphs.PetersenGraph().automorphism_group().order() == 120

# The research packages run from their checkouts under /repos. The homotopy
# package is a compiled extension built from its checkout, so its module is in
# site-packages.
for module in (
    "dzack_research", "latticedb", "pandoc_config", "sage_categories", "sage_extensions",
    "sage_indefinite_port", "sage_julia_bridge", "sage_lsp", "tree_sitter_sage",
    "vinal",
):
    origin = importlib.import_module(module).__file__
    assert origin.startswith("/repos/"), (module, origin)
importlib.import_module("sage_categories_homotopy")

# sage-categories runs its finite-category engine on GAP releases allocated to its
# own checkout: every consumer of a presented module fixes each package's path to
# .gap/pkg before the first LoadPackage, so the image's GAP cannot substitute for
# them. docker/install-research-repositories.sh runs the repository's own
# .gap-packages.g, and the library's loader is the assertion -- one installation of
# each exact version, loaded from that path.
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
# That list is GAP syntax whose elements are plain string triples -- name, version,
# release URL -- so it reads as a Python literal.
pinned = tuple(
    GapPackage(name, version)
    for name, version, _url in ast.literal_eval(f"[{declared.group(1)}]")
)
assert len(pinned) == len({package.name for package in pinned}), pinned
assert len(load_packages(pinned)) == len(pinned), len(pinned)

# The canonical pair: the port reads sage-extensions, and nothing revives the
# predecessor research library it used to read. A stale pair still loads, so
# the requirement the port installs and the category it composes are both
# checked, with one isometry and one group that exercise them.
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
assert julia.eval("JSON.json((a=1,))") == '{"a":1}'
julia.quit()

# The bridge's worker project pins JSON and imports it in its first statement
# (julia_bridge.jl:2). That package lives in /opt/julia-depot, so a host that
# runs this filesystem without a container runtime -- and so without the
# image's JULIA_DEPOT_PATH -- reaches it through /usr/local/bin/julia. This is
# that host: the bridge, with the variable removed from the environment.
without_depot = {name: value for name, value in os.environ.items() if name != "JULIA_DEPOT_PATH"}
subprocess.run(
    [
        "python",
        "-c",
        "from sage_julia_bridge import Julia; j = Julia();"
        " assert j.eval('JSON.json((a=1,))') == '{\"a\":1}'; j.quit()",
    ],
    env=without_depot,
    check=True,
)

# Each Lean checkout imports Mathlib the way a consumer runs it. A Lean release
# refuses another release's oleans, so a Mathlib is readable only by the toolchain
# that built it, and the same holds for every package Mathlib imports: docker/
# provision-lean-packages.sh builds each pinned Mathlib revision as its own project
# when the shared packages directory does not already carry that revision, and its
# dependencies are built inside that checkout by that checkout's toolchain (sage#12),
# which is what the launcher's view binds over the packages directory. The check
# reproduces that environment exactly: LEAN_PATH is the build directory of every
# package in the project's manifest, resolved the way the view resolves it, and the
# import runs on the toolchain the project pins rather than through Lake, whose
# `env` does not return in this environment.
import json


def pinned(project: Path) -> tuple[str, dict[str, str]]:
    """The toolchain a checkout pins and the revision it pins for every package."""
    toolchain = (project / "lean-toolchain").read_text(encoding="utf-8").strip()
    manifest = json.loads((project / "lake-manifest.json").read_text(encoding="utf-8"))
    return toolchain, {
        package["name"]: package["rev"]
        for package in manifest["packages"]
        if package.get("type") == "git"
    }


index = json.loads(Path("/opt/lake-views/index.json").read_text(encoding="utf-8"))
with tempfile.NamedTemporaryFile(
    "w", suffix=".lean", prefix="mathlib-import-", delete=False
) as handle:
    handle.write("import Mathlib\n#check (Nat.add_comm : \u2200 a b : Nat, a + b = b + a)\n")
    import_file = handle.name
imported = []
try:
    for toolchain_file in sorted(Path("/repos").glob("*/lean-toolchain")):
        project = toolchain_file.parent
        if not (project / "lake-manifest.json").is_file():
            continue
        pinned_toolchain, pins = pinned(project)
        subprocess.run(["lake", "--version"], cwd=project, check=True)
        entry = index.get(str(project))
        assert entry is not None, f"{project} is not in /opt/lake-views/index.json"
        packages_dir = Path(entry["packages_dir"])
        overrides = {item["name"]: item for item in entry["overrides"]}
        directories = {
            name: Path(overrides[name]["checkout"]) if name in overrides else packages_dir / name
            for name in pins
        }
        if "mathlib" in overrides:
            # A revision the shared directory does not carry. Its dependencies live
            # beside it only if this checkout resolved them itself; a Mathlib built
            # earlier against the shared directory carries none, and those packages
            # are still the ones it was built with, so the shared entry is used and
            # the revision check below holds it to the pin.
            mathlib = Path(overrides["mathlib"]["checkout"])
            _, closure = pinned(mathlib)
            for name in pins:
                if name == "mathlib":
                    continue
                bundled = mathlib / ".lake" / "packages" / name
                if bundled.is_dir():
                    directories[name] = bundled
                    if name in closure:
                        assert pins[name] == closure[name], (name, pins[name], closure[name])
            directories["mathlib"] = mathlib
            where = "from its override checkout"
        else:
            mathlib = (packages_dir / "mathlib").resolve()
            where = "from the shared packages directory"
        for name, directory in sorted(directories.items()):
            resolved = subprocess.run(
                ["git", "-C", str(directory), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            assert resolved == pins[name], (str(directory), resolved, pins[name])
        built_by = (mathlib / "lean-toolchain").read_text(encoding="utf-8").strip()
        assert built_by == pinned_toolchain, (str(mathlib), built_by, pinned_toolchain)
        lean_path = ":".join(
            str(directory / ".lake" / "build" / "lib" / "lean")
            for _, directory in sorted(directories.items())
        )
        output = subprocess.run(
            ["elan", "run", pinned_toolchain, "lean", import_file],
            cwd=project,
            env={**os.environ, "LEAN_PATH": lean_path},
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert "Nat.add_comm" in output, output
        imported.append(
            f"{project.name} ({pinned_toolchain}) {where} mathlib {pins['mathlib'][:8]}:"
            f" {output.splitlines()[-1]}"
        )
finally:
    Path(import_file).unlink()
for line in imported:
    print(line)

print(version())
