# Mathlib in the shared image

Reported: from `/repos/lean-categories` (toolchain `leanprover/lean4:v4.33.0`,
commit `d8b18978322de05a8f3dba51ef03cf5461676c17`; Mathlib pinned at
`db584cd6d46c92f209a44c0f1c829460d327499d`), `import Mathlib` fails,
`/opt/lake-packages/mathlib@db584cd6…` has no `.lake/build`, and `lake env`
resolves `/.local/share/lean/v4.33.0/packages` and stops at Batteries.

## Reproduction, in the image as published

```sh
cd /repos/lean-categories && lake env lean /tmp/lean-smoke.lean   # "import Mathlib"
# error: object file '/.local/share/lean/v4.33.0/packages/batteries/.lake/build/lib/lean/Batteries.olean'
# of module Batteries does not exist
```

## Cause: the recipe linked into a directory the projects do not read

All three Lean checkouts declare
`packagesDir = "../../.local/share/lean/v4.33.0/packages"` in their lakefile, and
their `lake-manifest.json` records the same value relative to the checkout,
which resolves to `/.local/share/lean/v4.33.0/packages`. Lake resolves a
project's dependencies from `packagesDir`, so `<checkout>/.lake/packages` — the
only place `install-research-repositories.sh` linked, and the guard it used to
decide whether to fetch Mathlib's cache — is never read by these projects.

State of that directory in the published image:

| package | `.lake/build` | oleans |
| --- | --- | --- |
| `mathlib` | yes | 8322 (the official cache, retrieved into the resolved directory) |
| `batteries` | yes | 1 |
| every other package | no | 0 |

`/opt/lake-packages/*@<rev>` — the shared checkouts — carry no build tree at all,
including `mathlib@db584cd6…`, because nothing ever resolved there. So the cache
retrieval worked, and `import Mathlib` still failed on the first package Mathlib
imports, because no dependency was ever built.

## Fix

`docker/install-research-repositories.sh`:

* reads `packagesDir` from each checkout's `lake-manifest.json` (default
  `.lake/packages`), resolves it against the checkout, and links the shared
  `/opt/lake-packages/<name>@<rev>` checkouts **there**, so the packages stay one
  copy under `/opt` instead of a second copy per project;
* retrieves the official pinned Mathlib cache once (`lake exe cache get`, which
  reads the checked-out Mathlib revision), then builds its dependency closure
  once (`lake build Mathlib`), so Mathlib itself is never compiled;
* fails the build unless the resolved `packagesDir` holds
  `mathlib/.lake/build/lib/lean/Mathlib.olean`.

`docker/research-environment-check.py` keeps the per-checkout `lake --version`
and adds the import the report was missing: `lake env lean` on a file containing
`import Mathlib` and a `#check`, from `/repos/lean-categories` itself.

## Evidence

