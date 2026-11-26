# The research Sage environment

`ghcr.io/dzackgarza/sage:develop` is the environment this fork's consumers run
Sage in: this tree built with CPython 3.14, GAP, Julia with Oscar/Hecke,
Macaulay2, Singular, Normaliz, polymake, CoxIter, Lean/elan, and the document
toolchain the project sites build with: quarto, a full TeX Live, pdf2svg,
poppler-utils and node.  JupyterLab runs in it with the `sagemath`,
`julia` (IJulia, on the image's Oscar depot) and `python3` kernels, whose
specs are under `/sage/.venv/share/jupyter/kernels`; the build check executes
a cell in the Sage and Julia kernels.  It is one image, built by `.github/workflows/research-environment-image.yml` from
`docker/research-environment.Dockerfile`, published for linux/amd64 only.

The fork's default branch is `develop`; there is no `main`.  The image is
published from `develop`, and `org.opencontainers.image.revision` in its config
names the commit it was built from.

## What the image is pinned to

`info` prints the index, the manifest, the config and the revision of the cache:

```sh
docker/sage-image.py info
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
namespaces — no root, no chroot, no ptrace, no container runtime.

`fetch` runs once per image: the current develop, then the same image pinned:

```sh
docker/sage-image.py fetch
docker/sage-image.py fetch --digest sha256:<the manifest it printed>
```

`run` uses the same interpreter, Sage build and libraries that the image ships:

```sh
docker/sage-image.py run -- sage -c 'print(ZZ(2)**10)'
docker/sage-image.py run -- /sage/.venv/bin/python -m pytest tests/
```

`check` runs the environment check of the image, which its build runs too:

```sh
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

`fetch` unpacks layers the image is published with, and those are zstd-compressed
(the build passes `compression=zstd`): it needs the `zstd` binary
(`apt install zstd`) unless the host's Python is 3.14 or later, whose
`compression.zstd` reads them. `run` and `check` need neither.

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

## One image, every component

There is one tag, `ghcr.io/dzackgarza/sage:develop`, and it carries every component
the environment is: Sage and its checkout, GAP with its packages, Julia with its
resolved depot, the one shared Lean project and the research checkouts, and the
document toolchain the two site builds outside this repository install for
themselves at every run — quarto, `texlive-full`, pdf2svg, poppler-utils and node
(`#22`). That last component is the largest addition the image has taken, about
5 GiB, and a site build now installs nothing. `luahyperbolic.sty` is the one
package outside `texlive-full`: it comes from a named mirror's copy of the CTAN
archive, checked against its SHA-256, because `mirrors.ctan.org` redirects each
request to a mirror of its own choosing and one of them serves an incomplete
certificate chain (`#38`).

The research checkouts are at the head of each repository's main branch, not
at the commit `uv.lock` holds (`#24`): every build resolves them at build
time. The image records the commit of each repository it installed in
`/sage/.research-revisions` — one `<name> <commit>` per line — so a consumer
can read, in the image, the revision it is running.

`docker/research-repositories.txt` names, one GitHub URL per line, each
repository the image checks out under `/repos`. Each repository of
`github.com/dzackgarza` that `uv.lock` sources is in that list, so the image
takes it at the head of its main branch and installs its packages editable from
the checkout; the image check fails on a source of that owner that the list does
not name. A git source of another owner is a dependency rather than a checkout:
it is installed from its URL, no build records a head for it, and the image
check holds it to the commit the lock pins (`#37`).

The `consumer-mathematics` job of the image workflow holds the image's checkouts
of `sage-indefinite-port` and `sage-extensions` to the heads in
`/sage/.research-revisions`. It then reads the checkout that each import comes
from: the job installs its own `sage-extensions` checkout editable, so that
package has two trees, the image's copy and the job's, and neither stands in for
the other. An editable install's `direct_url.json` has no `vcs_info`, so its
`commit_id` reads `None`; the job prints it beside the checkout revision. The
generator computation then runs with `PYTHONPATH` set to the image's checkouts:
in run 42379122786 the job's editable install shadowed the image's provider.
`git rev-parse` there states `safe.directory` for the path it reads, because the
runner creates the workspace `.git` with another owner.

A research checkout's suite runs with the test tooling that repository declares,
and the image is where that declaration is read. Each repository of
`docker/research-repositories.txt` states its own in its `pyproject.toml` —
sage-extensions' `[dependency-groups] dev` is where its pytest plugins are — and
`docker/research-test-dependencies.py` derives the set from those declarations,
writing it into `pyproject.toml`'s `[dependency-groups] research-environment-tests`.
`uv.lock` then pins it like any other package of the environment and
`research-environment-venv` syncs it, `--frozen`. A repository's `test` group or
`test` extra is taken where it declares one, and its `dev` group otherwise, so a
linter a project keeps apart from its suite stays out of the image. The lock is
the environment: a checkout that declares a plugin the lock does not carry yet is
a `note:` in the image check and a relock to repair
(`docker/research-test-dependencies.py --write`, then `uv lock`), not a reason to
stop publishing — while a plugin the group carries and pytest does not register
is a build failure, because that is `just test` exiting 4 on an unrecognized
argument before collection (`#37`).

A published tag with
fewer components is not a smaller environment, it is a different one, and consumers
written against this environment cannot be relied on to say which they need — the
reason `#9` was first answered with a reduced tag and then corrected: importing
`sage_categories` constructs functor object images through Catlab, which imports
`juliacall`, so even a Sage-and-GAP consumer loads Julia.

A consumer job's pull is therefore the whole image, and `#9` is about making that
pull cheap without removing anything: layer compression (zstd, which decompresses
several times faster than gzip), a layer layout in which a source push changes only
small layers (which is what `docker/research-environment-incremental.Dockerfile`
does), and the runner's pull concurrency. Each is measured on the research README
example job's "Initialize containers" time, against a `:develop` of identical
content; the numbers belong in `results/`, not here.

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
speaks for itself in the working directory: it walks `/repos` itself. It moves the
shared Lean project to the head of mathlib4 master — as a build does — or keeps the
revision `MATHLIB_REVISION` names, rebuilds its closure only if it moved, links each
checkout's Mathlib pins to it, and stops unless Mathlib builds. No Mathlib revision
is cloned twice. In each checkout it writes `lake-manifest.json` and
`lean-toolchain`, and the links of its packages directory.

`docker/provision-lean-packages.sh [REPOSITORIES_ROOT] [--dry-run]` reads these
variables: `MATHLIB_REVISION` (the head that the build resolved; without it the
script reads the head of master), `MATHLIB_PROJECT` (default `/opt/mathlib`),
`MATHLIB_RECORD` (default `/opt/lean-image.json`), `MATHLIB_REPOSITORY` (default
`https://github.com/leanprover-community/mathlib4`) and `PYTHON` (default
`python3`). Without `elan` on `PATH` or `ELAN_HOME` set, it uses `/opt/elan`, so a
runner that does not apply the environment of the image (PRoot, a bare exec) finds
the toolchains. When the head moved, the script removes the whole `.lake` of the
project, because a Lean release refuses the oleans of another release, and builds
the new closure one time. It builds each git package of the manifest by name, also
a package that `Mathlib` does not import (`Cli`), so that each package has a build
directory, which the check asserts.

**One shared Lean project, always on the latest Mathlib** (sage#13). The image carries
exactly one Lean project — `mathlib4` at the head of `leanprover-community/mathlib4`
master — on the toolchain that revision pins, with its whole dependency closure
built inside it and Mathlib's oleans taken from the official cache.

Every build moves to that head, incremental builds included. The workflow reads the
head when the build starts and passes it into the build
(`MATHLIB_REVISION`), which makes it a build
input: when the head has not moved, the steps that provision the project are a cache
hit and the layer holding it is reused; when it has moved, they run and rebuild its
closure. `docker/provision-lean-packages.sh` also compares the head with the record
the image already carries, so a build that passes this way still writes nothing when
the two agree. Provisioning installs the toolchain that revision pins as elan's
default, and records the revision and the toolchain in `/opt/lean-image.json`:

```json
{
  "project": "/opt/mathlib",
  "repository": "https://github.com/leanprover-community/mathlib4",
  "revision": "…",
  "master_head_at_resolution": "…",
  "toolchain": "leanprover/lean4:v4.36.0-rc2",
  "cache": "lake exe cache get (official Mathlib cache)",
  "resolved": "…"
}
```

Every Lean checkout under `/repos` resolves mathlib and its dependencies from that
one project. Lake resolves a package's dependencies through its manifest — the
Lean Language Reference's Lake chapter: "a manifest tracks the specific versions
of other packages that are used in a package … Before building, Lake
synchronizes the local copy of each dependency with the version specified in the
manifest" — and materializes them in the packages directory the lakefile
declares ("packagesDir: The directory to which Lake should download remote
dependencies"). Provisioning therefore sets each checkout's manifest entries for
mathlib and every package of the shared project's manifest to the shared
project's revisions, and links its packages directory to the project's built
copies: the project itself for `mathlib`,
`/opt/mathlib/.lake/packages/<name>` for Mathlib's closure. It also writes the
`lean-toolchain` of the shared project into the checkout, as Mathlib's guide for a
dependent project does ("Using mathlib4 as a dependency": `curl
https://raw.githubusercontent.com/leanprover-community/mathlib4/master/lean-toolchain
-o lean-toolchain`). elan runs the release that the `lean-toolchain` of the
checkout names, and a Lean release refuses an `.olean` that another release wrote:
"failed to read file '/opt/mathlib/.lake/build/lib/lean/Mathlib.olean',
incompatible header" (sage#42). A package the
checkout needs that the shared project does not carry keeps the revision the
checkout pinned, and Lake clones it when the checkout is next built.

A checkout that does not build against the shared Mathlib fails the image's
check loudly, naming the checkout and the revision it carries. Repairing such a
checkout is the owning repository's own work (lean-categories#118,
lean-cas-dsl#90), not the image's.

Readback, from the shared project and from a checkout that follows it:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --env ELAN_HOME=/opt/elan \
  -- /bin/sh -c 'cd /opt/mathlib && lake env lean --version && lake build Mathlib'

python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --env ELAN_HOME=/opt/elan \
  -- /bin/sh -c 'cd /repos/lean-categories && printf "import Mathlib\n#check (Nat.add_comm : ∀ a b : Nat, a + b = b + a)\n" > /tmp/mathlib-import.lean && lake env lean /tmp/mathlib-import.lean'
```

An unpacked image reaches the same state by running the same script; `--dry-run`
prints what it would do without touching anything. Pass the revision the image
already carries to keep it where it is — without it the script moves the image to the
head of master, as a build does:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --bind docker/provision-lean-packages.sh:/opt/provision-lean-packages.sh \
  --env ELAN_HOME=/opt/elan \
  --env MATHLIB_REVISION="$(cat ~/sage-image/rootfs/opt/lean-image.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["revision"])')" \
  -- /bin/bash /opt/provision-lean-packages.sh /repos --dry-run
```

An image published before this layout carries `mathlib@<revision>` checkouts under
`/opt/lake-packages` and `/opt/lake-views`; both are gone in this one, and a script
that still names them is reading an older image.

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

It checks that the copy is the published revision, that every file the patches
touch is either untouched or modified exactly by patches this copy already
carries, applies the ones it does not carry in the order given, runs Ninja and
Meson install in `/sage/builddir` (the image's own build system, so the build
files are regenerated from the patched Meson), runs the graph and automorphism
smoke tests, and records the base revision, every patch digest and the module
digest in `/opt/bliss-repair.json`. A copy that fails the smoke tests gets its
previous module and source back. Nothing is published and the image is
unchanged: the copy is repaired, not a new image. Re-running it is a no-op once
the stamp matches.

Two patches exist because the first one's Meson fallback chain was wrong: under
`-Dbliss=enabled` (or `auto_features=enabled`) a missing `libbliss-cxx` aborted
the configure instead of falling through. The second patch fixes that and keeps
`disabled`/`auto`/`enabled` semantics; a copy deployed with the first alone is
correct for this image, which has `libbliss-cxx`, but is not evidence that the
fallback works elsewhere.

## Shared hosts: one writer per unpacked copy

On a host where several projects run as the same user, `$HOME` — and therefore
`$HOME/sage-image/rootfs` — is one physical tree, not one per project. Only one
project should write to it: the one that provisioned it. Everyone else reads the
stamps and runs readback, and takes the artifacts (`provision-lean-packages.sh`,
`apply-bliss-repair.sh` with its patches) if they need to deploy into a copy of
their own; two projects running builds into one tree race on the same
`.lake/build`, the shared Lean project and site-packages, and produce duplicate
builds.

Readback, without writing: `bliss-repair.json` gives the base revision and the
digests of the patch and the module, and `lean-image.json` gives the Mathlib
revision and the toolchain that the image carries.

```sh
cat ~/sage-image/rootfs/opt/bliss-repair.json
cat ~/sage-image/rootfs/opt/lean-image.json
```

What can be observed of the host: one RAM figure and no swap (`free`), one set
of CPUs (`nproc`), and a cgroup path per project and session — this project's is
`/system.slice/nucleus.service/project-<id>/p<pid>`. What cannot: whether an
ancestor of those cgroups imposes a memory limit. `memory.max` and
`memory.events` are not readable from inside the namespace, so neither the
effective limit nor whether an earlier kill was an OOM is known here. Distinct
per-project paths are not evidence that no shared ancestor limit exists.

Because the limit is unknown, treat long builds as competing for one machine:
run them one at a time across projects, bound them, and keep a copy of their
logs. That guidance is about scheduling, not about a limit that has been
measured.

## Published image and what was verified

`ghcr.io/dzackgarza/sage:develop` built from `develop` at
`a20baff9109a3afa5b7cffb8e0dca6103eae8bc8`
([producer run 41281611312](https://github.com/dzackgarza/sage/actions/runs/41281611312),
built 2026-11-01 06:54:39 UTC):

| object | digest |
| --- | --- |
| OCI index | `sha256:4542f7bfb6051b82cadd74825a928bfb03a01cdcfff069d4d66b38fc06e644fb` |
| linux/amd64 manifest | `sha256:7e0fb939cf32170495c75c47f1292ed9cde1b270b15d6e652c2e95f79d37217c` |
| config | `sha256:028d7710055aeea357790fd5a3c983f349ae6681c7119cd3123c9bdad267d8e8` |

`org.opencontainers.image.revision` is `a20baff9109a…`. Pin the manifest digest;
the tag follows `develop`.

Scope of what these runs establish, and what they do not:

* the image build ran `docker/research-environment-check.py` and passed — every
  system feature, the research checkouts, the Maxima prefix, both
  canonical-label backends, the port/sage-extensions pair with its isometry and
  group checks, the bridge's `import JSON` without a depot path in the
  environment, and `import Mathlib` from a pinned checkout;
* a fresh hosted runner pulled the amd64 manifest by digest and passed the
  consumer smoke — container initialisation and exact arithmetic with
  `sys.prefix == /sage/.venv`
  ([run 41282864265](https://github.com/dzackgarza/sage/actions/runs/41282864265),
  finished 2026-11-01 07:09:15 UTC);
* **not** established by CI: the `no-runtime` job's fetch-and-check step, which
  every hosted runner so far has skipped because it does not permit
  unprivileged user namespaces — the probe runs, the step is skipped by policy,
  and the job reports success without executing it. `consumer-acceptance` is
  skipped on `develop` by its own condition. When it runs, its two steps are the
  statement a consumer makes: it constructs T_Co and computes its O(T_Co) generators
  through `sage_extensions` and fails unless that returns, printing the installed
  revisions of `sage-indefinite-port` and `sage-extensions` (sage#14); and it runs
  sage-extensions' `test_isotropic_line_orbits_of_small_indefinite_lattices.sage`
  from the installed checkout, which is the observation that the published counts
  reproduce inside the published image rather than on a PYTHONPATH binding. No port or spinor acceptance suite
  was run against this digest.

The Maxima regression is exercised by the reconfigure path in these runs, not
only by a fresh build. Both runs below are incremental builds on the same base
image (`develop@sha256:1b9628b4…`), both reconfigure the tree
(`[0/1] Regenerating build files`, with the Maxima `.fas` already loadable, so
the system-ECL branch is taken): 41280147369 predates the fix and the check
failed on `load(linearalgebra)` with an empty prefix; 41281611312 carries the
fix and its check layer completed in 90 s. The pair is the control and the
result for that branch.

## Checking a change to the image

## Run timings and consumer test reports

A timing question about an image build or a consumer run is answered from two records, and
neither is written by this repository: the runner keeps the first, and the workflow uploads
the second.

**Step wall times** are the runner's own, per job and per step, from the jobs API. Nothing in
the workflow measures them:

```sh
gh api repos/dzackgarza/sage/actions/runs/<run>/jobs \
  --jq '.jobs[]|{name, steps: [.steps[]|{name, started_at, completed_at, conclusion}]}'
```

Each step carries `started_at`, `completed_at` and `conclusion`; a skipped step has null
timestamps and a skipped job has no entry in the run. The record lives as long as the run
does, and reading it needs no more than `actions: read`.

**Consumer test reports** are artifacts of `.github/workflows/research-environment-image.yml`,
named `consumer-report-<job>` for each of its consumer jobs — `consumer-mathematics`,
`consumer-certify`, `consumer-records`, `consumer-contracts`, `consumer-chamber` — uploaded
with `if: always()`, so a failing job's record survives it, and kept 90 days
(`retention-days: 90`).

Each holds the `tests/.report/` of both checkouts a job may run pytest in: the image's
`/repos/sage-extensions` and the job's own checkout of `sage-extensions`.

| file | what it answers |
|---|---|
| `run.jsonl` | pytest's report log: one event per test, with its start time and its duration |
| `junit.xml` | the JUnit file: per-test `time`, and the suite's totals |
| `pytest.log` | the run's log at DEBUG, when the consumer's own options wrote it |

The two invocations that pass `-o addopts=` — the isotropic-line-orbit suite and
lattice-database's owner contracts — name `--junit-xml` and `--report-log` themselves, because
`-o addopts=` is what switches off the consumer's options that write them; the
isotropic-line-orbit run writes `junit-isotropic-line-orbits.xml` and
`run-isotropic-line-orbits.jsonl`, so the record of the `just test` step beside it is not
overwritten. A job that ran no pytest has an empty folder and uploads no artifact, which the
job's log states as a warning. This downloads the report folder of one job:

```sh
gh run download <run> -n consumer-report-consumer-contracts
```

## Why the image workflow steps are as they are

`.github/workflows/research-environment-image.yml` keeps no comments. The reasons
for its steps are here, keyed by step name.

| Step | Reason |
| --- | --- |
| Check out the complete Sage build context | `/sage` is the working checkout of the fork in the image: full history, contents fetched on demand (`fetch-depth: 0`, `filter: blob:none`). `.git` goes into the image, so `persist-credentials: false` keeps the token out of its config. |
| Build and publish the selected Sage image | The output is zstd with OCI media types, because the schema 2 of Docker has no zstd layer type. `force-compression` recompresses the layers that the registry cache serves, so a build whose steps are cache hits republishes them as zstd and does not reuse their gzip blobs. The runner daemon (Docker 28, legacy overlay2 store) accepts each `application/vnd.oci.image.*` layer type and decompresses zstd by magic number (`archive.DecompressStream`). One 11.4 GiB layer dominates the pull, and zstd transfers less and decompresses faster than gzip. |
| Run sage-extensions' own `just test` on the checkout the image installed | The recipe reads the QC plugins and `sage.just` from `~/ai-review-ci`; the job links its checkout of that repository there. |
| Construct T_Co and compute its O(T_Co) generators | See the `consumer-mathematics` paragraph above. T_Co = ⟨2⟩ ⊕ U(2) ⊕ E8(2): rank 11, determinant −2048, signature (2, 9). |
| Run sage-extensions' isotropic-line-orbit suite, and Run lattice-database's owner contracts | `-o addopts=` drops the consumer's own `--junit-xml` and `--report-log` (sage#40), so the step names them again, in the report folder that the job uploads, under names that the `just test` step does not use. |
| Certify lattice-database card 6JRR | `--root` is necessary: the CLI root defaults to the working directory, which is the sage-extensions checkout of the job, and there `corpus.load` does not find `families.yaml` (run 42362483952: `FileNotFoundError`, exit 1). The corpus is the lattice-database checkout. |
| Reproduce the stage-1 research records, and Reproduce the stage-1 known-family records | `coble_I18_vinberg-chamber` is the stage-2 record: Vinberg's algorithm on I_{1,8} with candidates k_0 ≥ 1, nine walls, and its printed Gram matrix is the comparison target. The step compares the whole body after the provenance block. Two forms of elapsed time are removed before the comparison and printed as diagnostics: a trailing `(152 s)`, and prose such as `materialised in 29.8s` or `built in 295 s` (sage#16; run 42362483952 on `coble_isotropic_orbits`). Each other character is compared, and a changed mathematical value fails the step with its diff. |
| Read the I_{1,8} chamber with CoxIter | `set -e` is necessary: the acceptance is a Python assertion, and without it a failed comparison falls through and the step stays green. CoxIter reads a graph file whose first line is the vertex count, then one `<a> <b> <order>` per edge. A research record is not that format: in run 42362483952 CoxIter read the digits of the first root line as a vertex count and reported an eight-vertex simplex. The step builds the graph from the `walls: 9` line and the `edges (i, j, label)` list of the record. The verdict of the engine (cocompactness, covolume, characteristic) is evidence, not a gate, so that call may exit non-zero. The acceptance is the reading: the Coxeter matrix that `-pcm` prints (m_ij = 2 where there is no edge) must equal, entry by entry, the matrix of the edge list of the record, and that call must exit 0. |
| Show the layer media types it published | The step reads the digest that a runner pulls and the compression of its layers. |
