#!/usr/bin/env bash
# Provision the image's one shared Lean project, and bind every Lean checkout
# under the repository root to it.
#
# The image carries a single Lean project -- mathlib4 at the head of its master
# branch, on the toolchain that revision pins, with its whole dependency closure
# built inside it and Mathlib's oleans from the official cache. Every build moves
# to the head of that branch as it is when the build starts, incremental builds
# included: this script compares the head with the record the image already
# carries (MATHLIB_RECORD) and rebuilds the closure only when the head has moved.
# When it has not, nothing is written -- the files stay byte for byte what the
# base image carries, so the layer that holds them is reused rather than
# republished (sage#13).
#
# Every checkout under the repository root that carries a lake-manifest.json
# resolves mathlib and its closure from that project: provisioning links each
# package its manifest pins to the image's copy of it, in the packages directory
# its lakefile declares. A pin the image does not carry is a checkout that does
# not follow the image: it is reported here, naming the checkout and both
# revisions, and nothing in the checkout is rewritten. Holding the Lean
# repositories to the image is each repository's own CI (lean-categories#118,
# lean-cas-dsl#90), never this image's run.
#
# An image that was unpacked before this was introduced reaches the same state
# without being rebuilt; see docker/SAGE-ENVIRONMENT.md.
#
#   docker/provision-lean-packages.sh [REPOSITORIES_ROOT] [--dry-run]
#
# --dry-run prints what would be done and touches nothing.
#
# Environment: MATHLIB_REVISION (the head this build resolved; without it the head
# is read here), MATHLIB_PROJECT (default /opt/mathlib), MATHLIB_RECORD (default
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

# The head of the repository's branch, as one revision -- the only place the image
# decides which Mathlib it carries. No tag and no revision is written here. The
# branch is master, which is what mathlib4 develops on.
resolve_head() {
    local head
    head="$(git ls-remote "${repository}" refs/heads/master | awk 'NR == 1 { print $1 }')"
    if [ -z "${head}" ]; then
        head="$(git ls-remote "${repository}" HEAD | awk 'NR == 1 { print $1 }')"
    fi
    printf '%s\n' "${head}"
}

record_field() {
    "${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' \
        "${record}" "$1"
}

olean="${project}/.lake/build/lib/lean/Mathlib.olean"

# What this build carries. The workflow reads the head for the build and passes it,
# so a head that has not moved leaves this step's inputs unchanged and its result is
# reused; a moved head is a different input, and the closure is rebuilt. Without the
# value -- an unpacked image, a local run -- the head is read here.
image_revision="${MATHLIB_REVISION:-}"
if [ -z "${image_revision}" ]; then
    image_revision="$(resolve_head)"
fi
case "${image_revision}" in
    *[!0-9a-f]* | '' | ????????????????????????????????????????[0-9a-f]*)
        printf 'error: %s is not a revision; the image cannot choose a Mathlib\n' \
            "${image_revision:-<empty>}" >&2
        exit 1
        ;;
esac
if [ "${#image_revision}" -ne 40 ]; then
    printf 'error: %s is not a 40-character revision\n' "${image_revision}" >&2
    exit 1
fi

recorded_revision=""
if [ -f "${record}" ]; then
    recorded_revision="$(record_field revision)"
fi
recorded_toolchain=""
if [ -f "${record}" ] && [ -n "${recorded_revision}" ]; then
    recorded_toolchain="$(record_field toolchain)"
fi

project_head="$(git_head "${project}")"
if [ "${recorded_revision}" = "${image_revision}" ]; then
    # The build resolved the head the image already carries. Nothing is written, so
    # the files keep their content and the layer holding them is reused -- provided
    # the project really is that revision, with a built Mathlib. A record that
    # disagrees with the tree is a broken image, not a cache hit.
    if [ "${project_head}" != "${image_revision}" ]; then
        printf 'error: %s is at %s, not the %s its record names; the image does not carry one built project\n' \
            "${project}" "${project_head:-no revision}" "${image_revision}" >&2
        exit 1
    fi
    if [ ! -f "${olean}" ]; then
        printf 'error: %s names mathlib %s and carries no built Mathlib; remove %s to rebuild it\n' \
            "${record}" "${image_revision}" "${project}" >&2
        exit 1
    fi
    image_toolchain="${recorded_toolchain}"
    printf 'the image carries mathlib %s on %s, the head this build resolved: nothing to rebuild (%s)\n' \
        "${image_revision}" "${image_toolchain}" "$(record_field resolved)"
elif [ "${dry_run}" = 1 ]; then
    if [ -n "${recorded_revision}" ]; then
        printf 'a build would move the shared Lean project from %s to %s and rebuild its closure\n' \
            "${recorded_revision}" "${image_revision}"
    else
        printf 'a build would resolve %s at %s and build its closure\n' "${project}" "${image_revision}"
    fi
    exit 0
