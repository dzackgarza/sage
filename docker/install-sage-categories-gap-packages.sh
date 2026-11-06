#!/usr/bin/env bash
# Check out sage-categories at its locked commit and install the GAP releases it
# pins, into that checkout's own .gap/pkg.
#
# This is the one research checkout the runtime image carries. The finite-category
# engine loads homalg/CAP from the checkout rather than from the image's GAP
# (sage#10), so a Sage consumer that builds a presented module needs this
# allocation present; the other 23 checkouts are a development concern and live
# only in the full image, installed by docker/install-research-repositories.sh.
#
#   docker/install-sage-categories-gap-packages.sh /repos
set -euo pipefail
sage_root="$(cd "$(dirname "$0")/.." && pwd)"
repositories_root="${1:-/repos}"
sage_python="${sage_root}/.venv/bin/python"
sage_gap="${sage_root}/.venv/bin/gap"

# The locked commit, from the same lock the environment is built from: there is no
# second place a revision could come from.
commit="$("${sage_python}" - "${sage_root}/uv.lock" <<'EOF'
import sys
import tomllib

for package in tomllib.load(open(sys.argv[1], "rb"))["package"]:
    git = package.get("source", {}).get("git")
    if package["name"] == "sage-categories" and git:
        print(git.split("#")[1])
        break
EOF
)"
if [ -z "${commit}" ]; then
    echo "FATAL: uv.lock pins no sage-categories commit" >&2
    exit 1
fi

categories_root="${repositories_root}/sage-categories"
if [ -d "${categories_root}/.git" ]; then
    git -C "${categories_root}" fetch --quiet origin
else
    mkdir -p "${repositories_root}"
    git clone --quiet --filter=blob:none https://github.com/dzackgarza/sage-categories "${categories_root}"
fi
branch="$(git -C "${categories_root}" symbolic-ref --short refs/remotes/origin/HEAD)"
branch="${branch#origin/}"
git -C "${categories_root}" checkout --quiet -B "${branch}" "${commit}"
echo "sage-categories at ${commit}"

# GAP scans the directories --packagedirs names when it starts, so the directory
# has to exist before the step runs: a missing one aborts the whole scan and the
# step then exits 0 having done nothing (measured, GAP 4.16.1).
mkdir -p "${categories_root}/.gap/pkg"
(cd "${categories_root}" && "${sage_gap}" -q -r \
    --packagedirs "${categories_root}/.gap/pkg" "${categories_root}/.gap-packages.g")

# The step reports failures on GAP's error stream and exits 0 regardless, so the
# allocation is counted rather than trusted: one directory per pinned release.
pinned="$("${sage_python}" - "${categories_root}/.gap-packages.g" <<'EOF'
import ast
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
declared = re.search(r"^packages := \[(.*?)^\];", text, re.DOTALL | re.MULTILINE)
assert declared is not None, "no `packages := [ ... ];` in .gap-packages.g"
print(len(ast.literal_eval(f"[{declared.group(1)}]")))
EOF
)"
installed="$(find "${categories_root}/.gap/pkg" -mindepth 1 -maxdepth 1 -type d ! -name '*.old' | wc -l)"
echo "installed ${installed} of ${pinned} pinned GAP packages"
if [ "${installed}" -lt "${pinned}" ]; then
    echo "FATAL: ${pinned} releases are pinned and ${installed} are installed" >&2
    exit 1
fi
