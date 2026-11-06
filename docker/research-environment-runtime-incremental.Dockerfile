# syntax=docker/dockerfile:1

# A source change rebuilt on top of the last published runtime image, for the same
# reason docker/research-environment-incremental.Dockerfile exists for the full one.
#
# The runtime tag's own Dockerfile starts from debian:trixie, so on a source push its
# `COPY . /sage` layer misses and the Sage compile that follows runs from scratch --
# the exact work the incremental path avoids for `:develop` (sage#9). This file does
# what that one does: derive from the previous runtime image, so the venv and the
# build tree are already there and only the modules whose bytes changed recompile.
#
# It is used only when the diff against the running `:develop` names no deletion and
# no change to the runtime Dockerfile itself; the workflow decides that and passes
# BASE_IMAGE as `sage:runtime-<base_revision>`.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS runtime

# Same reason as the main Dockerfile: Meson resolves `libgap` through pkg-config, and
# this file rebuilds the venv on top of an existing image. The base runtime image
# already sets it, so this is a guard against an unpinned base.
ENV PKG_CONFIG_PATH=/sage/.venv/lib/pkgconfig

# rsync --checksum gives unchanged files their old modification times, so ninja
# recompiles only what changed. Nothing is deleted, for the reason the full
# incremental Dockerfile gives.
COPY . /tmp/sage-source
RUN rsync --recursive --links --checksum \
        --exclude /builddir/ --exclude /.venv/ \
        /tmp/sage-source/ /sage/ \
 && rm -rf /tmp/sage-source

ENV CCACHE_DIR=/ccache
# RESEARCH_REPOSITORIES=0 is the virtual-environment half of the recipe: uv sync and
# the Sage compile. Julia, Lean and the research checkouts are not in this image.
ARG RELOCK=false
RUN --mount=type=cache,target=/ccache \
    if [ "$RELOCK" = true ]; then docker/relock-research-packages.sh; fi \
 && RESEARCH_REPOSITORIES=0 just research-environment-sync && ccache --show-stats

# The steps the runtime stage repeats after its sync. They are idempotent: the GAP
# step skips when the checkout already sits at the locked commit with its whole
# allocation, and the uninstall is a no-op once the packages are gone.
RUN docker/install-sage-categories-gap-packages.sh /repos

RUN uv pip uninstall --python /sage/.venv/bin/python juliacall juliapkg \
 && ! /sage/.venv/bin/python -c 'import juliacall' 2>/dev/null

ENV SAGE_BIN=/sage/.venv/bin/sage
ENV PATH=/sage/.venv/bin:$PATH

RUN "$SAGE_BIN" docker/runtime-environment-check.py
