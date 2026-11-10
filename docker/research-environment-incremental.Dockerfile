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

ENV JULIA_CPU_TARGET=generic
# Same reason as the full Dockerfile: Meson resolves `libgap` through pkg-config,
# and this file rebuilds the venv on top of an existing image.
ENV PKG_CONFIG_PATH=/sage/.venv/lib/pkgconfig

COPY . /tmp/sage-source
RUN rsync --recursive --links --checksum \
        --exclude /builddir/ --exclude /.venv/ \
        /tmp/sage-source/ /sage/ \
 && rm -rf /tmp/sage-source

ENV CCACHE_DIR=/ccache

# An incremental build inherits /opt/julia from the image it is based on, and the
# Sage environment's juliapkg requirements name an exact Julia
# (sage_categories/juliapkg.json pins =1.12.7). An inherited tree of another release
# sends juliapkg looking for a Julia at import time, which is the layout that could
# not load its system image in run 42227833648. Installing the pinned release here
# keeps the tree, its sysimage and the wrapper's target together in this image
# instead of inherited by assumption. Keep these two values in step with
# research-environment.Dockerfile, which installs the same tarball.
RUN set -eu; \
    version=1.12.7; \
    sha256=4e7e9e776634d24835250de67cde39b0d4af15bc432eb20697e6be6c28ea69e8; \
    if [ "$(/opt/julia/bin/julia --version 2>/dev/null)" = "julia version $version" ] && [ -f /opt/julia/lib/julia/sys.so ]; then \
        echo "julia $version already present with its sysimage"; \
    else \
        curl -fsSL -o /tmp/julia.tar.gz "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-${version}-linux-x86_64.tar.gz"; \
        echo "$sha256  /tmp/julia.tar.gz" | sha256sum -c -; \
        rm -rf /opt/julia; mkdir /opt/julia; \
        tar -xzf /tmp/julia.tar.gz -C /opt/julia --strip-components=1; \
        rm -f /tmp/julia.tar.gz; \
        test -f /opt/julia/lib/julia/sys.so; \
        echo "installed $(/opt/julia/bin/julia --version) with its sysimage"; \
    fi
# Debian's GAP does not belong in this environment and is not in the full
# Dockerfile's package lists: Sage's `gap` spkg is excluded by name and no other
# package depends on it, so a build from debian:trixie has none. A package list can
# only stop an install; it cannot remove one, and this image is built on a published
# base. A base older than e1e3235b ("build GAP, libgap and its packages from Sage's
# pinned source instead of Debian") carries Debian's 4.14 -- /usr/bin/gap,
# /usr/lib/gap, /usr/share/gap, libgap.so.9 -- and apt never removes what a layer
# installed. That copy is what sage.libs.gap.util.kernel_info() runs when PATH does
# not resolve $SAGE_LOCAL/bin/gap first, and libgap.so.11 then reads 4.14's library
# and segfaults in DoOperation1Args (sage#11). Nothing in the image is built against
# it, so it is purged here, and the build stops if the purge did not take.
RUN purged="$(dpkg-query -W -f='${Package} ${Status}\n' 'gap*' 'libgap*' 2>/dev/null \
        | awk '$2 == "install" && $3 == "ok" && $4 == "installed" {print $1}')" \
 && if [ -n "$purged" ]; then \
        printf 'purging the distribution GAP: %s\n' "$purged"; \
        apt-get purge -y $purged; \
    fi \
 && rm -rf /usr/share/gap /usr/lib/gap \
        /usr/lib/x86_64-linux-gnu/libgap.so.9 \
        /usr/lib/x86_64-linux-gnu/libgap.so \
        /usr/lib/x86_64-linux-gnu/pkgconfig/libgap.pc \
 && test ! -e /usr/bin/gap \
 && test ! -d /usr/share/gap

# The Mathlib head this build carries, resolved by the workflow when the build
# started. It is an input to the sync below, so an unchanged head is a cache hit and
# the layer holding the shared Lean project is reused; a moved head runs the sync,
# which rebuilds that project's closure and nothing else (`docker/
# provision-lean-packages.sh` compares the head with the record the base carries).
ARG MATHLIB_REVISION=
# The recipe's steps, each its own layer: a pull fetches layers in parallel, and
# one layer holding the whole environment downloads as a single stream (sage#9).
# The layers hold the venv's packages, the Sage build, the research checkouts,
# and the shared Lean project, in the recipe's own order. The stats print after
# the last step, as they did when the recipe was one command.
RUN --mount=type=cache,target=/ccache \
    echo "mathlib head for this build: ${MATHLIB_REVISION:-read by the provisioning script}" \
 && just research-environment-venv
RUN --mount=type=cache,target=/ccache \
    just research-environment-sage && ccache --show-stats
RUN --mount=type=cache,target=/ccache just research-environment-repositories
RUN --mount=type=cache,target=/ccache just research-environment-lean
RUN --mount=type=cache,target=/ccache \
    just research-environment-pip-check && ccache --show-stats

FROM scratch AS lock
COPY --from=environment /sage/uv.lock /uv.lock

FROM environment

ENV PATH=/sage/.venv/bin:$PATH

RUN "$SAGE_BIN" docker/research-environment-check.py
