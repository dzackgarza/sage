# Fails the image build if any system the research image exists to provide is
# absent. Run with the image's sage: `sage docker/research-environment-check.py`.
import importlib
import os
import subprocess
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
    "atlasrep", "design", "grape", "guava", "hap", "polenta", "polycyclic",
)]
missing = [feature.name for feature in features if not feature.is_present()]
assert not missing, missing

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

# Each Lean checkout runs Lake on the toolchain it pins, and the pinned project
# imports Mathlib. A version string says nothing about whether the packages the
# project resolves carry object files, which is what the import needs: the
# image ships Mathlib's official cache and builds the packages it imports.
for toolchain in Path("/repos").glob("*/lean-toolchain"):
    subprocess.run(["lake", "--version"], cwd=toolchain.parent, check=True)

mathlib_project = Path("/repos/lean-categories")
with tempfile.NamedTemporaryFile(
    "w", suffix=".lean", prefix="mathlib-import-", delete=False
) as handle:
    handle.write("import Mathlib\n#check (Nat.add_comm : \u2200 a b : Nat, a + b = b + a)\n")
    import_file = handle.name
try:
    subprocess.run(["lake", "env", "lean", import_file], cwd=mathlib_project, check=True)
finally:
    Path(import_file).unlink()

print(version())
