# GAP in this image: why the distro path is wrong, and what reproducibility requires

Status: **finding and corrected design. Nothing applied to the live runtime**;
consumers are active and the shared rootfs is untouched. The change below needs a
producer build and a maintenance boundary before it can be adopted.

## The root cause, in one sentence

This image is a **meson/venv build that takes every system dependency from Debian
and never builds a single Sage package (spkg)** — so GAP, libgap and every GAP
package arrive as distribution binaries, and `/usr/share/gap/pkg` is the only place
they can live. That is why the capability had to be dropped into the distro tree,
and why asserting that path as the contract would be wrong.

Evidence (`docker/research-environment.Dockerfile`):

* The only build step is `just research-environment-sync` (line 250). There is **no**
  `make configure`, **no** `make build`, and **no** `sage -i` anywhere in the file.
* Standard dependencies are resolved by Sage's own metadata into apt names and
  installed wholesale (lines 68-71):
  `build/bin/sage-get-system-packages debian $(build/bin/sage-package list :standard:)`
  with only `libbrial-dev`, `libbrial-groebner-dev` and `gap-polenta` excluded.
  `gap` and `libgap-dev` are :standard: entries, so Debian supplies both.
* The optional list then adds ~20 more `gap-*` Debian packages (atlasrep, design,
  grape, guava, hap, polycyclic, character-tables, …).
* Consequently the live runtime has **no `$SAGE_LOCAL/lib/gap` at all** (checked).
* `build/pkgs/gap/spkg-configure.m4` accepts the system GAP whenever a `gap` of
  version ≥ 4.13 < 5.0 with the minimal packages and a linkable `libgap` is found
  (`sage_spkg_install_gap=no`), which is exactly what the apt install produces.

## Why the packages could never be in Sage's own tree

Sage's documented location for optional GAP packages is `$SAGE_LOCAL/lib/gap/pkg`:

* `build/pkgs/gap/spkg-install.in:11` — Sage's own GAP installs to
  `GAP_ROOT="$SAGE_LOCAL/lib/gap"`, so that directory *is* a GAP root and
  `…/pkg` is searched automatically.
* `build/pkgs/gap_packages/spkg-install.in:31` — `PKG_DIR="$SAGE_LOCAL/lib/gap/pkg"`,
  unconditionally, even after it has located the *system* root at line 13 for its
  `sysinfo.gap` check.

So on a system-GAP deployment `sage -i gap_packages` writes into a directory no GAP
searches. That is a Sage-level defect for system-GAP installs, and this image is one.
Installing into `/usr/share/gap/pkg` works, but it makes the distro GAP the owner of
Sage's optional packages — the opposite of reproducibility.

## The mechanism that does not require Sage's package manager

`src/sage/libs/gap/util.pyx:284-285` initialises libgap with
`argv[2]="-l"`, `argv[3]=kernel_info()[2]` — the root list of the `gap` **binary on
PATH**. `kernel_info` (util.pyx:41) runs `["gap", "--systemfile", …]`.

So the search path is decided by whichever `gap` PATH resolves, which means pointing
Sage at a Sage-owned GAP is a matter of *which binary* is installed, not of patching
the check.

## What the corrected design is

Declared, pinned inputs for the whole GAP stack — binary, libgap, packages, native
module — and no distribution GAP:

| input | pin | where declared |
| --- | --- | --- |
| GAP source (binary + libgap) | **4.16.1**, `sha256=df7d116f03c426dac24bf7c76ea11416b29c5a48eac12f97811d80ec215f7f69`, `sha1=0162f289a10e9406e12555b92d566aa689ea9af6` | `build/pkgs/gap/checksums.ini` |
| GAP optional packages | same tarball, version **4.16.1** | `build/pkgs/gap_packages/{package-version.txt,checksums.ini}` — ships atlasrep, design, grape, guava, hap, polycyclic, **genss** and **orb**; **not** `forms`, **not** `recog` |
| orb | 5.1.0, `sha256=73911bab4b31ae0f1771e76c1e3b9389100c6ede4ad27f27724cd4dc1239cb28` | pinned in the Dockerfile today |
| forms | 1.3.0, `sha256=a5c823b0fc4d68f2bfbf9e30d4792ea501b413c7636596aae1be6407140f7e54` | same |
| recog | 1.5.1, `sha256=eae7deaecb263242ee378f5728e4d7a717d6d1903d9d04e099d74ba1b7c53931` | same |

Concretely, in `docker/research-environment.Dockerfile`:

