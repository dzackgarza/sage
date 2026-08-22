# syntax=docker/dockerfile:1

# The research Sage environment, built once and consumed everywhere.
#
# Every repository that writes Sage against this fork needs the same
# interpreter and the same composed environment. Building it per repository, or
# per CI run, is the same work repeated; this image is that work done once.
#
# SAGE_ROOT is baked in at configure time, so the tree lives at /sage here and
# consumers restore it to /sage rather than relocating it.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && rm -rf /var/lib/apt/lists/*

COPY . /sage
WORKDIR /sage

# Sage's own package metadata names what the build links against: every
# build/pkgs/*/distros/debian.txt, resolved by Sage's own scripts. This is the
# bootstrap from src/doc/en/installation/source.rst, not a hand-kept list, so
# it stays correct as the dependency set moves.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      $(build/bin/sage-get-system-packages debian $(build/bin/sage-package list :standard:)) \
 && rm -rf /var/lib/apt/lists/*

# uv supplies the managed 3.14 interpreter this fork requires; just runs the
# build recipe the desk uses, so the image and the desk build the same way.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -LsSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
ENV PATH="/root/.local/bin:${PATH}"

RUN just research-environment-sync

ENV SAGE_BIN=/sage/.venv/bin/sage

RUN "$SAGE_BIN" -c "import sage.all; print(sage.version.version)"
