#!/usr/bin/env bash
# Lock every git-sourced research package at its current head. The packages are
# the git entries of [tool.uv.sources], so a new git source joins the relock
# with no edit here. uv reads sagemath's metadata by building it in builddir,
# the tree research-environment-sync then installs from.
set -euo pipefail
cd "$(dirname "$0")/.."
packages="$(python3 -c 'import tomllib; print(" ".join(name for name, source in tomllib.load(open("pyproject.toml", "rb"))["tool"]["uv"]["sources"].items() if "git" in source))')"
test -n "$packages"
# sagemath builds without isolation, so its build requirements must already be
# in the project environment, which a fresh image build has not created yet.
uv venv --allow-existing .venv
python3 -c 'import tomllib; print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["build-system"]["requires"]))' \
    | uv pip install --python .venv/bin/python -r -
upgrade_arguments=()
for package in $packages; do
    upgrade_arguments+=(--upgrade-package "$package")
done
uv lock "${upgrade_arguments[@]}"
