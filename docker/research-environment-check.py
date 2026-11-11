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

# Exactly one GAP: the one built from the pinned source (sage#11, sage#26). What
# sage#11 found was a *distribution* GAP -- Debian's 4.14, whose library libgap.so.11
# reads and segfaults in DoOperation1Args -- so what is asserted here is what makes a
# path a distribution GAP, not that the path exists:
#
#   * a Debian package installed it. `dpkg-query -S` answers that for a path, and the
#     apt package list below answers it for the package database as a whole.
#   * /usr/bin/gap is not this image's launcher. docker/gap-launcher.sh, whose body is
#     `exec /sage/.venv/bin/gap "$@"`, is copied to /usr/local/bin/gap for anything
#     whose PATH this image built, and to /usr/bin/gap for a process with no PATH at
#     all: Python's own /bin:/usr/bin fallback is what `env -i`, and the probe below,
#     resolve `gap` through (sage#24). A launcher starts the same Sage-owned binary as
#     /sage/.venv/bin/gap, so it is not a second GAP -- and deleting it to satisfy this
#     check takes sage#24's function away, which is what fc971cae did and sage#26
#     restores.
launcher_path = "/usr/bin/gap"
# The rest of a distribution GAP's tree. The Sage-owned GAP's roots are under
# /sage/.venv (kernel_info() reports them above), so a tree at any of these paths came
# from somewhere else and is absent rather than merely unowned.
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
# The check's own path: under $SAGE_BIN, __file__ is the sage runner's own
# module (site-packages/sage/all.py), not this script's path, so the launcher
# cannot be read relative to __file__ (image run 42948264723). sys.argv[0] is
# the path the check was invoked as, which the sage runner forwards, so the
# launcher is read from beside the check wherever the check is run from.
launcher = Path(sys.argv[0]).resolve().with_name("gap-launcher.sh").read_bytes()
assert Path(launcher_path).is_file(), (
    "/usr/bin/gap is missing: a process whose environment did not come from this image "
    "has no `gap` at all (sage#24)"
)
assert Path(launcher_path).read_bytes() == launcher, (
    "/usr/bin/gap is not this image's launcher (docker/gap-launcher.sh): "
    f"{Path(launcher_path).read_text(errors='replace')[:120]!r}"
)

# The probe that found sage#11, and the reason the launcher is at /usr/bin/gap: an
# emptied environment leaves PATH unset, so a bare `gap` resolves through Python's own
# /bin:/usr/bin, and libgap is then initialised on whatever library that GAP reports.
# It must succeed -- the version the source pins, the Sage-owned roots, arithmetic
# through libgap -- because the launcher is always there: a traceback is a failure now,
# and dying on a signal is the segfault sage#11 was.
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

# A HOME past GAP's line width (sage#20, sage#27): the roots record GAP prints
# is broken at the width, and the fix reads it across the break. The import of
# the interface under that HOME is the acceptance: it succeeds on the image
# that carries the fix, and dies at ValueError on one that ships the defect.
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

# The commit of each research repository this image installed
# (docker/install-research-repositories.sh writes the file, resolved at each
# repository's main head at build time -- sage#24). Printed here for the
# consumer to read in the image; the file is the image's own record.
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

# ---- one libflint: python-flint and Sage in one process (sage#25) ----------
# python-flint's wheel vendors its own libflint, and Sage loads the system one:
# in one process that imports sage.all and then computes with fmpz_mat, the
# vendored build's symbols bind to the other build's library and the
# interpreter dies on SIGSEGV (lattice-database#29 found it in the published
# image). The repair is one libflint: python-flint is built against the flint
# Sage uses, which python-flint 0.9's build docs accept -- FLINT 3.0-3.6
# (pypi.org/project/python-flint/0.9.0) -- so the venv's wheel is replaced by a
# source build. The call of the issue, run in a fresh process, asserts its
# result; and the process maps exactly one libflint.
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

# ---- one libflint: pynormaliz and Sage in one process (sage#31) -----------
# pynormaliz's wheel vendors a Normaliz that vendors a libflint, and Sage loads
# the system one: the defect class of sage#25, from a second wheel. The pin
# that decides the repair: pynormaliz 2.24's own source refuses a Normaliz
# older than 3.11.1 (NormalizModule.cpp asserts NMZ_RELEASE >= 31100) while
# Debian trixie ships 3.10.4, so the image builds the Normaliz Sage's package
# metadata pins (build/pkgs/normaliz) into the venv against the system flint,
# and pynormaliz from source against it. Both engines compute the Hilbert
# basis of a non-unimodular cone -- [[1,0],[1,2]], whose basis has a point
# that is not a ray -- and must agree; and the same process maps exactly one
# libflint. Unlike sage#25's call this one survives a defective image, so the
# computing process reports its own maps.
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

