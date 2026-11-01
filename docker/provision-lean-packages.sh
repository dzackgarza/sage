#!/usr/bin/env bash
# Provision the Lean packages every checkout under a repository root resolves.
#
# The image build runs this after checking the research repositories out; an
# image that was unpacked earlier runs the same script, with the checks out
# already in place, and reaches the same state without being rebuilt.
#
# For every checkout with a lean-toolchain it installs the toolchain that
# checkout pins (a no-op where it is present), and for every Lake package its
# manifest pins it keeps one checkout per revision under /opt/lake-packages and
# links that checkout into the directory the project resolves. A project's
# packages directory is fixed by its lakefile -- these declare one shared
# packagesDir -- so a name pinned at two revisions there cannot be resolved for
# both: that is reported, neither revision is chosen, and the projects that need
# the other one fail below. Mathlib's oleans come from the official cache for
# the pinned revision, so Mathlib itself is never compiled; the packages Mathlib
# imports are built once. Finally each project is checked against its own
# manifest: every package it pins must be present, at the pinned revision, in
# the directory that project declares.
#
#   docker/provision-lean-packages.sh [REPOSITORIES_ROOT]   (default /repos)
#
# Environment: LAKE_PACKAGES (default /opt/lake-packages), PYTHON (default
# python3). The toolchain comes from elan; the image declares ELAN_HOME.
set -euo pipefail

repositories_root="${1:-${REPOSITORIES_ROOT:-/repos}}"
lake_packages="${LAKE_PACKAGES:-/opt/lake-packages}"
python_bin="${PYTHON:-python3}"

# The image keeps elan and its toolchains under /opt/elan. A runner that does
# not apply the image's environment -- PRoot over the unpacked filesystem, a
# bare exec -- still reaches them through these two lines.
if ! command -v elan > /dev/null 2>&1 && [ -x /opt/elan/bin/elan ]; then
    PATH="/opt/elan/bin:${PATH}"
    export PATH
fi
if [ -z "${ELAN_HOME:-}" ] && [ -d /opt/elan ]; then
    ELAN_HOME=/opt/elan
    export ELAN_HOME
fi

# checkout \t packages_dir \t name \t url \t revision, one row per pinned package
analysis="$("${python_bin}" - "${repositories_root}" <<'PY'
import json
import os
import sys

root = sys.argv[1]
for checkout in sorted(os.listdir(root)):
    directory = os.path.join(root, checkout)
    manifest = os.path.join(directory, "lake-manifest.json")
    if not os.path.isfile(os.path.join(directory, "lean-toolchain")) or not os.path.isfile(manifest):
        continue
    with open(manifest) as handle:
        data = json.load(handle)
    packages_dir = data.get("packagesDir") or ".lake/packages"
    if not os.path.isabs(packages_dir):
        packages_dir = os.path.join(directory, packages_dir)
    packages_dir = os.path.realpath(packages_dir)
    for package in data["packages"]:
        if package["type"] == "git":
            print(directory, packages_dir, package["name"], package["url"], package["rev"], sep="\t")
PY
)"

declare -A pinned=()
declare -A conflicting=()
problems=0
while IFS=$'\t' read -r checkout packages_dir name url revision; do
    [ -n "${checkout}" ] || continue
    key="${packages_dir}"$'\t'"${name}"
    if [ -z "${pinned[${key}]:-}" ]; then
        pinned[${key}]="${revision}"$'\t'"${checkout##*/}"
        continue
    fi
    IFS=$'\t' read -r prior_revision prior_checkout <<< "${pinned[${key}]}"
    if [ "${prior_revision}" != "${revision}" ]; then
        printf 'error: %s is pinned at %s by %s and at %s by %s, and both resolve %s\n' \
            "${name}" "${prior_revision}" "${prior_checkout}" "${revision}" "${checkout##*/}" "${packages_dir}" >&2
        printf 'error: one packages directory cannot hold both revisions; align the pins or give the checkouts distinct packagesDir values\n' >&2
        conflicting[${key}]=1
        problems=1
    fi
done <<< "${analysis}"

