default:
    @just --list

# Build Sage and compose the locked research projects into Sage's virtual environment.
#
# The steps are separate recipes because the image build runs each as its own
# layer, and a pull fetches layers in parallel: one layer holding the whole
# environment downloads as a single stream (sage#9). The desk runs the same
# steps in the same order through this recipe.
research-environment-sync: research-environment-venv research-environment-sage research-environment-repositories research-environment-lean research-environment-pip-check

# The locked research environment's Python packages, synced into the venv.
research-environment-venv:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"
    sage_python_version="${SAGE_PYTHON_VERSION:-3.14}"

    cd "${sage_root}"
    uv sync --python "${sage_python_version}" --frozen --inexact --no-install-project --group research-environment

# Sage, built and installed into the venv.
#
# builddir is also pyproject.toml's build-dir, where uv builds sagemath through
# meson-python whenever it reads the project's metadata (every `uv lock`). Setup
# here uses meson-python's own arguments and native file (mesonpy._configure),
# so that build finds the tree configured and compiled. Installing with meson
# instead of through a wheel skips packaging all of Sage on every sync.
research-environment-sage:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"
    sage_environment="${sage_root}/.venv"
    sage_build_path="${sage_root}/builddir"

    cd "${sage_root}"
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

# The research checkouts under /repos, each package the lock takes from one
# reinstalled as an editable package from the checkout, the bridge's julia-deps,
# and sage-categories' GAP releases.
research-environment-repositories:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"

    cd "${sage_root}"
    docker/install-research-repositories.sh

# The shared Lean project: mathlib4 at the head of its master branch, on the
# toolchain that revision pins, with its whole dependency closure built inside
# it, and every checkout under /repos bound to it.
research-environment-lean:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"

    cd "${sage_root}"
    PYTHON="${sage_root}/.venv/bin/python" "${sage_root}/docker/provision-lean-packages.sh" /repos

# The venv's installed distributions, checked for consistency.
research-environment-pip-check:
    #!/usr/bin/env bash
    set -euo pipefail
    sage_root="{{justfile_directory()}}"

    uv pip check --python "${sage_root}/.venv/bin/python"

