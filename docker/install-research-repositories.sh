#!/usr/bin/env bash
# Check out every repository in research-repositories.txt under /repos. A
# repository that is a git source of uv.lock is checked out at its locked
# commit, and each package the lock takes from it is reinstalled as an editable
# package from the checkout, so the environment runs the code agents edit.
set -euo pipefail
sage_root="$(cd "$(dirname "$0")/.." && pwd)"
repositories_root=/repos
sage_python="${sage_root}/.venv/bin/python"

# url -> "commit subdirectory..." for every git source of the lock.
locked="$("${sage_python}" - "${sage_root}/uv.lock" <<'EOF'
import sys
import tomllib
from urllib.parse import parse_qs, urlsplit

sources = {}
for package in tomllib.load(open(sys.argv[1], "rb"))["package"]:
    git = package.get("source", {}).get("git")
    if git is None:
        continue
    location, commit = git.split("#")
    parts = urlsplit(location)
    url = f"{parts.scheme}://{parts.netloc}{parts.path}".removesuffix(".git")
    subdirectory = parse_qs(parts.query).get("subdirectory", ["."])[0]
    sources.setdefault(url, [commit, []])[1].append(subdirectory)
for url, (commit, subdirectories) in sources.items():
    print(url, commit, *subdirectories)
EOF
)"

mkdir -p "${repositories_root}"
editable=()
while read -r url; do
    case "${url}" in ''|'#'*) continue ;; esac
    name="${url##*/}"
    checkout="${repositories_root}/${name}"
    if [ -d "${checkout}/.git" ]; then
        git -C "${checkout}" fetch --quiet origin
    else
        git clone --quiet --filter=blob:none "${url}" "${checkout}"
    fi
    branch="$(git -C "${checkout}" symbolic-ref --short refs/remotes/origin/HEAD)"
    branch="${branch#origin/}"
    lock_entry="$(awk -v url="${url}" '$1 == url' <<<"${locked}")"
    if [ -n "${lock_entry}" ]; then
        read -r _ commit subdirectories <<<"${lock_entry}"
        git -C "${checkout}" checkout --quiet -B "${branch}" "${commit}"
        git -C "${checkout}" branch --quiet --set-upstream-to="origin/${branch}"
        for subdirectory in ${subdirectories}; do
            editable+=(-e "${checkout}/${subdirectory}")
        done
    else
        git -C "${checkout}" checkout --quiet -B "${branch}" "origin/${branch}"
    fi
done < "${sage_root}/docker/research-repositories.txt"

cd "${sage_root}"
uv pip install --python "${sage_python}" --no-deps "${editable[@]}"

just -f "${repositories_root}/sage-julia-bridge/justfile" julia-deps

# Lean: each checkout with a root lean-toolchain gets its toolchain from elan.
# Every Lake package a manifest pins is checked out once per revision under
# /opt/lake-packages and linked into the directory that project resolves: a
# manifest records it as packagesDir, and a project that sets one -- these set
# ../../.local/share/lean/<toolchain>/packages -- never reads .lake/packages.
# The packages are one copy under /opt because each project's link points there.
# Mathlib's oleans come from the official cache for the pinned revision, so the
# multi-hour Mathlib build is never run; the packages Mathlib imports have no
# such cache and are built once, here. The checkouts' own targets are the
# agents' work and are not built.
lake_packages=/opt/lake-packages
mkdir -p "${lake_packages}"
lean_project=
lean_packages_dir=
for checkout in "${repositories_root}"/*/; do
    checkout="${checkout%/}"
    [ -f "${checkout}/lean-toolchain" ] || continue
    elan toolchain install "$(cat "${checkout}/lean-toolchain")"
    [ -f "${checkout}/lake-manifest.json" ] || continue
    packages_dir="$("${sage_python}" - "${checkout}/lake-manifest.json" <<'PY'
import json
import sys

print(json.load(open(sys.argv[1])).get("packagesDir") or ".lake/packages")
PY
)"
    case "${packages_dir}" in
        /*) ;;
        *) packages_dir="${checkout}/${packages_dir}" ;;
    esac
    packages_dir="$(realpath -m "${packages_dir}")"
    mkdir -p "${packages_dir}"
    "${sage_python}" - "${checkout}/lake-manifest.json" <<'PY' |
import json
import sys

for package in json.load(open(sys.argv[1]))["packages"]:
    if package["type"] == "git":
        print(package["name"], package["url"], package["rev"])
PY
    while read -r name url revision; do
        shared="${lake_packages}/${name}@${revision}"
        if [ ! -d "${shared}" ]; then
            git clone --quiet --filter=blob:none "${url}" "${shared}"
            git -C "${shared}" checkout --quiet "${revision}"
        fi
        ln -sfn "${shared}" "${packages_dir}/${name}"
    done
    if [ -e "${packages_dir}/mathlib" ] && [ -z "${lean_project}" ]; then
        lean_project="${checkout}"
        lean_packages_dir="${packages_dir}"
    fi
done

# One project's Mathlib closure is every project's: the packages are shared by
# revision. The cache is retrieved before the build, so Mathlib itself is not
# compiled here, and the image fails if Mathlib does not end up loadable.
if [ -n "${lean_project}" ]; then
    ( cd "${lean_project}" && lake exe cache get && lake build Mathlib )
    test -f "${lean_packages_dir}/mathlib/.lake/build/lib/lean/Mathlib.olean"
fi
elan default "$(cat "${repositories_root}/lean-categories/lean-toolchain")"
