default:
    @just --list

# Build Sage and compose the locked research projects into Sage's virtual environment.
research-environment-sync:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"
    sage_python_version="${SAGE_PYTHON_VERSION:-3.14}"
    sage_environment="${sage_root}/.venv"

    cd "${sage_root}"
    # uv builds sagemath through meson-python in pyproject.toml's build-dir, the
    # tree every later uv lock or sync reads its metadata from.
    uv sync --python "${sage_python_version}" --frozen --inexact --no-editable --group research-environment

    uv pip check --python "${sage_environment}/bin/python"