# An ordinary call through the *external* GAP interface saves a workspace of
# GAP's whole memory image and starts GAP from it on every call after that
# (`SaveWorkspace`, then `gap -L <workspace>`).  Three properties are asserted
# here, each of them wrong before sage#19:
#
# * the call works in an environment this image did not supply -- PATH without
#   $SAGE_LOCAL/bin, a HOME outside the image -- which is what PRoot over the
#   unpacked filesystem gives a process, and what made the interface stop with
#   `FileNotFoundError: 'gap'`;
# * the workspace's name is the GAP build's, not the caller's home, so a second
#   HOME over one DOT_SAGE reuses it instead of writing a second 70 MB copy;
# * on a filesystem with no room for another workspace, the workspaces of
#   *other* builds are what the cache gives up, and the call still returns.  The
#   threshold is raised rather than the disk filled.
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

# `from sage.interfaces.gap import gap` asks kernel_info() for the GAP build at
# import time -- the workspace is named after it -- and kernel_info() reads three
# records out of `gap --systemfile kernel-info.g`.  GAP breaks a printed line
# that reaches its line width and marks the break with a backslash, and the
# third record (the roots) begins with `$HOME/.gap/`: a HOME long enough to make
# GAP break that record used to stop the import with `ValueError: too many
# values to unpack (expected 3)`, before any mathematics ran (sage#20).  The
# records are read across the breaks now, so the length of HOME cannot decide
# whether the interface imports.  The HOME is grown until GAP is measured
# breaking the record, so the premise is asserted rather than assumed.
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
             # The image's own PATH: what is under test here is the length of
             # HOME, not whether a launcher's PATH finds a `gap` (sage#19).
             "PATH": "/sage/.venv/bin:/usr/local/bin:/usr/bin:/bin"},
        capture_output=True, text=True, check=False,
    )
    assert imported.returncode == 0, (imported.returncode, imported.stdout, imported.stderr)
    assert imported.stdout.strip().splitlines()[-1] == "order 24", imported.stdout
    print(f"the GAP interface imported with a {len(str(long_home))}-character HOME, "
          f"at which GAP breaks its roots record")

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

# The record: the revision of every research package this image actually carries.
# A checkout installed editable answers from its git tree; a git wheel answers with
# the commit_id in its direct_url.json. Neither is held to uv.lock: a research
# package is installed from its /repos checkout at the main head the build resolved
# (sage#24), so the lock's commit -- only where the last relock left it -- is not
# the source of truth for its revision. Each checkout is held to the head the
# install recorded in /sage/.research-revisions, one "<name> <commit>" per
# repository -- the file the block above validates, and what a consumer reads in
# the image -- and both revisions are printed, so a build log states them instead
# of implying them.
import json
import tomllib
from importlib.metadata import PackageNotFoundError, distribution

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
    # The repository a git source lives in: the URL's path, its query dropped --
    # sage-categories-homotopy is installed from a subdirectory of the
    # sage-categories checkout, and its source URL carries that subdirectory as
    # ?subdirectory=..., which is not part of any checkout's name.
    repository = source.split("#")[0].split("?")[0].rsplit("/", 1)[-1].removesuffix(".git")
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

# ---- the image's one shared Lean project (sage#13) ---------------------------
# The image carries mathlib4 at the head of its master branch, on the toolchain
# that revision pins, with its whole dependency closure built inside /opt/mathlib
# and Mathlib's oleans from the official cache.
# docker/provision-lean-packages.sh resolves that head on every build, compares it
# with this record, and rebuilds the closure only when it moved; what this check
# validates is the project the image carries -- and, since sage#13's acceptance
# asks it, the Lean checkouts under /repos against that project: each one that
# follows the image elaborates `import Mathlib` through its own Lake
# environment here, and a checkout whose pin disagrees fails this check loudly,
# naming the checkout and both revisions. Following the image is still filed in
# the owning repositories (lean-categories#118, lean-cas-dsl#90); what this check
# adds is the image's own half of that contract.
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

# The toolchain is the one that revision pins, and the image's own: there is no
# second Mathlib and no second toolchain.
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

# The closure, built once, in the one project: Mathlib's olean is there, and every
# package the project's own manifest pins is a checkout at exactly that revision
# with its build directory present.
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

# `lake env` is Lake itself answering, so the toolchain it reports is the one a
# consumer's build would run on.
lake_env_version = subprocess.run(
    ["lake", "env", "lean", "--version"], cwd=project, capture_output=True, text=True,
    check=True, timeout=900,
).stdout.strip()
expected_version = record["toolchain"].rsplit(":", 1)[-1].lstrip("v")
assert expected_version in lake_env_version, (lake_env_version, record["toolchain"])
print(f"lake env lean --version in {project}: {lake_env_version.splitlines()[0]}")

# A build of Mathlib from the project itself: after provisioning this is a no-op,
# and the assertion is that Lake finds the closure it was built with -- a project
# whose oleans are there but whose closure is not stops here.
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
    # The same import a consumer writes, elaborated through the image's own Lake
    # environment rather than a LEAN_PATH assembled here.
    elaborated = subprocess.run(
        ["lake", "env", "lean", import_file], cwd=project,
        capture_output=True, text=True, check=True, timeout=1800,
    ).stdout.strip()
    assert "Nat.add_comm" in elaborated, elaborated
finally:
    Path(import_file).unlink()
print(f"import Mathlib in {project}: {elaborated.splitlines()[-1]}")

