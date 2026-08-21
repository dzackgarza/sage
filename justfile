default:
    @just --list

# Build Sage and compose the locked research projects into Sage's virtual environment.
research-environment-sync:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"
    sage_python_version="${SAGE_PYTHON_VERSION:-3.14}"
    sage_environment="${sage_root}/.venv"
    sage_build_path="${sage_root}/builddir"

    cd "${sage_root}"
    uv sync --python "${sage_python_version}" --frozen --inexact --no-install-project --group research-environment

    export VIRTUAL_ENV="${sage_environment}"
    export PATH="${sage_environment}/bin:${PATH}"
    meson_command="${sage_environment}/bin/meson"
    if [ -f "${sage_build_path}/meson-private/coredata.dat" ]; then
        "${meson_command}" setup --reconfigure "${sage_build_path}" --prefix "${sage_environment}" -Dpython.install_env=prefix
    else
        "${meson_command}" setup "${sage_build_path}" --prefix "${sage_environment}" -Dpython.install_env=prefix
    fi
    "${meson_command}" compile -C "${sage_build_path}"
    "${meson_command}" install -C "${sage_build_path}"
    uv pip check --python "${sage_environment}/bin/python"
