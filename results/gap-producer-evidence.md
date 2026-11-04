# GAP matrix-group capability: producer evidence (image built from 6dc2659)

Recorded 2026-11-02. Consumer validation: the local run below, and the hosted run
[41275674403](https://github.com/dzackgarza/sage/actions/runs/41275674403) on the published digest.

## The published image

| | |
| --- | --- |
| index (OCI) | `sha256:122ccd3aac6d7dc7a991a3c35bbeb9e5749125dab8b0b62d6da004731e2ab8fb` |
| linux/amd64 manifest | `sha256:83aeb8ac2f05ee1a75d8b5a8b915991c1c609d97c1e1f434c4810473822a6a8d` |
| config | `sha256:20fe067d65e4433db0a7f85eaf25c4108109a3fe65641f65c26f1bb5f1e0c355` |
| config created | `2026-11-02T18:41:05Z` |
| `org.opencontainers.image.revision` | `6dc2659dd4aa7156e9d812afb8ccb317df033dd5` |
| tag pointing at the index | `develop` |
| layers | 21, 13,197,683,689 bytes |
| producer run | 41494813045 (run_number 113), all build steps success |

The revision label is the commit that carries the Dockerfile and check changes, so this
image is the one those changes produced, not an earlier build.

## What is inside it (read from the published layers, not from a local build)

* `sha256:a418ac6e…` (628,064 B) — `gap-dev`: `/usr/bin/gac`.
* `sha256:64a371b3…` (5,714,062 B) — the four packages and orb's module:
  `usr/share/gap/pkg/{forms-1.3.0, genss-1.6.10, orb-5.1.0, recog-1.5.1}` and
  `usr/share/gap/pkg/orb-5.1.0/bin/x86_64-pc-linux-gnu-default64-kv9/orb.so` —
  the compiled module under the GAParch this image's GAP reports
  (`x86_64-pc-linux-gnu-default64-kv9`).

Anonymous pull of the immutable reference works: a `ghcr.io` token scoped to
`repository:dzackgarza/sage:pull` fetches the index, the amd64 manifest, the config and
these layers without credentials.

## What the producer image itself asserts

`docker/research-environment-check.py` runs as the last step of the image build and
contains, unchanged from the commit:

1. `kernel_info()` roots contain `/usr/share/gap/` — the instance libgap drives;
2. `LoadPackage` is true for `orb`, `forms`, `genss`, `recog` in **that** instance;
3. `IsBound(RecognizeGroup)`;
4. the deg-4 GF(5) Borel subgroup order through genss's stabilizer chain equals 62,500;
5. plus the four names added to the `GapPackage` feature list.

Those are capability checks. They do not assert, and must not be read as, an order for
the port's generated orthogonal subgroup: genss's chain is Monte Carlo bounded by
`ErrorBound`, `VerifyStabilizerChainMC` has no method for a plain matrix group, and no
degree-10 computation is attempted anywhere in the image check.

## Consumer validation (2026-11-02, completed)

The published image was unpacked in an isolated cache and checked with the maintained
runner, `docker/sage-image.py --cache /workspace/nucleus/work/home/sage-consumer/image run`.
The stamp the script wrote:

| | |
| --- | --- |
| index | `sha256:122ccd3aac6d7dc7a991a3c35bbeb9e5749125dab8b0b62d6da004731e2ab8fb` |
| manifest | `sha256:83aeb8ac2f05ee1a75d8b5a8b915991c1c609d97c1e1f434c4810473822a6a8d` |
| config | `sha256:20fe067d65e4433db0a7f85eaf25c4108109a3fe65641f65c26f1bb5f1e0c355` |
| revision | `6dc2659dd4aa7156e9d812afb8ccb317df033dd5` |
| unpacked | `2026-11-02T20:17:33Z`, 40 GB, all 21 layers sha256-verified before `apply_layer` |

Output, verbatim, under `PEAKRSS_LIMIT_MIB=6144` and `timeout 600`:

```
kernel: GAP 4.14.0 arch x86_64-pc-linux-gnu-default64-kv9
roots: /root/.gap/;/root/gap/;/usr/local/lib/gap/;/usr/local/share/gap/;/usr/lib/gap/;/usr/share/gap/
LoadPackage(orb) = true in 0.073s, version 5.1.0
LoadPackage(forms) = true in 0.000s, version 1.3.0
LoadPackage(genss) = true in 0.000s, version 1.6.10
LoadPackage(recog) = true in 0.000s, version 1.5.1
genss chain order of the deg-4 GF(5) Borel: 62500 in 0.005s (expect 62500)
CONSUMER CAPABILITY CHECK PASSED
```

Exit status 0. Two corrections found by running it rather than reasoning about it: GAP's
`fail` has no Sage conversion, so the absent-package contract must be compared inside GAP
(`LoadPackage("x") = fail`); and the first attempt failed on exactly that, which is why the
check is worth running.

Scope, unchanged: this is capability evidence in the published image. The deg-4 Borel order
comes from genss's Monte Carlo chain (bounded by `ErrorBound`, with
`VerifyStabilizerChainMC` having no method for a plain matrix group), so it is **not** an
exact order for the port's generated subgroup at `p = 5`/`p = 7`, and no degree-10
computation was run. The Lorentz acceptance nodes remain the port's to close.

The live shared rootfs was not touched at any point; the consumer tree lives in
`/workspace/nucleus/work/home/sage-consumer/image` and is retained.

Transport note for anyone repeating this: the registry resets HTTP/2 streams every ~250 MiB
on this link, so `sage-image.py fetch` cannot deliver the 9.3 GB layer in one stream. The
unpack was completed over HTTP/1.1 with byte-range resume in four parallel parts, applying
each verified layer with `sage-image.py`'s own `apply_layer`.
