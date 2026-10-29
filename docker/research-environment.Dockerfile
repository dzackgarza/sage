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
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

# python3 is needed here, not later: build/bin/sage-package is a Python
# script, and it is what reports which packages to install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git python3 rustc cargo \
 && rm -rf /var/lib/apt/lists/*

COPY . /sage
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
# BRiAl and GAP's Polenta package are the Sage metadata names Debian trixie
# does not ship. BRiAl's Meson feature is `auto`, so sage.rings.polynomial.pbori
# is absent here; Polenta is installed by Sage's own GAP spkg (`pkg/polenta`).
# Exclude only these two known names so any other missing package still fails.
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

# uv supplies the managed 3.14 interpreter this fork requires; just runs the
# build recipe the desk uses, so the image and the desk build the same way.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -LsSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
ENV PATH="/root/.local/bin:${PATH}"

RUN git config --global url."https://github.com/".insteadOf "git@github.com:"
RUN just research-environment-sync

# The Sage build installs Maxima and its CL-INFO indexes into the same venv
# prefix. Keep the runtime prefix independent of the Maxima version and the
# Meson external-project staging directory.
ENV MAXIMA_PREFIX=/sage/.venv
# Meson's Maxima external project installs the same compiled ECL side module
# from its staging tree into this versioned ECL directory in the runtime venv.
# Point Sage at the installed artifact so the path is independent of Maxima's
# source version and the external project's staging-prefix layout.
ENV MAXIMA_FAS=/sage/.venv/lib/ecl-26.5.5/maxima.fas
ENV SAGE_BIN=/sage/.venv/bin/sage

RUN "$SAGE_BIN" -c "import sage.all; print(sage.version.version)"

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

ENV JULIA_DEPOT_PATH=/opt/julia-depot:

RUN set -eu; \
    julia --startup-file=no --color=no -e ' \
        using Pkg; \
        Pkg.add(["Oscar", "JSON"]); \
        Pkg.precompile(); \
        import JSON; \
        using Oscar; \
        println("JSON ", pkgversion(JSON), ", Oscar ", Oscar.VERSION_NUMBER, " loaded")'; \
    chmod -R a+rX /opt/julia-depot
