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

# Lean: each checkout with a root lean-toolchain gets its toolchain from elan.
# Every Lake package a manifest pins is checked out once per revision under
# /opt/lake-packages and linked into the checkout's .lake/packages, so the
# checkouts share one Mathlib, whose prebuilt cache is unpacked into it once.
# Each checkout is built, so the environment needs no Lean compilation at first
# use.
lake_packages=/opt/lake-packages
mkdir -p "${lake_packages}"
for checkout in "${repositories_root}"/*/; do
    checkout="${checkout%/}"
    [ -f "${checkout}/lean-toolchain" ] || continue
    elan toolchain install "$(cat "${checkout}/lean-toolchain")"
    [ -f "${checkout}/lake-manifest.json" ] || continue
    mkdir -p "${checkout}/.lake/packages"
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
        ln -sfn "${shared}" "${checkout}/.lake/packages/${name}"
    done
    if [ -L "${checkout}/.lake/packages/mathlib" ]; then
        (cd "${checkout}" && lake exe cache get)
    fi
    (cd "${checkout}" && lake build)
done
