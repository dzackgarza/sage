# `ghcr.io/dzackgarza/sage:develop` — why `canonical_label` segfaults

## Image identity (registry, verified)

| Object | Digest / value |
| --- | --- |
| OCI index `:develop` | `sha256:ccdea4a52158c8fea4ef46b80dcf4cecd90ef0b61afa467f9541c6c658eeff09` |
| linux/amd64 manifest | `sha256:c3a9f1637d43b727ab2b24c0ccf1bc9ee513a08a02094d20221065ef2d8643dd` |
| config | `sha256:2d6a4754b6f1518af356dd28ac6ec2e7678c7fe4ab0d70c2e7c9ecbc2c605eca` |
| `org.opencontainers.image.revision` | `b0cd7d86e21eb450ed90e4c83707920e1d5d429a` |

Both digests match `SAGE-CONTAINER.md`. `/sage/VERSION.txt` is `11.0.beta5`;
`/sage/.venv/pyvenv.cfg` and `/sage/.venv/bin/python -V` give CPython 3.14.10
from `/opt/uv-python/cpython-3.14-linux-x86_64-gnu` — the supported target, not
the host's Python 3.12 / Sage 10.8. `~/sage-image/rootfs` unpacks exactly this
config digest, so it *is* the published image.

## Reproduction, and where the fault is not

Native execution of that rootfs (real namespaces, no ptrace):

```sh
bwrap --bind ~/sage-image/rootfs / --proc /proc --dev /dev --tmpfs /tmp \
  --unshare-pid /sage/.venv/bin/sage -c \
  'from sage.all import Graph; print(Graph([[0,1]]).canonical_label())'
```

`Unhandled SIGSEGV` in `__libc_free`, called from
`sage/graphs/bliss...so:__pyx_f_4sage_6graphs_5bliss_canonical_form_from_edge_list`.
The same crash comes out of PRoot with the same rootfs, and a module built with
the fix runs the same cases correctly under PRoot, so PRoot, seccomp and CPU
instruction sets are not involved (`PROOT_NO_SECCOMP=1` cannot change the
outcome). The fault is in the image's build of Sage.

## Cause: the system bliss is a different ABI than its headers

`libbliss2 0.77-3+b3` is built with `BLISS_USE_GMP` (it needs `libgmp.so.10`
and imports `__gmpz_init/clear/mul_ui/set_ui`). `bliss/bignum.hh` picks the
GMP representation only when the consumer defines `BLISS_USE_GMP`; the default
is a non-GMP `BigNum`. The definition lives only in the packaged
`libbliss-cxx.pc` (`Cflags: -D BLISS_USE_GMP -I/usr/include`, `Requires: gmp`).
`src/sage/graphs/meson.build` linked `-lbliss` alone, so the `bliss::Stats` that
`bliss.pyx` allocates on its own stack (`sizeof` 80 with GMP, smaller without)
is handed to a library that writes the larger layout: stack corruption, then
`free()` on a pointer built from the library's data.

Minimal proof with the image's own compiler, header and library:

```c++
bliss::Graph g(2); g.add_edge(0,1); bliss::Stats s; g.canonical_form(s);
```

built with plain `-lbliss` → segfault; built with `-DBLISS_USE_GMP -lgmp`
(the pkg-config flags) → prints `canonical 1 0`.

Second defect, hidden behind the first: `bliss_find_automorphisms()` in
`src/sage/graphs/bliss_cpp/` took `bliss::Stats` **by value** while `bliss.pyx`
declared and called it with a reference. With `mpz_t` in `Stats` the copy and
the original clear the same limbs, so `automorphism_group()` aborts on
`free(): double free detected` as soon as the ABI matches. With the non-GMP
`BigNum` (Sage's own spkg) the copy is harmless, which is why upstream never saw
it.

## Matrix: same generated `bliss.pyx.cpp`, rebuilt three ways

| `BLISS_USE_GMP` | `Stats &` | `canonical_label` | `automorphism_group` |
| --- | --- | --- | --- |
| no (published image) | no | SIGSEGV | SIGSEGV |
| yes | no | ok | double free (SIGABRT) |
| no | yes | SIGSEGV | — |
| yes | yes | ok | ok (orders 2, 8, 120, 24141680640000) |

## Fix (canonical repo, `develop`)

* `src/sage/graphs/meson.build`: take the library's flags from
  `libbliss-cxx` (Debian/Ubuntu) or `bliss`, and keep `-lbliss` as the fallback
  for Sage's own spkg, which is built with `USE_GMP=OFF` and installs no
  pkg-config file.
* `src/sage/graphs/bliss_cpp/bliss_find_automorphisms.h`: `bliss::Stats &s`.
* `docker/research-environment-check.py`: both canonical-label backends on a
  relabelled copy of one labelled graph, the two-vertex case, and the bliss
  automorphism order of the Petersen graph — the image build runs this file, so
  the defect cannot ship again.

Verification on the image's own build tree (module rebuilt from its generated
C++, bound over the installed one):

