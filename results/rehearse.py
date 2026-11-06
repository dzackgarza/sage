import resource
guard = 6144 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (guard, guard))
from sage.libs.gap.libgap import libgap
from sage.libs.gap.util import kernel_info

version, arch, roots = kernel_info()
print("kernel:", version, arch)
print("roots:", roots)
assert "/usr/share/gap/" in roots, roots
for name in ("orb", "forms", "genss", "recog"):
    loaded = libgap.eval('LoadPackage("%s")' % name)
    print("load", name, "->", loaded)
    assert loaded.sage() is True, (name, loaded)
print("missing package ->", libgap.eval('LoadPackage("not_a_gap_package")'))

borel = libgap.function_factory(
    "function(d) local F, g, i, m; F := GF(5); g := []; "
    "for i in [1..d-1] do m := IdentityMat(d, F); m[i][i+1] := One(F); Add(g, m); od; "
    "m := IdentityMat(d, F); m[1][1] := Z(5); Add(g, m); return Group(g); end")
chain = libgap.function_factory(
    "function(G) return StabilizerChain(G, rec(ErrorBound := 1/10^6)); end")
size = libgap.function_factory("Size")
order = size(chain(borel(4))).sage()
print("genss chain order of the deg-4 GF(5) Borel:", order)
assert order == 4 * 5 ** 6, order
print("RecognizeGroup bound:", libgap.eval("IsBound(RecognizeGroup)"))
print("ALL ASSERTIONS PASSED")
