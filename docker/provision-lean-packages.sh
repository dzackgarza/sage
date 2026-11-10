#!/usr/bin/env bash
# Provision the image's one shared Lean project, and bind every Lean checkout
# under the repository root to it.
#
# The image carries a single Lean project -- mathlib4 at the head of its master
# branch, on the toolchain that revision pins, with its whole dependency closure
# built inside it and Mathlib's oleans from the official cache. A build that has
# no project yet resolves the head at build time and records the revision and
# toolchain it resolved; a build that inherits one -- an incremental image, which
# is `FROM` the image it extends -- keeps it, so the image's Lean content is one
# project rather than one per checkout and one per Mathlib revision (sage#13).
#
# Every checkout under the repository root that carries a lake-manifest.json then
# resolves mathlib and its closure from that project: provisioning links each
# package its manifest pins to the image's copy of it, in the packages directory
# its lakefile declares. A pin the image does not carry is reported as a
# disagreement, naming the checkout and both revisions -- nothing is rewritten in
# the checkout, and its manifest stays what its repository published. The
# environment check turns those reports into a failure (docker/
# research-environment-check.py).
#
# An image that was unpacked before this was introduced reaches the same state
# without being rebuilt; see docker/SAGE-ENVIRONMENT.md.
#
#   docker/provision-lean-packages.sh [REPOSITORIES_ROOT] [--dry-run]
#
# --dry-run prints the plan and touches nothing. Without an existing project it
# cannot plan: a build resolves the head first.
#
# Environment: MATHLIB_PROJECT (default /opt/mathlib), MATHLIB_RECORD (default
# /opt/lean-image.json), LAKE_PACKAGES (default /opt/lake-packages) for packages
# neither the project nor a checkout provides, MATHLIB_REPOSITORY (default
# https://github.com/leanprover-community/mathlib4), PYTHON (default python3).
set -euo pipefail

repositories_root="${1:-${REPOSITORIES_ROOT:-/repos}}"
case "${2:-}" in
    --dry-run) dry_run=1 ;;
    '') dry_run=0 ;;
    *) printf 'usage: %s [REPOSITORIES_ROOT] [--dry-run]\n' "$0" >&2; exit 2 ;;
esac
project="${MATHLIB_PROJECT:-/opt/mathlib}"
record="${MATHLIB_RECORD:-/opt/lean-image.json}"
lake_packages="${LAKE_PACKAGES:-/opt/lake-packages}"
repository="${MATHLIB_REPOSITORY:-https://github.com/leanprover-community/mathlib4}"
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

# A directory that is not a repository, or has no commit yet, is "no revision".
git_head() { git -C "$1" rev-parse --verify --quiet HEAD 2>/dev/null || true; }

# The head of the repository's branch, as one revision. This is the only place the
# image decides which Mathlib it carries, and it decides it per build: no tag and no
# revision is written here. The branch is master, which is what mathlib4 develops on.
resolve_head() {
    git ls-remote "${repository}" refs/heads/master \
        | awk 'NR == 1 { print $1 }' \
        || git ls-remote "${repository}" HEAD | awk 'NR == 1 { print $1 }'
}

if [ -f "${record}" ] && [ -d "${project}" ]; then
    image_revision="$("${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${record}")"
    image_toolchain="$("${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1]))["toolchain"])' "${record}")"
    head="$(git_head "${project}")"
    olean="${project}/.lake/build/lib/lean/Mathlib.olean"
    if [ "${head}" != "${image_revision}" ] || [ ! -f "${olean}" ]; then
        printf 'error: %s is at %s and %s, but %s records %s; the image does not carry one built project\n' \
            "${project}" "${head:-no revision}" \
            "$([ -f "${olean}" ] && echo has Mathlib.olean || echo has no Mathlib.olean)" \
            "${record}" "${image_revision}" >&2
        exit 1
    fi
    printf 'the image carries mathlib %s on %s, recorded by the build that resolved it (%s)\n' \
        "${image_revision}" "${image_toolchain}" "$("${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("resolved","no date"))' "${record}")"
elif [ "${dry_run}" = 1 ]; then
    printf 'no shared Lean project at %s; a build resolves %s at build time\n' "${project}" "${repository}"
    exit 0
