# syntax=docker/dockerfile:1

# A source change rebuilt on top of the last published image, as upstream's
# build.yml rebuilds incrementally from its published with-targets image.
#
# The new source is copied in by content: rsync --checksum leaves every
# unchanged file with its old modification time, so ninja recompiles only the
# modules whose sources changed. A plain COPY would give every file a new
# mtime and rebuild all of Sage. Nothing is deleted: meson writes generated
# files into the source tree, and removing them forces a reconfigure. A file
# deleted from the source, or a change to the system layers
# (research-environment.Dockerfile), needs the full build instead.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS environment

COPY . /tmp/sage-source
RUN rsync --recursive --links --checksum \
        --exclude /builddir/ --exclude /.venv/ \
        /tmp/sage-source/ /sage/ \
 && rm -rf /tmp/sage-source

ENV CCACHE_DIR=/ccache
# RELOCK=true first moves the git-sourced research packages to their heads; the
# sync then installs that lock, and the `lock` stage below exports it.
ARG RELOCK=false
RUN --mount=type=cache,target=/ccache \
    if [ "$RELOCK" = true ]; then docker/relock-research-packages.sh; fi \
 && just research-environment-sync && ccache --show-stats

FROM scratch AS lock
COPY --from=environment /sage/uv.lock /uv.lock

FROM environment

RUN "$SAGE_BIN" docker/research-environment-check.py
