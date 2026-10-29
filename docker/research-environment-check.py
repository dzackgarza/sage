# Fails the image build if any system the research image exists to provide is
# absent. Run with the image's sage: `sage docker/research-environment-check.py`.
import importlib

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

for module in (
    "sage_julia_bridge", "sage_extensions", "sage_categories",
    "sage_categories_homotopy", "sage_lsp", "vinal", "tree_sitter_sage",
):
    importlib.import_module(module)

print(version())
