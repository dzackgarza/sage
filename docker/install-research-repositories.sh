#!/usr/bin/env bash
# Check out every repository in research-repositories.txt under /repos. A
# repository that is a git source of uv.lock is checked out at the head of its
# main branch -- every build installs each research repository at that head
# (sage#24), and the locked commit is only where the last relock left it -- and
# each package the lock takes from it is reinstalled as an editable package
# from the checkout, so the environment runs the code agents edit. The head
# each repository was installed at is recorded in .research-revisions in this
# tree, one "<name> <commit>" per line, for a consumer to read in the image.
set -euo pipefail
# The script's own tree by default; a test or another tree points it elsewhere.
sage_root="${SAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
# /repos in the image; a test or another tree points the script at its own.
repositories_root="${REPOSITORIES_ROOT:-/repos}"
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
revisions="${sage_root}/.research-revisions"
: > "${revisions}"
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
        read -r _ _ subdirectories <<<"${lock_entry}"
        # The head of the main branch, not the commit the lock holds: the
        # build installs each repository at that head, and the locked commit
        # is only where the last relock left it (sage#24).
        git -C "${checkout}" checkout --quiet -B "${branch}" "origin/${branch}"
        git -C "${checkout}" branch --quiet --set-upstream-to="origin/${branch}"
        for subdirectory in ${subdirectories}; do
            editable+=(-e "${checkout}/${subdirectory}")
        done
        printf '%s %s\n' "${name}" "$(git -C "${checkout}" rev-parse HEAD)" >> "${revisions}"
    else
        git -C "${checkout}" checkout --quiet -B "${branch}" "origin/${branch}"
    fi
done < "${sage_root}/docker/research-repositories.txt"

# The heads this build resolved, one <name>=<commit> pair per repository, passed
# by the workflow as the RESEARCH_REVISIONS build argument (sage#24). The check
# runs after the checkout loop, so it compares the commit the script checked out
# with the commit the workflow resolved: a difference means the remote moved
# between the two reads, or that the script did not check out the head. In both
# cases the build fails, and the message names both commits.
research_revisions="${RESEARCH_REVISIONS:-}"
if [ -n "${research_revisions}" ]; then
    for pair in ${research_revisions}; do
        name="${pair%%=*}"
        expected="${pair#*=}"
        checkout="${repositories_root}/${name}"
        found="$(git -C "${checkout}" rev-parse HEAD 2>/dev/null || true)"
        if [ "${found}" != "${expected}" ]; then
            printf 'error: %s is at %s, not the %s this build resolved: the remote moved between the two reads, or the install did not check out the head\n' \
                "${checkout}" "${found:-no revision}" "${expected}" >&2
            exit 1
        fi
    done
fi

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
# PEP 503 normalization on both sides: uv prints a distribution under its
# normalized name (jupyter-mcp-server), while a project's own pyproject may spell it
# with the underscore its module uses (jupyter_mcp_server). Run 42274146900 failed
# the comparison on exactly that pair.
normalize() { tr '[:upper:]' '[:lower:]' | sed -e 's/[-_.]\{1,\}/-/g' | sort -u; }
expected="$(printf '%s\n' "${expected}" | normalize)"
installed="$(uv pip list --python "${sage_python}" --editable 2>/dev/null | awk 'NR>2 {print $1}' | normalize)"
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