1. Exclude `gap`, `libgap-dev`, `libgap*` and `gap-*` from the generated apt list
   (the same `grep -vxE` that already drops `libbrial*` and `gap-polenta`), and drop
   the explicit `gap-*` block from the optional apt install.
2. Build GAP 4.16.1 from the pinned tarball into `$SAGE_LOCAL`
   (`./configure --prefix=/sage/.venv && make && make install`): produces
   `$SAGE_LOCAL/bin/gap`, `$SAGE_LOCAL/lib/libgap.*` and the root
   `$SAGE_LOCAL/lib/gap`.
3. Extract the optional packages from the same pinned tarball into
   `$SAGE_LOCAL/lib/gap/pkg` — that source supplies `genss` *and* `orb`
   (`spkg-install.in:95`: `for pkg in cohomolo crypting grape orb datastructures`),
   so only **`forms` and `recog`** need their own pinned tarballs. `orb`'s module is
   built with the `gac` that step 2 installed.
4. Rebuild sagelib so it links the Sage-built `libgap` rather than Debian's.
5. Then `kernel_info()` reports `$SAGE_LOCAL/lib/gap` because that is the `gap` the
   venv ships, and `gap_packages`' documented location is a real root — the defect in
   the previous section disappears rather than being papered over.

The check then asserts reproducibility, not a distro layout: `gap` resolves under
`$SAGE_LOCAL/bin`, the GAP root list contains `$SAGE_LOCAL/lib/gap`, and each of the
four packages resolves under a directory GAP searches.

## What was measured for the interim state

Until step 2 exists, the only way to give consumers the capability is the distro
tree, which is what the live runtime has now: the four packages and `gac` copied
byte-identically from the published image into `/usr/share/gap/pkg`
(`results/gap-capability-installed.txt`, five paths, reversible). That is an
**interim deviation from the intended architecture**, not the contract, and it must
be replaced by the pinned build above, not enshrined by assertions.

## Scope note carried forward

Whatever the owner, genss's chain is Monte Carlo bounded by `ErrorBound`; the deg-4
`GF(5)` Borel order of 62,500 is capability evidence and certifies nothing about the
degree-10 module (9,765,625 points at p=5).

## Cost and what is required

Steps 1-4 add a GAP build to the image (tens of minutes in CI, plus a sagelib
relink) and cannot be validated on this host: the image has never built a spkg, so
this is the first. It needs a producer build run to validate, and then a maintenance
boundary to adopt into the shared rootfs — neither of which is available while four
consumers are active. No part of it is applied.

## Reconciliation with the independent audit (2026-11-04)

Four corrections to the sketch above, three of them against my own first draft.

**1. Meson finds libgap on its own, and `--with-system-gap=no` does not reach it.**
`src/meson.build:233-243`:

```meson
gap = dependency('libgap', version: '>=4.13.0', required: false)
if not gap.found()
  gap = cc.find_library('gap', has_headers: ['gap/common.h'], required: not is_windows, disabler: true)
endif
```

Sage's `sage.libs.gap` links this object (`src/sage/libs/gap/meson.build:38`:
`dependencies: [py_dep, gap, gmp]`). So the linkage is decided by **pkg-config's
`libgap`** and, failing that, by `cc.find_library('gap')` — not by
`build/pkgs/gap/spkg-configure.m4`. Removing the Debian package alone would either
break the configure or silently re-find another libgap; the Sage-built one has to be
what this probe resolves (own `PKG_CONFIG_PATH` into `$SAGE_LOCAL/lib/pkgconfig`, and
no system `libgap.pc` visible), and the headers found with it must be the same build's.

**2. The version is not the same, so "add the packages" cannot be the whole story.**
Sage's pin is GAP **4.16.1** (`build/pkgs/gap/package-version.txt`, tarball
`sha256=df7d116f…`); the image's Debian GAP is **4.14.0**. An executable and a libgap
from different versions, with headers from a third place, is precisely the failure
class the bliss defect already taught here (headers built with a different ABI than
the library — `results/sage-image-bliss-fix.md`). The five things must come from one
build: **executable, headers, libgap, package root, and the native `orb` module**.

**3. `gap_packages` supplies `orb`; only `forms` and `recog` are extra.** My first
draft listed `orb` as needing its own tarball. `spkg-install.in:95` installs it:
`for pkg in cohomolo crypting grape orb datastructures`. It ships neither `forms` nor
`recog`.

