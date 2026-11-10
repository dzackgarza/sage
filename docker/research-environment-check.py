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
# the commit_id in its direct_url.json. Both are printed and held to the lock, so a
# build log states the revisions instead of implying them.
import json
import tomllib
from importlib.metadata import PackageNotFoundError, distribution

lock = tomllib.loads(Path("/sage/uv.lock").read_text(encoding="utf-8"))
for package in sorted(lock["package"], key=lambda entry: entry["name"]):
    source = package.get("source", {}).get("git")
    if source is None:
        continue
    name, pinned = package["name"], source.split("#")[1]
    observed = None
    repository = source.split("#")[0].rsplit("/", 1)[-1].removesuffix(".git")
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
    print(f"research {name}: {observed} ({kind}, lock {pinned})")
    assert observed == pinned, (name, observed, pinned)

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

# ---- the Lean checkouts under /repos, against the one shared project (sage#13)
# The acceptance of sage#13: `lake build` of a file containing `import Mathlib`
# succeeds in each Lean checkout under /repos once it follows the image, and a
# checkout whose pin disagrees with the image fails the image's check loudly,
# naming the checkout and both revisions. A checkout follows the image when its
# mathlib pin is the revision the image resolved and every closure pin is the
# shared project's own; the probe is the same import a consumer writes,
# elaborated through the checkout's own Lake environment.
image_revision = record["revision"]
project_pins = pins_of(project)
checkouts = [
    directory for directory in sorted(Path("/repos").iterdir())
    if directory.is_dir() and not directory.name.startswith(".")
    and (directory / "lake-manifest.json").is_file()
]
assert checkouts, "the image carries no Lean checkout under /repos"
for directory in checkouts:
    pins = pins_of(directory)
    follows = pins.get("mathlib") == image_revision and all(
        project_pins.get(name) == revision for name, revision in pins.items()
    )
    if not follows:
        disagreeing = [
            f"{name}: the checkout pins {revision}, the image carries {project_pins.get(name)}"
            for name, revision in sorted(pins.items())
            if name == "mathlib" and revision != image_revision
            or name != "mathlib" and project_pins.get(name) != revision
        ]
        raise SystemExit(
            f"{directory} does not follow the image, and the image's check fails loudly "
            f"for it (sage#13): {'; '.join(disagreeing)}"
        )
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
        assert "Nat.add_comm" in checkout_elaborated, checkout_elaborated
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
