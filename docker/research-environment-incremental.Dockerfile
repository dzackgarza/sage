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

# GAP.jl 0.16.7 -- the version sage-julia-bridge's julia_env pins -- records
# GAP_pkg_crisp 1.4.8 with a version-less "latest" GitHub URL that now 404s, and
# Julia's package server 404s the artifact itself, so the only source left is
# files.gap-system.org. The sync instantiates that project, which makes the artifact
# a declared input of this image: fetch it from the mirror, check the tarball's
# sha256, and let Julia find it instead of resolving a URL set that rotted. The tree
# hash is what Julia checks, so the seeded copy is held to it rather than to the
# directory's existence.
RUN artifact=/opt/julia-depot/artifacts/85ac41f54aedd09fb370d977dd6ee3309684056d; \
    tree_hash() { julia --startup-file=no --color=no -e 'using Pkg; print(bytes2hex(Pkg.GitTools.tree_hash(ARGS[1])))' "$1"; }; \
    if [ -d "$artifact" ] && [ "$(tree_hash "$artifact")" = 85ac41f54aedd09fb370d977dd6ee3309684056d ]; then \
        echo "crisp-1.4.8: already the pinned tree"; \
    else \
        mkdir -p "$artifact"; \
        for attempt in 1 2 3 4 5; do \
            echo "crisp-1.4.8.tar.bz2: attempt $attempt"; \
            if curl -fsSL --retry 3 --retry-delay 10 --connect-timeout 20 --max-time 900 \
                    -o /tmp/crisp-1.4.8.tar.bz2 \
                    https://files.gap-system.org/pkg/crisp-1.4.8.tar.bz2; then break; fi; \
            sleep 15; \
        done; \
        echo "3360e17c1611a2ab1654d982aade5566a1c048c795675e321cbf15d06248d569  /tmp/crisp-1.4.8.tar.bz2" \
            | sha256sum -c -; \
        tar -xjf /tmp/crisp-1.4.8.tar.bz2 -C "$artifact"; \
        rm -f /tmp/crisp-1.4.8.tar.bz2; \
        test "$(tree_hash "$artifact")" = 85ac41f54aedd09fb370d977dd6ee3309684056d; \
    fi

# RELOCK=true first moves the git-sourced research packages to their heads; the
# sync then installs that lock, and the `lock` stage below exports it.
ARG RELOCK=false
RUN --mount=type=cache,target=/ccache \
    if [ "$RELOCK" = true ]; then docker/relock-research-packages.sh; fi \
 && just research-environment-sync && ccache --show-stats

FROM scratch AS lock
COPY --from=environment /sage/uv.lock /uv.lock

FROM environment

ENV PATH=/sage/.venv/bin:$PATH

RUN "$SAGE_BIN" docker/research-environment-check.py
