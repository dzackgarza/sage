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
    pandoc graphviz dvipng imagemagick \
    cmake libpcre2-dev cargo rustc ccache rsync binutils-gold \
 && rm -rf /var/lib/apt/lists/*

# The document toolchain the project sites build with (sage#22). Both site builds
# outside the image install it at every run -- research's docs.yml takes quarto from
# quarto-actions/setup and then `apt-get install pdf2svg poppler-utils texlive-full`,
# new-qual-site takes TeX Live's `scheme-full` and pdf2svg -- so the image carries it
# and a site build installs nothing. poppler-utils is here for `pdftoppm`, which the
# figures go through, and nodejs because new-qual-site's own test suite runs `node`.
#
# texlive-full WITH its Recommends, unlike the block above: the point is scheme-full,
# and a partial install diverges the moment a figure reaches for a package nobody
# listed -- research's docs.yml says so in as many words. It is the largest single
# addition this image has taken, about 5 GiB installed, which #9 pays for on every
# pull; that trade is this issue's decision, not this step's.
RUN apt-get update \
 && apt-get install -y texlive-full pdf2svg poppler-utils nodejs unzip xz-utils \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Quarto renders both sites and is not in Debian, so it comes from its release pinned
# by version and by the digest of the .deb, as julia and pcre do. Its own postinst
# links /opt/quarto/bin/quarto into /usr/local/bin, which is on PATH.
RUN set -eu; \
    version=1.11.9; \
    sha256=64078d1623d9ab89da766591f3410a0756f3737a37efb0897c7e84b863bf092a; \
    curl -fsSL -o /tmp/quarto.deb \
        "https://github.com/quarto-dev/quarto-cli/releases/download/v${version}/quarto-${version}-linux-amd64.deb"; \
    echo "$sha256  /tmp/quarto.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y /tmp/quarto.deb; \
    rm -f /tmp/quarto.deb; \
    rm -rf /var/lib/apt/lists/*; \
    test -x /usr/local/bin/quarto; \
    echo "quarto $(quarto --version)"; \
    test "$(quarto --version)" = "${version}"

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

# /usr/local/bin/gap is the image's GAP for anything that resolves it through
# PATH, which Sage does: `sage.interfaces.gap` starts the bare command `gap`, and
# kernel_info() runs it to hash the workspace name.  The image's own PATH finds
# $SAGE_LOCAL/bin/gap first, but a host that runs the unpacked filesystem -- PRoot
# over it, a bare exec, an entrypoint that rebuilds the environment -- inherits
# its own PATH instead, and then there is no `gap` and the interface cannot even
# be imported (sage#19).  A wrapper, not a symlink, for the reason given in the
# file: GAP derives its root paths from the program it was started as.
#
# /usr/bin/gap is the same launcher for the process that has no PATH at all:
# Python's own /bin:/usr/bin fallback is what an emptied environment --
# `env -i`, the probe the environment check runs kernel_info() under --
# resolves `gap` through, and the check reports `FileNotFoundError: 'gap'`
# when nothing is there (sage#24).  The same wrapper, not a distribution GAP:
# a distribution GAP at that path is what the incremental build purges.
COPY --chmod=0755 docker/gap-launcher.sh /usr/local/bin/gap
COPY --chmod=0755 docker/gap-launcher.sh /usr/bin/gap

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

FROM base AS environment

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
    rm /tmp/julia.tar.gz; \
    # Julia finds its system image relative to the binary it was started from, and
    # the entry point this image publishes is the wrapper at /usr/local/bin/julia.
    # Assert the layout here, where it is created, so a tree that cannot be loaded
    # fails the build with a named error instead of surfacing as a Pkg failure
    # hours later: measured in run 42227833648 as
    # `could not load library "/usr/local/bin/../lib/julia/sys.so"`.
    test -x /opt/julia/bin/julia; \
    test -f /opt/julia/lib/julia/sys.so; \
    test "$(/opt/julia/bin/julia --startup-file=no -e 'print(Sys.BINDIR)')" = /opt/julia/bin; \
    echo "julia $(/opt/julia/bin/julia --version) with its sysimage at /opt/julia/lib/julia/sys.so"

# /usr/local/bin/julia is the image's entry point rather than a symlink: it
# adds /opt/julia-depot to whatever JULIA_DEPOT_PATH the caller has, so a
# process whose environment did not come from this image (PRoot over the
# unpacked filesystem, a bare exec) still resolves the bridge's packages.
COPY --chmod=0755 docker/julia-launcher.sh /usr/local/bin/julia

# Package caches must load on both the CI CPU and the host CPU.
# https://docs.julialang.org/en/v1.12/manual/environment-variables/#JULIA_CPU_TARGET
# Two variables, for two mechanisms, and the distinction cost a build each way.
#
# JULIA_BINDIR is Julia's own: it tells a julia *process* where it lives, which is what
# juliapkg's resolve step runs (juliapkg/deps.py copies the environment it is given) and
# what the launcher states for itself.
#
# PYTHON_JULIAPKG_EXE is what makes the load that fails find the right tree. juliapkg
# reads every option from PYTHON_JULIAPKG_<NAME> (juliapkg/state.py:15) and takes
# STATE["override_executable"] from `get_config("exe")` (:51); find_julia.py:45 uses
# that override first, and only without it falls back to shutil.which("julia") (:81) --
# which finds this image's launcher at /usr/local/bin/julia. juliacall then loads
# libjulia into the Python process and, with no bindir stated, takes
# os.path.dirname(exepath) (juliacall :231-232) as the bindir it hands to
# jl_init_with_image (:264-270) -- /usr/local/bin for the launcher, hence
# /usr/local/lib/julia/sys.so. Naming the real binary makes that dirname
# /opt/julia/bin.
#
# Not PYTHON_JULIACALL_BINDIR: juliacall :190-192 turns a stated bindir into exepath,
# and :193-219 then refuses because the matching project is unset -- measured in run
# 75412165bc as "Both PYTHON_JULIACALL_PROJECT and PYTHON_JULIACALL_EXE must be set
# together". Not a symlink either: :231-232 takes the dirname of the path string, which
# a symlink does not change.
ENV JULIA_DEPOT_PATH=/opt/julia-depot: \
    JULIA_CPU_TARGET=generic \
    JULIA_BINDIR=/opt/julia/bin \
    PYTHON_JULIAPKG_EXE=/opt/julia/bin/julia

RUN set -eu; \
    julia --startup-file=no --color=no -e ' \
        using Pkg; \
        Pkg.add(["Oscar", "JSON"]); \
        Pkg.precompile(); \
        import JSON; \
        using Oscar; \
        println("JSON ", pkgversion(JSON), ", Oscar ", Oscar.VERSION_NUMBER, " loaded")'; \
    chmod -R a+rX /opt/julia-depot


ENV SAGE_BIN=/sage/.venv/bin/sage
ENV PATH=/sage/.venv/bin:$PATH


COPY . /sage

# ccache keeps compiler output across image builds; Meson uses it whenever it
# is on PATH. The cache mount is not part of the image, and CI carries it
# between runs, so a source change recompiles only the modules it touches.
ENV CCACHE_DIR=/ccache

# Lean 4 through elan. The image carries ONE shared Lean project -- mathlib4 at the
# head of its master branch, on the toolchain that revision pins, with its closure
# built inside it -- and install-research-repositories.sh provisions it and binds
# every Lean checkout under /repos to it (docker/provision-lean-packages.sh). No
# revision is written here: every build resolves the head, and records it.
ENV ELAN_HOME=/opt/elan
ENV PATH=/opt/elan/bin:$PATH
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --no-modify-path --default-toolchain none \
 && elan --version

# The Mathlib head this build carries. The workflow reads it when the build starts
# and passes it here, which is what makes the head a build input: unchanged, the
# steps below are a cache hit and their layer is reused; moved, they run and rebuild
# the closure. Without it the provisioning script reads the head itself.
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

# Resolve what the installed distributions require into the depot, so no later
# import has anything left to fetch: sage_categories pins Catlab =0.17.6 and GATlab
# =0.2.4, and a fresh depot resolves them in about four minutes. This runs HERE, and
# with the Sage venv's own interpreter, because juliapkg is a dependency of this
# environment: it arrives with the sync above and is what `import sage_categories`
# will use. Resolving earlier ran the uv-managed python, which has no juliapkg --
# measured: `ModuleNotFoundError: No module named 'juliapkg'` in run 42220489790.
RUN set -eu; \
    jl="$(command -v julia)"; \
    HOME=/root /sage/.venv/bin/python -c 'import juliapkg; juliapkg.resolve()'; \
    chmod -R a+rX /opt/julia-depot; \
    echo "depot resolved at build time against $("$jl" --version)"

FROM scratch AS lock
COPY --from=environment /sage/uv.lock /uv.lock

FROM environment

# Fail the build if any system the image exists to provide is absent. The Lean part
# asserts the image's own shared project -- the recorded revision is the one checked
# out, the toolchain is the one that revision pins, the closure and Mathlib's olean
# are built in it, and `import Mathlib` elaborates there -- and says nothing about
# whether a checkout under /repos agrees with it: that is each Lean repository's own
# CI (lean-categories#118, lean-cas-dsl#90).
RUN "$SAGE_BIN" docker/research-environment-check.py
