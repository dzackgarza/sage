# syntax=docker/dockerfile:1

# The research Sage environment, built once and consumed everywhere.
#
# Every repository that writes Sage against this fork needs the same
# interpreter and the same composed environment. Building it per repository, or
# per CI run, is the same work repeated; this image is that work done once.
#
# SAGE_ROOT is baked in at configure time, so the tree lives at /sage here and
# consumers restore it to /sage rather than relocating it.

# Debian, because Sage's system-package metadata is Debian's: every
# build/pkgs/*/distros/debian.txt names a package Debian ships. Ubuntu 24.04
# is missing five of them -- maxima-sage and HiGHS among them -- so the same
# metadata that resolves completely here resolves partially there.
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

# python3 is needed here, not later: build/bin/sage-package is a Python
# script, and it is what reports which packages to install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git python3 \
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
# BRiAl is the one name Sage lists that Debian no longer ships; it is excluded
# by name so that any *other* name failing to resolve still fails the build.
# Its meson feature is `auto`, so sage.rings.polynomial.pbori -- Boolean
# polynomial rings -- is absent from this image and present on a desk whose
# distribution still packages BRiAl.
RUN set -eu; \
    packages="$(build/bin/sage-get-system-packages debian $(build/bin/sage-package list :standard:) \
        | tr ' ' '\n' | grep -vxE 'libbrial-dev|libbrial-groebner-dev' | tr '\n' ' ')"; \
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

RUN just research-environment-sync

ENV SAGE_BIN=/sage/.venv/bin/sage

RUN "$SAGE_BIN" -c "import sage.all; print(sage.version.version)"
