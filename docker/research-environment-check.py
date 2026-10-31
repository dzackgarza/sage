# Fails the image build if any system the research image exists to provide is
# absent. Run with the image's sage: `sage docker/research-environment-check.py`.
import importlib
import os
import subprocess
from pathlib import Path

from sage.features.all import all_features
from sage.features.gap import GapPackage
from sage.features.interfaces import Macaulay2
from sage.all import Graph, graphs, QQ
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

# Each Lean checkout runs Lake on the toolchain it pins.
for toolchain in Path("/repos").glob("*/lean-toolchain"):
    subprocess.run(["lake", "--version"], cwd=toolchain.parent, check=True)

print(version())
