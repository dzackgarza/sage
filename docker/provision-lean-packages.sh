#!/usr/bin/env bash
# Provision the Lean packages every checkout under a repository root resolves.
#
# The image build runs this after checking the research repositories out; an
# image that was unpacked earlier runs the same script, with the checkouts
# already in place, and reaches the same state without being rebuilt.
#
# Lake fixes a project's packages directory in its lakefile and records it in
# the manifest: "-K packagesDir=" is ignored, and a lakefile whose packagesDir
# disagrees with its manifest is rejected as out of date. Two checkouts that pin
# one package at different revisions therefore cannot both be served by that one
# directory, so each checkout gets its own view -- a directory of links to the
# content-addressed checkouts under /opt/lake-packages, exactly the packages its
# manifest pins -- and the launcher binds that view over the packages directory
# for a single invocation (`docker/sage-image.py run --lean-view CHECKOUT`).
# The shared directory keeps only the packages every checkout agrees on, so
# nothing silently resolves another project's revision.
#
# Mathlib's oleans come from the official cache for the pinned revision, so
# Mathlib itself is never compiled; the packages Mathlib imports are built once.
#
#   docker/provision-lean-packages.sh [REPOSITORIES_ROOT]   (default /repos)
#
# Environment: LAKE_PACKAGES (default /opt/lake-packages), LAKE_VIEWS (default
# /opt/lake-views), PYTHON (default python3).
set -euo pipefail

repositories_root="${1:-${REPOSITORIES_ROOT:-/repos}}"
lake_packages="${LAKE_PACKAGES:-/opt/lake-packages}"
lake_views="${LAKE_VIEWS:-/opt/lake-views}"
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

# One plan, computed once: the checkouts, the checkouts' toolchains, the
# content-addressed packages, each checkout's view, and the packages the shared
# directory can carry.
plan="$("${python_bin}" - "${repositories_root}" "${lake_packages}" "${lake_views}" <<'PY'
import hashlib
import json
import os
import sys

root, lake_packages, lake_views = sys.argv[1:4]
checkouts, packages, views, shared = [], {}, [], {}
for name in sorted(os.listdir(root)):
    directory = os.path.join(root, name)
    manifest = os.path.join(directory, "lake-manifest.json")
    toolchain = os.path.join(directory, "lean-toolchain")
    if not os.path.isfile(toolchain) or not os.path.isfile(manifest):
        continue
    with open(toolchain) as handle:
        pinned_toolchain = handle.read().strip()
    with open(manifest) as handle:
        data = json.load(handle)
    packages_dir = data.get("packagesDir") or ".lake/packages"
    if not os.path.isabs(packages_dir):
        packages_dir = os.path.join(directory, packages_dir)
    packages_dir = os.path.realpath(packages_dir)
    pins = sorted(
        (package["name"], package["url"], package["rev"])
        for package in data["packages"]
        if package["type"] == "git"
    )
    checkouts.append((directory, pinned_toolchain, packages_dir))
    digest = hashlib.sha256(
        "\n".join(f"{packages_dir}\t{n}\t{r}" for n, _, r in pins).encode()
    ).hexdigest()[:12]
    view = os.path.join(lake_views, f"{name}@{digest}")
    views.append((directory, packages_dir, view, pins))
    for package_name, url, revision in pins:
        packages[(package_name, revision)] = url
        shared.setdefault((packages_dir, package_name), set()).add(revision)

for directory, pinned_toolchain, _ in checkouts:
    print("CHECKOUT", directory, pinned_toolchain, sep="\t")
for (package_name, revision), url in sorted(packages.items()):
    print("PACKAGE", package_name, revision, url, sep="\t")
for directory, packages_dir, view, pins in views:
    for package_name, _, revision in pins:
        print("PIN", directory, packages_dir, package_name, revision, sep="\t")
for (packages_dir, package_name), revisions in sorted(shared.items()):
    if len(revisions) == 1:
        print("SHARED", packages_dir, package_name, next(iter(revisions)), sep="\t")
    else:
        print("CONFLICT", packages_dir, package_name, " ".join(sorted(revisions)), sep="\t")
PY
)"

problems=0

# Content-addressed checkouts, shared by every view.
while IFS=$'\t' read -r kind name revision url; do
    [ "${kind}" = PACKAGE ] || continue
    shared_checkout="${lake_packages}/${name}@${revision}"
    if [ ! -d "${shared_checkout}" ]; then
        git clone --quiet --filter=blob:none "${url}" "${shared_checkout}"
        git -C "${shared_checkout}" checkout --quiet "${revision}"
    fi
done <<< "${plan}"

# What each checkout must have overridden, and the index the launcher reads:
# a package whose revision the shared directory does not hold for this checkout
# is mounted from its content-addressed checkout for that invocation only.
mkdir -p "${lake_views}"
overrides="$("${python_bin}" - "${plan}" "${lake_views}/index.json" <<'PY'
import json
import os
import sys

rows = [line.split("\t") for line in sys.argv[1].splitlines() if line]
shared = {}
for row in rows:
    if row[0] == "SHARED":
        _, packages_dir, name, revision = row
        shared[(packages_dir, name)] = revision
index = {}
for row in rows:
    if row[0] != "PIN":
        continue
    _, checkout, packages_dir, name, revision = row
    entry = index.setdefault(checkout, {"packages_dir": packages_dir, "packages": {}, "overrides": []})
    entry["packages"][name] = revision
