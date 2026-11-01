#!/usr/bin/env bash
# Provision the Lean packages every checkout under a repository root resolves.
#
# The image build runs this after checking the research repositories out; it is
# also how an image that was unpacked earlier receives the same setup without
# being rebuilt. For each checkout with a lean-toolchain it installs the
# toolchain the checkout pins (a no-op where it is present), links the shared
# Lake packages under /opt/lake-packages into the packages directory that
# checkout's manifest resolves -- a project that sets packagesDir never reads
# .lake/packages -- retrieves Mathlib's official cache for the pinned revision,
# builds the packages Mathlib imports, and fails unless Mathlib is loadable
# afterwards. Mathlib itself is never compiled, and no package is cloned twice:
# a copy already materialized at the pinned revision is kept as it is.
#
#   docker/provision-lean-packages.sh [REPOSITORIES_ROOT]   (default /repos)
#
# Environment: LAKE_PACKAGES (default /opt/lake-packages), PYTHON (default
# python3). The toolchain comes from elan; the image declares ELAN_HOME.
set -euo pipefail

repositories_root="${1:-${REPOSITORIES_ROOT:-/repos}}"
lake_packages="${LAKE_PACKAGES:-/opt/lake-packages}"
python_bin="${PYTHON:-python3}"

manifest_packages() {
    "${python_bin}" - "$1" <<'PY'
import json
import sys

for package in json.load(open(sys.argv[1]))["packages"]:
    if package["type"] == "git":
        print(package["name"], package["url"], package["rev"])
PY
}

manifest_packages_dir() {
    "${python_bin}" - "$1" <<'PY'
import json
import sys

print(json.load(open(sys.argv[1])).get("packagesDir") or ".lake/packages")
PY
}

mkdir -p "${lake_packages}"
lean_project=
lean_packages_dir=

for checkout in "${repositories_root}"/*/; do
    checkout="${checkout%/}"
    [ -f "${checkout}/lean-toolchain" ] || continue
    elan toolchain install "$(cat "${checkout}/lean-toolchain")"
    [ -f "${checkout}/lake-manifest.json" ] || continue

    packages_dir="$(manifest_packages_dir "${checkout}/lake-manifest.json")"
    case "${packages_dir}" in
        /*) ;;
        *) packages_dir="${checkout}/${packages_dir}" ;;
    esac
    packages_dir="$(realpath -m "${packages_dir}")"
    mkdir -p "${packages_dir}"

    while read -r name url revision; do
        shared="${lake_packages}/${name}@${revision}"
        if [ ! -d "${shared}" ]; then
            git clone --quiet --filter=blob:none "${url}" "${shared}"
            git -C "${shared}" checkout --quiet "${revision}"
        fi
        target="${packages_dir}/${name}"
        if [ -d "${target}" ] && [ ! -L "${target}" ]; then
            # An image unpacked earlier carries its own copy, with the cache
            # unpacked into it: keep that copy, and say so when the checkouts
            # disagree about the revision a shared directory can only hold once.
            current="$(git -C "${target}" rev-parse HEAD 2>/dev/null || true)"
            if [ "${current}" != "${revision}" ]; then
                printf 'warning: %s is at %s and is left as it is; %s pins %s\n' \
                    "${target}" "${current:-no revision}" "${checkout##*/}" "${revision}" >&2
            fi
        else
            if [ -L "${target}" ] && [ "$(readlink -f "${target}")" != "$(readlink -f "${shared}")" ]; then
                printf 'warning: %s is pinned at more than one revision; linking %s\n' \
                    "${target}" "${shared}" >&2
            fi
            ln -sfn "${shared}" "${target}"
        fi
    done < <(manifest_packages "${checkout}/lake-manifest.json")

    if [ -e "${packages_dir}/mathlib" ] && [ -z "${lean_project}" ]; then
        lean_project="${checkout}"
        lean_packages_dir="${packages_dir}"
    fi
done

# One project's Mathlib closure is every project's: the packages are shared by
# revision. The cache is retrieved before the build, so Mathlib itself is not
# compiled here; an image that already carries it skips the retrieval.
if [ -n "${lean_project}" ]; then
    mathlib_olean="${lean_packages_dir}/mathlib/.lake/build/lib/lean/Mathlib.olean"
    if [ ! -f "${mathlib_olean}" ]; then
        ( cd "${lean_project}" && lake exe cache get )
    fi
    ( cd "${lean_project}" && lake build Mathlib )
    test -f "${mathlib_olean}"
fi
