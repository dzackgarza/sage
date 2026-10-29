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
    # Sage's own pyproject has a `dev` group; the research-environment group
    # belongs to the separately locked research project and is not declared in
    # Sage's pyproject. Install each lock into the same Sage runtime explicitly.
    uv sync --python "${sage_python_version}" --frozen --inexact --no-install-project --group dev
    research_requirements="${sage_root}/.research-requirements.txt"
    uv export --project "${sage_root}/.research-env" --frozen --no-dev --no-emit-project --format requirements-txt --output-file "${research_requirements}"
    # The frozen export already contains every transitive requirement. Do not
    # re-resolve their direct-URL metadata: sage-extensions and the research
    # project name the same sage-julia-bridge repository at different lock
    # revisions, and uv's resolver rejects those URL constraints despite the
    # later public-consumer step deliberately installing its exact bridge SHA.
    uv pip install --no-deps --python "${sage_environment}/bin/python" --requirement "${research_requirements}"
    # Maxima 5.47.0's external project requires Meson >=1.11.2, while the
    # develop uv.lock currently pins 1.10.0. Upgrade only this build tool after
    # the frozen environment sync and before configuring any Meson project.
    uv pip install --python "${sage_environment}/bin/python" 'meson>=1.11.2'

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

    # The lock resolves every research project from its repository, so the
    # environment is constructible anywhere. A desk additionally has these
    # checked out, and wants edits live rather than a fetched snapshot: each
    # one present is reinstalled over the resolved copy. A machine without a
    # checkout -- a container, a CI runner -- simply has none of them and gets
    # the locked versions, which is the same environment.
    for research_checkout in "${HOME}/research" "${HOME}/gitclones/sage-extensions" "${HOME}/gitclones/tree-sitter-sage" "${HOME}/gitclones/jupyter-assistant-api"; do
        if [ -d "${research_checkout}" ]; then
            uv pip install --python "${sage_environment}/bin/python" --no-deps -e "${research_checkout}"
        fi
    done

    # sage-categories imports its native workspace member sage-categories-homotopy
    # but declares it only in its `platform` dependency group, which a --no-deps
    # install never reads. Its checkout is installed the way its own CI installs
    # it: the project together with that group.
    sage_categories_checkout="${HOME}/gitclones/sage-categories"
    if [ -d "${sage_categories_checkout}" ]; then
        uv pip install --python "${sage_environment}/bin/python" --project "${sage_categories_checkout}" --group platform --editable "${sage_categories_checkout}"
    fi

    uv pip check --python "${sage_environment}/bin/python"
