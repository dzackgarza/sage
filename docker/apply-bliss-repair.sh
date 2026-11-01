#!/usr/bin/env bash
# Deploy the checked Bliss repair into an unpacked copy of the research image.
#
# The published image links its system libbliss without the ABI its headers
# describe, so sage.graphs.bliss corrupts the heap and canonical_label()
# segfaults. The image is fixed by the checked commits, which cannot ship while
# publication is held. This applies the same checked patch to an existing copy,
# rebuilds only the module it touches with that copy's own Meson/Ninja build,
# installs it through Meson, runs the graph and automorphism smoke tests, and
# records what it did. It changes this copy only: the image is not fixed, not
# republished, and no branch is created.
#
#   docker/apply-bliss-repair.sh PATCH
#
# PATCH is the checked commit's own patch (docker/../patches/0001-*.patch, see
# the note shipped with it). Environment: SAGE_ROOT (default /sage), BUILD_DIR
# (default $SAGE_ROOT/builddir), EXPECTED_REVISION (default the published one).
set -euo pipefail

patch_file="${1:?usage: apply-bliss-repair.sh PATCH}"
sage_root="${SAGE_ROOT:-/sage}"
build_dir="${BUILD_DIR:-${sage_root}/builddir}"
expected_revision="${EXPECTED_REVISION:-b0cd7d86e21eb450ed90e4c83707920e1d5d429a}"
module="bliss.cpython-314-x86_64-linux-gnu.so"
stamp=/opt/bliss-repair.json
venv="${sage_root}/.venv"
target="src/sage/graphs/${module}"

die() {
    printf 'bliss-repair: %s\n' "$*" >&2
    exit 1
}

[ -f "${patch_file}" ] || die "${patch_file} is not readable"
[ -d "${sage_root}/.git" ] || die "${sage_root} is not the image's git checkout"
[ -d "${build_dir}" ] || die "${build_dir} is not the image's build directory"

# The copy must be the image this patch was checked against, and the two files
# it touches must be exactly as that image left them.
revision="$(git -C "${sage_root}" rev-parse HEAD)"
[ "${revision}" = "${expected_revision}" ] || \
    die "${sage_root} is at ${revision}, but this patch is checked against ${expected_revision}"
patch_sha256="$(sha256sum "${patch_file}" | cut -d' ' -f1)"
site_packages="$("${venv}/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
installed="${site_packages}/sage/graphs/${module}"
[ -f "${installed}" ] || die "${installed} is not the module this image installed"

# A copy that already carries the patched source does not need the patch again;
# whether it needs a rebuild depends on the module it installed.
applied=0
patched_here=0
if git -C "${sage_root}" apply --reverse --check "${patch_file}" 2>/dev/null; then
    applied=1
fi
if [ "${applied}" -eq 0 ]; then
    for file in src/sage/graphs/meson.build src/sage/graphs/bliss_cpp/bliss_find_automorphisms.h; do
        git -C "${sage_root}" diff --quiet -- "${file}" || \
            die "${file} has local changes; this copy is not the published image"
    done
    git -C "${sage_root}" apply --check "${patch_file}" || \
        die "the patch does not apply to this source tree"
    git -C "${sage_root}" apply "${patch_file}"
    patched_here=1
fi

module_sha256="$(sha256sum "${installed}" | cut -d' ' -f1)"
if [ "${applied}" -eq 1 ] && [ -f "${stamp}" ] && \
    grep -q "\"patch_sha256\": \"${patch_sha256}\"" "${stamp}" && \
    grep -q "\"module_sha256\": \"${module_sha256}\"" "${stamp}"; then
    printf 'bliss-repair: already applied to this copy (%s)\n' "${stamp}"
    exit 0
fi

# Apply the checked patch, then rebuild only the affected target with the
# image's own build system: Ninja regenerates the build files from the patched
# Meson, compiles the patched C++, and Meson installs the newer module.
if ! "${venv}/bin/ninja" -C "${build_dir}" "${target}"; then
    [ "${patched_here}" -eq 0 ] || \
        git -C "${sage_root}" checkout -- src/sage/graphs/meson.build src/sage/graphs/bliss_cpp/bliss_find_automorphisms.h
    die "the rebuild failed; the source tree was restored where this run changed it"
fi
cp -a "${installed}" "${installed}.orig"
"${venv}/bin/meson" install -C "${build_dir}" --only-changed --no-rebuild

# The copy now has to behave: both canonical-label backends, the labelled case
# that segfaulted, and automorphism groups at their known orders.
if ! "${venv}/bin/python" - <<'PY'
from sage.all import Graph, graphs

assert Graph([[0, 1]]).canonical_label(edge_labels=True) == Graph([[0, 1]])
assert Graph([[0, 1]]).canonical_label() == Graph([[0, 1]])
labelled = Graph([(0, 1, "a"), (2, 3, None), (1, 2, "a"), (3, 0, None)])
relabelled = labelled.relabel({0: 2, 1: 0, 2: 3, 3: 1}, inplace=False)
for algorithm in ("bliss", "sage"):
    assert labelled.canonical_label(algorithm=algorithm, edge_labels=True) == (
        relabelled.canonical_label(algorithm=algorithm, edge_labels=True)
    ), algorithm
assert Graph([[0, 1]]).automorphism_group().order() == 2
assert Graph([[0, 1], [1, 2], [2, 3], [3, 0]]).automorphism_group().order() == 8
assert graphs.PetersenGraph().automorphism_group().order() == 120
PY
then
    cp -a "${installed}.orig" "${installed}"
    [ "${patched_here}" -eq 0 ] || \
        git -C "${sage_root}" checkout -- src/sage/graphs/meson.build src/sage/graphs/bliss_cpp/bliss_find_automorphisms.h
    die "the rebuilt module failed its smoke tests; the previous module was restored"
fi

module_sha256="$(sha256sum "${installed}" | cut -d' ' -f1)"
cat > "${stamp}" <<JSON
{
  "base_revision": "${revision}",
  "patch": "$(basename "${patch_file}")",
  "patch_sha256": "${patch_sha256}",
  "module": "${installed}",
  "module_sha256": "${module_sha256}",
  "note": "Incremental deployment of the checked Bliss repair into this unpacked copy. The published image is unchanged and the repair ships in it only when a rebuilt image is published."
}
JSON
printf 'bliss-repair: applied %s to %s\n' "$(basename "${patch_file}")" "${installed}"
printf 'bliss-repair: %s\n' "${stamp} records the base revision, patch and module digests"
