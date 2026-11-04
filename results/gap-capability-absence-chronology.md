# Why the shared runtime had no GAP matrix-group capability, though the image does

Short answer: the four packages are installed **by the image build**, into a
**system path outside `/sage`**, by steps that have **no counterpart in the
adoption/sync recipe**. The unpacked shared runtime was produced from an image
built **before** those steps existed, and every subsequent update it received was
a source-and-venv sync, which cannot carry them. It was not a botched adoption
step; there was no step that could have carried them.

## Chronology (measured from this repository)

| when (UTC) | commit | what it did |
| --- | --- | --- |
| 2026-11-01 03:45:38 | `b1997dd9f1ba` | the pin the shared `/sage` tree was on before this repair |
| 2026-11-01 06:37:51 | `a20baff9109` | `src/sage/libs/meson.build`: the Maxima share prefix |
| 2026-11-02 17:48:54 | `6dc2659dd4a` | **adds** GAP `orb`, `genss`, `forms`, `recog` and `gac` |
| 2026-11-03 20:30:27 | `ec386a5b9b5` | records published digests; the pin adopted now |

`git merge-base --is-ancestor b1997dd9f1ba 6dc2659dd4a` → **true**: the deployed
source pin predates the commit that added the packages, by about 38 hours.

## What `6dc2659` added, and where it runs

`git show 6dc2659 --stat`:

```
 docker/research-environment-check.py   | 36 +++++++++++++++++++++-
 docker/research-environment.Dockerfile | 40 ++++++++++++++++++++++++++
```

In `docker/research-environment.Dockerfile` the added steps are image-build steps:
`apt-get install -y --no-install-recommends gap-dev` (for `gac`), then
`install_gap_package` of the four pinned release tarballs, each `tar -xzf … -C
/usr/share/gap/pkg`, then `./configure && make -j` inside `orb-5.1.0`, then a
`LoadPackage` gate.

Two properties of that location matter:

* `/usr/share/gap/pkg` is a **rootfs path, not a `/sage` path**. No checkout of the
  Sage source tree contains it, so no amount of source adoption puts it there.
* These are **GAP packages, not Python distributions**. `uv sync` reconciles
  `.venv` from `uv.lock`; it has nothing to say about them.

## Why the sync could not have brought them

`justfile` at `b1997dd` — the recipe the adoption path runs — does exactly two
things: `uv sync --python … --frozen --inexact … --group research-environment`,
then a `meson` install of `sage-cli`. Grepping that file for `apt-get`, `gap`,
`tar` or `curl` returns **nothing**.

So the unpacked runtime has one update channel, and it carries the Sage source and
the Python environment. The Dockerfile's apt and tarball layers are carried by the
*other* channel — building and unpacking an image — and the shared rootfs was last
unpacked from a build that predates them.

**Measured**: the deployed tree's stamp
(`$HOME/sage-image/config.json`) records config `sha256:2d6a4754…` and **18**
layers, whereas the image published from `6dc2659` is config `sha256:20fe067d…`
with **21** layers.
**Inference** (not a registry lookup): that 18-layer stamp corresponds to the
`b1997dd`-era build, which is consistent with, and corroborated by, `/sage` being
at `b1997dd`.

## Why no check caught it

The check deployed at `b1997dd`, `docker/research-environment-check.py`, asserted
exactly these GAP features:

```
"atlasrep", "design", "grape", "guava", "hap", "polenta", "polycyclic"
```

All seven are Debian or polenta packages that were present. Nothing asserted
`orb`, `forms`, `genss` or `recog`, because at that commit they were not part of
the image's intent. The check passed, and it was right to: the runtime was exactly
what that commit described. The capability was missing from the *intent*, not
failing an assertion.

`6dc2659` closes that by adding `genss` and `recog` to the feature list, a root-path
assertion, and the Borel-subgroup order to the same check — which is why the check
at `ec386a5b` is the one that can now fail if the packages go missing.

## What was measured in the live runtime before the repair

```
ls usr/share/gap/pkg   -> 29 dirs (AClib … utils, polenta-1.3.11); no orb, forms, genss, recog
/usr/bin/gac           -> absent
/sage HEAD             -> b1997dd9f1ba33ca3861786973cf177bfd1d9aa6
```

## The honest summary

The repair was published to the **image producer** on 2026-11-02 and the resulting
image was built and consumer-validated that evening. It was never propagated to
the **unpacked shared runtime**, and nothing in that runtime's update path could
have propagated it: the two share no mechanism for system-level files. The gap
became visible only when a consumer needed the capability and reported it absent,
which is exactly the failure mode the image-versus-rootfs split creates.