else
    if [ -n "${recorded_revision}" ]; then
        printf 'the head moved from %s to %s: rebuilding the shared project and its closure\n' \
            "${recorded_revision}" "${image_revision}"
        # A Lean release refuses another release's oleans, and so does every package
        # it imports: the build tree of the revision being left behind goes whole --
        # packages included -- and Lake fetches the new revision's closure and builds
        # it once. That is the closure layer being rebuilt, and the only time it is.
        rm -rf "${project}/.lake"
    else
        printf 'resolving mathlib at %s, the head of this build\n' "${image_revision}"
    fi
    mkdir -p "${project}"
    if [ ! -d "${project}/.git" ]; then
        git -C "${project}" init --quiet
    fi
    git -C "${project}" remote add origin "${repository}" 2>/dev/null \
        || git -C "${project}" remote set-url origin "${repository}"
    # One revision, not the history: Lake reads the lakefile and the manifest, and
    # the record is what a consumer reads for provenance. A server that will not
    # serve a revision by name still serves its head, which is what this build
    # resolved.
    git -C "${project}" fetch --quiet --depth 1 origin "${image_revision}" \
        || git -C "${project}" fetch --quiet origin "${image_revision}" \
        || git -C "${project}" fetch --quiet --depth 1 origin HEAD
    git -C "${project}" checkout --quiet --force "${image_revision}"
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
    # toolchain, and that built closure is what every checkout resolves. The
    # packages the manifest pins but Mathlib's own target never imports -- Cli,
    # on 4365edbea6's evidence -- are built too, each by name, so the closure is
    # complete: the environment check asserts a build directory for every
    # package the manifest pins (sage#13).
    ( cd "${project}" && lake exe cache get )
    closure="$("${python_bin}" - "${project}/lake-manifest.json" <<'PY'
import json, sys
print(" ".join(sorted(package["name"] for package in json.load(open(sys.argv[1]))["packages"] if package.get("type") == "git")))
PY
)"
    ( cd "${project}" && lake build Mathlib ${closure} )
    if [ ! -f "${olean}" ]; then
        printf 'error: %s is missing after the build; mathlib %s is not usable\n' \
            "${olean}" "${image_revision}" >&2
        exit 1
    fi
    "${python_bin}" - "${record}" "${project}" "${repository}" "${image_revision}" "${image_toolchain}" <<'PY'
import json
import sys
import time

record, project, repository, revision, toolchain = sys.argv[1:6]
# `master_head_at_resolution` is what the environment check reads back: it is the
# revision this build asked for, so a project at another revision is a defect and
# not a stale record.
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
    if os.path.isdir(directory) and head(directory) and not directory.endswith(".build"):
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
            # The checkout pins a revision the image does not carry. Nothing is
            # linked, and a link an earlier run left there is removed rather than
            # left to resolve the image's revision under this checkout's pin.
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
    if [ -d "${target}" ]; then
        # A revision an earlier row of this plan already cloned, or one the
        # shared store carried before the build, is reused: two checkouts can
        # pin one revision, and git clone refuses a destination that exists
        # and is not empty (sage#23).
        printf 'reused %s: the shared store already carries %s at %s\n' \
            "${target}" "${package_name}" "${revision}"
    else
        git clone --quiet --filter=blob:none "${url}" "${target}"
    fi
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

# A checkout that pins a revision the image does not carry is reported here and
# nowhere else: the image's own check validates the shared project, and holding a
# Lean repository to the image is that repository's CI.
lagging=0
while IFS=$'\t' read -r kind checkout package_name revision found; do
    [ "${kind}" = LAGS ] || continue
    lagging=$((lagging + 1))
    printf 'note: %s pins %s at %s and the image carries %s: the checkout does not follow the image\n' \
        "${checkout}" "${package_name}" "${revision}" "${found}"
done <<< "${plan}"

while IFS=$'\t' read -r kind checkout toolchain; do
    [ "${kind}" = CHECKOUT ] || continue
    if [ "${toolchain}" != "${image_toolchain}" ]; then
        lagging=$((lagging + 1))
        printf 'note: %s pins toolchain %s and the image has %s: the checkout does not follow the image\n' \
            "${checkout}" "${toolchain}" "${image_toolchain}"
    fi
done <<< "${plan}"

while IFS=$'\t' read -r kind message; do
    [ "${kind}" = NOTE ] || continue
    printf 'note: %s\n' "${message}"
done <<< "${plan}"

printf 'the shared project at %s (mathlib %s) serves %s link(s); %s checkout pin(s) do not follow it\n' \
    "${project}" "${image_revision}" "${links}" "${lagging}"
exit "${problems}"
