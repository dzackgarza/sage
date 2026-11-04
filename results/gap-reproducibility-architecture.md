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
| GAP optional packages | same tarball, version **4.16.1** | `build/pkgs/gap_packages/{package-version.txt,checksums.ini}` — it ships atlasrep, design, grape, guava, hap, polenta, polycyclic, **genss**, … |
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
   `$SAGE_LOCAL/lib/gap/pkg`, and add `orb`, `forms`, `recog` there from their pinned
   tarballs; build `orb`'s module with the `gac` that step 2 installed.
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