for checkout, entry in index.items():
    for name, revision in sorted(entry["packages"].items()):
        if shared.get((entry["packages_dir"], name)) != revision:
            entry["overrides"].append(
                {
                    "name": name,
                    "revision": revision,
                    "checkout": f"/opt/lake-packages/{name}@{revision}",
                }
            )
    del entry["packages"]
json.dump(index, open(sys.argv[2], "w"), indent=2, sort_keys=True)
open(sys.argv[2], "a").write("\n")
for checkout, entry in sorted(index.items()):
    for override in entry["overrides"]:
        print("OVERRIDE", checkout, override["name"], override["revision"], sep="\t")
PY
)"

# The shared directory carries only the packages every checkout agrees on, and
# carries them as links to the content-addressed checkout: an image unpacked
# earlier holds a copy of its own there, whose build tree moves into that
# checkout so every view sees one built Mathlib rather than a second copy.
while IFS=$'\t' read -r kind packages_dir name revision; do
    [ "${kind}" = SHARED ] || continue
    mkdir -p "${packages_dir}"
    target="${packages_dir}/${name}"
    shared_checkout="${lake_packages}/${name}@${revision}"
    if [ -d "${target}" ] && [ ! -L "${target}" ]; then
        # An image unpacked earlier carries its own copy, with the cache
        # unpacked into it: keep that copy where it is.
        current="$(git -C "${target}" rev-parse HEAD 2>/dev/null || true)"
        if [ "${current}" != "${revision}" ]; then
            printf 'error: %s is at %s, not the %s the checkouts share\n' \
                "${target}" "${current:-no revision}" "${revision}" >&2
            problems=1
        fi
    else
        ln -sfn "${shared_checkout}" "${target}"
    fi
done <<< "${plan}"

# The toolchain each checkout pins.
while IFS=$'\t' read -r kind checkout toolchain; do
    [ "${kind}" = CHECKOUT ] || continue
    elan toolchain install "${toolchain}"
done <<< "${plan}"

# One Mathlib for every view: the official cache for the pinned revision first,
# so Mathlib itself is not compiled here, then the packages it imports.
mathlib_checkout="$(awk -F'\t' '$1 == "PIN" && $4 == "mathlib" { print $2; exit }' <<< "${plan}")"
if [ -n "${mathlib_checkout}" ]; then
    mathlib_dir="$(awk -F'\t' -v c="${mathlib_checkout}" '$1 == "PIN" && $2 == c && $4 == "mathlib" { print $3; exit }' <<< "${plan}")"
    mathlib_olean="${mathlib_dir}/mathlib/.lake/build/lib/lean/Mathlib.olean"
    if [ ! -f "${mathlib_olean}" ]; then
        ( cd "${mathlib_checkout}" && lake exe cache get )
        ( cd "${mathlib_checkout}" && lake build Mathlib )
    fi
    if [ ! -f "${mathlib_olean}" ]; then
        printf 'error: %s is missing after the build\n' "${mathlib_olean}" >&2
        problems=1
    fi
fi

# Every checkout must either be fully carried by the shared directory or have
# an override for each package it pins differently; a checkout with no override
# must still resolve from the directory its lakefile declares.
while IFS=$'\t' read -r kind checkout toolchain; do
    [ "${kind}" = CHECKOUT ] || continue
    packages_dir="$(awk -F'\t' -v c="${checkout}" '$1 == "PIN" && $2 == c { print $3; exit }' <<< "${plan}")"
    missing=""
    while IFS=$'\t' read -r row_name row_revision; do
        current="$(git -C "${packages_dir}/${row_name}" rev-parse HEAD 2>/dev/null || true)"
        [ "${current}" = "${row_revision}" ] && continue
        if ! grep -qx "OVERRIDE"$'\t'"${checkout}"$'\t'"${row_name}"$'\t'"${row_revision}" <<< "${overrides}"; then
            printf 'error: %s needs %s at %s and has no override for it\n' \
                "${checkout##*/}" "${row_name}" "${row_revision}" >&2
            problems=1
        fi
        missing="${missing:+$missing }${row_name}"
    done < <(awk -F'\t' -v c="${checkout}" '$1 == "PIN" && $2 == c { print $4"\t"$5 }' <<< "${plan}")
    if [ -z "${missing}" ]; then
        # Lake reads the packages directory the lakefile declares; the entries
        # it puts on LEAN_PATH are those packages resolved to their checkouts,
        # so the revision check above is what proves the manifest is honoured.
        path="$( cd "${checkout}" && lake env printenv LEAN_PATH 2>/dev/null || true )"
        if [ -z "${path}" ]; then
            printf 'error: %s does not load its Lake environment\n' "${checkout##*/}" >&2
            problems=1
        fi
    else
        printf 'note: %s mounts %s for its own manifest; run it with --lean-view %s\n' \
            "${checkout##*/}" "${missing}" "${checkout}"
    fi
done <<< "${plan}"

while IFS=$'\t' read -r kind packages_dir name revisions; do
    [ "${kind}" = CONFLICT ] || continue
    printf 'note: %s is pinned at more than one revision (%s); each checkout mounts its own\n' \
        "${name}" "${revisions}"
done <<< "${plan}"

exit "${problems}"
