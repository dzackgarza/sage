#!/usr/bin/env bash
# Check out every repository in research-repositories.txt under /repos. A
# repository that is a git source of uv.lock is checked out at its locked
# commit, and each package the lock takes from it is reinstalled as an editable
# package from the checkout, so the environment runs the code agents edit.
set -euo pipefail
sage_root="$(cd "$(dirname "$0")/.." && pwd)"
repositories_root=/repos
sage_python="${sage_root}/.venv/bin/python"
# The GAP that libgap drives is the one the image builds from the pinned source
# into $SAGE_LOCAL, and it stays a declared path rather than whatever PATH
# resolves when this script runs outside the sync recipe.
sage_gap="${sage_root}/.venv/bin/gap"

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

# They must be editable installs, not wheels from those URLs: that property is what
# the environment check asserts an hour later, and a name missing here says which
# package to look at.
expected="$("${sage_python}" - "${editable[@]}" <<'EOF'
import sys
import tomllib

names = []
for argument in sys.argv[1:]:
    if argument == "-e":
        continue
    with open(f"{argument}/pyproject.toml", "rb") as handle:
        names.append(tomllib.load(handle)["project"]["name"])
print("\n".join(sorted(names)))
EOF
)"
installed="$(uv pip list --python "${sage_python}" --editable 2>/dev/null | awk 'NR>2 {print $1}' | sort -u)"
missing="$(comm -23 <(printf '%s\n' "${expected}") <(printf '%s\n' "${installed}"))"
if [ -n "${missing}" ]; then
    printf 'FATAL: these were to be installed from their checkouts and are not editable: %s\n' \
        "$(printf '%s' "${missing}" | tr '\n' ' ')" >&2
    exit 1
fi
echo "editable from their checkouts: $(printf '%s' "${expected}" | tr '\n' ' ')"

just -f "${repositories_root}/sage-julia-bridge/justfile" julia-deps

# GAP packages are a per-checkout allocation, not an image-wide one: sage-categories
# resolves the exact releases listed in its own .gap-packages.g with GAP's
# PackageManager, and every consumer of its finite-category engine loads them from
# the checkout (its justfile runs the same command with --packagedirs). GAP scans
# the directories --packagedirs names when it starts, so a fresh checkout needs the
# directory to exist before the step runs.
categories_root="${repositories_root}/sage-categories"
mkdir -p "${categories_root}/.gap/pkg"
(cd "${categories_root}" && "${sage_gap}" -q -r \
    --packagedirs "${categories_root}/.gap/pkg" "${categories_root}/.gap-packages.g")

# Lean: the toolchain each checkout pins and the packages its manifest
# resolves. The same script provisions an image that was unpacked earlier,
# without a rebuild: docker/provision-lean-packages.sh.
PYTHON="${sage_python}" "${sage_root}/docker/provision-lean-packages.sh" "${repositories_root}"
elan default "$(cat "${repositories_root}/lean-categories/lean-toolchain")"