* published module → SIGSEGV on the new check;
* definition only → `double free` on the new check;
* both changes → new check passes, `sage.doctest --optional=sage,bliss
  src/sage/graphs/bliss.pyx` passes all 95 tests, 40 combinations of
  `canonical_label`/`certificate`/`edge_labels` over both backends stay
  isomorphic.

Then the same from the project's own build: `meson setup` of the patched tree
generates `-D BLISS_USE_GMP` for `bliss.pyx.cpp.o` and links
`/usr/lib/x86_64-linux-gnu/libbliss.so` with `libgmp.so`, `ninja` builds
`src/sage/graphs/bliss.cpython-314-x86_64-linux-gnu.so`, and that module runs
every case above, including `Graph([[0,1]]).canonical_label(edge_labels=True)`.

## Reported `partn_ref` MemoryError

`algorithm='partn_ref'` is not a valid name in this Sage (`ValueError: 'algorithm'
must be equal to 'bliss', 'sage', or None`); the partn_ref backend is
`algorithm='sage'`. On the verified image it computes correct canonical labels
with and without edge labels and certificates, on the published module as well
as the fixed one (400 random graphs, 0–24 vertices, random densities and four
label kinds, both backends, canonical form invariant under relabelling: 0
failures, no MemoryError). The reported MemoryError belongs to the unsupported
host fallback (Sage 10.8 / Python 3.12 plus its own emulation), not to the
image; the heap corruption above does explain arbitrary failures in a process
that touched bliss first.

## Supported invocation for hosts without a runtime

Provisioning is owned by the fork, not by consumers: `docker/SAGE-ENVIRONMENT.md`
and `docker/sage-image.py` in the fork, committed on `develop` as `b75e5b3`, `091cb8c` and `c73d349`. The script fetches the image from the registry without a daemon,
verifies every layer digest, unpacks into a cache stamped with
index/manifest/config/revision, and runs commands in that tree with
bubblewrap's unprivileged user namespaces — no root, no chroot, no ptrace:

```sh
docker/sage-image.py fetch --digest sha256:<manifest from `info`>
docker/sage-image.py run -- sage -c 'print(ZZ(2)**10)'
docker/sage-image.py check
```

The caller's checkout is mounted at `/work`, extra paths with `--bind SRC:DEST`,
and the process gets the image's own environment (`JULIA_DEPOT_PATH`, `SAGE_BIN`,
`PATH`) with the host's cleared, as a runtime would. A missing `bubblewrap`, a
kernel without user namespaces, or Ubuntu's AppArmor restriction
(`kernel.apparmor_restrict_unprivileged_userns`, or the packaged
`bwrap-userns-restrict` profile) is named before anything runs, and neither the
script nor the workflow changes a sysctl or an AppArmor profile. A new
`no-runtime` job in `research-environment-image.yml` fetches the published image
and runs its `check` after every publish where the runner already permits
unprivileged user namespaces, and otherwise records the configuration as
unsupported and skips while the image build's own check and the container
consumer job stay the gate.

Verified here with no Docker, chroot or PRoot in use: `run` executes the image's
Sage and its partn_ref canonical label, mounts a consumer checkout, reproduces
the published image's bliss segfault, and exposes only the image's environment;
`check` runs the image's whole research environment check to completion and
reports `SageMath version 11.0.beta5, Release Date: 2026-10-28` (exit 0, with
its Julia/Oscar bridge and every Lean toolchain); `apply_layer` removes a
whited-out file, clears an opaque directory and preserves a symlink on synthetic
layers; `resolve` returns the config digest and all 18 layer digests of the
image that was unpacked independently; a digest mismatch is refused. Not
verified: the new CI job, a complete 13.6 GB `fetch` (its manifest and all 18
layer digests resolve and match the independent unpack, and the first layers
download and verify, but registry throughput fell below 100 kB/s inside layer 7
and the transfer was stopped), and a host whose kernel refuses user namespaces
outright.

