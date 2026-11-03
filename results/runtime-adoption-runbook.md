# Runtime adoption runbook — owner: this project

**Status: prepared, not executed.** The shared runtime changes below wait for the
explicit all-project maintenance boundary. A single empty process snapshot is not
evidence: consumers launch between checks.

## What this is, and what it is not

It moves the shared `/sage` to the published commit and re-installs the published
lock **through the maintained recipe**, in place. It is a reconciliation of
source and pins, not a byte-identical reproduction or verification of the
published OCI image: the image's own evidence is its build check plus the fresh
hosted consumer smoke pinned by digest
([run 41275674403](https://github.com/dzackgarza/sage/actions/runs/41275674403),
amd64 manifest `sha256:5b1f54f7…`, revision `b1997dd9…`). The local copy keeps
whatever it built itself.

## Already matches the published image

| item | local state |
| --- | --- |
| Bliss source | the two published commits' hunks are the local working-tree edits (`373d04d5…` diff digest) |
| Bliss module | built locally by the image's own Meson/Ninja, `d941337e…` |
| Lean Mathlib | official cache unpacked, 8322 oleans, dependency closure built |
| Lean views | `/opt/lake-views/index.json` with both `lean_categories` overrides |
| `sage-extensions` | `/repos` already at the published pin `7b222e86…` |
| `research` | `ec1333e…`, unchanged by the published lock |

## Remains to adopt

| item | from | to |
| --- | --- | --- |
| `/sage` source | `b0cd7d8` + two patched files | `b1997dd` — exactly the commit the published image was built from |
| `uv.lock` | port `86d860a`, ext `441519c5` | port `4f0ee50c`, ext `7b222e86` |
| `/repos/sage-indefinite-port` | `86d860a` | `4f0ee50c` |
| venv | old lock | reconciled by `uv sync` under the new lock |
| `/usr/local/bin/julia` | symlink to `/opt/julia/bin/julia` | the launcher from `docker/julia-launcher.sh` |

## The script

`results/runtime-adoption.sh` carries the exact steps so the prose below and the
run cannot diverge:

| subcommand | writes | what it does |
| --- | --- | --- |
| `preflight` | no | refuses if any `proot`/`udocker`/`bwrap` references the rootfs; prints source HEAD, diff digest, lock and module digests, launcher, free space |
| `verify` | no | compares the live files with `b1997dd` and prints the remaining delta |
| `adopt` | yes | fetch, guard the patched files, `checkout b1997dd`, `just research-environment-sync`, install the launcher — each under its own `timeout` |
| `check` | no | the image's own `research-environment-check.py` |
| `rollback` | yes | restores module, stamps and launcher from the snapshot, returns the source to `b0cd7d8` with both patches, prints the lock revert |

Expected hashes at `b1997dd`, as run against the live tree:

```
uv.lock                            b389c58acbb592c3   f070d20194761a12   differs
install-research-repositories.sh   bd603523dabd7077   a46fb9a7024d80bc   differs
research-environment-check.py      a1ae79e3bc5caa8a   53776377007c5a88   differs
provision-lean-packages.sh         absent             5af7c91b2b9eb994   absent
julia-launcher.sh                  absent             d1df681a03f2fe84   absent
src/.../meson.build                d8119d97dfa923a7   d8119d97dfa923a7   ok
```

`meson.build` already matches the published source byte for byte — the local
Bliss repair is exactly what shipped. `/repos` shows `sage-extensions` and
`research` already at their published pins, and `sage-indefinite-port` at
`86d860a` where the lock will move it to `4f0ee50c`.

## Preconditions — all of them


1. The coordinator confirms all four projects have stopped shared-runtime
   commands and their existing jobs have ended.
2. This project has no jobs running.
3. Nothing executes inside the rootfs — verify, do not assume:

   ```sh
   R=$HOME/sage-image/rootfs
   pgrep -af "proot|udocker|bwrap" | grep -F "$R"   # must print nothing
   ```

4. Pre-state re-captured and equal to `results/runtime-pre-adoption-state.txt`,
   or every difference explained before proceeding.

## Exact commands

```sh
R=$HOME/sage-image/rootfs

# 1. source: the published commit; the patched files are identical to it
git -C $R/sage fetch origin develop
git -C $R/sage diff --stat b1997dd -- \
  src/sage/graphs/meson.build src/sage/graphs/bliss_cpp/bliss_find_automorphisms.h   # must be empty
git -C $R/sage checkout b1997dd

# 2. lock, venv, /repos and the Lean views through the maintained recipe
cd $R/sage && just research-environment-sync

# 3. the launcher the published image ships
install -m 0755 $R/sage/docker/julia-launcher.sh $R/usr/local/bin/julia

# 4. readback, in place: the image's own check, then the pinned-project smokes
$R/sage/.venv/bin/sage docker/research-environment-check.py
```

Expected: `/sage` clean at `b1997dd`; `uv.lock` at the published pair;
`/repos/sage-indefinite-port` at `4f0ee50c`; the Lean provisioner adopting the
existing Mathlib build (no rebuild) and rewriting the same view overrides; the
check passing. Duration ~15–40 min, dominated by `uv sync` and the Lean
verification.

## Rollback — restore the recorded working state, not an assumed original

The installed Bliss module before adoption is the **repaired** one,
`d941337e3a69b8256771c2fbbff5c2604e724b717dcc41352e12a3f7f9b75a75`. Its `.orig`
sibling is not a safe source for rollback: each deployment copied the module it
found, so `.orig` holds whatever was installed at that moment, not the image's
original. Rollback therefore restores from the snapshot taken before adoption,
`results/runtime-rollback-snapshot/` (module, both stamps, launcher target, the
installed distribution list), never from `.orig`.

| change | revert |
| --- | --- |
| `/sage` at `b1997dd` | `git -C $R/sage checkout b0cd7d8 && git -C $R/sage apply results/bliss-repair.patch results/bliss-repair-v2.patch` — that reproduces the recorded tree (HEAD `b0cd7d8`, diff `373d04d5…`) |
| `uv.lock`, venv, `/repos` | `git -C $R/sage checkout b0cd7d8 -- uv.lock && (cd $R/sage && just research-environment-sync)` |
| installed distributions | compare `site-packages/*.dist-info` with `results/runtime-rollback-snapshot/installed-distributions.txt`; the sync under the old lock restores the set |
| Bliss module | `cp -a results/runtime-rollback-snapshot/bliss.cpython-314-x86_64-linux-gnu.so <site-packages>/sage/graphs/` and confirm `d941337e…` |
| stamps | `cp -a results/runtime-rollback-snapshot/bliss-repair.json $R/opt/bliss-repair.json` and `.../lake-views-index.json $R/opt/lake-views/index.json` |
| launcher | `ln -sfn "$(cat results/runtime-rollback-snapshot/julia-launcher-target.txt)" $R/usr/local/bin/julia` |
| a damaged venv edge | `meson install -C /sage/builddir --only-changed --no-rebuild` reinstalls the built Sage files from the untouched build directory — no recompile |

Every snapshot file's digest is in `results/runtime-rollback-snapshot/SHA256SUMS`.

## Bounded steps, and what ends the hold

Each step has a wall-clock limit; a step that exceeds it is stopped and rolled
back rather than left running, so the hold cannot turn into an open-ended build.

| step | limit | on timeout |
| --- | --- | --- |
| `git fetch origin develop` | 5 min | stop; nothing changed |
| `git checkout b1997dd` | 2 min | stop; `git checkout b0cd7d8` |
| `uv sync` (inside `research-environment-sync`) | 20 min | stop; revert the lock and sync again |
| `install-research-repositories.sh` (git fetches, editable installs, bridge `julia-deps`) | 20 min | stop; revert the lock and sync again |
| Lean provisioning (`provision-lean-packages.sh`) | 15 min | stop; it only adopts and verifies the existing Mathlib build, so a timeout means the cache is missing and the step must be reported, not run to a build |
| `install … julia-launcher.sh` | 1 min | stop; restore the symlink |
| `research-environment-check.py` readback | 20 min | report the failing phase |

**Surfaced before the hold starts, not during it:** a reachability and size probe
for the two downloads the reconcile needs — the `sage-indefinite-port` fetch
(`4f0ee50c`, a small git fetch) and the PyPI wheels the new lock adds
(`PyNormaliz` ~73 MB and friends). If either probe is slow, the adoption is
rescheduled instead of starting; no full build is run under any circumstance,
and the only Lean work allowed is the provisioner verifying the Mathlib build
that is already present.

## Invariants held throughout

* per-project binds and pins are untouched — each project keeps binding its own
  checkouts (`-b <its checkout>:<container path>`), and no consumer checkout is
  moved or edited;
* no project downloads or provisions a second copy of the image;
* nothing runs concurrently with a consumer job.

## Blockers to report rather than work around

* A digest-faithful **pull** of the published image is 13.11 GB compressed;
  registry throughput measured from this VM was ~0.1 MB/s, so it is tens of
  hours. That is why adoption is in place from the published commit and lock.
  Disk is not the constraint (158 GB free, rootfs 40 GB).
* If any project cannot stop for the boundary, adoption waits; there is no safe
  partial adoption of `/sage`, `/repos`, the venv or the launcher while a
  consumer runs inside the rootfs.