* Dependency closure built in this image (bound writable copies of the
  packages, Mathlib's cached tree linked read-only so it cannot be rebuilt):
  `Build completed successfully (8711 jobs)` in **under three minutes** — Mathlib was taken
  from the cache, only its imports were compiled. Not a multi-hour build.
* `lake env lean` on `import Mathlib` then returns
  `Nat.add_comm : ∀ (n m : ℕ), n + m = m + n`, exit 0, in 19 s.
* The whole `research-environment-check.py`, this change included, passes in one
  run with Mathlib provisioned this way (exit 0, `SageMath 11.0.beta5`).

Committed on `develop` as `3cee6bb` and `f6763b1` (the script the build
and an unpacked image both run); nothing pushed.

## Applying it to an image that is already unpacked

The repair is one script, `docker/provision-lean-packages.sh`, and the image
build calls it (`install-research-repositories.sh`). An image unpacked earlier
runs the same script, so the two paths cannot drift:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --bind docker/provision-lean-packages.sh:/opt/provision-lean-packages.sh \
  --env ELAN_HOME=/opt/elan \
  -- /bin/bash /opt/provision-lean-packages.sh /repos
```

`ELAN_HOME` is the only environment it needs beyond the runner's `PATH`, and it
needs no particular working directory: it walks `/repos` itself. It uses the
packages already checked out under `/opt/lake-packages`, keeps an image's own
copy of a package when that copy is at the pinned revision (the unpacked
Mathlib cache lives in one), retrieves the official cache only when the image
does not carry it, and builds only what Mathlib imports. No toolchain, no
second checkout, no consumer source edit.

That run has been made against the published unpacked image: it completed
(`Build completed successfully (8709 jobs)`), and the readback below printed
`Nat.add_comm : ∀ (n m : ℕ), n + m = m + n`. It also reported a real collision
rather than working around it — the checkouts share one `packagesDir`, and
`lean-cas-dsl` pins `lean_categories` `eea5c7f3…` while
`lean-cas-dsl-leaf-contracts` pins `82d1370d…`, so the shared directory holds
one of them; the script warns and leaves the copy in place.

Readback, from the pinned project:

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --env ELAN_HOME=/opt/elan \
  -- /bin/sh -c 'cd /repos/lean-categories && printf "import Mathlib\n#check (Nat.add_comm : ∀ a b : Nat, a + b = b + a)\n" > /tmp/mathlib-import.lean && lake env lean /tmp/mathlib-import.lean'
```

## Resolution, not first-writer-wins

Lake fixes a project's packages directory in its lakefile and records it in the
manifest — `-K packagesDir=` is ignored, and a lakefile whose `packagesDir`
disagrees with its manifest is rejected as out of date — so the path cannot be
overridden per project. The layout that resolves two checkouts pinning one
package at different revisions:

* `/opt/lake-packages/<name>@<revision>`: one checkout per package revision;
  every view links into it, so no revision is cloned twice.
* `/.local/share/lean/v4.33.0/packages`, the directory all three checkouts
  declare: the packages they agree on, as links into `/opt/lake-packages`. For a
  name they disagree on — `lean_categories`, pinned at `eea5c7f3…` by
  `lean-cas-dsl` and `82d1370d…` by `lean-cas-dsl-leaf-contracts` — provisioning
  links nothing and deletes nothing, so the `eea5c7f3…` directory the published
  image shipped is still on disk; no checkout is expected to resolve through it.
* `/opt/lake-views/index.json`: per checkout, an override for each package its
  manifest pins at a revision that directory does not hold. Both DSL checkouts
  carry an override for `lean_categories`; `lean-categories` carries none.

Both projects are launched explicitly. Before mounting, the launcher verifies the
checkout's **whole manifest**: every pinned package must be present at exactly
its revision — in its override or, for a shared package, in the declared
directory — and a package that resolves to another revision refuses the launch.

```sh
python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --env ELAN_HOME=/opt/elan --lean-view /repos/lean-cas-dsl \
  -- /bin/sh -c 'cd /repos/lean-cas-dsl && lake env lean /tmp/file.lean'

python3 docker/sage-image.py --rootfs ~/sage-image/rootfs run \
  --env ELAN_HOME=/opt/elan --lean-view /repos/lean-cas-dsl-leaf-contracts \
  -- /bin/sh -c 'cd /repos/lean-cas-dsl-leaf-contracts && lake env lean /tmp/file.lean'
```

Readback, both launched at the same time with those two commands:

| checkout | `lean_categories` resolved | manifest pin | Mathlib |
| --- | --- | --- | --- |
| `lean-cas-dsl` | `eea5c7f3bce7a1d2fdfbd58840c4d4bd75c9a8bc` | `eea5c7f3…` ✓ | `Nat.add_comm : ∀ (n m : ℕ), n + m = m + n`, OK |
| `lean-cas-dsl-leaf-contracts` | `82d1370de372a00a86391b74fc2566c9547dfcb6` | `82d1370d…` ✓ | `Nat.add_comm …`, OK |

A stale or wrong index is refused rather than resolved: pointing
`lean-cas-dsl`'s override at the other revision and launching it stops with

```
/repos/lean-cas-dsl pins lean_categories at eea5c7f3bce7a1d2fdfbd58840c4d4bd75c9a8bc
but resolves 82d1370de372a00a86391b74fc2566c9547dfcb6 from
…/opt/lake-packages/lean_categories@82d1370de372a00a86391b74fc2566c9547dfcb6;
run docker/provision-lean-packages.sh in this image
```

## The artifact itself

The script is committed at `docker/provision-lean-packages.sh` (`4f96c058b13e`)
and copied here byte for byte, because the commit is not published yet:

| file | sha256 |
| --- | --- |
| `results/provision-lean-packages.sh` | `c54e3a662eb5804d5fe0377e59655f058f7677f18075f888647d55cdb58af26e` |

It needs no environment of its own: it finds `/opt/elan` and its toolchains
where the image keeps them, so a PRoot or bare-exec launcher that does not apply
the image's environment still runs it:

```sh
proot -R ~/sage-image/rootfs \
  -b results/provision-lean-packages.sh:/opt/provision-lean-packages.sh \
  -w / /bin/bash /opt/provision-lean-packages.sh /repos
```

For a checkout whose manifest the shared directory cannot fully carry, mount its
overrides from the index for that run — one `-b` per override:

```sh
proot -R ~/sage-image/rootfs \
  -b ~/sage-image/rootfs/opt/lake-packages/lean_categories@82d1370de372a00a86391b74fc2566c9547dfcb6:/.local/share/lean/v4.33.0/packages/lean_categories \
  -w /repos/lean-cas-dsl-leaf-contracts /bin/sh -c 'lake env lean /tmp/file.lean'
```

## Not touched

The Lean checkouts (consumer repositories), their lakefiles and manifests, and
the toolchain: no new toolchain, no consumer-local installation. Publication
remains held.
