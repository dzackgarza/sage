#!/usr/bin/env bash
# Deploy the checked Bliss repair into an unpacked copy of the research image.
#
# The published image links its system libbliss without the ABI its headers
# describe, so sage.graphs.bliss corrupts the heap and canonical_label()
# segfaults. The image is fixed by the checked commits, which cannot ship while
# publication is held. This applies those commits' own patches, in the order
# given, to an existing copy; rebuilds only the module they touch with that
# copy's own Meson/Ninja build; installs it through Meson; runs the graph and
# automorphism smoke tests; and records which patches, at which digests, this
# copy carries. It changes this copy only: the image is not fixed, not
# republished, and no branch is created.
#
#   docker/apply-bliss-repair.sh PATCH [PATCH...]
#
# The patches are the checked commits' own patches, oldest first. Environment:
# SAGE_ROOT (default /sage), BUILD_DIR (default $SAGE_ROOT/builddir),
# EXPECTED_REVISION (default the published one).
set -euo pipefail

[ "$#" -ge 1 ] || {
    printf 'usage: apply-bliss-repair.sh PATCH [PATCH...]\n' >&2
    exit 2
}
patches=("$@")
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

for patch_file in "${patches[@]}"; do
    [ -f "${patch_file}" ] || die "${patch_file} is not readable"
done
[ -d "${sage_root}/.git" ] || die "${sage_root} is not the image's git checkout"
[ -d "${build_dir}" ] || die "${build_dir} is not the image's build directory"

# The copy must be the image these patches were checked against.
revision="$(git -C "${sage_root}" rev-parse HEAD)"
[ "${revision}" = "${expected_revision}" ] || \
    die "${sage_root} is at ${revision}, but these patches are checked against ${expected_revision}"

site_packages="$("${venv}/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
installed="${site_packages}/sage/graphs/${module}"
[ -f "${installed}" ] || die "${installed} is not the module this image installed"

# Every file the patches touch is either untouched by this copy or modified
# exactly by patches this copy already carries; anything else is someone's edit.
touched="$(grep -h '^diff --git ' "${patches[@]}" | awk '{ print $3 }' | sed 's|^a/||' | sort -u)"
for file in ${touched}; do
    git -C "${sage_root}" diff --quiet -- "${file}" && continue
    explained=0
    for patch_file in "${patches[@]}"; do
        grep -q "^diff --git a/${file} " "${patch_file}" || continue
        if git -C "${sage_root}" apply --reverse --check "${patch_file}" 2>/dev/null; then
            explained=1
        fi
    done
    [ "${explained}" -eq 1 ] || \
        die "${file} has local changes this repair does not explain; this copy is not the published image"
done

# Apply whatever this copy does not already carry, oldest patch first.
patched_here=0
records=()
for patch_file in "${patches[@]}"; do
    patch_sha256="$(sha256sum "${patch_file}" | cut -d' ' -f1)"
    records+=("$(basename "${patch_file}"):${patch_sha256}")
    if git -C "${sage_root}" apply --reverse --check "${patch_file}" 2>/dev/null; then
        continue
    fi
    git -C "${sage_root}" apply --check "${patch_file}" || \
        die "$(basename "${patch_file}") does not apply to this source tree"
    git -C "${sage_root}" apply "${patch_file}"
    patched_here=1
done

# Rebuild only when the source changed or the installed module is not the one
# the stamp records.
module_sha256="$(sha256sum "${installed}" | cut -d' ' -f1)"
up_to_date=0
if [ "${patched_here}" -eq 0 ] && [ -f "${stamp}" ]; then
    up_to_date=1
    for record in "${records[@]}"; do
        grep -q "\"${record}\"" "${stamp}" || up_to_date=0
    done
    grep -q "\"module_sha256\": \"${module_sha256}\"" "${stamp}" || up_to_date=0
fi
if [ "${up_to_date}" -eq 1 ]; then
    printf 'bliss-repair: this copy already carries %s\n' "${records[*]}"
    exit 0
fi

if ! "${venv}/bin/ninja" -C "${build_dir}" "${target}"; then
    if [ "${patched_here}" -eq 1 ]; then
        for patch_file in "${patches[@]}"; do
            git -C "${sage_root}" apply --reverse "${patch_file}" 2>/dev/null || true
        done
    fi
    die "the rebuild failed; patches this run applied were reverted"
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
    if [ "${patched_here}" -eq 1 ]; then
        for patch_file in "${patches[@]}"; do
            git -C "${sage_root}" apply --reverse "${patch_file}" 2>/dev/null || true
        done
    fi
    die "the rebuilt module failed its smoke tests; the previous module was restored"
fi

module_sha256="$(sha256sum "${installed}" | cut -d' ' -f1)"
{
    printf '{\n'
    printf '  "base_revision": "%s",\n' "${revision}"
    printf '  "patches": [\n'
    last=$(( ${#records[@]} - 1 ))
    for i in "${!records[@]}"; do
        record="${records[${i}]}"
        printf '    {"patch": "%s", "sha256": "%s"}' \
            "${record%%:*}" "${record##*:}"
        [ "${i}" -eq "${last}" ] && printf '\n' || printf ',\n'
    done
    printf '  ],\n'
    printf '  "module": "%s",\n' "${installed}"
    printf '  "module_sha256": "%s",\n' "${module_sha256}"
    printf '  "note": "Incremental deployment of the checked Bliss repair into this unpacked copy. The published image is unchanged and the repair ships in it only when a rebuilt image is published."\n'
    printf '}\n'
} > "${stamp}"
printf 'bliss-repair: applied %s to %s\n' "${records[*]}" "${installed}"
printf 'bliss-repair: %s records the base revision, patch digests and module digest\n' "${stamp}"
