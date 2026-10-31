# The research Sage environment

`ghcr.io/dzackgarza/sage:develop` is the environment this fork's consumers run
Sage in: this tree built with CPython 3.14, GAP, Julia with Oscar/Hecke,
Macaulay2, Singular, Normaliz, polymake, CoxIter and Lean/elan.  It is one
image, built by `.github/workflows/research-environment-image.yml` from
`docker/research-environment.Dockerfile`, published for linux/amd64 only.

The fork's default branch is `develop`; there is no `main`.  The image is
published from `develop`, and `org.opencontainers.image.revision` in its config
names the commit it was built from.

## What the image is pinned to

```sh
docker/sage-image.py info        # index, manifest, config, revision of the cache
```

`info` and `fetch` print the digests a consumer can pin: the OCI index, the
linux/amd64 manifest, and the config that carries the source revision.  A
consumer that records the manifest digest is unaffected by later rebuilds; a
consumer that pulls the tag follows `develop`.

## Invocations

### A workstation or CI runner with Docker

```sh
docker run --rm -it ghcr.io/dzackgarza/sage:develop bash
docker run --rm ghcr.io/dzackgarza/sage:develop python -c \
  'from sage.all import QQ, matrix; assert matrix(QQ, [[2, 1], [1, 2]]).det() == 3'
```

In GitHub Actions, use it as the job container, as
`.github/workflows/research-image-consumer.yml` does:

```yaml
jobs:
  qc:
    runs-on: ubuntu-latest
    container: ghcr.io/dzackgarza/sage:develop
    env:
      SAGE_BIN: /sage/.venv/bin/sage
```

### A host without Docker, chroot or PRoot

A container image is a filesystem and a process.  `docker/sage-image.py`
fetches the image from the registry without a daemon, verifies the digest of
every layer, unpacks it into a cache directory, and runs commands in that tree
with [bubblewrap](https://github.com/containers/bubblewrap)'s unprivileged user
namespaces — no root, no chroot, no ptrace, no container runtime:

```sh
# once per image: the current develop, then the same image pinned
docker/sage-image.py fetch
docker/sage-image.py fetch --digest sha256:<the manifest it printed>

# the same interpreter, Sage build and libraries the image ships
docker/sage-image.py run -- sage -c 'print(ZZ(2)**10)'
docker/sage-image.py run -- /sage/.venv/bin/python -m pytest tests/

# the image's own environment check, which its build runs too
docker/sage-image.py check
```

The current directory is mounted at `/work`, which is the working directory
inside the image, so a consumer checkout is visible to its tests.  The process
starts with the environment the image declares for itself — `PATH`,
`JULIA_DEPOT_PATH`, `SAGE_BIN` and the rest — and not with the host's, so a
host `PYTHONPATH`, `LD_LIBRARY_PATH` or `XDG_*` cannot leak in.  Use
`--bind SRC[:DEST]` for more paths and `--env KEY=VALUE` for variables of your
own:

```sh
docker/sage-image.py run --bind ~/research/src:/repos/research/src \
  --env PYTHONPATH=/repos/research/src -- sage -c 'import dzack_research'
```

Requirements, both checked before anything runs:

* `bubblewrap` installed (`apt install bubblewrap`, `dnf install bubblewrap`);
* unprivileged user namespaces permitted by the kernel
  (`/proc/sys/kernel/unprivileged_userns_clone` is `1`, or the distribution's
  equivalent). On Ubuntu 24.04 and later AppArmor restricts them: the packaged
  `bwrap-userns-restrict` profile permits bubblewrap, and on a host without
  that profile `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`
  permits them.

`run` stops with the missing piece named.  The cache lives in
`$XDG_CACHE_HOME/sage-image` and is reused only when its recorded manifest
matches the requested one, so a pinned digest and a moved tag cannot be
confused.

Where neither Docker nor unprivileged user namespaces are available, run the
job in the image on a CI runner, or on a machine that has a container runtime.
There is no third supported path.

### What is not an environment

A distribution Sage — on a host without a container runtime, an older Sage with
an older Python — is not this environment.  Its import failures, version
mismatches and missing modules describe the host's packaging, not the libraries
in the image, and cost real defects their diagnosis: a `canonical_label()`
segmentation fault in the image, for example, was reported as a Python 3.14
library defect after a fallback to a Sage 10.8 host, while the image's actual
fault was its own linkage against the distribution's `libbliss` (fixed in
"link bliss with the ABI its system library was built with").

Provisioning is owned here, once: consumers call `docker/sage-image.py` or use
the image as their job container, and do not carry their own copy of a fetch,
unpack or launcher script.

## Checking a change to the image

```sh
docker/sage-image.py check
```

`docker/research-environment-check.py` runs inside the image at build time and
verifies that every system the image exists to provide is present and works,
including the environment's own interpreter and both canonical-label backends.
A change that removes a library, breaks a link, or ships a build of Sage that
crashes is meant to fail the image build here rather than a consumer's job.
