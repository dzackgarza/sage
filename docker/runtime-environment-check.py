# Fails the runtime image build if anything a Sage-and-GAP consumer needs is
# absent. Run with the runtime stage's sage:
# `sage docker/runtime-environment-check.py`.
#
# The full image runs docker/research-environment-check.py, which is a superset
# and stays on the `develop` tag. This one covers exactly what the runtime tag
# ships: Sage and its checkout, GAP as the only GAP with its matrix-group
# packages, sage-categories' pinned GAP allocation, and the documented consumer
# commands run with no network, which is the property a README example depends on.
import importlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sage.all import QQ, matrix
from sage.libs.gap.libgap import libgap
from sage.libs.gap.util import kernel_info

subprocess.run([
    "python", "-c", "import sys, sage.all; assert sys.prefix == '/sage/.venv'",
], check=True)
print(f"python prefix /sage/.venv, Sage importable")

# Sage ships what the image declares: the version Sage reports and the commit the
# checkout sits at are both read from the tree, not assumed. This runs only inside a
# build, and the publish workflow writes `git rev-parse HEAD` into the stamp before
# the build starts (research-environment-image.yml, both the ordinary and the spinor
# revision steps), so the two must agree. A rootfs adopted in place is not a built
# image and is not what this check sees: its stamp names the image it came from,
# which results/runtime-adoption-220293469c53-acceptance.md records.
from sage.version import version as sage_version

declared_source = Path("/sage/.spinor-base-revision")
sage_root_commit = subprocess.run(
    ["git", "-C", "/sage", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
).stdout.strip()
assert len(sage_root_commit) == 40, sage_root_commit
print(f"Sage {sage_version} at {sage_root_commit}")
assert declared_source.is_file(), declared_source
recorded = declared_source.read_text().strip()
assert recorded == sage_root_commit, (recorded, sage_root_commit)
print(f"the image's recorded source is this checkout: {recorded}")

# Exactly one GAP, the one built from Sage's pinned source: no Debian copy is
# shipped, because kernel_info() runs the bare command `gap` and a second copy
# turns any PATH into a GAP that libgap.so.11 cannot read (sage#11).
distribution_gap = [
    path for path in (
        "/usr/bin/gap", "/usr/lib/gap", "/usr/share/gap",
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

declared_gap = Path("/sage/build/pkgs/gap/package-version.txt").read_text().strip()
gap_version, gap_arch, gap_roots = kernel_info()
assert gap_version == declared_gap, (gap_version, declared_gap)
assert "/sage/.venv/lib/gap/" in gap_roots, gap_roots
loaded_libgap = [
    line.split()[-1]
    for line in Path("/proc/self/maps").read_text().splitlines()
    if "libgap.so" in line and line.split()[-1].startswith("/")
]
assert loaded_libgap and all(path.startswith("/sage/.venv/lib/") for path in loaded_libgap), loaded_libgap
for name in ("orb", "forms", "genss", "recog"):
    assert libgap.eval(f'LoadPackage("{name}")').sage() is True, name
print(f"GAP {gap_version} ({gap_arch}) at {gap_roots}, libgap {loaded_libgap[0]}")

# sage-categories resolves its own exact homalg/CAP releases into its checkout
# (sage#10), so the runtime image carries that one checkout and this asserts the
# whole pin list is installed and loads through the library's own loader.
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
assert len(load_packages(pinned)) == len(pinned), len(pinned)
print(f"sage-categories: {len(pinned)} pinned GAP packages load from {allocation}")

# The documented consumer commands, with no network and an empty Julia depot: a
# README example must not fetch anything at import time. juliacall is the reason
# this matters -- its import resolves a Julia download through juliapkg -- so the
# runtime image does not ship it, and that absence is asserted rather than assumed.
for absent in ("juliacall", "juliapkg"):
    assert importlib.util.find_spec(absent) is None, (
        f"{absent} is installed; importing it resolves a Julia download, which a "
        "runtime image without Julia must never do"
    )
with tempfile.TemporaryDirectory() as empty_home:
    probe = (
        "import sys\n"
        "from sage.all import QQ, matrix\n"
        "assert sys.prefix == '/sage/.venv', sys.prefix\n"
        "assert matrix(QQ, [[2, 1], [1, 2]]).det() == 3\n"
        "from sage_extensions.all import Lattices\n"
        "from sage_julia_bridge import julia\n"
        "print('consumer example OK', sys.executable)\n"
    )
    environment = {
        "PATH": "/sage/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": empty_home,
        "JULIA_DEPOT_PATH": os.path.join(empty_home, "depot"),
    }
    # A dead proxy is the offline assertion available inside a build: any library
    # that tries to fetch fails instead of succeeding quietly.
    environment.update(
        {"http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
         "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
         "no_proxy": "", "NO_PROXY": ""}
    )
    run = subprocess.run(
        [sys.executable, "-c", probe], env=environment, capture_output=True, text=True
    )
    assert run.returncode == 0, (run.returncode, run.stdout, run.stderr)
    print(run.stdout.strip())

print(f"SageMath runtime image OK: {sage_version}")
