# Installing the published GAP capability into the shared unpacked runtime

Executed 2026-11-04 under the sole-writer boundary. No image rebuild, no pull.

## Installed versus required, measured

`results/runtime-adoption.sh verify` prints **no remaining delta against `b1997dd`**:
`sage HEAD b1997dd9f1ba`, `uv.lock f070d201…`, launcher `d1df681a…`, provisioner
`5af7c91b…`, installer `a46fb9a7…`, check `53776377…`, meson.build `d8119d97…`,
`/repos` at port `4f0ee50c`, extensions `7b222e86`, research `ec1333ee`.

That is issue #6's stated target, so the source and lock are as the issue asks. But the
*published intent has moved past it*: `develop` is now `ec386a5b`, and two runtime-affecting
commits landed after `b1997dd`:

| commit | changes | in the live runtime before this work |
| --- | --- | --- |
| `a20baff` | `src/sage/libs/meson.build` — the Maxima share prefix | present as a local hand-edit of the generated `config.py`, not as the maintained fix |
| `6dc2659` | `docker/research-environment.Dockerfile` — GAP orb/forms/genss/recog into `/usr/share/gap/pkg` | **absent** |

So the runtime was at the issue's stale pin and short the one capability the port's Lorentz
nodes are blocked on. Measured gap, before:

```
usr/share/gap/pkg: AClib … utils, polenta-1.3.11 (29 dirs)   — no orb, forms, genss, recog
/usr/bin/gac:                                                 — absent
```

## What was installed, and from where

The four packages and `gac` were copied from the **published image**, already unpacked and
digest-verified at `sha256:122ccd3a…` (config revision `6dc2659`), not rebuilt:

```
forms-1.3.0  genss-1.6.10  orb-5.1.0  recog-1.5.1   -> /usr/share/gap/pkg/
gac                                                  -> /usr/bin/gac
```

`results/gap-capability-install.sh` does this with `preflight` (refuses if any
proot/udocker/bwrap references the rootfs), `apply` (records every added path), `verify`
(the load gate) and `rollback` (removes exactly the recorded paths). The recorded manifest,
`results/gap-capability-installed.txt`, lists those five paths and nothing else.

Byte-identity with the published image, per package tree and for `gac`:

```
forms-1.3.0  identical (17d8702c49c1b562)
genss-1.6.10 identical (3021393db1545131)
orb-5.1.0    identical (b2af2d4317d9bb15)
recog-1.5.1  identical (aacdfa5d0fb63b90)
gac          d6213264a13983ee both sides
```

## Verification through the consumer path

Run inside the live rootfs with `/sage/.venv/bin/sage`, i.e. the instance libgap drives,
not the `gap` CLI:

```
kernel: GAP 4.14.0 arch x86_64-pc-linux-gnu-default64-kv9
roots: /root/.gap/;/root/gap/;/usr/local/lib/gap/;/usr/local/share/gap/;/usr/lib/gap/;/usr/share/gap/
LoadPackage(orb) = true in 0.866s, version 5.1.0
LoadPackage(forms) = true in 0.000s, version 1.3.0
LoadPackage(genss) = true in 0.000s, version 1.6.10
LoadPackage(recog) = true in 0.000s, version 1.5.1
genss chain order of the deg-4 GF(5) Borel: 62500 in 0.005s (expect 62500)
CONSUMER CAPABILITY CHECK PASSED
```

Scope unchanged: genss's chain is Monte Carlo bounded by `ErrorBound` and
`VerifyStabilizerChainMC` has no method for a plain matrix group, so 62,500 is capability
evidence, not an exact order for any generated subgroup of `O(V)`, and no degree-10
computation was run.

## Rollback

`MANIFEST=results/gap-capability-installed.txt results/gap-capability-install.sh rollback`
removes those five paths and restores the pre-install package set exactly.

## Still outstanding

1. `/sage` source is at `b1997dd`, not `ec386a5b`. Bringing it forward changes
   `src/sage/libs/meson.build` and requires `just research-environment-sync` (~5 min) plus a
   reinstall, which supersedes the local `MAXIMA_PREFIX` hand-edit recorded in
   `results/maxima-local-remediation.md`. That edit currently works and was left in place.
2. The image's own `docker/research-environment-check.py` was **not** run in this window: it
   imports Mathlib and starts the Julia bridge, so it is minutes of CPU and gigabytes of
   RSS, not a bounded smoke. What ran instead is the GAP-focused `results/consumer-check.py`.
3. Issue bookkeeping is blocked: `gh` is unauthenticated in this VM, so `itree` cannot run,
   and the GitHub connector is read-only for issues (no comment, label or close).