# ---- the Lean checkouts under /repos, resolved at the Mathlib the image carries (sage#13)
# Each checkout's manifest is resolved by the image's own provisioning -- the
# entries for mathlib and every package of the shared project's manifest are
# set to the shared project's revisions, and the checkout's packages are the
# shared project's built copies -- so the revision the image recorded is the
# one each checkout resolves. What is asserted here is that the checkout
# elaborates `import Mathlib` through its own Lake environment against that
# Mathlib; a checkout that does not build against it fails here, loudly,
# naming the checkout and the revision.
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
        checkout_elaborated = subprocess.run(
            ["lake", "env", "lean", checkout_file], cwd=directory,
            capture_output=True, text=True, check=True, timeout=1800,
        ).stdout.strip()
        if "Nat.add_comm" not in checkout_elaborated:
            raise SystemExit(
                f"{directory} does not build against the Mathlib the image carries, and "
                f"the image's check fails loudly for it (sage#13): it carries "
                f"{image_revision}"
            )
    finally:
        Path(checkout_file).unlink()
    print(f"import Mathlib in {directory}: {checkout_elaborated.splitlines()[-1]}")

# ---- the document toolchain the project sites build with (sage#22) ----------
# Both site builds outside the image install this at every run, so the image carries
# it and a site build installs nothing: quarto, a full TeX Live, pdf2svg,
# poppler-utils and node. Each is asserted by doing what the sites do with it -- a
# document through TeX's own file lookup, a page through pdf2svg and poppler, the
# version quarto reports -- and an absent one fails here, in the build, rather than
# in a consumer's run.
import shutil

document_tools = ["quarto", "pdf2svg", "pdftoppm", "kpsewhich", "node", "lualatex"]
absent = [tool for tool in document_tools if shutil.which(tool) is None]
assert not absent, f"the image carries no {absent}"

# The TeX packages the two sites load, from the sources themselves: research's
# docs.yml renders figures through the shared pandoc-config preamble
# (styles/preambles/dzg-preamble.tex in dzackgarza/pandoc-config) and installs
# luahyperbolic from CTAN, and new-qual-site's development.yml builds with
# TeX Live's scheme-full. Each is asserted by kpsewhich finding it.
tex_packages = [
    "amsmath", "amsthm", "amssymb", "amsfonts", "mathtools", "mathrsfs",
    "bm", "esint", "stmaryrd", "bbm", "upgreek", "iftex", "fontenc",
    "graphicx", "subcaption", "xcolor", "amscd", "centernot", "slashed",
    "tikz", "tikz-cd", "tikz-3dplot", "etoolbox", "xparse",
    "dynkin-diagrams", "quiver", "pgfplots", "luatex85", "luahyperbolic",
    "xy", "microtype", "hyperref", "bookmark", "enumitem",
    "standalone",
]
for package in tex_packages:
    found = subprocess.run(
        ["kpsewhich", f"{package}.sty"], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert found, f"kpsewhich found no {package}.sty: the image does not carry it"

# The TikZ libraries the same preamble loads.
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

# Full TeX Live, not a subset: the package the issue names, and the files the sites'
# figures load. `luahyperbolic.sty` is the one research's CI has to fetch from CTAN
# because Ubuntu's TeX Live is older than the package; TeX Live 2025 has it, so a
# full set in this image has it too.
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

# pdf2svg and poppler on a page this check writes: the same two steps a site build
# runs to turn a figure into an SVG and a thumbnail. A presence test would pass on a
# binary whose library is missing.
pdf = Path(tempfile.mkdtemp(prefix="document-tools-"))
objects = [
    b"<</Type/Catalog/Pages 2 0 R>>",
    b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
    b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 10 10]>>",
]
page = bytearray(b"%PDF-1.4\n")
offsets = []
for number, body in enumerate(objects, start=1):
    offsets.append(len(page))
    page += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
xref = len(page)
page += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
for offset in offsets:
    page += f"{offset:010d} 00000 n \n".encode()
page += f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
(pdf / "page.pdf").write_bytes(bytes(page))
subprocess.run(["pdf2svg", str(pdf / "page.pdf"), str(pdf / "page.svg")], check=True)
svg = (pdf / "page.svg").read_text(encoding="utf-8", errors="replace")
assert "<svg" in svg, svg[:400]
poppler_version = subprocess.run(
    ["pdftoppm", "-v"], capture_output=True, text=True, check=False
).stderr.strip() or subprocess.run(
    ["pdftoppm", "-v"], capture_output=True, text=True, check=False
).stdout.strip()
assert "pdftoppm" in poppler_version, poppler_version
subprocess.run(
    ["pdftoppm", "-r", "10", "-png", str(pdf / "page.pdf"), str(pdf / "thumb")], check=True
)
assert list(pdf.glob("thumb*.png")), "pdftoppm wrote no image"
print(f"pdf2svg rendered a page: {len(svg)} bytes of SVG; {poppler_version.splitlines()[0]}")

node_version = subprocess.run(
    ["node", "--version"], capture_output=True, text=True, check=True
).stdout.strip()
assert node_version.startswith("v"), node_version
print(f"node {node_version}")


print(version())