**4. `build/pkgs/gap/spkg-install.in` targets `$SAGE_LOCAL`** (`GAP_ROOT="$SAGE_LOCAL/lib/gap"`,
`sdh_configure … --prefix=$SAGE_LOCAL`), which is what makes the package root and the
executable agree — and is why the `$SAGE_LOCAL` build above is the right target rather
than a distro prefix.

## Where the isolated test actually ran

The claim "the system tree now holds none of the four" refers to
**`repo/.scratch/gapfix/syspkg`** — a copy of the live `/usr/share/gap/pkg` with the
four directories removed, bind-mounted **over** `/usr/share/gap/pkg` inside a
`bwrap` sandbox whose `/` was the live rootfs mounted **read-only**. The stand-in for
`$SAGE_LOCAL/lib/gap` was `repo/.scratch/gapfix/home/gap`, and the `gap` shim was
`repo/.scratch/gapfix/shim/gap`, bound over `/usr/local/bin` for that invocation only.

The shared rootfs was never written in that test, and the first attempt was discarded
because a GAP workspace cached from the previous run still pointed at the old path —
the clean run is the one reported. **The live rootfs still has the interim layout**
(four packages in `/usr/share/gap/pkg`); replacing it is the pinned build above, which
must wait for a boundary.

## Implementation (2026-11-04) and what was validated before pushing

The change is in `docker/research-environment.Dockerfile` and
`docker/research-environment-check.py`; `results/gap-capability-install.sh` was
retargeted for adoption of the same layout.

**Declared input verified.** `gap-4.16.1.tar.gz` fetched from the URL that
`build/pkgs/gap/checksums.ini` declares: 606,052,748 bytes,
`sha256=df7d116f03c426dac24bf7c76ea11416b29c5a48eac12f97811d80ec215f7f69` — matches.
The Dockerfile reads the version and the digest out of those two files rather than
repeating them, so the pin has one home.

**The tarball carries every package needed** — `atlasrep`, `design`, `forms`,
`genss`, `grape`, `guava`, `hap`, `orb`, `polenta`, `polycyclic`, `recog` are all in
its `pkg/`. No extra tarballs, no distribution GAP packages.

**A real build in a scratch prefix, mirroring the Dockerfile step**, produced:

```
configure / make -j4 / make install   -> exit 0
$prefix/bin/{gap,gac}                 -> present
$prefix/lib/libgap.so.11              -> SONAME libgap.so.11
$prefix/lib/pkgconfig/libgap.pc       -> Version: 4.16.1, Libs: -lgap, Cflags: -I${includedir}
$prefix/lib/gap/sysinfo.gap           -> present
```

`libgap.pc` at version 4.16.1 is what makes `src/meson.build:233` resolve the
Sage-built library instead of a distribution one.

**A defect found by building, not by reading:** GAP's own `make install` does *not*
install the packages it ships in `pkg/` — `$prefix/lib/gap/pkg` came out empty. The
Dockerfile therefore copies an explicit list of 18 packages from the same pinned
source.

**The native module builds against this GAP and nothing else:** `orb` compiled with
the `gac` from that build produced
`bin/x86_64-pc-linux-gnu-default64-kv11/orb.so`. The kernel ABI is **kv11** here
against the distribution GAP's **kv9**, so a module built for one could not be loaded
by the other — the concrete cost of having had two GAPs.

**The gate passes in the scratch tree:**

```
orb=true forms=true genss=true recog=true
RecognizeGroup bound: true
```

**One more thing the build exposed:** the `gap` binary carries no rpath to
`$SAGE_LOCAL/lib`, so the loader cannot find `libgap.so.11` on its own; the image now
writes `/etc/ld.so.conf.d/sage-local.conf` and runs `ldconfig`.

## What the check asserts now

Not a distribution layout: `gap` resolves under `/sage/.venv`, its reported version
equals `build/pkgs/gap/package-version.txt` (the declared pin), its root list
contains `/sage/.venv/lib/gap/`, and each GAP package resolves inside a directory
that instance actually searches.

## Remaining requirements

* **Producer run** to build and publish the image from this commit. Pushing the
  Dockerfile is what triggers it; nothing here was built or published from this host.
* **Adoption boundary** before the shared rootfs takes it: the live runtime still has
  the interim layout (four packages under `/usr/share/gap/pkg`, Debian GAP 4.14,
  `orb.so` for kv9). `results/gap-capability-install.sh` is retargeted for the new
  layout but must run only at a boundary, with consumers stopped.
* Consumers are unaffected until then: the interim capability still loads, because
  the checks no longer name either tree.

