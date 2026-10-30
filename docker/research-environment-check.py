# Fails the image build if any system the research image exists to provide is
# absent. Run with the image's sage: `sage docker/research-environment-check.py`.
import importlib
import subprocess
from pathlib import Path

from sage.features.all import all_features
from sage.features.gap import GapPackage
from sage.features.interfaces import Macaulay2

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

# The research packages run from their checkouts under /repos. The homotopy
# package is a compiled extension built from its checkout, so its module is in
# site-packages.
for module in (
    "dzack_research", "latticedb", "sage_categories", "sage_extensions",
    "sage_indefinite_port", "sage_julia_bridge", "sage_lsp", "tree_sitter_sage",
    "vinal",
):
    origin = importlib.import_module(module).__file__
    assert origin.startswith("/repos/"), (module, origin)
importlib.import_module("sage_categories_homotopy")

# Each Lean checkout runs Lake on the toolchain it pins.
for toolchain in Path("/repos").glob("*/lean-toolchain"):
    subprocess.run(["lake", "--version"], cwd=toolchain.parent, check=True)

print(version())
