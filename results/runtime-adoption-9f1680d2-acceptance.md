# Adoption of the published runtime 9f1680d2 — acceptance

The shared `/sage` rootfs was moved from `ec386a5b` to the published image's source
`9f1680d2`, and the Sage-built GAP was installed into `$SAGE_LOCAL`, at a coordinated
maintenance boundary with zero processes inside the rootfs (three consecutive polls).

## The check that accepts it

`docker/research-environment-check.py` at `9f1680d2`, run in the live rootfs through the
maintained no-runtime path, bounded at `PEAKRSS_LIMIT_MIB=10240` (the environment-level
check's bound; the 6144 MiB guard continues to apply to consumer workloads):

```
/sage/.venv/lib/python3.14/site-packages/sage/categories/category.py:1612: UserWarning: _RuntimeImplementationCategory.ParentMethods should not have a super class
  warn("%s.%s should not have a super class" % (cls.__name__, method_provider))
Lake version 5.0.0-src+d8b1897 (Lean version 4.33.0)
Lake version 5.0.0-src+d8b1897 (Lean version 4.33.0)
Lake version 5.0.0-src+d8b1897 (Lean version 4.33.0)
Nat.add_comm : ∀ (n m : ℕ), n + m = m + n
docker/research-environment-check.py:203: DeprecationWarning: Use sage.version.version instead.
See https://github.com/sagemath/sage/issues/39015 for details.
  print(version())
Detected IPython. Loading juliacall extension. See https://juliapy.github.io/PythonCall.jl/stable/compat/#IPython
SageMath version 11.0.beta5, Release Date: 2026-10-28
[peakrss] acceptance: child waited=0 shell_code=0 samples=23
[peakrss] peak tree RSS      : 8548 MiB
```

`child waited=0 shell_code=0` — every assertion in the check passed, including the GAP
provenance assertions added for this work: `gap` resolving under `/sage/.venv`, its
version equal to `build/pkgs/gap/package-version.txt`, `/sage/.venv/lib/gap/` in its
root list, and the mapped `libgap` coming from `$SAGE_LOCAL/lib`.

Measured peak: **8,548 MiB tree RSS** (Lean 6,422; Julia 1,974; sage 1,322; lake 807),
host MemAvailable never below 9,735 MiB.

## What the boundary did, in order

| step | result |
| --- | --- |
| three consecutive zero-process polls | boundary held |
| GAP installation into `$SAGE_LOCAL` | 9 paths, 173 packages, manifest `results/gap-capability-installed-9f1680d2.txt` |
| `ldconfig` for `libgap.so.11` | required: writing `ld.so.conf.d` alone leaves the loader unaware |
| `/sage` checkout to `9f1680d2` | clean |
| `just research-environment-sync` | 1m24.7s, exit 0 |
| relink the GAP-facing modules | needed, see below |

## The one defect this run exposed

After the sync the runtime **segfaulted** (exit 139) with
`Error before error-handling is initialized`. Cause, measured by `readelf`: the installed
`sage/libs/gap` modules still recorded `NEEDED libgap.so.9` — Debian's GAP 4.14 — while
the runtime now provides `libgap.so.11`. `uv sync` does not trigger a relink, and Meson
kept its cached probe (`Run-time dependency libgap found: YES 4.14.0 (cached)`), even
after `--reconfigure` and `configure --clearcache`.

Resolved by making the superseded `libgap.pc` unavailable (`mv … libgap.pc
libgap.pc.disabled`, reversible), clearing `coredata.dat`, reconfiguring, and rebuilding
the GAP targets. Meson then reported `libgap found: YES 4.16.1`, and all three modules
now record `NEEDED libgap.so.11`.

This belongs in the image build too: a build that changes GAP must force the GAP-facing
modules to relink, or a runtime can carry modules from the previous GAP. Recorded here as
the known follow-up rather than silently absorbed.

## Consumers

| | |
| --- | --- |
| image | `ghcr.io/dzackgarza/sage@sha256:59568577510bd76fc9c405c81e6cb185656a193a24ee08b33e1b8b7fa6ae9d2b` |
| source pin | `9f1680d2a7bcf001e50714768e6066e6652d1708` |
| GAP | 4.16.1, kernel ABI `kv11`, at `$SAGE_LOCAL`, 173 packages |
| libgap | `libgap.so.11`, mapped from `/sage/.venv/lib` |

## Rollback

1. restore `libgap.pc.disabled` → `libgap.pc`;
2. `git -C /sage checkout ec386a5b` and re-sync (which relinks against Debian's GAP);
3. remove the nine paths in `results/gap-capability-installed-9f1680d2.txt`;
4. `results/runtime-pre-adoption-9f1680d2.txt` records the state to compare against,
   `results/runtime-rollback-snapshot/` the module/stamps/launcher.

Scope note unchanged: the deg-4 Borel order is Monte Carlo capability evidence, not an
exact order for any subgroup of `O(V)`.