else
    image_revision="$(resolve_head)"
    if [ -z "${image_revision}" ]; then
        printf 'error: %s reports no head; the image cannot choose a Mathlib\n' "${repository}" >&2
        exit 1
    fi
    printf 'resolving %s at %s, the head of its default branch\n' "${repository}" "${image_revision}"
    current="$(git_head "${project}" 2>/dev/null || true)"
    if [ -n "${current}" ] && [ "${current}" != "${image_revision}" ]; then
        printf 'error: %s already holds %s, not the %s this build resolves; remove it to move the project\n' \
            "${project}" "${current}" "${image_revision}" >&2
        exit 1
    fi
    if [ "${current}" != "${image_revision}" ]; then
        mkdir -p "${project}"
        git -C "${project}" init --quiet
        git -C "${project}" remote add origin "${repository}" 2>/dev/null \
            || git -C "${project}" remote set-url origin "${repository}"
        # One revision, not the history: Lake reads the lakefile and the manifest,
        # and the record is what a consumer reads for provenance. A server that will
        # not serve a revision by name still serves its head, which is what the
        # resolution asked for.
        git -C "${project}" fetch --quiet --depth 1 origin "${image_revision}" \
            || git -C "${project}" fetch --quiet origin "${image_revision}" \
            || git -C "${project}" fetch --quiet --depth 1 origin HEAD
        git -C "${project}" checkout --quiet "${image_revision}"
    fi
    if [ "$(git_head "${project}")" != "${image_revision}" ]; then
        printf 'error: %s is at %s after the checkout, not %s\n' \
            "${project}" "$(git_head "${project}")" "${image_revision}" >&2
        exit 1
    fi
    # The toolchain is not chosen here either: it is the one that revision pins.
    image_toolchain="$(cat "${project}/lean-toolchain")"
    elan toolchain install "${image_toolchain}"
    elan default "${image_toolchain}"
    # Mathlib itself comes from the official cache for this exact revision, so it
    # is never compiled; the packages it imports are built once, here, by this
    # toolchain, and that built closure is what every checkout resolves.
    ( cd "${project}" && lake exe cache get )
    ( cd "${project}" && lake build Mathlib )
    olean="${project}/.lake/build/lib/lean/Mathlib.olean"
    if [ ! -f "${olean}" ]; then
        printf 'error: %s is missing after the build; mathlib %s is not usable\n' "${olean}" "${image_revision}" >&2
        exit 1
    fi
    "${python_bin}" - "${record}" "${project}" "${repository}" "${image_revision}" "${image_toolchain}" <<'PY'
import json
import sys
import time

record, project, repository, revision, toolchain = sys.argv[1:6]
# `master_head_at_resolution` is read back by the environment check: it is the
# revision the build asked for, so a checkout that is not at it proves the
# project moved rather than that the record is stale.
with open(record, "w") as handle:
    json.dump(
        {
            "project": project,
            "repository": repository,
            "revision": revision,
            "master_head_at_resolution": revision,
            "toolchain": toolchain,
            "cache": "lake exe cache get (official Mathlib cache)",
            "resolved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        handle,
        indent=2,
        sort_keys=True,
    )
    handle.write("\n")
PY
    printf 'recorded mathlib %s on %s in %s\n' "${image_revision}" "${image_toolchain}" "${record}"
fi

# One plan, computed once: every Lean checkout, what each of its pins resolves to
# in this image, and the link that puts it in the directory its lakefile declares.
plan="$("${python_bin}" - "${repositories_root}" "${project}" "${lake_packages}" <<'PY'
import json
import os
import subprocess
import sys

root, project, lake_packages = sys.argv[1:4]
project = os.path.realpath(project)


def head(path):
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


carried = {"mathlib": project}
closure_directory = os.path.join(project, ".lake", "packages")
# A project whose closure has not been resolved yet carries Mathlib alone; a real
# one has every package its own manifest pins.
for name in sorted(os.listdir(closure_directory)) if os.path.isdir(closure_directory) else []:
    directory = os.path.join(closure_directory, name)
    if os.path.isdir(directory):
        carried[name] = directory

checkouts = 0
for name in sorted(os.listdir(root)):
    directory = os.path.join(root, name)
    manifest = os.path.join(directory, "lake-manifest.json")
    toolchain = os.path.join(directory, "lean-toolchain")
    if not os.path.isfile(manifest) or not os.path.isfile(toolchain):
        continue
    checkouts += 1
    with open(toolchain) as handle:
        pinned_toolchain = handle.read().strip()
    with open(manifest) as handle:
        data = json.load(handle)
    packages_dir = data.get("packagesDir") or ".lake/packages"
    if not os.path.isabs(packages_dir):
        packages_dir = os.path.join(directory, packages_dir)
    packages_dir = os.path.realpath(packages_dir)
    print("CHECKOUT", directory, pinned_toolchain, sep="\t")
    for package in sorted(data["packages"], key=lambda item: item["name"]):
        if package.get("type") != "git":
            continue
        package_name, revision = package["name"], package["rev"]
        target = carried.get(package_name)
        if target is None:
            # A package neither Mathlib's closure nor a checkout of this image
            # provides: one clone per revision, shared by every checkout that
            # pins it, and nothing built here.
            target = os.path.join(lake_packages, f"{package_name}@{revision}")
            if not os.path.isdir(target):
                print("FETCH", directory, package_name, revision, package["url"], sep="\t")
                print("LINK", os.path.join(packages_dir, package_name), target, sep="\t")
                continue
        found = head(target)
        if found == revision:
            print("FOLLOWS", directory, package_name, revision, sep="\t")
            print("LINK", os.path.join(packages_dir, package_name), target, sep="\t")
        else:
            # Disagreement: the image carries this package at another revision, so
            # nothing is linked and the checkout keeps its own manifest. A link an
            # earlier run left at that path would resolve the image's revision under
            # this checkout's pin, so it is removed rather than left to be read.
            print("LAGS", directory, package_name, revision, found or target, sep="\t")
            print("REMOVE", os.path.join(packages_dir, package_name), sep="\t")
if not checkouts:
    print("NOTE", f"no Lean checkout under {root}", sep="\t")
PY
)"