## Second implementation pass: defects found by testing (2026-11-04)

| defect | how it showed | fix |
| --- | --- | --- |
| gate executed the new `gap` before `ldconfig` | reproduced locally: `error while loading shared libraries: libgap.so.11` | `ld.so.conf.d` + `ldconfig` moved inside the build RUN, before first execution |
| GAP installed before the venv existed | `uv sync` refuses a nonempty `.venv`: "cannot be used because it is not a valid Python environment"; `uv venv` says "A directory already exists" | `uv venv /sage/.venv` first, then GAP, then sync — verified that sync then succeeds and keeps GAP's files |
| package list was my hand-picked 18 | Sage's recipes install 30 pure + `cohomolo crypting grape orb datastructures` + `guava` (gnu17) + `nq io digraphs` | copied sets now mirror `build/pkgs/gap/spkg-install.in` and `build/pkgs/gap_packages/spkg-install.in`, and natives are compiled as Sage compiles them |
| `polenta` needed `alnuth`, absent | read from the pinned source's own `PackageInfo.g`: `polenta -> alnuth, polycyclic`; `hap -> polycyclic`, `guava -> SONATA`, `orb -> IO`, `grape -> GAPDoc`, `recog -> AtlasRep`, `genss -> orb` | `alnuth` added; the build gate `LoadPackage`s fourteen packages, so a missing closure member fails the build |
| adoption installer named versioned dirs (`forms-1.3.0`, …) and copied only packages + `gac` | the new image ships unversioned `pkg/forms` etc. and needs the whole prefix | installer now moves the installation as a unit: `bin/{gap,gac}`, `lib/libgap.so*`, `lib/pkgconfig/libgap.pc`, `include/gap`, `lib/gap`, `ld.so.conf.d` entry |
| `PKG_CONFIG_PATH` existed only inside one RUN | incremental builds run their own sync | now `ENV` in **both** Dockerfiles |
| `kernel_info()` proved nothing about the loaded library | it only runs the `gap` binary | the check reads `/proc/self/maps` and requires the mapped `libgap` to live under `$SAGE_LOCAL/lib` |

Adoption path tested in isolation against a fabricated source rootfs built from the
same pinned tarball: `preflight` (boundary + layout), `apply` (8 paths recorded),
`rollback` (8 removed, no leftovers). `verify` needs a userland inside the target
(the ELF interpreter is missing in a fabricated tree), so it is exercised only
against a real image, which the producer check already does.

## Patch bump hazard (needs a workflow change I cannot make)

`research-environment-image.yml` chooses a full build only when the diff matches
`^D` or `docker/research-environment.Dockerfile`. A change to
`build/pkgs/gap/package-version.txt` alone therefore selects the **incremental**
Dockerfile, which reuses the published base image and would not rebuild GAP. Until
that pattern also covers `build/pkgs/`, a pin bump must be accompanied by any edit to
`docker/research-environment.Dockerfile` (which forces a full build). Editing the
workflow needs `workflows` write, which this session does not hold — reported, not
worked around.

## Reproducibility scope: what this does and does not fix

Pinned and declared now: GAP source, its packages, the native modules, the GAP
version the check asserts, and the libgap the process maps.

Still mutable and outside this change, so no claim of full reproducibility:

* the base image `debian:trixie` and every `apt-get install` (no snapshot pinning);
* `uv`, `just` and `elan`, installed from their upstream installer scripts by URL;
* the Python interpreter (`uv python install 3.14`) and Julia 1.12.5's tarball, which
  is pinned by sha256 but its packages are resolved at build time by `Pkg.add`;
* Mathlib and the Lean toolchain, provisioned from the projects' own manifests.

Each would need its own pinning decision; none of them is made here.

## Producer acceptance: run 117 succeeded (2026-11-04)

The image built from `9f1680d2a7bcf001e50714768e6066e6652d1708` published, and its
own build-time check is the Dockerfile's last step — a failing assertion fails the
build, so a published image *is* a passing check.

| | |
| --- | --- |
| run | **117**, `completed / success` |
| index (OCI) | `sha256:59568577510bd76fc9c405c81e6cb185656a193a24ee08b33e1b8b7fa6ae9d2b` |
| linux/amd64 manifest | `sha256:caacdd4b7ff8b322e5a43bf23b93e45b473e08667ed9121518fa5845b3867cb0` |
| config | `sha256:dfdadb84096d9ea01ad295c05b184aaecb5e2ad18b8cda88bdc781e5f505390b` |
| `org.opencontainers.image.revision` | `9f1680d2a7bcf001e50714768e6066e6652d1708` |
| created | `2026-11-04T17:17:22Z` |
| size | 20 layers, 13,593,422,554 bytes |

