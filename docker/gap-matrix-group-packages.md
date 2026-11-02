# GAP's matrix-group order and recognition packages in this image

`docker/research-environment.Dockerfile` installs `orb`, `forms`, `genss` and `recog` into
`/usr/share/gap/pkg`. This note records why that directory and not another, what the
packages can and cannot decide, and how a published image is validated.

## Why that directory

Sage's libgap does not run a GAP of its own here. `sage.libs.gap.util.kernel_info` runs the
system `gap` binary and hands libgap the root paths it reports; the Debian wrapper sets
them to `$HOME/gap;/usr/local/lib/gap;/usr/local/share/gap;/usr/lib/gap;/usr/share/gap`.
Sage's optional `gap_packages` spkg does list `genss`, but installs it into
`$SAGE_LOCAL/lib/gap/pkg`, which is on none of those roots -- so `sage -i gap_packages` in
this image installs files that never load. Debian trixie packages none of the four
(`sources.debian.org/api/src/<name>/` is 404), so they come from pinned release tarballs,
the way `polenta` already does. `gap-dev` supplies the `gac` that orb's C module needs.

| package | version | needs |
| --- | --- | --- |
| recog | 1.5.1 | GAP >= 4.13, AtlasRep >= 2.1.0, FactInt >= 1.6.3, Forms >= 1.2.11, genss >= 1.6.8, Orb >= 4.9.0 |
| genss | 1.6.10 | GAP >= 4.9, orb >= 4.5 |
| forms | 1.3.0 | GAP >= 4.9 |
| orb | 5.1.0 | GAP >= 4.12, compiled module |

## What the capability is, and what it is not

`StabilizerChain(G, rec(ErrorBound := e))` builds a randomized (Monte Carlo) Schreier-Sims
chain in whatever action `G` carries -- for a matrix group, the matrix action, not a
permutation representation of the natural module. `Size` of that chain is the product of
its orbit lengths. `SizeMC(G, e)` is the direct entry point.

What this does not give:

* exactness. The chain is Monte Carlo bounded by `ErrorBound`;
  `VerifyStabilizerChainMC(chain, n)` has no method for a plain matrix group ("no 1st
  choice method found"), so the package does not certify the order of such a group.
* a faster `Size(G)`. genss installs `Size` methods only for a group with a *stored*
  stabilizer chain (`HasStoredStabilizerChain`); plain `Size` still resolves through
  `grpnice.gd:241`.

So an order obtained this way is evidence that the capability exists and runs, not an
accepted order for any particular subgroup. The port's `p = 5`/`p = 7` acceptance nodes
still have to reproduce their recorded image orders themselves.

## How the image asserts it

`docker/research-environment-check.py`, run as the last step of the image build, asserts
the reported roots contain `/usr/share/gap/`, that each of the four loads there,
`RecognizeGroup` is bound, and that a deg-4 `GF(5)` upper-triangular (Borel) subgroup is
ordered through genss's chain as 62,500 = 4 * 5^6. No degree-10 computation is attempted:
the module the port cares about has 9,765,625 points at p = 5.

## Validating a published image on a host without a container runtime

```
docker/sage-image.py --cache DIR --reference sha256:<index digest> fetch
docker/sage-image.py --cache DIR --reference sha256:<index digest> info     # records both digests
PEAKRSS_LIMIT_MIB=6144 python peakrss.py -- \
    python3 docker/sage-image.py --cache DIR run -- \
        /sage/.venv/bin/sage /work/results/consumer-check.py
```

The guard is the shared process-tree RSS guard (`sage-image/peakrss.py`): it samples the
summed RSS of the whole tree every 2 s, stops the run above `PEAKRSS_LIMIT_MIB`, and
propagates the child's exit status so a killed run cannot read as a pass. Do **not**
substitute `ulimit -v` — a virtual-address cap is not the same bound and has already caused
false setup failures in this environment.

`--digest` is documented as the linux/amd64 manifest digest but `resolve()` fetches the
reference with the OCI *index* media type and then indexes into it; an amd64 manifest
digest therefore answers 404. Pin with `--reference sha256:<index digest>` and check
`info` reports the expected `index` and `manifest`.

## The consumer workflow change that could not be pushed

`.github/workflows/research-image-consumer.yml` asserted only a `QQ` determinant, so a
consumer run would pass on an image missing every GAP package. `gap-consumer-workflow.patch`
adds a step making the same assertions from a fresh runner. Pushing it fails with
`refusing to allow a GitHub App to create or update workflow .github/workflows/...
without workflows permission`; apply it with a credential that has that permission.
