#!/usr/bin/env bash
set -euo pipefail

repositories_root="${1:-${REPOSITORIES_ROOT:-/repos}}"
case "${2:-}" in
    --dry-run) dry_run=1 ;;
    '') dry_run=0 ;;
    *) printf 'usage: %s [REPOSITORIES_ROOT] [--dry-run]\n' "$0" >&2; exit 2 ;;
esac
project="${MATHLIB_PROJECT:-/opt/mathlib}"
record="${MATHLIB_RECORD:-/opt/lean-image.json}"
repository="${MATHLIB_REPOSITORY:-https://github.com/leanprover-community/mathlib4}"
python_bin="${PYTHON:-python3}"

if ! command -v elan > /dev/null 2>&1 && [ -x /opt/elan/bin/elan ]; then
    PATH="/opt/elan/bin:${PATH}"
    export PATH
fi
if [ -z "${ELAN_HOME:-}" ] && [ -d /opt/elan ]; then
    ELAN_HOME=/opt/elan
    export ELAN_HOME
fi

git_head() { git -C "$1" rev-parse --verify --quiet HEAD 2>/dev/null || true; }

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
    git -C "${project}" fetch --quiet --depth 1 origin "${image_revision}" \
        || git -C "${project}" fetch --quiet origin "${image_revision}" \
        || git -C "${project}" fetch --quiet --depth 1 origin HEAD
    git -C "${project}" checkout --quiet --force "${image_revision}"
    if [ "$(git_head "${project}")" != "${image_revision}" ]; then
        printf 'error: %s is at %s after the checkout, not %s\n' \
            "${project}" "$(git_head "${project}")" "${image_revision}" >&2
        exit 1
    fi
    image_toolchain="$(cat "${project}/lean-toolchain")"
    elan toolchain install "${image_toolchain}"
    elan default "${image_toolchain}"
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

plan="$("${python_bin}" - "${repositories_root}" "${project}" <<'PY'
import os
import sys

root, project = sys.argv[1:3]

for name in sorted(os.listdir(root)):
    directory = os.path.join(root, name)
    if not os.path.isdir(directory) or name.startswith("."):
        continue
    if not (os.path.isfile(os.path.join(directory, "lake-manifest.json"))):
        continue
    print("RESOLVE", directory, sep="\t")
if not any(
    os.path.isfile(os.path.join(root, name, "lake-manifest.json"))
    for name in os.listdir(root)
):
    print("NOTE", f"no Lean checkout under {root}", sep="\t")
PY
)"

if [ "${dry_run}" = 1 ]; then
    printf '%s\n' "${plan}"
    exit 0
fi

problems=0
while IFS=$'\t' read -r kind checkout; do
    [ "${kind}" = RESOLVE ] || continue
    printf 'resolving %s at the revisions of the shared project\n' "${checkout}"
    "${python_bin}" - "${checkout}" "${project}" "${record}" <<'PY' || problems=1
import json
import os
import sys

checkout, project, record = sys.argv[1:4]
project = os.path.realpath(project)

image = json.load(open(record))
image_revision = image["revision"]

shared_manifest = json.load(open(os.path.join(project, "lake-manifest.json")))
shared = {
    package["name"]: package["rev"]
    for package in shared_manifest["packages"]
    if package.get("type") == "git"
}

manifest_path = os.path.join(checkout, "lake-manifest.json")
manifest = json.load(open(manifest_path))
packages_dir = manifest.get("packagesDir") or ".lake/packages"
if not os.path.isabs(packages_dir):
    packages_dir = os.path.join(checkout, packages_dir)

resolved = 0
for package in manifest["packages"]:
    if package.get("type") != "git":
        continue
    name = package["name"]
    if name == "mathlib":
        package["rev"] = image_revision
    elif name in shared:
        package["rev"] = shared[name]
    else:
        continue
    resolved += 1

with open(manifest_path, "w") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")

with open(os.path.join(project, "lean-toolchain"), encoding="utf-8") as handle:
    toolchain = handle.read()
with open(os.path.join(checkout, "lean-toolchain"), "w", encoding="utf-8") as handle:
    handle.write(toolchain)

os.makedirs(packages_dir, exist_ok=True)
for package in manifest["packages"]:
    if package.get("type") != "git":
        continue
    name = package["name"]
    if name == "mathlib":
        target = project
    elif name in shared:
        target = os.path.join(project, ".lake", "packages", name)
    else:
        continue
    link = os.path.join(packages_dir, name)
    if os.path.islink(link):
        os.unlink(link)
    elif os.path.isdir(link):
        import shutil
        shutil.rmtree(link)
    os.symlink(target, link)

print(f"{checkout}: {resolved} entries resolved at the shared project's revisions, on {toolchain.strip()}")
PY
done <<< "${plan}"

while IFS=$'\t' read -r kind message; do
    [ "${kind}" = NOTE ] || continue
    printf 'note: %s\n' "${message}"
done <<< "${plan}"

resolved_count="$(grep -c '^RESOLVE' <<<"${plan}" || true)"
printf 'the shared project at %s (mathlib %s): %s checkout(s) resolved at its revisions\n' \
    "${project}" "${image_revision}" "${resolved_count}"
exit "${problems}"
