# Consumer validation of the GAP matrix-group capability in a published image.
#
# Run inside the image, not on the host:
#   PEAKRSS_LIMIT=...  (the shared process-tree RSS guard, not ulimit -v):
#   PEAKRSS_LIMIT_MIB=6144 python peakrss.py -- \
#       python3 docker/sage-image.py --cache <cache> --reference sha256:<index digest> run -- \
#           /sage/.venv/bin/sage /work/results/consumer-check.py
#
# What it establishes: the image's Sage loads the four GAP packages through libgap,
# from the root the Debian `gap` wrapper puts on GAP_ROOT_PATHS, and an order comes
# back from genss's stabilizer chain. What it does not establish: any exact order for
# the port's generated subgroup of O(V). genss's chain is Monte Carlo bounded by
# ErrorBound and VerifyStabilizerChainMC has no method for a plain matrix group, so
# the deg-4 Borel number below is capability evidence only, and the degree-10 module
# the port needs is not attempted here.
import sys
import time

from sage.libs.gap.libgap import libgap
from sage.libs.gap.util import kernel_info

version, arch, roots = kernel_info()
print(f"kernel: GAP {version} arch {arch}")
print(f"roots: {roots}")
assert sys.prefix == "/sage/.venv", sys.prefix
assert "/usr/share/gap/" in roots, roots

for name in ("orb", "forms", "genss", "recog"):
    started = time.time()
    loaded = libgap.eval('LoadPackage("%s")' % name)
    assert loaded.sage() is True, (name, loaded)
    print(f"LoadPackage({name}) = true in {time.time() - started:.3f}s, version "
          f"{libgap.eval('PackageInfo(\"%s\")[1].Version' % name)}")

assert libgap.eval("IsBound(RecognizeGroup)").sage() is True
assert libgap.eval("IsBound(StabilizerChain)").sage() is True
assert libgap.eval("IsBound(SizeMC)").sage() is True
# GAP answers an unknown package with `fail`, a boolean that has no Sage
# conversion (element.pyx raises for it), so the comparison happens in GAP.
assert libgap.eval('LoadPackage("not_a_gap_package") = fail').sage() is True

borel = libgap.function_factory(
    "function(d) local F, g, i, m; F := GF(5); g := []; "
    "for i in [1..d-1] do m := IdentityMat(d, F); m[i][i+1] := One(F); Add(g, m); od; "
    "m := IdentityMat(d, F); m[1][1] := Z(5); Add(g, m); return Group(g); end"
)
chain = libgap.function_factory(
    "function(G) return StabilizerChain(G, rec(ErrorBound := 1/10^6)); end"
)
gap_size = libgap.function_factory("Size")

started = time.time()
order = gap_size(chain(borel(4))).sage()
elapsed = time.time() - started
print(f"genss chain order of the deg-4 GF(5) Borel: {order} in {elapsed:.3f}s "
      f"(expect {4 * 5**6})")
assert order == 4 * 5**6, order

print("CONSUMER CAPABILITY CHECK PASSED")