# Content-addressed checkouts, and the links each project resolves.
declare -A linked=()
while IFS=$'\t' read -r checkout packages_dir name url revision; do
    [ -n "${checkout}" ] || continue
    key="${packages_dir}"$'\t'"${name}"
    [ -z "${conflicting[${key}]:-}" ] || continue
    mkdir -p "${packages_dir}"
    shared="${lake_packages}/${name}@${revision}"
    if [ ! -d "${shared}" ]; then
        git clone --quiet --filter=blob:none "${url}" "${shared}"
        git -C "${shared}" checkout --quiet "${revision}"
    fi
    target="${packages_dir}/${name}"
    if [ -d "${target}" ] && [ ! -L "${target}" ]; then
        # An image unpacked earlier carries its own copy, with the cache
        # unpacked into it: keep that copy rather than duplicating the packages.
        current="$(git -C "${target}" rev-parse HEAD 2>/dev/null || true)"
        if [ "${current}" != "${revision}" ]; then
            printf 'warning: %s is at %s; left as it is\n' "${target}" "${current:-no revision}" >&2
        fi
    else
        ln -sfn "${shared}" "${target}"
    fi
    linked[${key}]=1
done <<< "${analysis}"

# The toolchain each checkout pins, then one Mathlib build for every project:
# the packages are shared by revision, and the cache is retrieved first so
# Mathlib itself is not compiled here. Projects with conflicting pins never get
# here with a wrong package, because nothing was linked for them.
checkouts="$(printf '%s\n' "${analysis}" | cut -f1 | awk '!seen[$0]++')"
while read -r toolchain; do
    [ -n "${toolchain}" ] || continue
    elan toolchain install "${toolchain}"
done <<< "$(while read -r checkout; do cat "${checkout}/lean-toolchain"; done <<< "${checkouts}" | sort -u)"

mathlib_project=
mathlib_packages_dir=
while IFS=$'\t' read -r checkout packages_dir name url revision; do
    [ -n "${checkout}" ] || continue
    if [ "${name}" = mathlib ] && [ -z "${mathlib_project}" ] && [ -n "${linked[${packages_dir}$'\t'mathlib]:-}" ]; then
        mathlib_project="${checkout}"
        mathlib_packages_dir="${packages_dir}"
    fi
done <<< "${analysis}"

if [ -n "${mathlib_project}" ]; then
    mathlib_olean="${mathlib_packages_dir}/mathlib/.lake/build/lib/lean/Mathlib.olean"
    if [ ! -f "${mathlib_olean}" ]; then
        ( cd "${mathlib_project}" && lake exe cache get )
    fi
    ( cd "${mathlib_project}" && lake build Mathlib )
    if [ ! -f "${mathlib_olean}" ]; then
        printf 'error: %s is missing after the build\n' "${mathlib_olean}" >&2
        problems=1
    fi
fi

# Each project must resolve its own manifest, package by package, from the
# directory that project declares -- not merely import Mathlib.
while read -r checkout; do
    packages_dir="$(awk -F'\t' -v c="${checkout}" '$1 == c { print $2; exit }' <<< "${analysis}")"
    resolved=0
    while IFS=$'\t' read -r row_checkout row_dir row_name row_url row_revision; do
        [ "${row_checkout}" = "${checkout}" ] || continue
        target="${row_dir}/${row_name}"
        current=""
        [ -d "${target}" ] && current="$(git -C "${target}" rev-parse HEAD 2>/dev/null || true)"
        if [ "${current}" != "${row_revision}" ]; then
            printf 'error: %s resolves %s at %s, not the %s its manifest pins\n' \
                "${checkout##*/}" "${row_name}" "${current:-nothing}" "${row_revision}" >&2
            resolved=1
        fi
    done <<< "${analysis}"
    path="$( cd "${checkout}" && lake env printenv LEAN_PATH 2>/dev/null || true )"
    case ":${path}:" in
        *":${packages_dir}/"*) ;;
        *)
            printf 'error: %s does not resolve its packages from %s\n' "${checkout##*/}" "${packages_dir}" >&2
            resolved=1
            ;;
    esac
    [ "${resolved}" -eq 0 ] || problems=1
done <<< "${checkouts}"

exit "${problems}"
