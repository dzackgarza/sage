# Local Maxima remediation — provenance until the recipe supersedes it

The runtime reconciliation to `b1997dd` (`just research-environment-sync`, which
reconfigures the Meson tree) regenerated `sage/config.py` with an **empty**
`MAXIMA_PREFIX`: `(require 'maxima)` now succeeds under the system ECL, so
`src/sage/libs/meson.build` took the “ECL has Maxima” branch, which set
`SAGE_MAXIMA_PREFIX` to `''`. Maxima's package files — `linearalgebra.mac` and
the rest of `share/maxima` — are found through that prefix, so
`sage.interfaces.maxima_lib` died with

```
RuntimeError: ECL says: THROW: The catch MACSYMA-QUIT is undefined.
while evaluating #$load(linearalgebra)$
```

and the image's own check failed while probing `sage.symbolic`. The published
image is unaffected: its first build could not load `maxima.fas` yet, so it took
the branch that builds Maxima and set the prefix.

## What was changed locally, exactly

| item | value |
| --- | --- |
| file edited | `~/sage-image/rootfs/sage/builddir/src/sage/config.py` (Meson-generated) |
| line before | `MAXIMA_PREFIX = ""` |
| line after | `MAXIMA_PREFIX = "/sage/builddir/subprojects/maxima-5.49.0/dist/sage/.venv"` |
| installed with | `meson install -C /sage/builddir --only-changed --no-rebuild` (“Preserved 4675 unchanged files”) |
| installed copy | `/sage/.venv/lib/python3.14/site-packages/sage/config.py`, line 15 |
| when | 2026-11-01, during the reconciliation window (before the readback at 06:12:07 UTC) |

Verified at the time: `sage -c 'from sage.all import var; x=var("x"); print((x+1)^2)'`
→ `(x + 1)^2`, and `docker/research-environment-check.py` exited 0 with
`SageMath version 11.0.beta5, Release Date: 2026-10-28`.

The prefix chosen locally is the Maxima subproject's staging prefix, which exists
in this tree and holds `share/maxima/5.49.0/share/linearalgebra/linearalgebra.mac`.
`/sage/.venv` (the value the recipe fix now produces) resolves the same files and
was also verified.

## What supersedes it

Recipe commit on `develop` (this project) sets `SAGE_MAXIMA_PREFIX` to
`SAGE_LOCAL` whenever `SAGE_LOCAL/share/maxima` exists, in the branch where the
system ECL can already load Maxima, and the image check now asserts
`MAXIMA_PREFIX` points at a directory containing
`share/maxima/*/share/linearalgebra/linearalgebra.mac` and that `var("x") + 1`
evaluates. The next image built from that commit — and any reconfigure of a tree
carrying it — produces `MAXIMA_PREFIX = /sage/.venv` without a local edit.

Until that image replaces this unpacked copy, the generated-config edit above
stands and must not be re-applied or re-edited: a future `research-environment-sync`
in this tree would regenerate the file from the recipe, so no further local
change is safe while consumers use it.

## The maintained fix, and the published image that carries it

`src/sage/libs/meson.build` on `develop` now sets `SAGE_MAXIMA_PREFIX` from
`get_option('prefix')` (Meson is configured with `--prefix=SAGE_LOCAL`, i.e.
`/sage/.venv`), falling back to the `SAGE_LOCAL` option and then to empty. The
first attempt read `get_option('SAGE_LOCAL')`, which is empty by default, so it
never fired; the correction is commit `a20baff9109a3afa5b7cffb8e0dca6103eae8bc8`.

That commit's image published at 06:54:39 UTC:

| object | digest |
| --- | --- |
| OCI index | `sha256:4542f7bfb6051b82cadd74825a928bfb03a01cdcfff069d4d66b38fc06e644fb` |
| linux/amd64 manifest | `sha256:7e0fb939cf32170495c75c47f1292ed9cde1b270b15d6e652c2e95f79d37217c` |
| config | `sha256:028d7710055aeea357790fd5a3c983f349ae6681c7119cd3123c9bdad267d8e8` |

`org.opencontainers.image.revision` is `a20baff9109a…`. A tree reconfigured from
that source produces `MAXIMA_PREFIX = /sage/.venv`, so the local edit above is
no longer needed by anything built from it.

**Relation to this copy:** the local remediation stays as it is. The shared
unpacked runtime is not being re-adopted or mutated for this image — it keeps the
generated `config.py` edit until someone deliberately replaces the copy with the
published image. The two are equivalent in effect (both make `MAXIMA_PREFIX`
point at a prefix holding `share/maxima/*/share/linearalgebra/linearalgebra.mac`);
the image's version is the maintained one, the local one is a recorded,
provenance-carrying patch to a generated file.