if [ "${dry_run}" = 1 ]; then
    printf '%s\n' "${plan}"
    exit 0
fi

problems=0
links=0
while IFS=$'\t' read -r kind checkout package_name revision url; do
    [ "${kind}" = FETCH ] || continue
    target="${lake_packages}/${package_name}@${revision}"
    mkdir -p "${lake_packages}"
    git clone --quiet --filter=blob:none "${url}" "${target}"
    git -C "${target}" checkout --quiet "${revision}"
    if [ "$(git_head "${target}")" != "${revision}" ]; then
        printf 'error: %s is at %s after the clone, not the %s %s pins\n' \
            "${target}" "$(git_head "${target}")" "${revision}" "${checkout##*/}" >&2
        problems=1
    fi
done <<< "${plan}"

while IFS=$'\t' read -r kind path target; do
    [ "${kind}" = LINK ] || continue
    if [ ! -d "${target}" ]; then
        printf 'error: %s is not present, so %s is left unlinked\n' "${target}" "${path}" >&2
        problems=1
        continue
    fi
    if [ -d "${path}" ] && [ ! -L "${path}" ]; then
        # A copy an earlier image left there, with its build tree. It is kept
        # rather than replaced: deleting a build tree to make room for a link
        # would hide whichever revision it holds.
        printf 'note: %s is a copy, not a link to %s; it stays as it is\n' "${path}" "${target}"
        continue
    fi
    mkdir -p "$(dirname "${path}")"
    ln -sfn "${target}" "${path}"
    links=$((links + 1))
done <<< "${plan}"

while IFS=$'\t' read -r kind path; do
    [ "${kind}" = REMOVE ] || continue
    if [ -L "${path}" ]; then
        rm -f "${path}"
        printf 'removed the link %s: it does not hold what the checkout pins\n' "${path}"
    fi
done <<< "${plan}"

while IFS=$'\t' read -r kind checkout package_name revision found; do
    [ "${kind}" = LAGS ] || continue
    printf 'error: %s pins %s at %s and the image carries %s: the checkout does not follow the image\n' \
        "${checkout}" "${package_name}" "${revision}" "${found}" >&2
done <<< "${plan}"

while IFS=$'\t' read -r kind checkout toolchain; do
    [ "${kind}" = CHECKOUT ] || continue
    if [ "${toolchain}" != "${image_toolchain}" ]; then
        printf 'error: %s pins toolchain %s and the image has %s: the checkout does not follow the image\n' \
            "${checkout}" "${toolchain}" "${image_toolchain}" >&2
    fi
done <<< "${plan}"

printf 'the shared project at %s serves %s link(s); %s disagreement(s) reported\n' \
    "${project}" "${links}" "$(grep -c $'^LAGS\t' <<< "${plan}" || true)"
exit "${problems}"