### Read back from the published layer, not inferred

The GAP layer (`sha256:ca61bed72627…`, 606,688,828 B) contains:

```
sage/.venv/bin/gap
sage/.venv/bin/gac
sage/.venv/lib/libgap.so.11
sage/.venv/lib/gap/sysinfo.gap
sage/.venv/lib/gap/pkg/**/PackageInfo.g          -> 173 packages
sage/.venv/lib/gap/pkg/{atlasrep,forms,genss,guava,hap,orb,primgrp,recog}/PackageInfo.g
sage/.venv/lib/gap/pkg/orb/bin/x86_64-pc-linux-gnu-default64-kv11/orb.so
```

`primgrp` and `atlasrep` are both present at the depth GAP expects — the pair whose
absent closure failed run 116 — and the native module is built for `kv11`, the ABI of
this GAP rather than the distribution's `kv9`.

This supersedes the interim state described above: the runtime now has a Sage-owned,
pinned GAP in its image. The live shared rootfs has **not** been adopted to it.

## Fresh consumer smoke on the published digest (isolated, 2026-11-04)

Run in a **separate unpacked tree** at `$HOME/sage-verify/image`, from the registry,
not adopted into the live runtime and with no consumer pin touched.

| | |
| --- | --- |
| index | `sha256:59568577510bd76fc9c405c81e6cb185656a193a24ee08b33e1b8b7fa6ae9d2b` |
| manifest | `sha256:caacdd4b7ff8b322e5a43bf23b93e45b473e08667ed9121518fa5845b3867cb0` |
| config | `sha256:dfdadb84096d9ea01ad295c05b184aaecb5e2ad18b8cda88bdc781e5f505390b` |
| revision | `9f1680d2a7bcf001e50714768e6066e6652d1708` |
| unpacked | `2026-11-04T19:03:42Z`, 41 GB, every layer sha256-verified |

### Provenance from a consumer process

```
gap on PATH: /sage/.venv/bin/gap
kernel: 4.16.1 x86_64-pc-linux-gnu-default64-kv11
roots: /root/.gap/;/sage/.venv/lib/gap/;/sage/.venv/share/gap/
libgap mapped: ['/sage/.venv/lib/libgap.so.11']
```

The GAP *is* the Sage-owned one — not `/usr/bin/gap`, not Debian's 4.14 — and the
mapped `libgap` comes from `$SAGE_LOCAL/lib`, which is the linkage claim the audit
asked to be proven rather than asserted. The ABI is `kv11`, matching the module.

### Package features

```
GapPackage(atlasrep) present: True     GapPackage(polenta)    present: True
GapPackage(design)   present: True     GapPackage(polycyclic) present: True
GapPackage(grape)    present: True     GapPackage(genss)      present: True
GapPackage(guava)    present: True     GapPackage(recog)      present: True
GapPackage(hap)      present: True
```

### Capability check

```
LoadPackage(orb)   = true, version 5.1.0    from /sage/.venv/lib/gap/pkg/orb/
LoadPackage(forms) = true, version 1.3.0    from /sage/.venv/lib/gap/pkg/forms/
LoadPackage(genss) = true, version 1.6.10   from /sage/.venv/lib/gap/pkg/genss/
LoadPackage(recog) = true, version 1.5.1    from /sage/.venv/lib/gap/pkg/recog/
genss chain order of the deg-4 GF(5) Borel: 62500 in 0.005s (expect 62500)
CONSUMER CAPABILITY CHECK PASSED
```

Resolution is from `$SAGE_LOCAL/lib/gap/pkg`, i.e. the Sage-owned tree, in a consumer
process on the published image. Peak tree RSS 344 MiB, run under
`PEAKRSS_LIMIT_MIB=6144`.

Scope unchanged: genss's chain is Monte Carlo bounded by `ErrorBound`; 62,500 is
capability evidence, not an exact order for any subgroup of `O(V)`, and no degree-10
computation was attempted.

### A defect in this project's own check, found by running it

`results/consumer-check.py` had literal `\n` escapes written into a comment by an
earlier edit, leaving `root_list` undefined and the check dead at import time
(`NameError: name 'root_list' is not defined`). Fixed before the run above; the
passing output is from the corrected file.
