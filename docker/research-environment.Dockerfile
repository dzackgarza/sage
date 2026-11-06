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
FROM debian:trixie AS base

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
        | tr ' ' '\n' | grep -vxE 'libbrial-dev|libbrial-groebner-dev|gap|libgap.*|gap-.*' | tr '\n' ' ')"; \
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
    sagemath-database-graphs sagemath-database-polytopes \
    pari-galdata pari-elldata pari-seadata pari-galpol \
    pandoc graphviz dvipng imagemagick texlive-latex-extra \
    cmake libpcre2-dev cargo rustc ccache rsync binutils-gold \
 && rm -rf /var/lib/apt/lists/*

# The venv has to exist before GAP is installed into it. uv refuses to adopt a
# nonempty .venv that is not a valid Python environment -- "cannot be used
# because it is not a valid Python environment (no Python executable was found)"
# -- which is precisely what installing GAP into the directory first produces.
# So: create the venv, install GAP into it, then let the sync populate it. The
# files GAP installs are not Python's and survive `uv sync` (verified).
RUN uv venv /sage/.venv --python 3.14

# src/meson.build:233 asks pkg-config for `libgap >= 4.13` before falling back to
# cc.find_library('gap'). An ENV, not an export inside one RUN: an incremental
# build reuses this image and runs its own `research-environment-sync`, and Meson
# caches dependency discovery in the build directory, so the variable has to be in
# the environment every such run starts from.
ENV PKG_CONFIG_PATH=/sage/.venv/lib/pkgconfig

# GAP, libgap, its headers and every GAP package come from ONE pinned upstream
# source: the tarball Sage's own `gap` and `gap_packages` spkgs declare in
# build/pkgs/gap/checksums.ini. Nothing here comes from the distribution, and no
# path outside $SAGE_LOCAL is involved.
#
# Why this replaces the Debian GAP the image used to install:
#
#  * Reproducibility. A distro GAP is whatever trixie ships (4.14.0 here) while
#    Sage pins 4.16.1. An executable, a libgap, headers and package roots from
#    different builds is the failure class this repository already recorded once
#    for bliss: headers and library disagreeing about ABI.
#  * Reachability. Sage's documented home for optional GAP packages is
#    $SAGE_LOCAL/lib/gap/pkg (build/pkgs/gap_packages/spkg-install.in:31), but
#    that is only a GAP root when GAP itself was built into $SAGE_LOCAL
#    (build/pkgs/gap/spkg-install.in:11). With a distro GAP, `sage -i
#    gap_packages` installs files no GAP searches.
#  * Linkage. src/meson.build:233 resolves `libgap` through pkg-config and falls
#    back to cc.find_library('gap') -- independently of spkg-configure -- so
#    building GAP here is only half the job: PKG_CONFIG_PATH must point at this
#    prefix and no system libgap.pc may be visible, which is why the distro
#    packages are excluded above.
#
# src/sage/libs/gap/util.pyx:284 hands libgap `-l <roots of the gap on PATH>`, so
# once $SAGE_LOCAL/bin/gap is the one PATH resolves, the root list follows.
RUN set -eu; \
    SAGE_LOCAL=/sage/.venv; \
    version="$(cat build/pkgs/gap/package-version.txt)"; \
    sha256="$(sed -n 's/^sha256=//p' build/pkgs/gap/checksums.ini)"; \
    curl -fsSL -o /tmp/gap.tar.gz "https://github.com/gap-system/gap/releases/download/v${version}/gap-${version}.tar.gz"; \
    echo "${sha256}  /tmp/gap.tar.gz" | sha256sum -c -; \
    mkdir /tmp/gap; tar -xzf /tmp/gap.tar.gz -C /tmp/gap --strip-components=1; \
    cd /tmp/gap; \
    ./configure --prefix="$SAGE_LOCAL"; \
    make -j"$(nproc)"; \
    make install; \
    test -x "$SAGE_LOCAL/bin/gap" && test -f "$SAGE_LOCAL/lib/gap/sysinfo.gap"; \
    # Every package the pinned GAP distribution ships, not a curated subset: a
    # hand-picked list keeps turning out to be missing a member of some package's
    # NeededOtherPackages closure -- `polenta` wants `alnuth`, `atlasrep` wants
    # `primgrp`+`gapdoc`, `guava` wants `sonata`, `orb` wants `io` -- and GAP then
    # refuses to load the package that needed it. A normal GAP installation has
    # all of them, so this one does too.
    #
    # GAP's `make install` does not install pkg/ at all, so it is copied, whole,
    # from the same pinned source into the root GAP searches. `/.` copies the
    # contents; without it a second run would nest pkg/pkg.
    GAP_ROOT_PKG="$SAGE_LOCAL/lib/gap/pkg"; \
    mkdir -p "$GAP_ROOT_PKG"; \
    cp -a /tmp/gap/pkg/. "$GAP_ROOT_PKG/"; \
    echo "installed $(ls "$GAP_ROOT_PKG" | wc -l) GAP packages"; \
    # The packages Sage's own gap_packages spkg compiles; the pinned source ships
    # their C, so they are built here against this GAP and its gac.
    compiled_old="cohomolo crypting grape orb datastructures"; \
    compiled_new="nq io digraphs"; \
    for pkg in $compiled_old; do \
        echo "building GAP package $pkg"; \
        cd "$GAP_ROOT_PKG/$pkg" && ./configure "$SAGE_LOCAL/lib/gap" && make -j"$(nproc)" && cd /; \
    done; \
    echo "building GAP package guava"; \
    export CFLAGS="-std=gnu17 -Wno-implicit-function-declaration ${CFLAGS:-}"; \
    cd "$GAP_ROOT_PKG/guava" && ./configure "$SAGE_LOCAL/lib/gap" && make -j"$(nproc)" && cd /; \
    for pkg in $compiled_new; do \
        echo "building GAP package $pkg"; \
        cd "$GAP_ROOT_PKG/$pkg" && ./configure --with-gaproot="$SAGE_LOCAL/lib/gap" && make -j"$(nproc)" && cd /; \
    done; \
    cd /; rm -rf /tmp/gap /tmp/gap.tar.gz; \
    # The binary carries no rpath to $SAGE_LOCAL/lib, so the loader must be told
    # where libgap.so.11 is before this build runs it -- and before anything else
    # in the image runs it.
    printf '%s\n' "$SAGE_LOCAL/lib" > /etc/ld.so.conf.d/sage-local.conf; \
    ldconfig; \
    # Load, not just list: LoadPackage fails when a NeededOtherPackages entry is
    # missing from the root, so this is the closure check. hap needs polycyclic,
    # guava needs sonata, orb needs io, grape needs GAPDoc, polenta needs alnuth
    # and polycyclic, recog needs atlasrep, genss needs orb -- all pinned source.
    "$SAGE_LOCAL/bin/gap" -q --nointeract -c 'for n in ["atlasrep", "design", "grape", "guava", "hap", "polenta", "polycyclic", "sonata", "io", "alnuth", "orb", "forms", "genss", "recog"] do if LoadPackage(n) <> true then Print("FATAL: GAP package ", n, " does not load\n"); QUIT_GAP(1); fi; od;'

# The GAP packages Sage's feature checks and the matrix-group work need are all
# inside that same tarball (the spkg installs them from its pkg/ directory), so
# there is nothing else to fetch: atlasrep, design, grape, guava, hap, polenta,
# polycyclic, factint, tomlib, genss, orb, forms and recog are bundled.

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

# Two images come out of this file, and the order of the layers is what keeps the
# smaller one small. A consumer job pays for the whole image before its first step
# runs, so the layers a Sage-and-GAP consumer needs are built FIRST and the tag it
# pulls stops there:
#
#   runtime    base + Sage's system packages + GAP + /sage + the Sage venv +
#              sage-categories' pinned GAP allocation + Julia and its resolved
#              depot. No Lean, no research checkouts beyond that one. Julia is here
#              because importing sage_categories loads it: the engine builds functor
#              object images through Catlab, which imports juliacall.
#   develop    the runtime plus elan, the Lean packages and every research checkout
#              under /repos (what "full" below adds).
#
# The runtime's layers are a byte-identical prefix of the full image's, so the
# registry stores the difference rather than a second image, and Dockerfile edits
# beyond the split point cannot invalidate the runtime tag.

# ---------------------------------------------------------------------------
# The runtime image: everything above, the source, the Sage virtual environment
# and sage-categories' own GAP allocation. Nothing here needs Julia, Lean or the
# research checkouts, so the tag a Sage-and-GAP consumer pulls stops at this point.
# ---------------------------------------------------------------------------
FROM base AS runtime

# The source, once, here: everything above it depends only on Sage's package
# metadata, so a source change reuses every system layer and rebuilds from this
# point. ccache keeps compiler output across image builds; Meson uses it whenever
# it is on PATH, and the cache mount is not part of the image.
COPY . /sage
ENV CCACHE_DIR=/ccache

# RESEARCH_REPOSITORIES=0 runs the virtual-environment half of the recipe only:
# `uv sync`, Sage compiled and installed. The other research checkouts and the Lean
# packages are what the full image adds below.
ARG RELOCK=false
RUN --mount=type=cache,target=/ccache \
    if [ "$RELOCK" = true ]; then docker/relock-research-packages.sh; fi \
 && RESEARCH_REPOSITORIES=0 just research-environment-sync && ccache --show-stats

# The one research checkout the runtime image carries: its finite-category engine
# loads homalg/CAP from the checkout itself rather than from the image's GAP
# (sage#10), so a Sage consumer that builds a presented module needs this
# allocation present. The other 23 checkouts stay in the full image.
RUN docker/install-sage-categories-gap-packages.sh /repos

# Julia, because the consumers this image exists for need it: importing
# sage_categories constructs functor object images through Catlab, which imports
# juliacall, so every sage-categories consumer -- sage-extensions included -- loads
# Julia. The depot is resolved HERE, at build time, for the same reason: at import
# juliapkg resolves the Julia and package requirements of every installed
# distribution, and against an unresolved depot that is a network fetch.
# sage_categories/juliapkg.json pins Julia =1.12.7; measured with 1.12.5 in the
# image, `import sage_categories` reached julialang-s3.julialang.org and died with
# the network down, which is why this installs that exact release.
#
# Oscar and JSON go into the default environment of the read-only /opt/julia-depot,
# so no desk keeps its own copy of the Oscar artifacts; the bridge's own --project
# stacks on top of it. At runtime a writable depot is placed in front of this one;
# the trailing empty entry keeps Julia's bundled stdlib depot on the path.
RUN set -eu; \
    curl -LsSf -o /tmp/julia.tar.gz https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.7-linux-x86_64.tar.gz; \
    echo "4e7e9e776634d24835250de67cde39b0d4af15bc432eb20697e6be6c28ea69e8  /tmp/julia.tar.gz" | sha256sum -c -; \
    mkdir /opt/julia; \
    tar -xzf /tmp/julia.tar.gz -C /opt/julia --strip-components=1; \
    rm /tmp/julia.tar.gz

# /usr/local/bin/julia is the image's entry point rather than a symlink: it
# adds /opt/julia-depot to whatever JULIA_DEPOT_PATH the caller has, so a
# process whose environment did not come from this image (PRoot over the
# unpacked filesystem, a bare exec) still resolves the bridge's packages.
COPY --chmod=0755 docker/julia-launcher.sh /usr/local/bin/julia

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

# Resolve what those distributions require into the depot, so no later import has
# anything left to fetch: sage_categories pins Catlab =0.17.6 and GATlab =0.2.4, and
# a fresh depot resolves them in about four minutes. The runtime check below then
# asserts the property with the network unreachable.
RUN set -eu; \
    jl="$(command -v julia)"; \
    HOME=/root python -c 'import juliapkg; juliapkg.resolve()'; \
    chmod -R a+rX /opt/julia-depot; \
    echo "depot resolved at build time against $("$jl" --version)"

ENV SAGE_BIN=/sage/.venv/bin/sage
ENV PATH=/sage/.venv/bin:$PATH

# What the runtime tag ships, asserted at build time: Sage and its checkout, GAP as
# the only GAP with its matrix-group packages, sage-categories' 26 pinned releases,
# and the documented consumer commands with the network unreachable.
RUN "$SAGE_BIN" docker/runtime-environment-check.py

# ---------------------------------------------------------------------------
# The full image: the runtime plus elan, the Lean packages and every research
# checkout. This is the `develop` tag.
# ---------------------------------------------------------------------------
FROM runtime AS environment


# Lean 4 through elan; install-research-repositories.sh installs the toolchain
# each Lean checkout pins.
ENV ELAN_HOME=/opt/elan
ENV PATH=/opt/elan/bin:$PATH
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --no-modify-path --default-toolchain none \
 && elan --version

# The whole recipe: the virtual environment (already built) and then every research
# checkout, the bridge's julia-deps, sage-categories' GAP releases and the Lean
# packages each checkout pins.
RUN --mount=type=cache,target=/ccache \
    just research-environment-sync && ccache --show-stats

FROM scratch AS lock
COPY --from=environment /sage/uv.lock /uv.lock

# The default (last) stage is the full image: `docker build` with no --target
# produces the `develop` tag, and --target runtime produces the other one.
FROM environment

# Fail the build if any system the image exists to provide is absent. The Lean
# part of the check imports Mathlib from a pinned checkout, which exercises
# docker/provision-lean-packages.sh against whatever this build left in place: a
# full build is the only one that runs it with an empty packages directory.
# This is the full check and it stays on this tag; the runtime tag has its own,
# which covers only what the runtime image ships.
RUN "$SAGE_BIN" docker/research-environment-check.py
