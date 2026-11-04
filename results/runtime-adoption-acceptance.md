# Issue #6 acceptance record — instrument retargeted at the shipping image

Supersedes the earlier version of this record, which targeted `ec386a5b`. The
runtime has moved on: the image that ships the Sage-owned GAP is `9f1680d2`
(producer run 117, index `sha256:59568577`), and `verify` now measures against it
instead of a pin that no longer describes what consumers should run.

## What `verify` reports today, against the live runtime

```
research-environment-check.py      57427990eaaf1d10   ee249af72d358cfd   differs
install-research-repositories.sh   a46fb9a7024d80bc   a46fb9a7024d80bc   ok
provision-lean-packages.sh         5af7c91b2b9eb994   5af7c91b2b9eb994    ok
julia-launcher.sh                  d1df681a03f2fe84   d1df681a03f2fe84   ok
src/.../meson.build                d8119d97dfa923a7   d8119d97dfa923a7   ok
src/.../libs/meson.build           a25ab4a58e5a788d   a25ab4a58e5a788d   ok

GAP in $SAGE_LOCAL  absent          packages 33 (distribution tree)   expected 173
sage HEAD ec386a5b9b51 (published 9f1680d2a7bcf001e50714768e6066e6652d1708)
```

That is the honest remaining delta, and it is exactly what #6 must close:

1. `/sage` source `ec386a5b` -> `9f1680d2`;
2. the check file, which at the new pin also asserts the GAP provenance;
3. the Sage-owned GAP installation itself: 33 distribution packages in
   `/usr/share/gap/pkg` replaced by 173 packages plus `bin/gap`, `bin/gac`,
   `lib/libgap.so.11`, `lib/pkgconfig/libgap.pc` and `include/gap` under
   `$SAGE_LOCAL`, with `ld.so.conf.d` told about the library.

The GAP line is new to `verify`; without it the instrument understated adoption
by omitting the largest part of the change.

## The adoption path, dry-run in isolation

Against the verified published tree (`$HOME/sage-verify`, index `59568577`) as
source, and a fabricated target with the live layout (no GAP in `$SAGE_LOCAL`):

```
preflight  -> source carries the Sage-owned GAP; 8 paths would be installed
apply      -> 8 paths recorded and installed; 173 packages
              bin/gap, lib/libgap.so.11, lib/gap/sysinfo.gap byte-identical to the source
rollback   -> 8 paths removed; no recorded path left behind
```

So the installer moves the installation as a unit and reverses exactly what it did.
It has **not** been run against the live rootfs: that is the boundary-gated step of
#6 and consumers are active.

## What is still required for #6

* a coordinated maintenance boundary with zero processes inside the rootfs, then
  `gap-capability-install.sh apply`, the source checkout to `9f1680d2` and
  `just research-environment-sync`, and `runtime-adoption.sh check`;
* the run recorded from that boundary, and `verify` printing no delta.

Until then #6 stays open and this record is the acceptance instrument, not the
acceptance.
