# syntax=docker/dockerfile:1

# The research Sage environment, built once and consumed everywhere.
#
# Every repository that writes Sage against this fork needs the same
# interpreter and the same composed environment. Building it per repository, or
# per CI run, is the same work repeated; this image is that work done once.
#
# SAGE_ROOT is baked in at configure time, so the tree lives at /sage and is
# not relocatable. Neither is it separable: sagelib's extension modules link
# against the system libraries installed below, so a consumer runs inside this
# image rather than copying /sage out of it.

# Debian, because Sage's system-package metadata is Debian's: every
# build/pkgs/*/distros/debian.txt names a package Debian ships. Ubuntu 24.04
# is missing five of them -- maxima-sage and HiGHS among them -- so the same
# metadata that resolves completely here resolves partially there.
FROM debian:trixie AS environment

ENV DEBIAN_FRONTEND=noninteractive
# /sage is the fork's git checkout. Meson's vcs_tag would stamp its commit into
# HiGHS's HConfig.h and recompile HiGHS on every commit; git stops looking for a
# repository at the subprojects directory, so the stamp stays at its fallback.
ENV GIT_CEILING_DIRECTORIES=/sage/subprojects

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && rm -rf /var/lib/apt/lists/*

# uv supplies the managed 3.14 interpreter that Sage's venv is built on; it is
# the Python everything in the image runs: --default installs it as python3,
# ahead of any Debian python3 on PATH, so Sage's bootstrap shebangs resolve to it.
# just runs the build recipe the desk uses, so the image and the desk build the
# same way. Both live outside /root, which is mode 0700: the launcher runs Sage
# as the desk's own uid, and the venv's interpreter must be readable by it.
ENV UV_INSTALL_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PYTHON_BIN_DIR=/usr/local/bin \
    UV_NO_MODIFY_PATH=1
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && uv python install --default 3.14 \
 && test "$(command -v python3)" = /usr/local/bin/python3 \
 && curl -LsSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Everything up to the full source copy below depends only on Sage's package
# metadata (build/, pyproject.toml, and configure.ac, which sage_bootstrap
# requires to recognise SAGE_ROOT), so a source change reuses these layers.
COPY build /sage/build
COPY pyproject.toml configure.ac /sage/
WORKDIR /sage

# Sage's own package metadata names what the build links against: every
# build/pkgs/*/distros/debian.txt, resolved by Sage's own scripts. This is the
# bootstrap from src/doc/en/installation/source.rst, not a hand-kept list, so
# it stays correct as the dependency set moves.
# The list is captured and checked rather than substituted inline: an empty
# substitution makes `apt-get install` succeed having installed nothing, and
# the build then runs on for ten minutes before failing somewhere unrelated
# for want of a compiler. Both checks turn that into an immediate, named
# failure.
#
# BRiAl and gap-polenta are the names Sage lists that Debian trixie does not
# ship; they are excluded by name so that any *other* name failing to resolve
# still fails the build. Polenta is pure GAP and is installed below.
# Its meson feature is `auto`, so sage.rings.polynomial.pbori -- Boolean
# polynomial rings -- is absent from this image and present on a desk whose
# distribution still packages BRiAl.
RUN set -eu; \
    packages="$(build/bin/sage-get-system-packages debian $(build/bin/sage-package list :standard:) \
        | tr ' ' '\n' | grep -vxE 'libbrial-dev|libbrial-groebner-dev|gap-polenta' | tr '\n' ' ')"; \
    if [ -z "$packages" ]; then \
        echo "FATAL: Sage's package metadata produced no Debian packages" >&2; exit 1; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends $packages; \
    rm -rf /var/lib/apt/lists/*; \
    if ! command -v gcc >/dev/null; then \
        echo "FATAL: no C compiler after installing Sage's prerequisites" >&2; exit 1; \
    fi

# Sage's optional packages and the other systems research code calls. Sage's
# metadata marks these optional, so the standard list above omits them; the
# Debian names come from build/pkgs/*/distros/debian.txt where Sage records one.
# Meson's optional features (bliss, libbraiding, libhomfly, rankwidth) are
# `auto`, so their libraries being present is what builds them.
# binutils-gold: polymake-config's --ldflags select -fuse-ld=gold, so jupymake
# does not link without it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libbliss-dev libhomfly-dev librw-dev \
    macaulay2 \
    4ti2 latte-int lrslib topcom msolve normaliz-bin libnormaliz-dev \
    polymake libpolymake-dev libgiac-dev xcas fricas kissat cliquer \
    gap-atlasrep gap-design gap-grape gap-guava gap-guava-bin gap-hap gap-radiroot \
    gap-polycyclic gap-alnuth gap-autpgrp gap-cryst gap-crystcat gap-io gap-nq \
    gap-character-tables gap-table-of-marks gap-transgrp gap-primgrp gap-smallgrp-extra \
    gap-utils gap-float gap-toric gap-laguna gap-sonata gap-factint gap-congruence \
    sagemath-database-graphs sagemath-database-polytopes \
    pari-galdata pari-elldata pari-seadata pari-galpol \
    pandoc graphviz dvipng imagemagick texlive-latex-extra \
    cmake libpcre2-dev cargo rustc ccache rsync binutils-gold \
 && rm -rf /var/lib/apt/lists/*

# Polenta (polycyclic presentations of matrix groups) is a standard GAP package
# for Sage, but Debian trixie does not package it; its release is pure GAP.
RUN set -eu; \
    curl -fsSL -o /tmp/polenta.tar.gz https://github.com/gap-packages/polenta/releases/download/v1.3.11/polenta-1.3.11.tar.gz; \
    echo "aabf20981e438c2b361f416527163ae299a27a0a95ff3eb908a1aeae07b21bc1  /tmp/polenta.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/polenta.tar.gz -C /usr/share/gap/pkg; \
    rm /tmp/polenta.tar.gz

# Debian installs these programs under package prefixes (4ti2-hilbert,
# latte-count, topcom-points2allfinetriangs); Sage's features look for the
# unprefixed names, so link them into /usr/local/bin. 4ti2 and LattE both ship
# `minimize`; 4ti2 is linked first and keeps the name, which Sage's 4ti2
# feature uses.
RUN set -eu; \
    for prefix in 4ti2- latte- topcom-; do \
        for program in /usr/bin/"$prefix"*; do \
            name="${program#/usr/bin/$prefix}"; \
            if [ "$prefix$name" = latte-minimize ]; then continue; fi; \
            ln -s "$program" /usr/local/bin/"$name"; \
        done; \
    done; \
    command -v hilbert count points2allfinetriangs

# Sage needs libbraiding >= 1.3.1 and Debian trixie ships 1.1, so the release
# Sage's own package metadata pins (build/pkgs/libbraiding) is built here.
RUN set -eu; \
    version="$(cat build/pkgs/libbraiding/package-version.txt)"; \
    sha256="$(sed -n 's/^sha256=//p' build/pkgs/libbraiding/checksums.ini)"; \
    curl -fsSL -o /tmp/libbraiding.tar.gz "https://github.com/miguelmarco/libbraiding/releases/download/$version/libbraiding-$version.tar.gz"; \
    echo "$sha256  /tmp/libbraiding.tar.gz" | sha256sum -c -; \
    mkdir /tmp/libbraiding; tar -xzf /tmp/libbraiding.tar.gz -C /tmp/libbraiding --strip-components=1; \
    cd /tmp/libbraiding; ./configure --prefix=/usr/local; make -j"$(nproc)"; make install; ldconfig; \
    rm -rf /tmp/libbraiding /tmp/libbraiding.tar.gz; \
    pkg-config --atleast-version=1.3.1 libbraiding

# CoxIter (Guglielmetti) computes invariants of hyperbolic Coxeter groups.
# It is not packaged anywhere and needs PCRE1, which Debian trixie no longer
# ships, so PCRE 8.45 (the final PCRE1 release) is built into /opt/pcre for it.
# Its coxiter_maths target includes pcre.h without PCRE's include path, hence
# the explicit -I.
RUN set -eu; \
    curl -fsSL -o /tmp/pcre.tar.bz2 https://sourceforge.net/projects/pcre/files/pcre/8.45/pcre-8.45.tar.bz2/download; \
    echo "4dae6fdcd2bb0bb6c37b5f97c33c2be954da743985369cddac3546e3218bffb8  /tmp/pcre.tar.bz2" | sha256sum -c -; \
    mkdir /tmp/pcre; tar -xjf /tmp/pcre.tar.bz2 -C /tmp/pcre --strip-components=1; \
    cd /tmp/pcre; ./configure --prefix=/opt/pcre --disable-shared --enable-utf --enable-unicode-properties; \
    make -j"$(nproc)"; make install; \
    git clone https://github.com/rgugliel/CoxIter /tmp/coxiter; \
    git -C /tmp/coxiter -c advice.detachedHead=false checkout b800be48d8240fbabd2d1c9542e61054584ad7fe; \
    cmake -S /tmp/coxiter -B /tmp/coxiter/build -DCMAKE_PREFIX_PATH=/opt/pcre -DCMAKE_CXX_FLAGS=-I/opt/pcre/include -DCMAKE_INSTALL_PREFIX=/usr/local; \
    cmake --build /tmp/coxiter/build -j"$(nproc)"; \
    cmake --install /tmp/coxiter/build; \
    rm -rf /tmp/pcre /tmp/pcre.tar.bz2 /tmp/coxiter; \
    command -v coxiter

# Julia and Oscar for sage-julia-bridge. Oscar and JSON go into the default
# environment of the read-only /opt/julia-depot, so no desk keeps its own copy
# of the Oscar artifacts; the bridge's own --project stacks on top of it. At
# runtime a writable depot is placed in front of this one; the trailing empty
# entry keeps Julia's bundled stdlib depot on the path.
RUN set -eu; \
    curl -LsSf -o /tmp/julia.tar.gz https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.5-linux-x86_64.tar.gz; \
    echo "41b84d727e4e96fbf3ed9e92fa195d773d247b9097f73fad688f8b699758bae7  /tmp/julia.tar.gz" | sha256sum -c -; \
    mkdir /opt/julia; \
    tar -xzf /tmp/julia.tar.gz -C /opt/julia --strip-components=1; \
    rm /tmp/julia.tar.gz; \
    ln -s /opt/julia/bin/julia /usr/local/bin/julia

# Package caches must load on both the CI CPU and the host CPU.
# https://docs.julialang.org/en/v1.12/manual/environment-variables/#JULIA_CPU_TARGET
ENV JULIA_DEPOT_PATH=/opt/julia-depot: \
    JULIA_CPU_TARGET=generic

RUN set -eu; \
    julia --startup-file=no --color=no -e ' \
        using Pkg; \
        Pkg.add(["Oscar", "JSON"]); \
        Pkg.precompile(); \
        import JSON; \
        using Oscar; \
        println("JSON ", pkgversion(JSON), ", Oscar ", Oscar.VERSION_NUMBER, " loaded")'; \
    chmod -R a+rX /opt/julia-depot

# Lean 4 through elan; install-research-repositories.sh installs the toolchain
# each Lean checkout pins.
ENV ELAN_HOME=/opt/elan
ENV PATH=/opt/elan/bin:$PATH
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --no-modify-path --default-toolchain none \
 && elan --version

COPY . /sage

# ccache keeps compiler output across image builds; Meson uses it whenever it
# is on PATH. The cache mount is not part of the image, and CI carries it
# between runs, so a source change recompiles only the modules it touches.
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

ENV SAGE_BIN=/sage/.venv/bin/sage
ENV PATH=/sage/.venv/bin:$PATH

# Fail the build if any system the image exists to provide is absent.
RUN "$SAGE_BIN" docker/research-environment-check.py
