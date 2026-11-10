# image#9: the image is published with zstd layers

The publish step now exports the image with zstd layers and OCI media types, and
the full/incremental selector rebuilds in full while its base is gzip
(`be68c0e53a`, landed from `results/pull-zstd-workflow.patch`, deleted once landed).

## The publish, from the run's own job (read by the orchestrator)

| | |
| --- | --- |
| run | [42824498117](https://github.com/dzackgarza/sage/actions/runs/42824498117), revision `be68c0e53a038f67ba621414cc53193efd99829a` |
| job | `publish` (id 129915256258), **success**, 15:08:06Z to 16:19:31Z |
| changes since the base image (`1ccd5c88cd…`) | 8 files, no deletion, the Dockerfile not among them |
| selector line | `The base image carries zstd layers: 0`, so the step wrote `kind=full` |
| exporter | `type=image,push=true,compression=zstd,compression-level=3,force-compression=true,oci-mediatypes=true` |

`The base image carries zstd layers: 0` is the new rule doing its job: the base
`1ccd5c88cd` is gzip, and an incremental build is `FROM ${BASE_IMAGE}`, so it would
have inherited the 11 GiB Sage-build layer as gzip and recompressed only the few
hundred megabytes it wrote itself. It is one-way — the image this run published is
the base of the increments after it, and it carries zstd.

## The published `:develop`, read from the registry

Read back with `docker buildx imagetools inspect --raw`'s equivalent over the GHCR
HTTP API (this host has no docker daemon):

| | before (`2e8306e94c`…`1ccd5c88cd` era) | after `be68c0e53a` |
| --- | --- | --- |
| revision label | `087adc21c8…` | `be68c0e53a038f67ba621414cc53193efd99829a` |
| amd64 manifest | `sha256:aa036c9ade68…` | `sha256:5304338e9381…` |
| layers | 33 | 22 |
| layer media types | 33 × `…layer.v1.tar+gzip` | 22 × `application/vnd.oci.image.layer.v1.tar+zstd` |
| compressed size | 15.72 GiB (16.88 GB) | 14.19 GiB (15.24 GB) |
| largest layer | 11.40 GiB (`just research-environment-sync`) | 10.71 GiB (same step) |

The top-level index is `application/vnd.oci.image.index.v1+json` with an `amd64`
and an `unknown/unknown` manifest (the build's attestation), and the config is
`…config.v1+json`: consumers pulled an OCI index from this registry before this
change, so the manifest format is not new to them.

Compression is worth 1.5 GiB here and no more, because what dominates the image is
Mathlib's oleans and Sage's compiled tree, which neither gzip nor zstd shrinks
much: 9.7% fewer bytes on the wire and 9.7% faster to write for the same content.

## Why the runner can read it

The `zstd-probe`/`zstd-pull` jobs exist to answer this on a real runner; it is also
answerable from the daemon's own source, which is what the change rests on:

* `actions/runner-images`, `images/ubuntu/scripts/build/install-docker.sh` installs
  Docker Server **28.0.4** from `download.docker.com` and writes no `daemon.json`.
* Docker's containerd image store — the other path that reads zstd — is the default
  only **from Engine 29.0** on fresh installations
  (`docs.docker.com/engine/storage/containerd`). So the runner is on the legacy
  overlay2 store.
* On that path in moby `v28.0.4`: `distribution/registry.go` admits any
  `application/vnd.oci.image.*` layer media type, so `…layer.v1.tar+zstd` passes
  `checkSupportedMediaType` (`distribution/pull_v2.go`); every downloaded layer goes
  through `archive.DecompressStream` (`distribution/xfer/download.go`), which
  detects zstd by magic number and decompresses it with `klauspost/compress/zstd`
  (`pkg/archive/archive.go`); the graphdriver only ever sees the uncompressed tar.

The jobs are unchanged and still run under a `zstd_probe=true` dispatch.

## The measurement: "Initialize containers", research README example

`container: ghcr.io/dzackgarza/sage:develop`, fresh runner, so the step is the pull
and the unpack. Read from each run's own job steps.

Publish completed at **16:19:31Z**. The first README job whose container
initialisation began after that:

| run | init started | init ended | time |
| --- | --- | --- | --- |
| [42849732024](https://github.com/dzackgarza/research/actions/runs/42849732024) | 2026-11-10T16:42:26Z | 2026-11-10T16:51:05Z | **519 s** (8 min 39 s) |
| 42852166802 | 2026-11-10T16:44:53Z | 2026-11-10T16:52:55Z | 482 s |
| 42856712769 | 2026-11-10T16:50:21Z | 2026-11-10T17:01:08Z | 647 s |

For comparison, on the gzip image earlier the same day, the same step:

| run | init time |
| --- | --- |
| 42840602901 | 580 s |
| 42841470367 | 762 s |
| 42842480280 | 648 s |
| 42846759644 | 445 s |
| 42820409235 | 619 s |
| 42818838543 | 697 s |

**This sample does not show an improvement, and image#9's target is not met.**
519 s sits inside the 445–762 s range of the gzip image, and the spread within one
image is larger than the difference between the two (runner network contention: the
lattice-database daily certification held 16 runners through this window,
lattice-database#28). The pull is ~14 GiB whatever its compression, at roughly the
25–30 MB/s a shared runner sustains, which is where the ~9 minutes comes from.

So the remaining distance to image#9's 3 minutes is **bytes and parallelism, not
compression**:

* one layer is 10.71 GiB — 75% of the image — and a single blob downloads as one
  serial stream. Splitting the Sage/Mathlib build layer would let the runner's
  daemon fetch several blobs at once, which is the only lever that can turn 9
  minutes into 3 without removing a component;
* the runner's own pull cache does not survive between jobs on `ubuntu-latest`, so
  nothing is reused across consumers;
* a reduced tag is excluded by image#9 and by the reason `docker/SAGE-ENVIRONMENT.md`
  gives: `sage_categories` imports `juliacall`, so even a Sage-and-GAP consumer loads
  Julia.

## Rollback

Revert `be68c0e53a` and the next build exports gzip again. Mixed-compression images
are legal, so a base published with zstd stays readable to every consumer; the only
cost of a revert is that the Sage-build layer stays zstd until a full build replaces
it.