## Deploying the repair into an existing copy

Publication is held, so the repair reaches an existing unpacked copy
incrementally: the checked commits' own patches, applied to that copy and
rebuilt through its own Meson/Ninja tree. Two patches, because the first one's
Meson fallback chain was wrong (see below); they apply in order.

| artifact | sha256 | bytes |
| --- | --- | --- |
| `results/apply-bliss-repair.sh` | `8e2eeec1bfebff712e539ac38057354be6a9af850d4538887aaa75c875e0795e` | 6828 |
| `results/bliss-repair.patch` (v1, the checked repair) | `baf4b826e8093c7891de3650789c7f1e13c7d9e82de362a124486956e53f32b3` | 4342 |
| `results/bliss-repair-v2.patch` (the fallback correction) | `ff86f4a9a3cf02ae47ee81dc221ee048ba7f9fe277cfc3dbeb2f1ae091dbb5e1` | 4410 |

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --bind results/apply-bliss-repair.sh:/opt/apply-bliss-repair.sh \
  --bind results/bliss-repair.patch:/opt/bliss-repair.patch \
  --bind results/bliss-repair-v2.patch:/opt/bliss-repair-v2.patch \
  -- /bin/bash /opt/apply-bliss-repair.sh /opt/bliss-repair.patch /opt/bliss-repair-v2.patch
```

The script checks the copy is the published revision `b0cd7d8…` and that every
file the patches touch is either untouched or modified exactly by patches the
copy already carries; applies what is missing, in order; runs
`ninja -C /sage/builddir src/sage/graphs/bliss.cpython-…so` so Meson regenerates
from the patched `meson.build`; installs with
`meson install --only-changed --no-rebuild`; runs the graph and automorphism
smoke tests; and records base revision, every patch digest and the module digest
in `/opt/bliss-repair.json`. A failing smoke restores the module and reverts the
patches that run applied. The image stays as published.

A copy deployed with v1 alone is correct for this image — it has
`libbliss-cxx` — and its stamp records that. It is not evidence that the
fallback chain works, which is what v2 fixes.

### The fallback defect v2 corrects

`required: get_option('bliss')` on the first pkg-config probe aborted the
configure before the fallbacks under `-Dbliss=enabled`, or under
`auto_features=enabled` which turns feature options into enabled;
`disabler: true` does not make a required dependency optional. The chain is now
guarded by `not bliss_opt.disabled()`, both pkg-config probes are
`required: false`, and only `cc.find_library('bliss')` carries
`required: bliss_opt`. Resolution cases, run against the extracted block with a
feature option in this image:

| names resolve | feature | result |
| --- | --- | --- |
| `libbliss-cxx` present | enabled | found |
| no pkg-config files, raw library present | enabled | found through `cc.find_library`, no abort |
| no pkg-config files, raw library present | auto | found |
| present | auto | found |
| nowhere | auto | not found, exit 0 (disabler) |
| nowhere | enabled | exit 1 from the last probe: `C++ shared or static library '…' not found` |
| nowhere | disabled | not found, exit 0, no probe run |
| present | disabled | not found, exit 0, no probe run |

## Publishing

Held deliberately: the standing instruction names `main`, this fork's default
branch is `develop`, and it has no `main`. No `main` and no feature branch were
created; nothing was pushed. The five commits sit on `develop` in the local
clone (`~/gitclones/sage`, based on `924d8f8`) and are exported here as
`patches/0001-*.patch` … `patches/0005-*.patch` and
`patches/sage-bliss-fix.bundle`. When the integration branch is settled,
`git push origin develop` publishes; `.github/workflows/research-environment-image.yml`
then rebuilds the image on a push to `develop` that touches `src/**` or
`docker/**`, and the new `org.opencontainers.image.revision` and manifest digest
are what consumers pin.
