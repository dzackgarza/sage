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
  `bwrap-userns-restrict` profile permits bubblewrap, and where that profile is
  not loaded the restriction is the host administrator's to change. This
  script and the image workflow never change a sysctl or an AppArmor profile;
  such a host is reported as unsupported, and the image runs there through
  Docker or as a CI job container instead.

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

## Julia and the bridge

`/usr/local/bin/julia` is a launcher, not a symlink: it adds `/opt/julia-depot`
to whatever `JULIA_DEPOT_PATH` the caller has. The image declares that depot in
its own environment and a container runtime applies it; a host that runs the
unpacked filesystem — PRoot, a bare exec, an entrypoint that rebuilds the
environment — does not, and `sage_julia_bridge` then stops at
`julia_bridge.jl:2` with `Package JSON ... is required but does not seem
installed`. The image instantiates the bridge's worker project
(`/repos/sage-julia-bridge/src/sage_julia_bridge/julia_env`) into that depot, so
JSON and Oscar come from the image and no consumer installs them for itself.
A bridge checkout changed inside the persistent volume brings its own
`Project.toml`/`Manifest.toml`; its `just julia-deps` instantiates that revision
into the writable depot.

## Provisioning an image that is already unpacked

An image unpacked before a provisioning change reaches the same state without
being rebuilt, by running the repair the image build runs:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --bind docker/provision-lean-packages.sh:/opt/provision-lean-packages.sh \
  --env ELAN_HOME=/opt/elan \
  -- /bin/bash /opt/provision-lean-packages.sh /repos
```

`ELAN_HOME` is the only environment it needs beyond the runner's `PATH`, and it
speaks for itself in the working directory: it walks `/repos` itself. It links
or adopts the Lake packages each manifest pins, retrieves Mathlib's official
cache only if the image does not already carry it, builds the packages Mathlib
imports, and stops unless Mathlib is loadable. No toolchain is added, no package
is cloned twice, and no consumer checkout is edited.

Lake fixes a project's packages directory in its lakefile and records it in the
manifest — `-K packagesDir=` is ignored, and a lakefile whose `packagesDir`
disagrees with its manifest is rejected as out of date — so two checkouts that
pin one package at different revisions cannot both be served by that directory.
The checkouts keep their pins. The shared packages directory carries the
packages they agree on; `/opt/lake-views/index.json` records, per checkout,
which packages its manifest pins at a revision the shared directory does not
hold, each naming the content-addressed checkout under `/opt/lake-packages`.
A run mounts exactly those over the packages directory for that invocation:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --lean-view /repos/lean-cas-dsl-leaf-contracts \
  -- /bin/sh -c 'cd /repos/lean-cas-dsl-leaf-contracts && lake env lean /tmp/file.lean'
```

Nothing global is rewritten, so two checkouts resolve different revisions of one
package at the same time in separate mount namespaces. A checkout the shared
directory fully carries needs no flag.
Under PRoot the same mount is one `-b` per override, both paths taken from the
index: `-b <rootfs>/opt/lake-packages/<name>@<revision>:<packagesDir>/<name>`.

Readback, from the pinned project:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --env ELAN_HOME=/opt/elan \
  -- /bin/sh -c 'cd /repos/lean-categories && printf "import Mathlib\n#check (Nat.add_comm : ∀ a b : Nat, a + b = b + a)\n" > /tmp/mathlib-import.lean && lake env lean /tmp/mathlib-import.lean'
```

## Deploying the Bliss repair into an existing copy

The published image links its system libbliss without the ABI its headers
describe, so `sage.graphs.bliss` corrupts the heap and `canonical_label()`
segfaults (`Graph([[0,1]]).canonical_label(edge_labels=True)`, and every other
canonical label, and `automorphism_group()`). The repair is checked in
`src/sage/graphs/meson.build` and `bliss_cpp/bliss_find_automorphisms.h`; while
publication is held, an existing unpacked copy can carry it without being
rebuilt, by applying that same patch and rebuilding only the module it touches:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --bind results/apply-bliss-repair.sh:/opt/apply-bliss-repair.sh \
  --bind results/bliss-repair.patch:/opt/bliss-repair.patch \
  -- /bin/bash /opt/apply-bliss-repair.sh /opt/bliss-repair.patch
```

It checks that the copy is the published revision with the two files untouched,
applies the patch, runs Ninja and Meson install in `/sage/builddir` (the image's
own build system, so the build files are regenerated from the patched Meson),
runs the graph and automorphism smoke tests, and records the base revision,
patch and module digests in `/opt/bliss-repair.json`. A copy that fails the
smoke tests gets its previous module and source back. Nothing is published and
the image is unchanged: the copy is repaired, not a new image. Re-running it is
a no-op once the stamp matches.

## Checking a change to the image

```sh
docker/sage-image.py check
```

`docker/research-environment-check.py` runs inside the image at build time and
verifies that every system the image exists to provide is present and works,
including the environment's own interpreter and both canonical-label backends.
A change that removes a library, breaks a link, or ships a build of Sage that
crashes is meant to fail the image build here rather than a consumer's job.
