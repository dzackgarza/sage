default:
    @just --list

# Build Sage's virtual environment: the locked Python set, Sage compiled and
# installed into it, and nothing from /repos. This is the whole of what the
# runtime image needs, and it is separate from the research provisioning below so
# that a consumer that wants only Sage and GAP does not pull the rest.
# Sage only, for the runtime image
research-environment-venv:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"
    sage_python_version="${SAGE_PYTHON_VERSION:-3.14}"
    sage_environment="${sage_root}/.venv"
    sage_build_path="${sage_root}/builddir"

    cd "${sage_root}"
    uv sync --python "${sage_python_version}" --frozen --inexact --no-install-project --group research-environment

    # builddir is also pyproject.toml's build-dir, where uv builds sagemath through
    # meson-python whenever it reads the project's metadata (every `uv lock`). Setup
    # here uses meson-python's own arguments and native file (mesonpy._configure),
    # so that build finds the tree configured and compiled. Installing with meson
    # instead of through a wheel skips packaging all of Sage on every sync.
    export VIRTUAL_ENV="${sage_environment}"
    export PATH="${sage_environment}/bin:${PATH}"
    mkdir -p "${sage_build_path}"
    native_file="${sage_build_path}/meson-python-native-file.ini"
    # Rewriting the file would make ninja regenerate the whole build on every sync.
    native_file_content="$(printf "[binaries]\npython = '%s'" "${sage_environment}/bin/python")"
    if [ "$(cat "${native_file}" 2>/dev/null)" != "${native_file_content}" ]; then
        printf '%s\n' "${native_file_content}" > "${native_file}"
    fi
    setup_arguments=(
        -Dbuildtype=release -Db_ndebug=if-release -Db_vscrt=md --default-library=static
        "--native-file=${native_file}"
        --prefix "${sage_environment}" -Dpython.install_env=prefix
    )
    # A configured tree is otherwise left as it is: `meson compile` regenerates
    # it when a meson.build changes, and an explicit reconfigure costs minutes.
    # meson-python configures a fresh tree without the install prefix (a relock
    # builds it before this sync), so the prefix is set when it differs.
    if [ ! -f "${sage_build_path}/meson-private/coredata.dat" ]; then
        meson setup "${sage_root}" "${sage_build_path}" "${setup_arguments[@]}"
    elif [ "$(meson introspect --buildoptions "${sage_build_path}" | python -c 'import json, sys; print(next(o["value"] for o in json.load(sys.stdin) if o["name"] == "prefix"))')" != "${sage_environment}" ]; then
        meson configure "${sage_build_path}" --prefix "${sage_environment}" -Dpython.install_env=prefix
    fi
    meson compile -C "${sage_build_path}"
    meson install -C "${sage_build_path}"

    uv pip check --python "${sage_environment}/bin/python"

# Sage plus every research checkout under /repos, the Julia depot and the Lean
# packages. RESEARCH_REPOSITORIES=0 stops after the virtual environment, which is
# what the runtime image builds.
# Sage, the checkouts, Julia and Lean
research-environment-sync: research-environment-venv
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"
    sage_environment="${sage_root}/.venv"

    if [ "${RESEARCH_REPOSITORIES:-1}" = 0 ]; then
        echo "RESEARCH_REPOSITORIES=0: stopping at the Sage virtual environment"
        exit 0
    fi
    docker/install-research-repositories.sh

    uv pip check --python "${sage_environment}/bin/python"
