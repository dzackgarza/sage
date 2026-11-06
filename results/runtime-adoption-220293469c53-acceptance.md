# Adoption of the published runtime 220293469c53 — acceptance

The shared `/sage` rootfs was moved from the published image of source `9f1680d2` to
the image published from `6a1d6d9f`, carrying sage#10 (sage-categories' GAP
allocation), sage#11 (one GAP in the image) and sage#12 (a Mathlib build per pinned
revision). The consumers were confirmed idle by their owners and the preflight found
no process inside the rootfs.

## The two commits and the digest

| object | value |
| --- | --- |
| OCI index (as the producer reported it) | `sha256:220293469c53eef012ce94ed52795216ff5b27f65a1f401a41864f45967d3851` |
| linux/amd64 manifest | `sha256:220927bf28cff7c8129a5a53dd26a2b3949f4ce8bc23243fd3db6b91f5544cb3` |
| config | `sha256:edf81e07170039e8707bed09b366520533b31c07b1602ce83b3b917f90cb47e1` |
| image source pin | `6a1d6d9f8ebf276a06245f3045b78834219ea09a` |
| runtime's `/sage` after adoption | `281da26ffdce65f72203b75fe7c932684ce8fcff` |
| instrument pinned to | `published=281da26ffd`, `expected_check=3937c63650` |
| rollback target | `9f1680d2a7bcf001e50714768e6066e6652d1708` |

`ghcr.io/dzackgarza/sage@sha256:220293469c53…` is the **index** digest the producer
prints; `docker/sage-image.py` resolves a reference through the index and unpacks the
amd64 manifest, so the index is what pins these bytes.

## The image's own copy of the checker carries a defect

`docker/research-environment-check.py` **at `6a1d6d9f`** cannot pass on this runtime:
its Lean route assumed a Mathlib override checkout always carries its dependencies
under `.lake/packages`. After the sync, Mathlib is an override for all three
checkouts, and only one of the two checkouts has a bundled closure:

```
mathlib@0df444a360ea…  .lake/packages: Cli LeanSearchClient Qq aesop …   olean: yes
mathlib@db584cd6d46c…  .lake/packages: (absent)                          olean: yes
```

`db584cd6` was built in the base image against the *shared* packages directory, which
is still what it compiled against; there is no bundled copy to find. The first run of
the check against this runtime died there:

```
git -C /opt/lake-packages/mathlib@db584cd6…/.lake/packages/Cli rev-parse HEAD
subprocess.CalledProcessError: … returned non-zero exit status 128
```

**The acceptance below is therefore the fixed checker, `281da26f`, run against this
adopted rootfs** — not the checker the image ships. The fix (use the bundled copy when
it exists, the shared entry otherwise, per-package revision asserted either way) is on
`develop` and in the live `/sage`; **the next published image carries it**.

## What the boundary did

| step | result |
| --- | --- |
| preflight | no process inside the rootfs, `sage` clean at `9f1680d2`, 48 G free |
| checkout | `9f1680d2` → `6a1d6d9f` |
| purge Debian's GAP (sage#11) | 36 packages, 315 MB freed, four paths removed, 0 apt GAP packages left |
| `just research-environment-sync`, in the runtime | 8 m 54 s, exit 0, peak **3,787 MiB** tree RSS |
| julia launcher | installed, `d1df681a03f2fe84…` |
| checker fix | `281da26f` checked out in `/sage` (only `docker/` changed; no re-sync) |
| environment check | **`child waited=0 shell_code=0`**, peak **8,109 MiB**, 11.3 GiB low-water MemAvail |

Two defects in the instrument were found and fixed on the way, both because they had
only ever been exercised by hand: it ran `just research-environment-sync` and the
check on the *host*, where `just` does not exist and the venv's interpreter is the
absolute path `/sage/.venv/bin/python`; and its `apt-get purge` could not drop to
apt's `_apt` sandbox user in a namespace that maps one uid. Both now run inside the
runtime through `docker/sage-image.py run`, and the purge passes
`-o APT::Sandbox::User=root`.

## A property of the in-place adoption: the source stamp

The runtime's `/sage` is at `281da26f` while `/sage/.spinor-base-revision` still reads
`b0cd7d86`. That stamp is written by the image workflow, not by an adoption, so an
adopted rootfs keeps the stamp of the image it came from; `git -C /sage rev-parse
HEAD` is the authority for what the runtime carries. `docker/runtime-environment-check.py`
asserts the two agree, and that is correct because it runs only inside a build, where
the workflow writes the fresh revision into the stamp first. The two images this
record accepts for consumers — the adopted rootfs and the published image — differ in
exactly this, and only for the adopted one.

## The check, verbatim

```
Lake version 5.0.0-src+d8b1897 (Lean version 4.33.0)
Lake version 5.0.0-src+d8b1897 (Lean version 4.33.0)
Lake version 5.0.0-src+819816b (Lean version 4.33.1)
kernel_info() under env -i raised: FileNotFoundError: [Errno 2] No such file or directory: 'gap'
lean-cas-dsl (leanprover/lean4:v4.33.0) from its override checkout mathlib db584cd6: Nat.add_comm : ∀ (n m : ℕ), n + m = m + n
lean-cas-dsl-leaf-contracts (leanprover/lean4:v4.33.0) from its override checkout mathlib db584cd6: Nat.add_comm : ∀ (n m : ℕ), n + m = m + n
lean-categories (leanprover/lean4:v4.33.1) from its override checkout mathlib 0df444a3: Nat.add_comm : ∀ (n m : ℕ), n + m = m + n
SageMath version 11.0.beta5, Release Date: 2026-10-28
[peakrss] check-281da26f: child waited=0 shell_code=0 samples=34
[peakrss] peak tree RSS      : 8109 MiB
```

Every section before the printed Lean lines also passed: the system features, the
research checkouts, the Maxima prefix, both canonical-label backends, the
port/sage-extensions pair, GAP's matrix-group packages loaded from `$SAGE_LOCAL`, the
single-GAP assertions with the empty-environment branch taking the accepted
`FileNotFoundError`, the sage-categories pin list, and the Julia sections.

## Runtime facts

| | |
| --- | --- |
| GAP | 4.16.1, `kv11`, at `$SAGE_LOCAL`, 173 packages, `libgap.so.11` mapped from `/sage/.venv/lib` |
| Debian's GAP | gone: `/usr/bin/gap`, `/usr/lib/gap`, `/usr/share/gap`, `libgap.so.9`, 0 apt `gap*`/`libgap*` |
| sage-categories | `.gap/pkg` with 26 pinned homalg/CAP releases, reloaded by its own loader in the check |
| Mathlib | `db584cd6` (shared/build tree of the base image) and `0df444a3` (cache + `lake build`, 8,705 jobs), each read by its own toolchain |
| toolchains | `leanprover/lean4:v4.33.0`, `v4.33.1`, `v4.33.1` the elan default |
| Julia | depot artifact for GAP_pkg_crisp 1.4.8 present and tree-hash verified; seed step in the incremental Dockerfile |

## Rollback

1. `git -C /sage checkout 9f1680d2` and re-sync inside the runtime — this restores the
   source, venv, Lean views and launcher of the previous runtime;
2. the purged Debian GAP is **not** restored: it came from an image layer, apt no
   longer has it, and a rollback leaves the runtime with the Sage-owned GAP only;
3. the check hash goes back to `ee249af7…` and `expected_check` with it.

Scope note: the deg-4 Borel order in the check is Monte Carlo capability evidence, not
an exact order for any subgroup of `O(V)`; and the acceptance above is the fixed
checker, as stated.
